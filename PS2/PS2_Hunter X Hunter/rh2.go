// rh2.go
package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"image"
	"image/color"
	"image/draw"
)

type QRS struct {
	q, r, s int
}

func parseRH2(data []byte) []QRS {
	var blocks []QRS
	n := len(data)
	if n < 4 { return nil }

	mode := binary.LittleEndian.Uint16(data[0x50:])

	for pos := 0; pos <= n-4; pos++ {
		if data[pos] == 0x51 && data[pos+1] == 0x00 && data[pos+2] == 0x00 && data[pos+3] == 0x00 {
			q := pos
			r, s := -1, -1
			
			endSearch := pos + 256
			if endSearch > n { endSearch = n }
			
			for off := pos + 4; off <= endSearch-4; off++ {
				if data[off] == 0x52 && data[off+1] == 0x00 && data[off+2] == 0x00 && data[off+3] == 0x00 {
					r = off
				} else if data[off] == 0x53 && data[off+1] == 0x00 && data[off+2] == 0x00 && data[off+3] == 0x00 {
					s = off
				}
				if r != -1 && s != -1 { break }
			}
			
			if r != -1 && s != -1 {
				blocks = append(blocks, QRS{q, r, s})
				
				// Intelligent skip to avoid false positives in pixel data
				if q+16 <= n {
					tw := binary.LittleEndian.Uint32(data[q+8:])
					th := binary.LittleEndian.Uint32(data[q+12:])
					
					dataSize := 0
					if mode == 0x14 { // 4bpp
						dataSize = int((tw * th) / 2)
					} else if mode == 0x13 { // 8bpp
						dataSize = int(tw * th)
					} else { // 16bit Direct Color
						dataSize = int(tw * th * 2)
					}
					
					jumpTo := s + 0x18 + dataSize
					if jumpTo > pos && jumpTo < n {
						pos = jumpTo - 1
					}
				}
			}
		}
	}
	return blocks
}

