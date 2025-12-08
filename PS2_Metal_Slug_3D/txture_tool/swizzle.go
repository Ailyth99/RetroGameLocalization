package main

//---------------------------------------------------------------------------
//Part1: 调色板重排 (Palette/CLUT Swizzling)
//---------------------------------------------------------------------------

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

//---------------------------------------------------------------------------
//Part2:像素重排，基础&8/16/32bpp
//---------------------------------------------------------------------------

func Unswizzle8(data []byte, width, height int) []byte {
	out := make([]byte, len(data))
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			blockLoc := (y & (^0xF)) * width + (x & (^0xF)) * 2			
			swapSel := (((y + 2) >> 2) & 0x1) * 4			
			posY := (((y & (^3)) >> 1) + (y & 1)) & 0x7			
			colLoc := posY * width * 2 + ((x + swapSel) & 0x7) * 4
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
			//32bpp可以看作是4倍宽的8bpp或者是2倍宽的16bpp
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

//---------------------------------------------------------------------------
// Part3 像素重排4bpp
//---------------------------------------------------------------------------

func Unswizzle4By8(data []byte, width, height int) []byte {
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

	unswizzled8 := Unswizzle8(temp8, width, height)

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
				srcOffset := po0Offset + k * nInputWidthByte * nPageW
				dstOffset := k * (psmct32PageW * 4)
				
				copyLen := nInputWidthByte
				if srcOffset+copyLen <= len(data) && dstOffset+copyLen <= len(inputPage) {
					copy(inputPage[dstOffset:], data[srcOffset:srcOffset+copyLen])
				}
			}

			outputPage := unswizzle4ConvertPage(psmt4PageW, psmt4PageH, inputPage, index32H, index32V)

			pi0Offset := (nOutputWidthByte * nOutputHeight) * nPageW * i + nOutputWidthByte * j
			
			for k := 0; k < nOutputHeight; k++ {
				srcOffset := k * (psmt4PageW / 2)
				
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

//---------------------------------------------------------------------------
//Part4: 高低位变化，一般4bpp会用到
//---------------------------------------------------------------------------

func SwapNibbles(data []byte) []byte {
	out := make([]byte, len(data))
	for i, b := range data {
		out[i] = (b&0x0F)<<4 | (b&0xF0)>>4
	}
	return out
}

//---------------------------------------------------------------------------
//LUTs for Unswizzle4
//---------------------------------------------------------------------------

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

//===========================================================================
// Part5: 反向操作。像素重排Swizzle
//===========================================================================

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
				//反向赋值
				//把线性图里的点，塞进乱序的坑里
				out[swizzleIdx] = linearData[linearIdx]
			}
		}
	}
	return out
}

//Swizzle4By8: 将线性4bpp数据->解压->Swizzle8->压缩
func Swizzle4By8(linearData []byte, width, height int) []byte {
	temp8 := make([]byte, width*height)
	for i := 0; i < len(linearData); i++ {
		//线性图解包：低位在前，高位在后 (PS2标准)
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

//===========================================================================
//Part6: 反向操作-调色板重排 (CSM1是PS2 SDK里面索尼自己的叫法)
//===========================================================================

//SwizzleCSM1_32: 将线性调色板转换为CSM1乱序
//0-7->0-7
//8-15->16-23 (存放到后面)
//16-23->8-15  (存放到前面)
//24-31->24-31
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

//SwizzleCSM1_16: 同上针对16bit调色板（16位的比较少）
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