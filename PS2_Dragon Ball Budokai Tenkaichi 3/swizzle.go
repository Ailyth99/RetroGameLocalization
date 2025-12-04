
/*
Package swizzle implements PlayStation 2 texture swizzling and unswizzling algorithms.

Author: aikika/ailyth99
Date: 2025.11
License: GPL-3.0
------------------------------------------------------------------------------
Portions of the pixel swizzling algorithms (specifically Unswizzle4/Native and LUTs) 
are derived from the Python library "reversebox".
Original Author: Copyright © 2024-2025 Bartłomiej Duda
License: GPL-3.0
------------------------------------------------------------------------------

This library is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
*/

package main

// ---------------------------------------------------------------------------
// Part 1: 调色板重排 (Palette / CLUT Swizzling)
// ---------------------------------------------------------------------------

func UnswizzleCSM1_16(entries []uint16) []uint16 {
	if len(entries) == 0 {
		return nil
	}
	out := make([]uint16, 0, len(entries))
	for i := 0; i < len(entries); i += 32 {
		end := i + 32
		if end > len(entries) {
			end = len(entries)
		}
		if end-i < 32 {
			out = append(out, entries[i:end]...)
			continue
		}
		out = append(out, entries[i:i+8]...)
		out = append(out, entries[i+16:i+24]...)
		out = append(out, entries[i+8:i+16]...)
		out = append(out, entries[i+24:i+32]...)
	}
	return out
}

func UnswizzleCSM1_32(entries []uint32) []uint32 {
	if len(entries) == 0 {
		return nil
	}
	out := make([]uint32, 0, len(entries))
	for i := 0; i < len(entries); i += 32 {
		end := i + 32
		if end > len(entries) {
			end = len(entries)
		}
		if end-i < 32 {
			out = append(out, entries[i:end]...)
			continue
		}
		out = append(out, entries[i:i+8]...)
		out = append(out, entries[i+16:i+24]...)
		out = append(out, entries[i+8:i+16]...)
		out = append(out, entries[i+24:i+32]...)
	}
	return out
}

// ---------------------------------------------------------------------------
// Part 2: 像素重排 - 基础 & 8/16/32bpp
// ---------------------------------------------------------------------------

// Unswizzle8 对应 Python _convert_ps2_8bit
// 严格匹配 Python 的位运算逻辑
func Unswizzle8(data []byte, width, height int) []byte {
	out := make([]byte, len(data))
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			// Python: block_location = (y & (~0xF)) * img_width + (x & (~0xF)) * 2
			blockLoc := (y & (^0xF)) * width + (x & (^0xF)) * 2
			
			// Python: swap_selector = (((y + 2) >> 2) & 0x1) * 4
			swapSel := (((y + 2) >> 2) & 0x1) * 4
			
			// Python: pos_y = (((y & (~3)) >> 1) + (y & 1)) & 0x7
			posY := (((y & (^3)) >> 1) + (y & 1)) & 0x7
			
			// Python: column_location = pos_y * img_width * 2 + ((x + swap_selector) & 0x7) * 4
			colLoc := posY * width * 2 + ((x + swapSel) & 0x7) * 4
			
			// Python: byte_num = ((y >> 1) & 1) + ((x >> 2) & 2)
			byteNum := ((y >> 1) & 1) + ((x >> 2) & 2)
			
			swizzleIdx := blockLoc + colLoc + byteNum

			linearIdx := y*width + x
			if swizzleIdx < len(data) && linearIdx < len(out) {
				out[linearIdx] = data[swizzleIdx]
			}
		}
	}
	return out
}

func Unswizzle16(data []byte, width, height int) []byte {
	out := make([]byte, len(data))
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			swizzledOffset := pixel16Offset(x, y, width)
			srcIdx := swizzledOffset * 2
			dstIdx := (y*width + x) * 2
			if srcIdx+1 < len(data) && dstIdx+1 < len(out) {
				out[dstIdx] = data[srcIdx]
				out[dstIdx+1] = data[srcIdx+1]
			}
		}
	}
	return out
}

