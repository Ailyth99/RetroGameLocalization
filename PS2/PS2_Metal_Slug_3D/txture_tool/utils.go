/*
Author: aikika/ailyth99
Date: 2025.11
License: GPL-3.0

------------------------------------------------------------------------------

This library is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
*/


package main

import (
	"image"
	"image/color"
	"math"
	"sort"
)


func scaleAlpha(a uint8) uint8 {
	// PS2 0-128 -> PC 0-255
	return uint8(int(a) * 255 / 128)
}

//decodeABGR1555返回 NRGBA,确保颜色亮度不被Alpha衰减,一定要NRGBA，不然要出问题
func decodeABGR1555(v uint16, fixAlpha bool) color.NRGBA {
	r := uint8((v & 0x1F) << 3)
	g := uint8(((v >> 5) & 0x1F) << 3)
	b := uint8(((v >> 10) & 0x1F) << 3)
	aBit := (v >> 15) & 1
	a := uint8(0)
	if aBit == 1 {
		a = 255
	}
	//填充低位获得更精确的颜色5bit->8bit
	r |= r >> 5
	g |= g >> 5
	b |= b >> 5
	return color.NRGBA{R: r, G: g, B: b, A: a}
}

// decodeRGBA8888返回NRGBA
func decodeRGBA8888(v uint32, fixAlpha bool) color.NRGBA {
	// Memory: R G B A -> Uint32 Little Endian: A B G R
	r := uint8(v & 0xFF)
	g := uint8((v >> 8) & 0xFF)
	b := uint8((v >> 16) & 0xFF)
	a := uint8((v >> 24) & 0xFF)
	
	if fixAlpha {
		if a > 0x80 { a = 0x80 }
		a = scaleAlpha(a)
	}
	return color.NRGBA{R: r, G: g, B: b, A: a}
}

//===========================================================================
//Part2: 颜色编码；注入时需要
//===========================================================================

// encodeABGR1555: NRGBA -> uint16 (PS2)
func encodeABGR1555(c color.RGBA) uint16 {
	// 32bit (8888) -> 16bit (5551)
	r := uint16(c.R >> 3) & 0x1F
	g := uint16(c.G >> 3) & 0x1F
	b := uint16(c.B >> 3) & 0x1F
	a := uint16(0)
	if c.A > 127 { 
		a = 1
	}
	// PS2: ABGR  （目前已知的16位的都是ABGR，其他的没见过）
	return (a << 15) | (b << 10) | (g << 5) | r
}

// encodeRGBA8888:NRGBA->uint32 (PS2)
func encodeRGBA8888(c color.RGBA, toPs2Alpha bool) uint32 {
	r := uint32(c.R)
	g := uint32(c.G)
	b := uint32(c.B)
	a := uint32(c.A)

	if toPs2Alpha {
		// PC (0-255) -> PS2 (0-128)
		a = a / 2
		if a > 0x80 { a = 0x80 }
	}
	
	//R G B A （小端）
	//Uint32 Value: 0xAABBGGRR
	return (a << 24) | (b << 16) | (g << 8) | r
}

//===========================================================================
//Part 3: 调色板量化，索引映射 
//===========================================================================

//统计图片颜色频率并生成临时调色板
func extractPalette(img image.Image, maxColors int) []color.RGBA {
	counts := make(map[color.RGBA]int)
	bounds := img.Bounds()
	
	for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
		for x := bounds.Min.X; x < bounds.Max.X; x++ {
			//使用NRGBA获取原始值
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
	
	//按频率排序
	sort.Slice(freqs, func(i, j int) bool { return freqs[i].n > freqs[j].n })

	pal := make([]color.RGBA, 0, maxColors)
	for i := 0; i < len(freqs) && i < maxColors; i++ {
		pal = append(pal, freqs[i].c)
	}
	//填充剩余位置
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