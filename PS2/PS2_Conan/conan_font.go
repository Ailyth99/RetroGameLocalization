package main

import (
	"flag"
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
	CONAN_TILE_W = 20
	CONAN_TILE_H = 20
	CONAN_COLS   = 26

	TEX_W = 640
	TEX_H = 768
)

var StandardColors = []color.RGBA{
	{0, 0, 0, 255},
	{141, 141, 141, 255},
	{218, 218, 218, 255},
	{255, 255, 255, 255},
}

var ExportPalette = color.Palette{
	color.RGBA{0, 0, 0, 0},
	color.RGBA{141, 141, 141, 255},
	color.RGBA{218, 218, 218, 255},
	color.RGBA{255, 255, 255, 255},
}

func main() {
	tileMode := flag.Bool("tile", false, "Enable Conan Tile Font mode (20x20)")
	texMode := flag.Bool("tex", false, "Enable Conan Full Texture mode (640x768)")
	repackMode := flag.Bool("r", false, "Repack mode")

	flag.Parse()
	args := flag.Args()

	if !*tileMode && !*texMode {
		fmt.Println("Usage:")
		fmt.Println("  [kanji.dat,Tile Mode 20x20]")
		fmt.Println("    Extract: conan_font -tile <kanji.dat>")
		fmt.Println("    Repack : conan_font -tile -r <l1.png> <l2.png> <out.dat>")
		fmt.Println("  [driknj1.dat & driknj2.dat,Texture Mode 640x768]")
		fmt.Println("    Extract: conan_font -tex <driknj.dat>")
		fmt.Println("    Repack : conan_font -tex -r <l1.png> <l2.png> <out.dat>")
		return
	}

	if *repackMode {
		if len(args) < 3 {
			log.Fatal("Repack needs: layer1.png layer2.png output.bin")
		}
		if *tileMode {
			ConanRepack(args[0], args[1], args[2], true)
		} else {
			ConanRepack(args[0], args[1], args[2], false)
		}
	} else {
		if len(args) < 1 {
			log.Fatal("Extract needs: input.bin")
		}
		if *tileMode {
			ConanExtract(args[0], true)
		} else {
			ConanExtract(args[0], false)
		}
	}
}

func ConanExtract(fpath string, isTile bool) {
	data, err := os.ReadFile(fpath)
	if err != nil {
		log.Fatal(err)
	}

	var imgW, imgH int
	var img1, img2 *image.Paletted

	if isTile {
		tileBytes := (CONAN_TILE_W * CONAN_TILE_H) / 2
		numTiles := len(data) / tileBytes
		imgRows := (numTiles + CONAN_COLS - 1) / CONAN_COLS
		imgW, imgH = CONAN_COLS*CONAN_TILE_W, imgRows*CONAN_TILE_H
		img1 = image.NewPaletted(image.Rect(0, 0, imgW, imgH), ExportPalette)
		img2 = image.NewPaletted(image.Rect(0, 0, imgW, imgH), ExportPalette)

		for i := 0; i < numTiles; i++ {
			tileData := data[i*tileBytes : (i+1)*tileBytes]
			tileX := (i % CONAN_COLS) * CONAN_TILE_W
			tileY := (i / CONAN_COLS) * CONAN_TILE_H
			for ty := 0; ty < CONAN_TILE_H; ty++ {
				for txB := 0; txB < CONAN_TILE_W/2; txB++ {
					b := tileData[ty*(CONAN_TILE_W/2)+txB]
					setPixel(img1, img2, tileX+txB*2, tileY+ty, b)
				}
			}
		}
	} else {
		imgW, imgH = TEX_W, TEX_H
		img1 = image.NewPaletted(image.Rect(0, 0, imgW, imgH), ExportPalette)
		img2 = image.NewPaletted(image.Rect(0, 0, imgW, imgH), ExportPalette)
		expectedSize := (TEX_W * TEX_H) / 2
		if len(data) < expectedSize {
			log.Fatalf("File too small for 640x768 texture. Need %d bytes.", expectedSize)
		}

		for y := 0; y < TEX_H; y++ {
			for xB := 0; xB < TEX_W/2; xB++ {
				b := data[y*(TEX_W/2)+xB]
				setPixel(img1, img2, xB*2, y, b)
			}
		}
	}

	baseName := strings.TrimSuffix(fpath, filepath.Ext(fpath))
	savePng(baseName+"_1.png", img1)
	savePng(baseName+"_2.png", img2)
	fmt.Println("Extract Done.")
}

