// utils.go
package main

import (
	"image"
	"image/color"
	"math"
	"sort"
)

// --- Color Conversion ---

func scale5to8(v uint16) uint8 {
	return uint8((v << 3) | (v >> 2))
}

// PS2 Alpha (1-bit) <-> PC Alpha
func alphaPs2ToPc(aBit uint16) uint8 {
	if aBit == 1 { return 255 }
	return 0
}
func alphaPcToPs2(a uint8) uint16 {
	if a > 127 { return 1 }
	return 0
}

// PS2 Alpha (8-bit, 0-128) <-> PC Alpha (8-bit, 0-255)
func alphaPs2ByteToPc(a uint8) uint8 {
	// 0x80 (128) -> 0xFF (255)
	// Simple *2 logic with clamp
	v := int(a) * 2
	if v > 255 { v = 255 }
	return uint8(v)
}

func alphaPcByteToPs2(a uint8) uint8 {
	// 0xFF -> 0x7F (or 0x80)
	return a / 2
}

// ABGR1555 -> RGBA
func decodeABGR1555(v uint16) color.RGBA {
	r := v & 0x1F
	g := (v >> 5) & 0x1F
	b := (v >> 10) & 0x1F
	a := (v >> 15) & 0x1
	return color.RGBA{scale5to8(r), scale5to8(g), scale5to8(b), alphaPs2ToPc(a)}
}

// RGBA -> ABGR1555
func encodeABGR1555(c color.RGBA) uint16 {
	r := uint16(c.R >> 3)
	g := uint16(c.G >> 3)
	b := uint16(c.B >> 3)
	a := alphaPcToPs2(c.A)
	return (a << 15) | (b << 10) | (g << 5) | r
}

// RGBX8888 -> RGBA
// PS2 Memory (Little Endian): R, G, B, A(0-128)
func decodeRGBX8888(v uint32) color.RGBA {
	r := uint8(v & 0xFF)
	g := uint8((v >> 8) & 0xFF)
	b := uint8((v >> 16) & 0xFF)
	a := uint8((v >> 24) & 0xFF)
	return color.RGBA{r, g, b, alphaPs2ByteToPc(a)}
}

// RGBA -> RGBX8888
func encodeRGBX8888(c color.RGBA) uint32 {
	r := uint32(c.R)
	g := uint32(c.G)
	b := uint32(c.B)
	a := uint32(alphaPcByteToPs2(c.A))
	return (a << 24) | (b << 16) | (g << 8) | r
}

// --- Palette Quantization ---

func extractPalette(img image.Image, maxColors int) []color.RGBA {
	counts := make(map[color.RGBA]int)
	bounds := img.Bounds()
	for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
		for x := bounds.Min.X; x < bounds.Max.X; x++ {
			r, g, b, a := img.At(x, y).RGBA()
			c := color.RGBA{uint8(r >> 8), uint8(g >> 8), uint8(b >> 8), uint8(a >> 8)}
			counts[c]++
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

	idx := 0
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			r32, g32, b32, a32 := img.At(bounds.Min.X+x, bounds.Min.Y+y).RGBA()
			r, g, b, a := float64(r32>>8), float64(g32>>8), float64(b32>>8), float64(a32>>8)

			bestIdx := 0
			minDist := math.MaxFloat64

			for i, pc := range palCache {
				dr, dg, db, da := r-pc.r, g-pc.g, b-pc.b, a-pc.a
				d := dr*dr + dg*dg + db*db + da*da
				if d < minDist {
					minDist = d
					bestIdx = i
					if d == 0 { break }
				}
			}
			out[idx] = uint8(bestIdx)
			idx++
		}
	}
	return out
}

// --- Swizzle Logic ---

func swapNibbles(data []byte) []byte {
	res := make([]byte, len(data))
	for i, b := range data {
		res[i] = (b&0x0F)<<4 | (b&0xF0)>>4
	}
	return res
}

func ps2Swizzle(data []byte, w, h int, swizzle bool) []byte {
	out := make([]byte, w*h)
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			blk := (y & (^0xF)) * w
			blk += (x & (^0xF)) * 2
			swap := (((y + 2) >> 2) & 0x1) * 4
			py := (((y & (^3)) >> 1) + (y & 1)) & 0x7
			col := py*w*2 + ((x+swap)&0x7)*4
			bn := ((y >> 1) & 1) + ((x >> 2) & 2)
			sid := blk + col + bn

			if swizzle {
				out[sid] = data[y*w+x]
			} else {
				if sid < len(data) {
					out[y*w+x] = data[sid]
				}
			}
		}
	}
	return out
}

// CSM1 for 16-bit palette
func palCSM1(entries []uint16) []uint16 {
	out := make([]uint16, 0, len(entries))
	for i := 0; i < 256; i += 32 {
		out = append(out, entries[i:i+8]...)
		out = append(out, entries[i+16:i+24]...) // Swap middle blocks
		out = append(out, entries[i+8:i+16]...)
		out = append(out, entries[i+24:i+32]...)
	}
	return out
}

// CSM1 for 32-bit palette (RGBX8888)
func palCSM1_32(entries []uint32) []uint32 {
	out := make([]uint32, 0, len(entries))
	for i := 0; i < 256; i += 32 {
		out = append(out, entries[i:i+8]...)
		out = append(out, entries[i+16:i+24]...) // Swap middle blocks
		out = append(out, entries[i+8:i+16]...)
		out = append(out, entries[i+24:i+32]...)
	}
	return out
}