func Unswizzle32(data []byte, width, height int) []byte {
	out := make([]byte, len(data))
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			// 32bpp通常可以看作是4倍宽度的 8bpp 或者是2倍宽度的16bpp
			// 但这里使用类似8bpp的Zorder逻辑映射4字节块
			blockLoc := (y & (^0xF)) * width + (x & (^0xF)) * 2
			swapSel := (((y + 2) >> 2) & 0x1) * 4
			posY := (((y & (^3)) >> 1) + (y & 1)) & 0x7
			colLoc := posY * width * 2 + ((x + swapSel) & 0x7) * 4
			byteNum := ((y >> 1) & 1) + ((x >> 2) & 2)
			
			swizzleIdx := blockLoc + colLoc + byteNum

			srcIdx := swizzleIdx * 4
			dstIdx := (y*width + x) * 4
			
			if srcIdx+3 < len(data) && dstIdx+3 < len(out) {
				copy(out[dstIdx:dstIdx+4], data[srcIdx:srcIdx+4])
			}
		}
	}
	return out
}

func pixel16Offset(x, y, width int) int {
	bit := 0
	if width >= 16 {
		pageX := x >> 6
		pageY := y >> 6
		newX := (y & 0x38) + (x & 0x07)
		newY := ((x & 0x30) >> 1) + (y & 0x07)
		bit = (x & 0x08) << 1
		x = (pageX << 6) + newX
		y = (pageY << 5) + newY
	}
	return 32*(y*width+x) + bit
}

// ---------------------------------------------------------------------------
// Part 3: 像素重排 - 4bpp
// ---------------------------------------------------------------------------

func Unswizzle4By8(data []byte, width, height int) []byte {
	// 1. Unpack 4bpp -> 8bpp
	// Python: input_pixels_8bpp[i * 2] = nybble_low
	// Python: input_pixels_8bpp[i * 2 + 1] = nybble_high
	// Low nibble (0-3 bits) -> Even index
	// High nibble (4-7 bits) -> Odd index
	temp8 := make([]byte, width*height)
	for i := 0; i < len(data); i++ {
		b := data[i]
		if i*2 < len(temp8) {
			temp8[i*2] = b & 0x0F
		}
		if i*2+1 < len(temp8) {
			temp8[i*2+1] = (b >> 4) & 0x0F
		}
	}

	// 2. 8bpp Unswizzle
	unswizzled8 := Unswizzle8(temp8, width, height)

	// 3. Repack 8bpp -> 4bpp
	// Python: byte_value = (nybble_high << 4) | nybble_low
	out := make([]byte, len(data))
	for i := 0; i < len(out); i++ {
		p1 := uint8(0)
		p2 := uint8(0)
		
		if i*2 < len(unswizzled8) {
			p1 = unswizzled8[i*2] & 0x0F
		}
		if i*2+1 < len(unswizzled8) {
			p2 = unswizzled8[i*2+1] & 0x0F
		}
		out[i] = p1 | (p2 << 4)
	}
	return out
}

