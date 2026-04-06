package main

import (
	"bytes"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"math"
	"os"
	"os/exec"
	"sort"
)


// ===========================================================================
// Part 1: 颜色解码 (Raw -> Go Color NRGBA)
// ===========================================================================

func scaleAlpha(a uint8, mode string) uint8 {
	val := int(a)
	switch mode {
	case "ps2":
		val = val * 255 / 128
	case "ps2x2":
		val = val * 4
	case "raw":
		// keep raw
	}
	if val > 255 {
		return 255
	}
	return uint8(val)
}

func decodeABGR1555(v uint16, alphaMode string) color.NRGBA {
	r := uint8((v & 0x1F) << 3)
	g := uint8(((v >> 5) & 0x1F) << 3)
	b := uint8(((v >> 10) & 0x1F) << 3)
	aBit := (v >> 15) & 1
	a := uint8(0)
	if aBit == 1 {
		a = 255
	}
	r |= r >> 5
	g |= g >> 5
	b |= b >> 5
	return color.NRGBA{R: r, G: g, B: b, A: a}
}

func decodeRGBA8888(v uint32, alphaMode string) color.NRGBA {
	r := uint8(v & 0xFF)
	g := uint8((v >> 8) & 0xFF)
	b := uint8((v >> 16) & 0xFF)
	a := uint8((v >> 24) & 0xFF)
	
	// PS2 Clamp
	if alphaMode == "ps2" && a > 0x80 { a = 0x80 }
	
	a = scaleAlpha(a, alphaMode)
	
	return color.NRGBA{R: r, G: g, B: b, A: a}
}

// ===========================================================================
// Part 2: 颜色编码 (Go Color NRGBA -> Raw)
// ===========================================================================

func encodeABGR1555(c color.NRGBA) uint16 {
	r := uint16(c.R >> 3) & 0x1F
	g := uint16(c.G >> 3) & 0x1F
	b := uint16(c.B >> 3) & 0x1F
	a := uint16(0)
	if c.A > 127 {
		a = 1
	}
	return (a << 15) | (b << 10) | (g << 5) | r
}

func encodeRGBA8888(c color.NRGBA, toPs2Alpha bool) uint32 {
	r := uint32(c.R)
	g := uint32(c.G)
	b := uint32(c.B)
	a := uint32(c.A)

	if toPs2Alpha {
		// PC (0-255) -> PS2 (0-128)
		a = (a*128 + 127) / 255
		if a > 0x80 { a = 0x80 }
	}
	
	return (a << 24) | (b << 16) | (g << 8) | r
}

// ===========================================================================
// Part 3: 调色板量化与索引映射
// ===========================================================================

func extractPalette(img image.Image, maxColors int) []color.RGBA {
	counts := make(map[color.RGBA]int)
	bounds := img.Bounds()
	
	for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
		for x := bounds.Min.X; x < bounds.Max.X; x++ {
			c := color.NRGBAModel.Convert(img.At(x, y)).(color.NRGBA)
			k := color.RGBA{c.R, c.G, c.B, c.A}
			counts[k]++
		}
	}

	type colorFreq struct {
		c color.RGBA
		n int
	}
	freqs := make([]colorFreq, 0, len(counts))
	for c, n := range counts {
		freqs = append(freqs, colorFreq{c, n})
	}
	sort.Slice(freqs, func(i, j int) bool { return freqs[i].n > freqs[j].n })

	pal := make([]color.RGBA, 0, maxColors)
	for i := 0; i < len(freqs) && i < maxColors; i++ {
		pal = append(pal, freqs[i].c)
	}
	for len(pal) < maxColors {
		pal = append(pal, color.RGBA{0, 0, 0, 0})
	}
	return pal
}

func imageToIndexed(img image.Image, pal []color.RGBA) []uint8 {
	bounds := img.Bounds()
	w, h := bounds.Dx(), bounds.Dy()
	out := make([]uint8, w*h)

	type fColor struct { r, g, b, a float64 }
	palCache := make([]fColor, len(pal))
	for i, c := range pal {
		palCache[i] = fColor{float64(c.R), float64(c.G), float64(c.B), float64(c.A)}
	}

	lookupCache := make(map[uint32]uint8)

	idx := 0
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			c := color.NRGBAModel.Convert(img.At(bounds.Min.X+x, bounds.Min.Y+y)).(color.NRGBA)
			key := uint32(c.R) | uint32(c.G)<<8 | uint32(c.B)<<16 | uint32(c.A)<<24
			if cachedIdx, ok := lookupCache[key]; ok {
				out[idx] = cachedIdx
				idx++
				continue
			}

			r, g, b, a := float64(c.R), float64(c.G), float64(c.B), float64(c.A)
			bestIdx := 0
			minDist := math.MaxFloat64

			for i, pc := range palCache {
				dr := (r - pc.r) * 0.30
				dg := (g - pc.g) * 0.59
				db := (b - pc.b) * 0.11
				da := (a - pc.a) * 2.0 
				d := dr*dr + dg*dg + db*db + da*da
				if d < minDist {
					minDist = d
					bestIdx = i
					if d < 1.0 { break } 
				}
			}
			res := uint8(bestIdx)
			lookupCache[key] = res
			out[idx] = res
			idx++
		}
	}
	return out
}

