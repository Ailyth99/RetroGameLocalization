package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"image"
	"image/color"
	_ "image/png" // Import for side-effects: png decoder
	"image/png"
	"io/fs"
	"log"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

var (
	magic = []byte{0x50, 0x53, 0x32, 0x00} // "PS2\0"
	sigS  = []byte{0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x53, 0x00, 0x00, 0x00}
)

type texInfo struct {
	id      int
	head    int
	w, h    uint32
	bpp     int
	px, pal int
}

func main() {
	if len(os.Args) < 2 {
		usage()
		return
	}

	mode := os.Args[1]
	
	switch mode {
	case "-scan":
		if len(os.Args) != 3 {
			usage()
			return
		}
		scanFile(os.Args[2])
	case "-ex":
		if len(os.Args) != 3 {
			usage()
			return
		}
		batchEx(os.Args[2])
	case "-inject":
		if len(os.Args) < 5 {
			usage()
			return
		}
		pngPath := os.Args[2]
		binPath := os.Args[3]
		id, err := strconv.Atoi(os.Args[4])
		if err != nil {
			log.Fatal("Error: Texture ID must be a number.")
		}

		outPath := binPath // Default: overwrite
		if len(os.Args) == 7 && os.Args[5] == "-o" {
			outPath = os.Args[6]
		} else if len(os.Args) != 5 {
			usage()
			return
		}
		
		injectPNG(pngPath, binPath, outPath, id)
	default:
		usage()
	}
}

func usage() {
	exe := filepath.Base(os.Args[0])
	fmt.Println("Metal Slug 3D Texture Tool (.mst)")
	fmt.Println("\nUsage:")
	fmt.Printf("  Scan a file       : %s -scan <file.bin>\n", exe)
	fmt.Printf("  Extract from a dir: %s -ex <folder_path>\n", exe)
	fmt.Printf("  Inject into a file: %s -inject <in.png> <in.bin> <tex_id> [-o <out.bin>]\n", exe)
}

//扫描贴图
func scanFile(path string) {
	data, err := os.ReadFile(path)
	if err != nil {
		log.Printf("Error: Can't read file %s: %v", path, err)
		return
	}

	fmt.Printf("Scanning %s (size: %d bytes)...\n", path, len(data))
	fmt.Println("-------------------------------------------------------------------------------------")
	fmt.Println("Tex #   | Head      | Dims         | BPP  | Pixels    | Palette")
	fmt.Println("-------------------------------------------------------------------------------------")

	texs := findTexs(data)
	for _, t := range texs {
		bppStr := fmt.Sprintf("%dbpp", t.bpp)
		fmt.Printf("Tex %-3d | 0x%-7X | %-12s | %-4s | 0x%-7X | 0x%-7X\n",
			t.id, t.head, fmt.Sprintf("%dx%d", t.w, t.h), bppStr, t.px, t.pal)
	}

	fmt.Println("-------------------------------------------------------------------------------------")
	fmt.Printf("Scan complete. Found %d textures.\n", len(texs))
}

//导出贴图
func batchEx(dir string) {
	fmt.Printf("Starting batch extract for dir: %s\n", dir)
	
	binSig := []byte{0x16, 0x00, 0x00, 0x00}

	err := filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil { return err }
		if d.IsDir() || !strings.HasSuffix(strings.ToLower(path), ".bin") {
			return nil
		}
		
		fmt.Printf("\n--- Processing: %s ---\n", filepath.Base(path))
		data, err := os.ReadFile(path)
		if err != nil {
			log.Printf("  Skip: Can't read file: %v", err)
			return nil
		}

		if len(data) < 4 || !bytes.Equal(data[:4], binSig) {
			fmt.Println("  Skip: Header mismatch (not 0x16000000).")
			return nil
		}
		
		texs := findTexs(data)
		if len(texs) == 0 {
			fmt.Println("  No textures found in this file.")
			return nil
		}

		fmt.Printf("  Found %d textures, exporting...\n", len(texs))
		for _, t := range texs {
			if err := savePNG(data, t, path); err != nil {
				fmt.Printf("    Failed to export tex #%d: %v\n", t.id, err)
			} else {
				base := strings.TrimSuffix(filepath.Base(path), filepath.Ext(path))
				fmt.Printf("    ✓ Tex #%d -> %s_%03d.png\n", t.id, base, t.id)
			}
		}
		return nil
	})

	if err != nil {
		log.Fatalf("Error walking directory: %v", err)
	}
	fmt.Println("\nBatch extract complete.")
}