func Unswizzle4(data []byte, width, height int) []byte {
	const (
		psmt4PageW  = 128
		psmt4PageH  = 128
		psmct32PageW = 64
	)

	nPageW := (width - 1) / psmt4PageW + 1
	nPageH := (height - 1) / psmt4PageH + 1

	nInputWidthByte := 0
	nOutputHeight := 0
	nInputHeight := 0
	nOutputWidthByte := 0

	if nPageH == 1 {
		nInputWidthByte = height * 2
		nOutputHeight = height
	} else {
		nInputWidthByte = psmct32PageW * 4
		nOutputHeight = psmt4PageH
	}

	if nPageW == 1 {
		nInputHeight = width / 4
		nOutputWidthByte = width / 2
	} else {
		nInputHeight = 32
		nOutputWidthByte = psmt4PageW / 2
	}

	outputData := make([]byte, len(data))
	
	index32H := make([]int, 32)
	index32V := make([]int, 32)
	idx0 := 0
	for i := 0; i < 4; i++ {
		for j := 0; j < 8; j++ {
			idx1 := blockTable32[idx0]
			index32H[idx1] = j
			index32V[idx1] = i
			idx0++
		}
	}

	for i := 0; i < nPageH; i++ {
		for j := 0; j < nPageW; j++ {
			
			po0Offset := (nInputWidthByte * nInputHeight) * nPageW * i + nInputWidthByte * j
			
			pageBufSize := (psmt4PageW / 2) * psmt4PageH
			inputPage := make([]byte, pageBufSize)
			
			for k := 0; k < nInputHeight; k++ {
				// Python: src_offset = k * n_input_width_byte * n_page_w
				srcOffset := po0Offset + k * nInputWidthByte * nPageW
				
				// Python: dst_offset = k * n_page32_width_byte
				// n_page32_width_byte = 64 * 4 = 256
				dstOffset := k * (psmct32PageW * 4)
				
				copyLen := nInputWidthByte
				if srcOffset+copyLen <= len(data) && dstOffset+copyLen <= len(inputPage) {
					copy(inputPage[dstOffset:], data[srcOffset:srcOffset+copyLen])
				}
			}

			outputPage := unswizzle4ConvertPage(psmt4PageW, psmt4PageH, inputPage, index32H, index32V)

			// Python: pi0_offset = (n_output_width_byte * n_output_height) * n_page_w * i + n_output_width_byte * j
			pi0Offset := (nOutputWidthByte * nOutputHeight) * nPageW * i + nOutputWidthByte * j
			
			for k := 0; k < nOutputHeight; k++ {
				// Python: src_offset = k * n_page4_width_byte
				srcOffset := k * (psmt4PageW / 2)
				
				// Python: dst_offset = pi0_offset + k * n_output_width_byte * n_page_w
				dstOffset := pi0Offset + k * nOutputWidthByte * nPageW
				
				copyLen := nOutputWidthByte
				if srcOffset+copyLen <= len(outputPage) && dstOffset+copyLen <= len(outputData) {
					copy(outputData[dstOffset:], outputPage[srcOffset:srcOffset+copyLen])
				}
			}
		}
	}
	return outputData
}

// ---------------------------------------------------------------------------
// Part 4: Helper Bit Ops
// ---------------------------------------------------------------------------

func SwapNibbles(data []byte) []byte {
	out := make([]byte, len(data))
	for i, b := range data {
		out[i] = (b&0x0F)<<4 | (b&0xF0)>>4
	}
	return out
}

// ---------------------------------------------------------------------------
// Internal LUTs for Unswizzle4
// ---------------------------------------------------------------------------

var unswizzleLutTable = [256]uint8{
	0, 8, 16, 24, 32, 40, 48, 56, 2, 10, 18, 26, 34, 42, 50, 58,
	4, 12, 20, 28, 36, 44, 52, 60, 6, 14, 22, 30, 38, 46, 54, 62,
	64, 72, 80, 88, 96, 104, 112, 120, 66, 74, 82, 90, 98, 106, 114, 122,
	68, 76, 84, 92, 100, 108, 116, 124, 70, 78, 86, 94, 102, 110, 118, 126,
	33, 41, 49, 57, 1, 9, 17, 25, 35, 43, 51, 59, 3, 11, 19, 27,
	37, 45, 53, 61, 5, 13, 21, 29, 39, 47, 55, 63, 7, 15, 23, 31,
	97, 105, 113, 121, 65, 73, 81, 89, 99, 107, 115, 123, 67, 75, 83, 91,
	101, 109, 117, 125, 69, 77, 85, 93, 103, 111, 119, 127, 71, 79, 87, 95,
	32, 40, 48, 56, 0, 8, 16, 24, 34, 42, 50, 58, 2, 10, 18, 26,
	36, 44, 52, 60, 4, 12, 20, 28, 38, 46, 54, 62, 6, 14, 22, 30,
	96, 104, 112, 120, 64, 72, 80, 88, 98, 106, 114, 122, 66, 74, 82, 90,
	100, 108, 116, 124, 68, 76, 84, 92, 102, 110, 118, 126, 70, 78, 86, 94,
	1, 9, 17, 25, 33, 41, 49, 57, 3, 11, 19, 27, 35, 43, 51, 59,
	5, 13, 21, 29, 37, 45, 53, 61, 7, 15, 23, 31, 39, 47, 55, 63,
	65, 73, 81, 89, 97, 105, 113, 121, 67, 75, 83, 91, 99, 107, 115, 123,
	69, 77, 85, 93, 101, 109, 117, 125, 71, 79, 87, 95, 103, 111, 119, 127,
}