func setPixel(img1, img2 *image.Paletted, x, y int, b byte) {
	p0, p1 := b&0x0F, (b>>4)&0x0F
	img1.SetColorIndex(x, y, p0&0x3)
	img1.SetColorIndex(x+1, y, p1&0x3)
	img2.SetColorIndex(x, y, (p0>>2)&0x3)
	img2.SetColorIndex(x+1, y, (p1>>2)&0x3)
}

func ConanRepack(p1Path, p2Path, outPath string, isTile bool) {
	img1 := loadPng(p1Path)
	img2 := loadPng(p2Path)
	bounds := img1.Bounds()
	imgW, imgH := bounds.Dx(), bounds.Dy()

	var outData []byte
	if isTile {
		rows := imgH / CONAN_TILE_H
		totalTiles := rows * CONAN_COLS
		tileBytes := (CONAN_TILE_W * CONAN_TILE_H) / 2
		outData = make([]byte, totalTiles*tileBytes)

		for i := 0; i < totalTiles; i++ {
			tileX := (i % CONAN_COLS) * CONAN_TILE_W
			tileY := (i / CONAN_COLS) * CONAN_TILE_H
			for ty := 0; ty < CONAN_TILE_H; ty++ {
				for txB := 0; txB < CONAN_TILE_W/2; txB++ {
					b := packByte(img1, img2, tileX+txB*2, tileY+ty)
					outData[i*tileBytes+ty*(CONAN_TILE_W/2)+txB] = b
				}
			}
		}
	} else {
		// 强制使用 640x768 逻辑
		if imgW != TEX_W || imgH != TEX_H {
			fmt.Printf("Warning: PNG size (%dx%d) differs from 640x768.\n", imgW, imgH)
		}
		outData = make([]byte, (TEX_W*TEX_H)/2)
		for y := 0; y < TEX_H; y++ {
			for xB := 0; xB < TEX_W/2; xB++ {
				outData[y*(TEX_W/2)+xB] = packByte(img1, img2, xB*2, y)
			}
		}
	}

	os.WriteFile(outPath, outData, 0644)
	fmt.Printf("Repack Success! Saved to %s\n", outPath)
}

func packByte(img1, img2 image.Image, x, y int) byte {
	idx1_p0 := findColorIdx(img1.At(x, y))
	idx2_p0 := findColorIdx(img2.At(x, y))
	idx1_p1 := findColorIdx(img1.At(x+1, y))
	idx2_p1 := findColorIdx(img2.At(x+1, y))

	val_p0 := (idx2_p0 << 2) | idx1_p0
	val_p1 := (idx2_p1 << 2) | idx1_p1
	return (val_p0 & 0x0F) | ((val_p1 & 0x0F) << 4)
}

func loadPng(path string) image.Image {
	f, err := os.Open(path)
	if err != nil {
		log.Fatal(err)
	}
	defer f.Close()
	img, err := png.Decode(f)
	if err != nil {
		log.Fatal(err)
	}
	return img
}

func savePng(name string, img image.Image) {
	f, _ := os.Create(name)
	defer f.Close()
	png.Encode(f, img)
	fmt.Println("Saved:", name)
}

func findColorIdx(c color.Color) uint8 {
	nc := color.NRGBAModel.Convert(c).(color.NRGBA)
	if nc.A < 128 {
		return 0
	}
	minDist := math.MaxFloat64
	bestIdx := 0
	for i, sc := range StandardColors {
		dr, dg, db := int(nc.R)-int(sc.R), int(nc.G)-int(sc.G), int(nc.B)-int(sc.B)
		dist := float64(dr*dr + dg*dg + db*db)
		if dist < minDist {
			minDist = dist
			bestIdx = i
		}
	}
	return uint8(bestIdx)
}