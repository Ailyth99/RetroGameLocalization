package main

import (
	"bytes"
	//"fmt"
	"image"
	"image/color"
	"image/png"
	"math"
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
	
	if alphaMode == "ps2" && a > 0x80 { a = 0x80 }
	a = scaleAlpha(a, alphaMode)
	
	return color.NRGBA{R: r, G: g, B: b, A: a}
}



func decodeBGRA8888(v uint32, alphaMode string) color.NRGBA {
	b := uint8(v & 0xFF)
	g := uint8((v >> 8) & 0xFF)
	r := uint8((v >> 16) & 0xFF)
	a := uint8((v >> 24) & 0xFF)
	
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
		a = (a*128 + 127) / 255
		if a > 0x80 { a = 0x80 }
	}
	
	return (a << 24) | (b << 16) | (g << 8) | r
}


func encodeBGRA8888(c color.NRGBA, toPs2Alpha bool) uint32 {
	r := uint32(c.R)
	g := uint32(c.G)
	b := uint32(c.B)
	a := uint32(c.A)

	if toPs2Alpha {
		a = (a*128 + 127) / 255
		if a > 0x80 { a = 0x80 }
	}
	
	
	return (a << 24) | (r << 16) | (g << 8) | b
}

// ===========================================================================
// Part 3: Median Cut 颜色量化算法 (Pure Go)
// ===========================================================================

type mcColor struct { R, G, B, A uint8 }

type mcBox struct {
	colors []mcColor
}

func (b *mcBox) bounds() (min, max mcColor) {
	if len(b.colors) == 0 { return }
	min = b.colors[0]
	max = b.colors[0]
	for _, c := range b.colors {
		if c.R < min.R { min.R = c.R }; if c.R > max.R { max.R = c.R }
		if c.G < min.G { min.G = c.G }; if c.G > max.G { max.G = c.G }
		if c.B < min.B { min.B = c.B }; if c.B > max.B { max.B = c.B }
		if c.A < min.A { min.A = c.A }; if c.A > max.A { max.A = c.A }
	}
	return
}

func (b *mcBox) longestAxis() int {
	min, max := b.bounds()
	dr := max.R - min.R
	dg := max.G - min.G
	db := max.B - min.B
	da := max.A - min.A
	maxD := dr
	axis := 0
	if dg > maxD { maxD = dg; axis = 1 }
	if db > maxD { maxD = db; axis = 2 }
	if da > maxD { maxD = da; axis = 3 }
	return axis
}

func (b *mcBox) split() (*mcBox, *mcBox) {
	axis := b.longestAxis()
	sort.Slice(b.colors, func(i, j int) bool {
		switch axis {
		case 0: return b.colors[i].R < b.colors[j].R
		case 1: return b.colors[i].G < b.colors[j].G
		case 2: return b.colors[i].B < b.colors[j].B
		default: return b.colors[i].A < b.colors[j].A
		}
	})
	mid := len(b.colors) / 2
	return &mcBox{colors: b.colors[:mid]}, &mcBox{colors: b.colors[mid:]}
}

func (b *mcBox) average() color.RGBA {
	if len(b.colors) == 0 { return color.RGBA{} }
	var r, g, bl, a int
	for _, c := range b.colors {
		r += int(c.R); g += int(c.G); bl += int(c.B); a += int(c.A)
	}
	count := len(b.colors)
	return color.RGBA{uint8(r / count), uint8(g / count), uint8(bl / count), uint8(a / count)}
}

// quantizeMedianCut 基于中值切割算法将图像量化为指定数量的颜色
func quantizeMedianCut(img image.Image, maxColors int) []color.RGBA {
	bounds := img.Bounds()
	colorMap := make(map[mcColor]int)
	
	for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
		for x := bounds.Min.X; x < bounds.Max.X; x++ {
			c := color.NRGBAModel.Convert(img.At(x, y)).(color.NRGBA)
			colorMap[mcColor{c.R, c.G, c.B, c.A}]++
		}
	}
	
	var allColors []mcColor
	for c, count := range colorMap {
		for i := 0; i < count; i++ {
			allColors = append(allColors, c)
		}
	}

	boxes := []*mcBox{{colors: allColors}}
	
	for len(boxes) < maxColors {
		maxIdx := -1
		maxLen := 0
		for i, b := range boxes {
			if len(b.colors) > maxLen {
				maxLen = len(b.colors)
				maxIdx = i
			}
		}
		if maxLen <= 1 { break } 
		
		target := boxes[maxIdx]
		b1, b2 := target.split()
		
		boxes[maxIdx] = b1
		boxes = append(boxes, b2)
	}
	
	pal := make([]color.RGBA, 0, maxColors)
	for _, b := range boxes {
		pal = append(pal, b.average())
	}
	for len(pal) < maxColors {
		pal = append(pal, color.RGBA{0, 0, 0, 0})
	}
	return pal
}

// ===========================================================================
// Part 4: 索引映射
// ===========================================================================

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

func ImgToBytes(img image.Image) []byte {
	buf := new(bytes.Buffer)
	png.Encode(buf, img)
	return buf.Bytes()
}

func BytesToImg(data []byte) (image.Image, error) {
	return png.Decode(bytes.NewReader(data))
}