var blockTable4 = [32]int{
	0, 2, 8, 10, 1, 3, 9, 11, 4, 6, 12, 14, 5, 7, 13, 15,
	16, 18, 24, 26, 17, 19, 25, 27, 20, 22, 28, 30, 21, 23, 29, 31,
}

var blockTable32 = [32]int{
	0, 1, 4, 5, 16, 17, 20, 21, 2, 3, 6, 7, 18, 19, 22, 23,
	8, 9, 12, 13, 24, 25, 28, 29, 10, 11, 14, 15, 26, 27, 30, 31,
}

func unswizzle4ConvertBlock(inputBlockData []byte) []byte {
	outputBlockData := make([]byte, 256)
	index1 := 0
	pIn := 0
	for k := 0; k < 4; k++ {
		index0 := (k % 2) * 128
		for i := 0; i < 16; i++ {
			for j := 0; j < 4; j++ {
				cOut := uint8(0x00)
				// Low nibble
				i0 := int(unswizzleLutTable[index0]); index0++
				i1 := i0 / 2
				i2 := (i0 & 0x1) * 4
				cIn := (inputBlockData[pIn+i1] & (0x0F << i2)) >> i2
				cOut |= cIn

				// High nibble
				i0 = int(unswizzleLutTable[index0]); index0++
				i1 = i0 / 2
				i2 = (i0 & 0x1) * 4
				cIn = (inputBlockData[pIn+i1] & (0x0F << i2)) >> i2
				cOut |= (cIn << 4) & 0xF0

				outputBlockData[index1] = cOut
				index1++
			}
		}
		pIn += 64
	}
	return outputBlockData
}

func unswizzle4ConvertPage(width, height int, inputPageData []byte, index32H, index32V []int) []byte {
	// Output page: PSMCT32 64 * 4 * 32
	outputPageData := make([]byte, 64 * 4 * 32)
	
	nWidth := width / 32
	nHeight := height / 16
	inputPageLineSize := 256
	outputPageLineSize := 128 / 2

	for i := 0; i < nHeight; i++ {
		for j := 0; j < nWidth; j++ {
			inBlockNb := blockTable4[i*nWidth+j]
			
			po0 := make([]byte, 256)
			po1Offset := 8 * index32V[inBlockNb] * inputPageLineSize + index32H[inBlockNb] * 32
			
			for k := 0; k < 8; k++ {
				start := po1Offset + k*inputPageLineSize
				copy(po0[k*32:], inputPageData[start:start+32])
			}

			outputBlock := unswizzle4ConvertBlock(po0)

			for k := 0; k < 16; k++ {
				start := (16 * i * outputPageLineSize) + j*16 + k*outputPageLineSize
				copy(outputPageData[start:], outputBlock[k*16:k*16+16])
			}
		}
	}
	return outputPageData
}

// ===========================================================================
// Part 5: 反向操作 - 像素重排 (Swizzling: Linear -> PS2 Raw)
// ===========================================================================

