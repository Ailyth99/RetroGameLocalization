package main

import (
	"encoding/hex"
	"flag"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const (
	ImgW, ImgH   = 512, 512
	PixSize      = 131072
	TotalSize    = 131600
	
	PixOff       = 0xB0
	Clut1HeadOff = 0x200B0
	Clut1DataOff = 0x20120
	Clut2HeadOff = 0x20160
	Clut2DataOff = 0x201D0
)

var (
	HeadHex      = "10020200010000000000000000000000200000000000000000000000000000001E2000700000000000000000000000000000000000000000000000001D20005105000000000000100E00000000000000FFFFFFFF000000003F0000000000000000000000403B0814500000000000000000000000000000005100000000000000000200000002000052000000000000000000000000000000530000000000000000200000000000080000000000000000"
	ClutHeadHex1 = "05000000000000100E00000000000000FFFFFFFF000000003F0000000000000000000000E03F0100500000000000000000000000000000005100000000000000080000000200000052000000000000000000000000000000530000000000000004800000000000080000000000000000"
	ClutHeadHex2 = "05000000000000100E00000000000000FFFFFFFF000000003F0000000000000000000000E13F0100500000000000000000000000000000005100000000000000080000000200000052000000000000000000000000000000530000000000000004800000000000080000000000000000"
)

var (
	Col0 = color.RGBA{0xA9, 0xA9, 0xA9, 0x80}
	Col1 = color.RGBA{0x74, 0x74, 0x74, 0x80}
	Col2 = color.RGBA{0x37, 0x37, 0x37, 0x80}
	Col3 = color.RGBA{0x00, 0x00, 0x00, 0x00}
)

var PaletteView = color.Palette{
	color.RGBA{0, 0, 0, 0},         // 0: Trans (TMR 3)
	color.RGBA{55, 55, 55, 255},    // 1: Dark  (TMR 2)
	color.RGBA{116, 116, 116, 255}, // 2: Light (TMR 1)
	color.RGBA{255, 255, 255, 255}, // 3: White (TMR 0)
}

func main() {
	if len(os.Args) < 2 {
		printUsage()
		return
	}

	switch os.Args[1] {
	case "-e":
		fs := flag.NewFlagSet("extract", flag.ExitOnError)
		fs.Parse(os.Args[2:])
		if fs.NArg() < 1 { printUsage(); return }
		doExtract(fs.Arg(0))
	case "-r":
		fs := flag.NewFlagSet("repack", flag.ExitOnError)
		fs.Parse(os.Args[2:])
		if fs.NArg() < 3 { printUsage(); return }
		doRepack(fs.Arg(0), fs.Arg(1), fs.Arg(2))
	default:
		printUsage()
	}
}

func printUsage() {
	fmt.Println("KING'S FIELD IV TMR Font Tool v1.2")
	fmt.Println("Usage:")
	fmt.Println("  Extract: tmr_font_tool -e <in.tmr>")
	fmt.Println("  Repack:  tmr_font_tool -r <L1.png> <L2.png> <out.tmr>")
}

func doExtract(fpath string) {
	fmt.Printf("Extracting %s...\n", fpath)
	
	raw, err := os.ReadFile(fpath)
	if err != nil { log.Fatal(err) }
	
	if len(raw) < PixOff+PixSize { log.Fatal("File too small") }
	
	pixels := raw[PixOff : PixOff+PixSize]

	l1 := make([]uint8, ImgW*ImgH)
	l2 := make([]uint8, ImgW*ImgH)
	
//TMR(0,1,2,3) -> PNG(3,2,1,0)
	lut := []uint8{3, 2, 1, 0}

	for i, b := range pixels {
		p0, p1 := b&0xF, b>>4
		
		l1[i*2]   = lut[p0&3]
		l1[i*2+1] = lut[p1&3]
		l2[i*2]   = lut[(p0>>2)&3]
		l2[i*2+1] = lut[(p1>>2)&3]
	}

	base := strings.TrimSuffix(fpath, filepath.Ext(fpath))
	savePng(base+"_L1.png", l1)
	savePng(base+"_L2.png", l2)
	fmt.Println("Done.")
}

func doRepack(p1, p2, out string) {
	fmt.Printf("Building %s from %s & %s...\n", out, p1, p2)
	
	idx1 := loadAndMapByBrightness(p1)
	idx2 := loadAndMapByBrightness(p2)
	
	packed := make([]byte, PixSize)
	//PNG(0,1,2,3) -> TMR(3,2,1,0)
	lut := []uint8{3, 2, 1, 0}

	for i := 0; i < len(packed); i++ {
		v1a, v2a := lut[idx1[i*2]], lut[idx2[i*2]]
		valA := (v2a << 2) | v1a

		v1b, v2b := lut[idx1[i*2+1]], lut[idx2[i*2+1]]
		valB := (v2b << 2) | v1b

		packed[i] = (valA & 0xF) | ((valB & 0xF) << 4)
	}

	outData := make([]byte, TotalSize)
	copy(outData[0:], hex2bytes(HeadHex))
	copy(outData[PixOff:], packed)
	copy(outData[Clut1HeadOff:], hex2bytes(ClutHeadHex1))
	copy(outData[Clut1DataOff:], genClut1())
	copy(outData[Clut2HeadOff:], hex2bytes(ClutHeadHex2))
	copy(outData[Clut2DataOff:], genClut2())

	if err := os.WriteFile(out, outData, 0644); err != nil { log.Fatal(err) }
	fmt.Println("Success.")
}

func loadAndMapByBrightness(path string) []uint8 {
	f, err := os.Open(path)
	if err != nil { log.Fatal(err) }
	defer f.Close()
	
	img, err := png.Decode(f)
	if err != nil { log.Fatal(err) }
	
	if img.Bounds().Dx() != ImgW || img.Bounds().Dy() != ImgH {
		log.Fatalf("Size mismatch: %s", path)
	}

	type ColorInfo struct {
		C    color.NRGBA
		Luma float64
	}
	colorMap := make(map[color.NRGBA]float64)
	
	for y := 0; y < ImgH; y++ {
		for x := 0; x < ImgW; x++ {
			c := color.NRGBAModel.Convert(img.At(x, y)).(color.NRGBA)
			if c.A < 10 {
				c = color.NRGBA{0,0,0,0} 
			}
			if _, exists := colorMap[c]; !exists {
				luma := (float64(c.R)*0.299 + float64(c.G)*0.587 + float64(c.B)*0.114) * (float64(c.A)/255.0)
				colorMap[c] = luma
			}
		}
	}

	var sortedColors []ColorInfo
	for c, l := range colorMap {
		sortedColors = append(sortedColors, ColorInfo{c, l})
	}
	sort.Slice(sortedColors, func(i, j int) bool {
		return sortedColors[i].Luma < sortedColors[j].Luma
	})

	indexMap := make(map[color.NRGBA]uint8)
	maxRank := len(sortedColors) - 1
	if maxRank < 0 { maxRank = 0 }

	for i, info := range sortedColors {
		var mappedIdx uint8
		if len(sortedColors) <= 4 {
			mappedIdx = uint8(i)
			if len(sortedColors) == 2 && i == 1 { mappedIdx = 3 }
		} else {
			mappedIdx = uint8(float64(i) / float64(maxRank) * 3.0 + 0.5) 
		}
		indexMap[info.C] = mappedIdx
	}

	res := make([]uint8, ImgW*ImgH)
	for y := 0; y < ImgH; y++ {
		for x := 0; x < ImgW; x++ {
			c := color.NRGBAModel.Convert(img.At(x, y)).(color.NRGBA)
			if c.A < 10 { c = color.NRGBA{0,0,0,0} }
			
			if idx, ok := indexMap[c]; ok {
				res[y*ImgW+x] = idx
			} else {
				res[y*ImgW+x] = 0 
			}
		}
	}
	return res
}

func savePng(name string, idx []uint8) {
	img := image.NewPaletted(image.Rect(0, 0, ImgW, ImgH), PaletteView)
	copy(img.Pix, idx)
	f, _ := os.Create(name)
	defer f.Close()
	png.Encode(f, img)
}

func hex2bytes(h string) []byte {
	b, err := hex.DecodeString(h)
	if err != nil { log.Fatal("Hex decode error:", err) }
	return b
}

func toBytes(c color.RGBA) []byte { return []byte{c.R, c.G, c.B, c.A} }

func genClut1() []byte {
	buf := make([]byte, 0, 64)
	pat := []color.RGBA{Col0, Col1, Col2, Col3}
	for i := 0; i < 4; i++ {
		for _, c := range pat { buf = append(buf, toBytes(c)...) }
	}
	return buf
}

func genClut2() []byte {
	buf := make([]byte, 0, 64)
	cols := []color.RGBA{Col0, Col1, Col2, Col3}
	for _, c := range cols {
		for k := 0; k < 4; k++ { buf = append(buf, toBytes(c)...) }
	}
	return buf
}

func SwapNibbles(data []byte) []byte {
	return data
}