// ===========================================================================
// Part 4: Helpers & PNGQuant
// ===========================================================================

func Quantize(rawPng []byte, nColors int) ([]byte, error) {
	exeName := "pngquant"
	if _, err := os.Stat("pngquant.exe"); err == nil {
		exeName = ".\\pngquant.exe"
	}
	cmd := exec.Command(exeName, fmt.Sprintf("%d", nColors), "-")
	cmd.Stdin = bytes.NewReader(rawPng)
	var outBuf bytes.Buffer
	var errBuf bytes.Buffer
	cmd.Stdout = &outBuf
	cmd.Stderr = &errBuf
	
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("%v (Stderr: %s)", err, errBuf.String())
	}
	return outBuf.Bytes(), nil
}

func ImgToBytes(img image.Image) []byte {
	buf := new(bytes.Buffer)
	png.Encode(buf, img)
	return buf.Bytes()
}

func BytesToImg(data []byte) (image.Image, error) {
	return png.Decode(bytes.NewReader(data))
}



// data: 压缩数据, decompSize: 预期的解压后大小, dicOff: 字典初始偏移 (默认 0xFEE)
func DecompressLZSS(data []byte, decompSize int, dicOff int) []byte {
	dict := make([]byte, 0x1000) // 4096 字节字典
	dec := make([]byte, decompSize)
	
	inOff := 0
	outOff := 0
	var mask uint8 = 0
	var cb uint8 = 0

	for outOff < decompSize {
		if mask == 0 {
			if inOff >= len(data) { break }
			cb = data[inOff]
			inOff++
			mask = 1
		}

		if (mask & cb) != 0 {
			
			if inOff >= len(data) || outOff >= decompSize { break }
			val := data[inOff]
			dec[outOff] = val
			dict[dicOff] = val
			outOff++
			inOff++
			dicOff = (dicOff + 1) & 0xFFF
		} else {
			
			if inOff+1 >= len(data) { break }
			b1 := data[inOff]
			b2 := data[inOff+1]
			inOff += 2

			length := int(b2&0x0F) + 3
			loc := int(b1) | (int(b2&0xF0) << 4)

			for b := 0; b < length; b++ {
				if outOff >= decompSize { break }
				val := dict[(loc+b)&0xFFF]
				dec[outOff] = val
				dict[dicOff] = val
				outOff++
				dicOff = (dicOff + 1) & 0xFFF
			}
		}
		mask = (mask << 1)
	}
	return dec
}


func CompressLZSS(input []byte, dicOff int) []byte {
	inputLen := len(input)
	if inputLen == 0 { return nil }

	var out []byte
	dict := make([]byte, 4096)
	
	for i := range dict { dict[i] = 0 }
	
	inPos := 0
	writePos := dicOff

	for inPos < inputLen {
		flagPos := len(out)
		out = append(out, 0) 
		var flags uint8 = 0

		for i := 0; i < 8; i++ {
			if inPos >= inputLen { break }

			bestLen := 0
			bestDist := 0

			maxMatch := 18
			if inputLen-inPos < maxMatch {
				maxMatch = inputLen - inPos
			}

			if maxMatch >= 3 {
				for d := 0; d < 4096; d++ {
					currLen := 0
					for currLen < maxMatch {
					
						if input[inPos+currLen] != dict[(d+currLen)&0xFFF] {
							break
						}
						currLen++
					}
					if currLen >= bestLen {
						bestLen = currLen
						bestDist = d
						if bestLen == maxMatch { break }
					}
				}
			}

			if bestLen >= 3 {
				b1 := uint8(bestDist & 0xFF)
				b2 := uint8((bestDist>>4)&0xF0) | uint8(bestLen-3)
				out = append(out, b1, b2)

				for j := 0; j < bestLen; j++ {
					dict[writePos] = input[inPos]
					writePos = (writePos + 1) & 0xFFF
					inPos++
				}
			} else {
				
				flags |= (1 << i)
				val := input[inPos]
				out = append(out, val)

				dict[writePos] = val
				writePos = (writePos + 1) & 0xFFF
				inPos++
			}
		}
		out[flagPos] = flags
	}
	return out
}