//注入图像数据
func injectPNG(pngPath, binPath, outPath string, texID int) {
	fmt.Printf("Injecting %s into %s (Tex ID: %d)...\n", filepath.Base(pngPath), filepath.Base(binPath), texID)

	binData, err := os.ReadFile(binPath)
	if err != nil {
		log.Fatalf("Error: Could not read target bin: %v", err)
	}
	
	modData := make([]byte, len(binData))
	copy(modData, binData)

	texs := findTexs(modData)
	var t texInfo
	found := false
	for _, tex := range texs {
		if tex.id == texID {
			t = tex
			found = true
			break
		}
	}
	if !found {
		log.Fatalf("Error: Texture ID #%d not found in %s", texID, filepath.Base(binPath))
	}
	fmt.Printf("  Target texture found: %dx%d %dbpp\n", t.w, t.h, t.bpp)

	f, err := os.Open(pngPath)
	if err != nil {
		log.Fatalf("Error: Could not open PNG: %v", err)
	}
	defer f.Close()

	img, _, err := image.Decode(f)
	if err != nil {
		log.Fatalf("Error: Could not decode PNG: %v", err)
	}

	if img.Bounds().Dx() != int(t.w) || img.Bounds().Dy() != int(t.h) {
		log.Fatalf("Error: PNG dims (%dx%d) mismatch target (%dx%d)",
			img.Bounds().Dx(), img.Bounds().Dy(), t.w, t.h)
	}

	rawPx, rawPal, err := pngToMst(img, t.bpp)
	if err != nil {
		log.Fatalf("Error: Failed to convert png to mst: %v", err)
	}
	fmt.Println("  PNG converted to raw PS2 data successfully.")

	expectedPxSize := (int(t.w) * int(t.h) * t.bpp) / 8
	expectedPalSize := (1 << t.bpp) * 4
	if len(rawPx) != expectedPxSize {
		log.Fatalf("Error: Pixel size mismatch (got %d, want %d)", len(rawPx), expectedPxSize)
	}
	if len(rawPal) != expectedPalSize {
		log.Fatalf("Error: Palette size mismatch (got %d, want %d)", len(rawPal), expectedPalSize)
	}

	copy(modData[t.pal:], rawPal)
	copy(modData[t.px:], rawPx)
	
	if err := os.WriteFile(outPath, modData, 0644); err != nil {
		log.Fatalf("Error: Failed to write output file: %v", err)
	}

	if outPath == binPath {
		fmt.Printf("Success! Original file %s has been overwritten.\n", filepath.Base(outPath))
	} else {
		fmt.Printf("Success! Injected data saved to %s\n", filepath.Base(outPath))
	}
}



func findTexs(data []byte) []texInfo {
	var texs []texInfo
	count := 0
	pos := 0

	for {
		nextMatch := bytes.Index(data[pos:], magic)
		if nextMatch == -1 { break }

		head := pos + nextMatch
		count++

		var s1, s2 = -1, -1
		search := head

		idx1 := bytes.Index(data[search:], sigS)
		if idx1 != -1 {
			s1 = search + idx1 + 8
			search = search + idx1 + 1
			idx2 := bytes.Index(data[search:], sigS)
			if idx2 != -1 {
				s2 = search + idx2 + 8
			}
		}

		if s1 == -1 || s2 == -1 {
			pos = head + 1
			continue
		}

		wAddr := s1 - 24
		hAddr := s1 - 20
		pxStart := s1 + 24
		
		if hAddr+4 > len(data) {
			pos = head + 1
			continue
		}

		w := binary.LittleEndian.Uint32(data[wAddr:]) * 2
		h := binary.LittleEndian.Uint32(data[hAddr:]) * 2

		bppFlagOff := s2 + 8
		if bppFlagOff >= len(data) {
			pos = head + 1
			continue
		}

		var bpp int
		switch data[bppFlagOff] {
		case 0x40: bpp = 8
		case 0x06: bpp = 4
		default:
			pos = head + 1
			continue
		}
		
		palStart := bppFlagOff + 16

		texs = append(texs, texInfo{
			id:   count,
			head: head,
			w:    w,
			h:    h,
			bpp:  bpp,
			px:   pxStart,
			pal:  palStart,
		})

		pos = head + 1
	}
	return texs
}