func Swizzle8(linearData []byte, width, height int) []byte {
	out := make([]byte, len(linearData))
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			blockLoc := (y&(^0xF))*width + (x&(^0xF))*2
			swapSel := (((y + 2) >> 2) & 0x1) * 4
			posY := (((y & (^3)) >> 1) + (y & 1)) & 0x7
			colLoc := posY*width*2 + ((x + swapSel) & 0x7) * 4
			byteNum := ((y >> 1) & 1) + ((x >> 2) & 2)
			
			swizzleIdx := blockLoc + colLoc + byteNum
			linearIdx := y*width + x

			if swizzleIdx < len(out) && linearIdx < len(linearData) {
				out[swizzleIdx] = linearData[linearIdx]
			}
		}
	}
	return out
}

func Swizzle4By8(linearData []byte, width, height int) []byte {
	// 1. Unpack 4bpp Linear -> 8bpp Linear
	temp8 := make([]byte, width*height)
	for i := 0; i < len(linearData); i++ {
		temp8[i*2] = linearData[i] & 0x0F
		if i*2+1 < len(temp8) {
			temp8[i*2+1] = (linearData[i] >> 4) & 0x0F
		}
	}

	swizzled8 := Swizzle8(temp8, width, height)

	out := make([]byte, len(linearData))
	for i := 0; i < len(out); i++ {
		p1 := uint8(0)
		p2 := uint8(0)
		if i*2 < len(swizzled8) {
			p1 = swizzled8[i*2] & 0x0F
		}
		if i*2+1 < len(swizzled8) {
			p2 = swizzled8[i*2+1] & 0x0F
		}
		out[i] = p1 | (p2 << 4)
	}
	return out
}

func Swizzle16(linearData []byte, width, height int) []byte {
	out := make([]byte, len(linearData))
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			swizzledOffset := pixel16Offset(x, y, width)
			dstIdx := swizzledOffset * 2
			srcIdx := (y*width + x) * 2
			
			if dstIdx+1 < len(out) && srcIdx+1 < len(linearData) {
				out[dstIdx] = linearData[srcIdx]
				out[dstIdx+1] = linearData[srcIdx+1]
			}
		}
	}
	return out
}

func Swizzle32(linearData []byte, width, height int) []byte {
	out := make([]byte, len(linearData))
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			blockLoc := (y & (^0xF)) * width + (x & (^0xF)) * 2
			swapSel := (((y + 2) >> 2) & 0x1) * 4
			posY := (((y & (^3)) >> 1) + (y & 1)) & 0x7
			colLoc := posY * width * 2 + ((x + swapSel) & 0x7) * 4
			byteNum := ((y >> 1) & 1) + ((x >> 2) & 2)
			
			swizzleIdx := blockLoc + colLoc + byteNum

			dstIdx := swizzleIdx * 4
			srcIdx := (y*width + x) * 4
			
			if dstIdx+3 < len(out) && srcIdx+3 < len(linearData) {
				copy(out[dstIdx:dstIdx+4], linearData[srcIdx:srcIdx+4])
			}
		}
	}
	return out
}

// ===========================================================================
// Part 6: 反向操作 - 调色板重排 (CSM1 Encoding)
// ===========================================================================

// SwizzleCSM1_32: 将线性调色板转换为CSM1乱序
// 0-7   -> 0-7
// 8-15  -> 16-23 (存放到后面)
// 16-23 -> 8-15  (存放到前面)
// 24-31 -> 24-31
func SwizzleCSM1_32(entries []uint32) []uint32 {
	if len(entries) == 0 { return nil }
	out := make([]uint32, 0, len(entries))
	
	for i := 0; i < len(entries); i += 32 {
		end := i + 32
		if end > len(entries) { end = len(entries) }
		if end-i < 32 {
			out = append(out, entries[i:end]...)
			continue
		}
		
		out = append(out, entries[i:i+8]...)		
		out = append(out, entries[i+16:i+24]...)		
		out = append(out, entries[i+8:i+16]...)		
		out = append(out, entries[i+24:i+32]...)
	}
	return out
}

