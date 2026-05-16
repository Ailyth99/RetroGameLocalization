package main

import (
	"encoding/binary"
	"fmt"
	"image"
	_ "image/png"
	"log"
	"os"
	"path/filepath"
	"strings"
)



func Ps2Swizzle8(in []byte, w, h int) []byte {
	out := make([]byte, len(in))
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			blockLoc := (y & (^0xF)) * w + (x & (^0xF)) * 2
			swapSel := (((y + 2) >> 2) & 0x1) * 4
			posY := (((y & (^3)) >> 1) + (y & 1)) & 0x7
			colLoc := posY*w*2 + ((x + swapSel) & 0x7) * 4
			byteNum := ((y >> 1) & 1) + ((x >> 2) & 2)
			swizzleIdx := blockLoc + colLoc + byteNum

			if swizzleIdx < len(out) {
				out[swizzleIdx] = in[y*w+x]
			}
		}
	}
	return out
}

func SwizzleCSM1(entries []uint32) []uint32 {
	if len(entries) < 256 {
		tmp := make([]uint32, 256)
		copy(tmp, entries)
		entries = tmp
	}
	out := make([]uint32, 0, 256)
	for i := 0; i < 256; i += 32 {
		out = append(out, entries[i:i+8]...)
		out = append(out, entries[i+16:i+24]...)
		out = append(out, entries[i+8:i+16]...)
		out = append(out, entries[i+24:i+32]...)
	}
	return out
}


func encodeRGBA8888FullAlpha(c image.Paletted, idx int) uint32 {
	r16, g16, b16, a16 := c.Palette[idx].RGBA()
	r := uint32(r16 >> 8)
	g := uint32(g16 >> 8)
	b := uint32(b16 >> 8)
	a := uint32(a16 >> 8)


	return (a << 24) | (b << 16) | (g << 8) | r
}


func isPowerOfTwo(n int) bool {
	return n > 0 && (n&(n-1)) == 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("PS2 TEX Tool (Alpha x2 / Raw Version)")
		fmt.Println("Usage: tex_tool <input.png> [-o output.TEX]")
		return
	}

	pngPath := os.Args[1]
	outPath := ""

	for i := 1; i < len(os.Args); i++ {
		if os.Args[i] == "-o" && i+1 < len(os.Args) {
			outPath = os.Args[i+1]
			break
		}
	}

	if outPath == "" {
		ext := filepath.Ext(pngPath)
		outPath = strings.TrimSuffix(pngPath, ext) + ".TEX"
	}

	f, err := os.Open(pngPath)
	if err != nil {
		log.Fatal("Open error:", err)
	}
	defer f.Close()

	img, _, err := image.Decode(f)
	if err != nil {
		log.Fatal("Decode error:", err)
	}

	palImg, ok := img.(*image.Paletted)
	if !ok {
		log.Fatal("Error: PNG must be Indexed (8bpp).")
	}

	w := palImg.Bounds().Dx()
	h := palImg.Bounds().Dy()

	if !isPowerOfTwo(w) || !isPowerOfTwo(h) || w > 1024 || h > 1024 {
		log.Fatalf("Error: Dimension %dx%d invalid. Must be power of 2 and <= 1024.", w, h)
	}

	fmt.Printf("Encoding %dx%d TEX with Full Alpha (x2)...\n", w, h)

	header := make([]byte, 32)
	binary.LittleEndian.PutUint32(header[0x00:], uint32(w))
	binary.LittleEndian.PutUint32(header[0x04:], uint32(h))
	binary.LittleEndian.PutUint32(header[0x08:], 8)
	binary.LittleEndian.PutUint32(header[0x0C:], 0x13) // 强制模式 0x13
	binary.LittleEndian.PutUint32(header[0x10:], 0)

	swizzledPixels := Ps2Swizzle8(palImg.Pix, w, h)

	u32Pal := make([]uint32, 256)
	for i := 0; i < 256; i++ {
		if i < len(palImg.Palette) {
			u32Pal[i] = encodeRGBA8888FullAlpha(*palImg, i)
		} else {
			u32Pal[i] = 0
		}
	}
	swizzledPal := SwizzleCSM1(u32Pal)

	outF, err := os.Create(outPath)
	if err != nil {
		log.Fatal(err)
	}
	defer outF.Close()

	outF.Write(header)
	outF.Write(swizzledPixels)
	for _, colorVal := range swizzledPal {
		binary.Write(outF, binary.LittleEndian, colorVal)
	}

	fmt.Printf("Success! Alpha boosted. Saved to: %s\n", outPath)
}