func RH2ToImage(data []byte) (image.Image, error) {
	if len(data) < 0x60 { return nil, fmt.Errorf("file too small") }
	
	mode := binary.LittleEndian.Uint16(data[0x50:])
	w := int(binary.LittleEndian.Uint16(data[0x54:]))
	h := int(binary.LittleEndian.Uint16(data[0x56:]))
	
	blocks := parseRH2(data)
	if len(blocks) == 0 {
		return nil, fmt.Errorf("no image blocks found")
	}
	
	var palette []color.RGBA
	startBlockIdx := 0
	
	// 1. Identify Mode and Load Palette (if indexed)
	if mode == 0x14 { // 4bpp
		palOffset := blocks[0].s + 0x18
		for i := 0; i < 16; i++ {
			v := binary.LittleEndian.Uint16(data[palOffset+i*2:])
			palette = append(palette, decodeABGR1555(v))
		}
		startBlockIdx = 1 // Block 0 is palette
	} else if mode == 0x13 { // 8bpp
		palOffset := blocks[0].s + 0x18
		marker := binary.BigEndian.Uint16(data[blocks[0].s+8:])
		
		if marker == 0x2080 { // ABGR1555
			rawPal := make([]uint16, 256)
			for i := 0; i < 256; i++ {
				rawPal[i] = binary.LittleEndian.Uint16(data[palOffset+i*2:])
			}
			unswizzled := palCSM1(rawPal)
			for _, v := range unswizzled {
				palette = append(palette, decodeABGR1555(v))
			}
		} else if marker == 0x4080 { // RGBX8888
			rawPal := make([]uint32, 256)
			for i := 0; i < 256; i++ {
				rawPal[i] = binary.LittleEndian.Uint32(data[palOffset+i*4:])
			}
			unswizzled := palCSM1_32(rawPal)
			for _, v := range unswizzled {
				palette = append(palette, decodeRGBX8888(v))
			}
		}
		startBlockIdx = 1 // Block 0 is palette
	} else {
		// Assume 16-bit Direct Color (No Palette)
		// Block 0 is the first tile
		startBlockIdx = 0
	}

	img := image.NewRGBA(image.Rect(0, 0, w, h))

	// 2. Process Tiles
	for i := startBlockIdx; i < len(blocks); i++ {
		q := blocks[i]
		if q.q+16 > len(data) { continue }
		tw := int(binary.LittleEndian.Uint32(data[q.q+8:]))
		th := int(binary.LittleEndian.Uint32(data[q.q+12:]))
		
		cols := w / tw
		// Adjust dimensions for 8bpp 
		if mode == 0x13 { cols = w / (tw * 2); tw *= 2; th *= 2 }
		// For 16-bit, usually tw/th are correct in bytes, but check if we need scaling
		// (Assuming standard 16bit here based on Q header)
		
		if cols == 0 { cols = 1 }
		
		// Correct tile index logic based on start block
		ti := i - startBlockIdx
		tx := (ti % cols) * tw
		ty := (ti / cols) * th
		
		pixOffset := q.s + 0x18
		
		if mode == 0x14 {
			size := (tw * th) / 2
			if pixOffset+size > len(data) { continue }
			raw := data[pixOffset : pixOffset+size]
			swapped := swapNibbles(raw)
			for py := 0; py < th; py++ {
				for px := 0; px < tw; px += 2 {
					idx := (py*tw + px) / 2
					if idx < len(swapped) {
						b := swapped[idx]
						img.Set(tx+px, ty+py, palette[b>>4])
						img.Set(tx+px+1, ty+py, palette[b&0x0F])
					}
				}
			}
		} else if mode == 0x13 {
			size := tw * th
			if pixOffset+size > len(data) { continue }
			raw := data[pixOffset : pixOffset+size]
			unswizzled := ps2Swizzle(raw, tw, th, false)
			for py := 0; py < th; py++ {
				for px := 0; px < tw; px++ {
					idx := unswizzled[py*tw+px]
					img.Set(tx+px, ty+py, palette[idx])
				}
			}
		} else {
			// 16-bit Direct Color (ABGR1555)
			// No Swizzle for these RH2s usually
			size := tw * th * 2
			if pixOffset+size > len(data) { continue }
			for py := 0; py < th; py++ {
				for px := 0; px < tw; px++ {
					offset := pixOffset + (py*tw+px)*2
					v := binary.LittleEndian.Uint16(data[offset:])
					img.Set(tx+px, ty+py, decodeABGR1555(v))
				}
			}
		}
	}
	return img, nil
}