func SwizzleCSM1_16(entries []uint16) []uint16 {
	if len(entries) == 0 { return nil }
	out := make([]uint16, 0, len(entries))
	for i := 0; i < len(entries); i += 32 {
		end := i + 32
		if end > len(entries) { end = len(entries) }
		if end-i < 32 {
			out = append(out, entries[i:end]...)
			continue
		}
		out = append(out, entries[i:i+8]...)
		out = append(out, entries[i+16:i+24]...)
		out = append(out, entries[i+8:i+16]...)
		out = append(out, entries[i+24:i+32]...)
	}
	return out
}

// ===========================================================================
// Part 5.5: 补充 - 4bpp Native Swizzle 
// ===========================================================================

func Swizzle4(linearData []byte, width, height int) []byte {
	const (
		psmt4PageW   = 128
		psmt4PageH   = 128
		psmct32PageW = 64
	)

	nPageW := (width - 1) / psmt4PageW + 1
	nPageH := (height - 1) / psmt4PageH + 1

	nInputWidthByte := 0
	nOutputHeight := 0
	nInputHeight := 0
	nOutputWidthByte := 0

	if nPageW == 1 {
		nInputWidthByte = width / 2
		nOutputHeight = width / 4
	} else {
		nInputWidthByte = psmt4PageW / 2
		nOutputHeight = 32 // PSMCT32_PAGE_HEIGHT
	}

	if nPageH == 1 {
		nInputHeight = height
		nOutputWidthByte = height * 2
	} else {
		nInputHeight = psmt4PageH
		nOutputWidthByte = psmct32PageW * 4
	}

	outputData := make([]byte, len(linearData))

	index32H := make([]int, 32)
	index32V := make([]int, 32)
	idx0 := 0
	for i := 0; i < 4; i++ {
		for j := 0; j < 8; j++ {
			idx1 := blockTable32[idx0]
			index32H[idx1] = j
			index32V[idx1] = i
			idx0++
		}
	}

	for i := 0; i < nPageH; i++ {
		for j := 0; j < nPageW; j++ {
			
			
			inputPage := make([]byte, (psmt4PageW/2)*psmt4PageH)
			
			for k := 0; k < nInputHeight; k++ {
				// Python: src_idx = (n_input_width_byte * n_input_height) * n_page_w * i + n_input_width_byte * j + k * n_input_width_byte * n_page_w
				srcIdx := (nInputWidthByte * nInputHeight) * nPageW * i + nInputWidthByte * j + k * nInputWidthByte * nPageW
				
				// Python: dst_idx = k * n_page4_width_byte
				dstIdx := k * (psmt4PageW / 2)
				
				copyLen := nInputWidthByte
				if srcIdx+copyLen <= len(linearData) && dstIdx+copyLen <= len(inputPage) {
					copy(inputPage[dstIdx:], linearData[srcIdx:srcIdx+copyLen])
				}
			}

			outputPage := swizzle4ConvertPage(psmt4PageW, psmt4PageH, inputPage, index32H, index32V)

			for k := 0; k < nOutputHeight; k++ {
				// Python: src_idx = k * n_page32_width_byte
				srcIdx := k * (psmct32PageW * 4)
				
				// Python: dst_idx = (n_output_width_byte * n_output_height) * n_page_w * i + n_output_width_byte * j + k * n_output_width_byte * n_page_w
				dstIdx := (nOutputWidthByte * nOutputHeight) * nPageW * i + nOutputWidthByte * j + k * nOutputWidthByte * nPageW
				
				copyLen := nOutputWidthByte
				if srcIdx+copyLen <= len(outputPage) && dstIdx+copyLen <= len(outputData) {
					copy(outputData[dstIdx:], outputPage[srcIdx:srcIdx+copyLen])
				}
			}
		}
	}
	return outputData
}

