package main

import (
	"fmt"
	"image"
	"image/color"
	"image/png"
	"log"
	"math"
	"os"
	"path/filepath"
	"strings"
)

const (
	FntWidth       = 512
	FntHeight      = 512
	FntPixelOffset = 0xE0   // 224
	FntPixelSize   = 131072 // 512*512/2 (4bpp)
)

var (
	ColBlack = color.RGBA{0, 0, 0, 255}
	ColDGray = color.RGBA{141, 141, 141, 255}
	ColLGray = color.RGBA{218, 218, 218, 255}
	ColWhite = color.RGBA{255, 255, 255, 255}
	StandardColors = []color.RGBA{ColBlack, ColDGray, ColLGray, ColWhite}
)

func main() {
	if len(os.Args) < 3 {
		printUsage()
		return
	}

	mode := os.Args[1]
	
	switch mode {
	case "-e":
		// dbzfnt_tool -e <file.fnt>
		doExtract(os.Args[2])
	case "-r":
		// dbzfnt_tool -r <file.fnt> <img1.png> <img2.png> <out.fnt>
		if len(os.Args) < 6 {
			fmt.Println("Error: Missing arguments for repack.")
			printUsage()
			return
		}
		doRepack(os.Args[2], os.Args[3], os.Args[4], os.Args[5])
	default:
		printUsage()
	}
}

func printUsage() {
	fmt.Println("DBZ Budokai Tenkaichi 3 Font Tool / aikika 202512")
	fmt.Println("Usage:")
	fmt.Println("  EXTRACT TO PNG: dbzfnt_tool -e <file.fnt>")
	fmt.Println("  REBUILD FNT:  dbzfnt_tool -r <orig.fnt> <clut1.png> <clut2.png> <out.fnt>")

}


func doExtract(fpath string) {
	fmt.Printf("Extracting %s ...\n", fpath)

	f, err := os.Open(fpath)
	if err != nil { log.Fatal(err) }
	defer f.Close()

	rawPacked := make([]byte, FntPixelSize)
	f.Seek(FntPixelOffset, 0)
	f.Read(rawPacked)

	fmt.Println("  Applying Unswizzle4 (Native)...")
	unswizzledPacked := Unswizzle4(rawPacked, FntWidth, FntHeight)

	indices := make([]uint8, FntWidth*FntHeight)
	for i, b := range unswizzledPacked {
		indices[i*2] = b & 0x0F
		if i*2+1 < len(indices) {
			indices[i*2+1] = (b >> 4) & 0x0F
		}
	}

	baseName := strings.TrimSuffix(fpath, filepath.Ext(fpath))
	savePng(baseName+"_clut1.png", indices, makeClut1())
	savePng(baseName+"_clut2.png", indices, makeClut2())
	fmt.Println("Done!")
}


func doRepack(origFntPath, png1Path, png2Path, outFntPath string) {
	fmt.Printf("Repacking %s + %s -> %s ...\n", png1Path, png2Path, outFntPath)

	img1 := loadPng(png1Path)
	img2 := loadPng(png2Path)

	if img1.Bounds().Dx() != FntWidth || img1.Bounds().Dy() != FntHeight {
		log.Fatalf("Image 1 size mismatch: expected %dx%d", FntWidth, FntHeight)
	}
	
	// -------------------------------------------------------
	linearIndices := make([]byte, FntWidth*FntHeight)
	
	for y := 0; y < FntHeight; y++ {
		for x := 0; x < FntWidth; x++ {
			c1 := img1.At(x, y)
			c2 := img2.At(x, y)
			
			// 找到最近的颜色索引 (0-3)
			idx1 := findNearestColorIndex(c1)
			idx2 := findNearestColorIndex(c2)
			
			// 合并: High 2 bits = idx2, Low 2 bits = idx1
			combined := (idx2 << 2) | idx1
			
			linearIndices[y*FntWidth+x] = combined
		}
	}

	// -------------------------------------------------------
	linearPacked := make([]byte, FntPixelSize)
	for i := 0; i < len(linearPacked); i++ {
		p1 := linearIndices[i*2] & 0x0F
		p2 := uint8(0)
		if i*2+1 < len(linearIndices) {
			p2 = linearIndices[i*2+1] & 0x0F
		}
		linearPacked[i] = p1 | (p2 << 4)
	}

	// -------------------------------------------------------
	fmt.Println("  Applying Swizzle4 (Native)...")
	swizzledData := Swizzle4(linearPacked, FntWidth, FntHeight)

	// -------------------------------------------------------
	inputData, err := os.ReadFile(origFntPath)
	if err != nil { log.Fatal(err) }
	
	outData := make([]byte, len(inputData))
	copy(outData, inputData)
	
	if FntPixelOffset+len(swizzledData) > len(outData) {
		log.Fatal("Generated data too large for original file!")
	}
	copy(outData[FntPixelOffset:], swizzledData)
	
	err = os.WriteFile(outFntPath, outData, 0644)
	if err != nil { log.Fatal(err) }
	
	fmt.Println("Success! Saved to:", outFntPath)
}


func loadPng(path string) image.Image {
	f, err := os.Open(path)
	if err != nil { log.Fatal(err) }
	defer f.Close()
	img, err := png.Decode(f)
	if err != nil { log.Fatal(err) }
	return img
}

func savePng(name string, indices []uint8, pal color.Palette) {
	img := image.NewPaletted(image.Rect(0, 0, FntWidth, FntHeight), pal)
	copy(img.Pix, indices)
	f, _ := os.Create(name)
	defer f.Close()
	png.Encode(f, img)
	fmt.Printf("  -> Saved: %s\n", name)
}

func findNearestColorIndex(c color.Color) uint8 {
	nc := color.NRGBAModel.Convert(c).(color.NRGBA)
	r, g, b := int(nc.R), int(nc.G), int(nc.B)
	
	minDist := math.MaxFloat64
	bestIdx := 0
	
	for i, sc := range StandardColors {
		dr := r - int(sc.R)
		dg := g - int(sc.G)
		db := b - int(sc.B)
		
		dist := float64(dr*dr + dg*dg + db*db)
		if dist < minDist {
			minDist = dist
			bestIdx = i
		}
	}
	return uint8(bestIdx)
}

func makeClut1() color.Palette {
	p := make(color.Palette, 16)
	pattern := []color.RGBA{ColBlack, ColDGray, ColLGray, ColWhite}
	for i := 0; i < 16; i++ { p[i] = pattern[i%4] }
	return p
}

func makeClut2() color.Palette {
	p := make(color.Palette, 16)
	for i := 0; i < 16; i++ {
		if i < 4 { p[i] = ColBlack } else if i < 8 { p[i] = ColDGray } else if i < 12 { p[i] = ColLGray } else { p[i] = ColWhite }
	}
	return p
}