func savePNG(data []byte, t texInfo, srcPath string) error {
	pxSize := (int(t.w) * int(t.h) * t.bpp) / 8
	if t.px+pxSize > len(data) { return fmt.Errorf("pixel data out of bounds") }
	rawPx := data[t.px : t.px+pxSize]

	var finalPx []byte
	if t.bpp == 8 {
		finalPx = Unswizzle8(rawPx, int(t.w), int(t.h))
	} else {
		finalPx = Unswizzle4By8(rawPx, int(t.w), int(t.h))
	}

	numColors := 1 << t.bpp
	palSize := numColors * 4
	if t.pal+palSize > len(data) { return fmt.Errorf("palette data out of bounds") }
	rawPal := data[t.pal : t.pal+palSize]

	u32Pal := make([]uint32, numColors)
	for i := 0; i < numColors; i++ {
		u32Pal[i] = binary.LittleEndian.Uint32(rawPal[i*4 : i*4+4])
	}
	unswizzledPal := UnswizzleCSM1_32(u32Pal)

	goPal := make(color.Palette, numColors)
	for i, v := range unswizzledPal {
		goPal[i] = decodeRGBA8888(v, true)
	}
	
	img := image.NewPaletted(image.Rect(0, 0, int(t.w), int(t.h)), goPal)
	if t.bpp == 8 {
		copy(img.Pix, finalPx)
	} else {
		for i, b := range finalPx {
			img.Pix[i*2] = b & 0x0F
			if i*2+1 < len(img.Pix) {
				img.Pix[i*2+1] = (b >> 4) & 0x0F
			}
		}
	}
	
	base := strings.TrimSuffix(filepath.Base(srcPath), filepath.Ext(srcPath))
	outName := fmt.Sprintf("%s_%03d.png", base, t.id)
	outPath := filepath.Join(filepath.Dir(srcPath), outName)

	f, err := os.Create(outPath)
	if err != nil { return err }
	defer f.Close()

	return png.Encode(f, img)
}

func pngToMst(img image.Image, bpp int) (pixels []byte, palette []byte, err error) {
	palettedImg, ok := img.(*image.Paletted)
	if !ok {
		fmt.Println("  Warning: PNG is not paletted, quantizing...")
		numColors := 1 << bpp
		palRGBA := extractPalette(img, numColors)
		
		goPalette := make(color.Palette, len(palRGBA))
		for i, c := range palRGBA {
			goPalette[i] = c
		}

		indices := imageToIndexed(img, palRGBA)
		palettedImg = image.NewPaletted(img.Bounds(), goPalette)
		palettedImg.Pix = indices
	}

	goPal := palettedImg.Palette
	numColors := 1 << bpp
	linearPal := make([]uint32, numColors)
	for i := 0; i < numColors; i++ {
		if i < len(goPal) {
			nrgba := color.NRGBAModel.Convert(goPal[i]).(color.NRGBA)
			rgba := color.RGBA{nrgba.R, nrgba.G, nrgba.B, nrgba.A}
			linearPal[i] = encodeRGBA8888(rgba, true)
		}
	}
	
	swizzledPal := SwizzleCSM1_32(linearPal)
	
	palette = make([]byte, numColors*4)
	for i, v := range swizzledPal {
		binary.LittleEndian.PutUint32(palette[i*4:], v)
	}

	linearPx := palettedImg.Pix
	if bpp == 8 {
		pixels = Swizzle8(linearPx, palettedImg.Bounds().Dx(), palettedImg.Bounds().Dy())
	} else {
		packedPx := make([]byte, len(linearPx)/2)
		for i := 0; i < len(packedPx); i++ {
			p1 := linearPx[i*2] & 0x0F
			p2 := uint8(0)
			if i*2+1 < len(linearPx) {
				p2 = linearPx[i*2+1] & 0x0F
			}
			packedPx[i] = p1 | (p2 << 4)
		}
		pixels = Swizzle4By8(packedPx, palettedImg.Bounds().Dx(), palettedImg.Bounds().Dy())
	}
	
	return pixels, palette, nil
}