func swizzle4ConvertPage(width, height int, inputPageData []byte, index32H, index32V []int) []byte {
	// Output Page Size: PSMCT32 64 * 4 * 32
	outputPageData := make([]byte, 64*4*32)

	nWidth := width / 32
	nHeight := height / 16
	inputPageLineSize := 128 / 2 // 64
	outputPageLineSize := 256

	inputBlock := make([]byte, 256)

	for i := 0; i < nHeight; i++ {
		for j := 0; j < nWidth; j++ {
			pi1Idx := 16 * i * inputPageLineSize + j * 16
			
			for k := 0; k < 16; k++ {
				start := pi1Idx + k * inputPageLineSize
				copy(inputBlock[k*16:], inputPageData[start:start+16])
			}

			outputBlock := swizzle4ConvertBlock(inputBlock)

			inBlockNb := blockTable4[i*nWidth+j]
			po0Idx := 8 * index32V[inBlockNb] * outputPageLineSize + index32H[inBlockNb] * 32

			for k := 0; k < 8; k++ {
				start := k * 32
				outStart := po0Idx + k * outputPageLineSize
				copy(outputPageData[outStart:], outputBlock[start:start+32])
			}
		}
	}
	return outputPageData
}

func swizzle4ConvertBlock(inputBlockData []byte) []byte {
	outputBlockData := make([]byte, 256)
	index1 := 0
	pIn := 0
	for k := 0; k < 4; k++ {
		index0 := (k % 2) * 128
		for i := 0; i < 16; i++ {
			for j := 0; j < 4; j++ {
				cOut := uint8(0x00)
				for step := 0; step < 2; step++ {
					i0 := int(swizzleLutTable[index0]); index0++
					i1 := i0 / 2
					i2 := (i0 & 0x1) * 4
					cIn := (inputBlockData[pIn+i1] & (0x0F << i2)) >> i2
					if step == 0 {
						cOut |= cIn
					} else {
						cOut |= (cIn << 4) & 0xF0
					}
				}
				outputBlockData[index1] = cOut
				index1++
			}
		}
		pIn += 64
	}
	return outputBlockData
}

var swizzleLutTable = [256]uint8{
	0, 68, 8, 76, 16, 84, 24, 92, 1, 69, 9, 77, 17, 85, 25, 93, 2, 70, 10, 78, 18, 86, 26, 94, 3, 71, 11, 79, 19, 87, 27, 95,
	4, 64, 12, 72, 20, 80, 28, 88, 5, 65, 13, 73, 21, 81, 29, 89, 6, 66, 14, 74, 22, 82, 30, 90, 7, 67, 15, 75, 23, 83, 31, 91,
	32, 100, 40, 108, 48, 116, 56, 124, 33, 101, 41, 109, 49, 117, 57, 125, 34, 102, 42, 110, 50, 118, 58, 126, 35, 103, 43, 111, 51, 119, 59, 127,
	36, 96, 44, 104, 52, 112, 60, 120, 37, 97, 45, 105, 53, 113, 61, 121, 38, 98, 46, 106, 54, 114, 62, 122, 39, 99, 47, 107, 55, 115, 63, 123,
	4, 64, 12, 72, 20, 80, 28, 88, 5, 65, 13, 73, 21, 81, 29, 89, 6, 66, 14, 74, 22, 82, 30, 90, 7, 67, 15, 75, 23, 83, 31, 91,
	0, 68, 8, 76, 16, 84, 24, 92, 1, 69, 9, 77, 17, 85, 25, 93, 2, 70, 10, 78, 18, 86, 26, 94, 3, 71, 11, 79, 19, 87, 27, 95,
	36, 96, 44, 104, 52, 112, 60, 120, 37, 97, 45, 105, 53, 113, 61, 121, 38, 98, 46, 106, 54, 114, 62, 122, 39, 99, 47, 107, 55, 115, 63, 123,
	32, 100, 40, 108, 48, 116, 56, 124, 33, 101, 41, 109, 49, 117, 57, 125, 34, 102, 42, 110, 50, 118, 58, 126, 35, 103, 43, 111, 51, 119, 59, 127,
}