func InjectPNGToRH2(pngImg image.Image, rh2Data []byte) ([]byte, error) {
	if len(rh2Data) < 0x60 { return nil, fmt.Errorf("template too small") }
	
	mode := binary.LittleEndian.Uint16(rh2Data[0x50:])
	w := int(binary.LittleEndian.Uint16(rh2Data[0x54:]))
	h := int(binary.LittleEndian.Uint16(rh2Data[0x56:]))

	if pngImg.Bounds().Dx() != w || pngImg.Bounds().Dy() != h {
		fmt.Printf("Warning: PNG size (%dx%d) != RH2 header size (%dx%d). Proceeding...\n", 
			pngImg.Bounds().Dx(), pngImg.Bounds().Dy(), w, h)
	}

	blocks := parseRH2(rh2Data)
	if len(blocks) == 0 {
		return nil, fmt.Errorf("template has no blocks")
	}

	var pal []color.RGBA
	startBlockIdx := 0
	
	// 1. Palette Injection
	if mode == 0x14 {
		startBlockIdx = 1
		palOffset := blocks[0].s + 0x18
		pal = extractPalette(pngImg, 16)
		fmt.Printf("  Mode: 4bpp (ABGR1555), Palette: %d colors\n", len(pal))
		
		buf := new(bytes.Buffer)
		for _, c := range pal {
			binary.Write(buf, binary.LittleEndian, encodeABGR1555(c))
		}
		if palOffset+buf.Len() <= len(rh2Data) {
			copy(rh2Data[palOffset:], buf.Bytes())
		}
		
	} else if mode == 0x13 {
		startBlockIdx = 1
		palOffset := blocks[0].s + 0x18
		pal = extractPalette(pngImg, 256)
		marker := binary.BigEndian.Uint16(rh2Data[blocks[0].s+8:])
		
		if marker == 0x2080 {
			fmt.Println("  Mode: 8bpp (ABGR1555)")
			vals := make([]uint16, 256)
			for i, c := range pal { vals[i] = encodeABGR1555(c) }
			swizzled := palCSM1(vals)
			buf := new(bytes.Buffer)
			binary.Write(buf, binary.LittleEndian, swizzled)
			if palOffset+buf.Len() <= len(rh2Data) {
				copy(rh2Data[palOffset:], buf.Bytes())
			}
		} else if marker == 0x4080 {
			fmt.Println("  Mode: 8bpp (RGBX8888)")
			vals := make([]uint32, 256)
			for i, c := range pal { vals[i] = encodeRGBX8888(c) }
			swizzled := palCSM1_32(vals)
			buf := new(bytes.Buffer)
			binary.Write(buf, binary.LittleEndian, swizzled)
			if palOffset+buf.Len() <= len(rh2Data) {
				copy(rh2Data[palOffset:], buf.Bytes())
			}
		}
	} else {
		fmt.Printf("  Mode: 16-bit Direct Color (0x%X)\n", mode)
		startBlockIdx = 0 // No palette block
	}

	// 2. Tile Injection
	outData := make([]byte, len(rh2Data))
	copy(outData, rh2Data)
	
	// Calculate expected tiles for warning
	tileBlockIdx := startBlockIdx
	if tileBlockIdx < len(blocks) {
		firstQ := blocks[tileBlockIdx]
		tw := int(binary.LittleEndian.Uint32(rh2Data[firstQ.q+8:]))
		// th := int(binary.LittleEndian.Uint32(rh2Data[firstQ.q+12:])) // Unused
		if mode == 0x13 { tw *= 2 }
		// totalExpected calculation logic here... (omitted for brevity)
	}

	processedCount := 0
	for i := startBlockIdx; i < len(blocks); i++ {
		q := blocks[i]
		tw := int(binary.LittleEndian.Uint32(rh2Data[q.q+8:]))
		th := int(binary.LittleEndian.Uint32(rh2Data[q.q+12:]))
		
		cols := w / tw
		if mode == 0x13 { cols = w / (tw * 2); tw *= 2; th *= 2 }
		if cols == 0 { cols = 1 }
		
		ti := i - startBlockIdx
		tx := (ti % cols) * tw
		ty := (ti / cols) * th
		
		if tx >= pngImg.Bounds().Dx() || ty >= pngImg.Bounds().Dy() {
			continue
		}

		tile := image.NewRGBA(image.Rect(0, 0, tw, th))
		draw.Draw(tile, tile.Bounds(), pngImg, image.Pt(tx, ty), draw.Src)
		
		pixOffset := q.s + 0x18
		
		if mode == 0x14 {
			indexed := imageToIndexed(tile, pal)
			packed := make([]byte, 0, len(indexed)/2)
			for j := 0; j < len(indexed); j += 2 {
				p1 := indexed[j] & 0xF
				p2 := uint8(0)
				if j+1 < len(indexed) { p2 = indexed[j+1] & 0xF }
				packed = append(packed, (p1<<4)|p2)
			}
			swapped := swapNibbles(packed)
			if pixOffset+len(swapped) <= len(outData) {
				copy(outData[pixOffset:], swapped)
			}
		} else if mode == 0x13 {
			indexed := imageToIndexed(tile, pal)
			swizzled := ps2Swizzle(indexed, tw, th, true)
			if pixOffset+len(swizzled) <= len(outData) {
				copy(outData[pixOffset:], swizzled)
			}
		} else {
			// 16-bit Direct Color Encode
			// Directly write ABGR1555 pixels
			for py := 0; py < th; py++ {
				for px := 0; px < tw; px++ {
					c := tile.At(px, py).(color.RGBA)
					v := encodeABGR1555(c)
					offset := pixOffset + (py*tw+px)*2
					if offset+2 <= len(outData) {
						binary.LittleEndian.PutUint16(outData[offset:], v)
					}
				}
			}
		}
		fmt.Printf("  Encoded Tile %d @ %d,%d\n", i, tx, ty)
		processedCount++
	}
	
	return outData, nil
}