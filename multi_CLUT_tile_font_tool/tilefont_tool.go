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
	"strconv"
	"strings"
)

var (
	inputPath   string
	img1Path    string
	img2Path    string
	outPath     string
	offsetStr   string
	tileW       int
	tileH       int
	tilesPerRow int
)


//一般4BPP的tile字库，别管他CLUT具体包含什么颜色，只要按照四种基础颜色就行，底色+两种过渡色+字色
//这里是用纯黑当底色A，纯白为字色D，中间用两种灰色作为过渡色B/C。
//核心的原理是：四种颜色，在4BPP CLUT中，按照ABCDABCDABCDABCD 以及 AAAABBBBCCCCDDD 这两种排列来处理。
//当然有些游戏不一定使用，可能它CLUT颜色不一定是从深到浅或从浅到深，可能它是浅灰-黑-白-深灰，但是CLUT的颜色排列一定遵守上面的组合。
//还有这个支持线性排列的像素数据，万一遇到那种需要高低位互换的，就不能直接用这个，需要改一些。


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

func init() {
	flag.StringVar(&inputPath, "i", "", "Input binary file (.bin)")
	flag.StringVar(&offsetStr, "o", "0", "Start offset (Decimal or Hex 0x...)")
	flag.IntVar(&tileW, "tw", 24, "Tile Width")
	flag.IntVar(&tileH, "th", 24, "Tile Height")
	flag.IntVar(&tilesPerRow, "cols", 16, "Tiles per row in exported PNG")

	flag.StringVar(&img1Path, "img1", "", "Repack: Layer 1 PNG")
	flag.StringVar(&img2Path, "img2", "", "Repack: Layer 2 PNG")
	flag.StringVar(&outPath, "out", "", "Repack: Output filename")
}

func main() {
	flag.Parse()

	if inputPath == "" {
		printUsage()
		return
	}

	offset := parseOffset(offsetStr)

	if img1Path != "" && img2Path != "" {
		if outPath == "" {
			outPath = inputPath + ".new"
		}
		doRepack(inputPath, img1Path, img2Path, outPath, offset)
	} else {
		doExtract(inputPath, offset)
	}
}

func printUsage() {
	fmt.Println("==============================================================================")
	fmt.Println("MULTI-CLUT TileFont Tool - PS2 Tiled Linear 4bpp multi-CLUT Font TOOL - aikika")
	fmt.Println("==============================================================================")
	fmt.Println("\n[Options]")
	fmt.Println("  -i    <file>   Input binary file (Required)")
	fmt.Println("  -o    <offset> Start offset (Default: 0)")
	fmt.Println("  -tw   <int>    Tile Width (Default: 24)")
	fmt.Println("  -th   <int>    Tile Height (Default: 24)")
	fmt.Println("  -cols <int>    Columns in PNG (Default: 16)")
	fmt.Println("\n[Repack Only]")
	fmt.Println("  -img1 <file>   Modified Layer 1 PNG")
	fmt.Println("  -img2 <file>   Modified Layer 2 PNG")
	fmt.Println("  -out  <file>   Output filename")

	fmt.Println("\n----------------------------------------------------------")
	fmt.Println("EXAMPLES:")
	fmt.Println("----------------------------------------------------------")
	fmt.Println("1. Extract (24x24 tiles, 16 per row):")
	fmt.Println("   tilefont_tool -i font.bin -o 0x800 -tw 24 -th 24")
	fmt.Println("\n2. Extract (16x16 tiles, 32 per row):")
	fmt.Println("   tilefont_tool -i icon.bin -o 32768 -tw 16 -th 16 -cols 32")
	fmt.Println("\n3. Repack (Inject back to bin):")
	fmt.Println("   tilefont_tool -i font.bin -o 0x800 -tw 24 -th 24 -img1 layer1.png -img2 layer2.png -out font_new.bin")
	fmt.Println("----------------------------------------------------------")
}

func parseOffset(s string) int64 {
	s = strings.TrimSpace(s)
	base := 10
	if strings.HasPrefix(s, "0x") || strings.HasPrefix(s, "0X") {
		s = s[2:]
		base = 16
	}
	val, err := strconv.ParseInt(s, base, 64)
	if err != nil {
		log.Fatal("Invalid offset format:", s)
	}
	return val
}

//--------------------------------------------------------
//导出字库图像，分别按照像素+调色板1，+调色板2，输出两张图
//------------------------------------------------------

func doExtract(fpath string, offset int64) {
	tileBytes := (tileW * tileH) / 2
	f, err := os.Open(fpath)
	if err != nil {
		log.Fatal(err)
	}
	defer f.Close()

	info, _ := f.Stat()
	dataSize := info.Size() - offset
	if dataSize <= 0 {
		log.Fatal("Offset exceeds file size")
	}

	numTiles := int(dataSize / int64(tileBytes))
	fmt.Printf("[Extract] Tiles Found: %d | TileSize: %dx%d\n", numTiles, tileW, tileH)

	f.Seek(offset, 0)
	rawData := make([]byte, numTiles*tileBytes)
	f.Read(rawData)

	imgCols := tilesPerRow
	imgRows := (numTiles + imgCols - 1) / imgCols
	imgW, imgH := imgCols*tileW, imgRows*tileH

	img1 := image.NewPaletted(image.Rect(0, 0, imgW, imgH), ExportPalette)
	img2 := image.NewPaletted(image.Rect(0, 0, imgW, imgH), ExportPalette)

	for i := 0; i < numTiles; i++ {
		tileData := rawData[i*tileBytes : (i+1)*tileBytes]
		tileX := (i % imgCols) * tileW
		tileY := (i / imgCols) * tileH

		for ty := 0; ty < tileH; ty++ {
			rowBytes := tileW / 2
			for txByte := 0; txByte < rowBytes; txByte++ {
				b := tileData[ty*rowBytes+txByte]
				p0, p1 := b&0x0F, (b>>4)&0x0F

				absX, absY := tileX+txByte*2, tileY+ty

				// Layer 1 (Low 2 bits)
				img1.SetColorIndex(absX, absY, p0&0x3)
				img1.SetColorIndex(absX+1, absY, p1&0x3)

				// Layer 2 (High 2 bits)
				img2.SetColorIndex(absX, absY, (p0>>2)&0x3)
				img2.SetColorIndex(absX+1, absY, (p1>>2)&0x3)
			}
		}
	}

	baseName := strings.TrimSuffix(fpath, filepath.Ext(fpath))
	savePng(baseName+"_layer1.png", img1)
	savePng(baseName+"_layer2.png", img2)
	fmt.Println("Done.")
}







//----------------
//重建tile字库文件
//----------------




func doRepack(origPath, p1Path, p2Path, outPath string, offset int64) {
	fmt.Printf("[Repack] Merging PNGs...\n")

	img1 := loadPng(p1Path)
	img2 := loadPng(p2Path)

	width := img1.Bounds().Dx()
	height := img1.Bounds().Dy()

	if img2.Bounds().Dx() != width || img2.Bounds().Dy() != height {
		log.Fatal("Dimension mismatch between Layer 1 and Layer 2 images")
	}

	cols := tilesPerRow
	rows := height / tileH
	totalTiles := rows * cols
	tileBytes := (tileW * tileH) / 2

	repackData := make([]byte, 0, totalTiles*tileBytes)

	//处理tile
	tilesProcessed := 0
	for i := 0; i < totalTiles; i++ {
		tileX := (i % cols) * tileW
		tileY := (i / cols) * tileH

		currentTileData := make([]byte, tileBytes)

		for ty := 0; ty < tileH; ty++ {
			for txByte := 0; txByte < tileW/2; txByte++ {
				x0, y0 := tileX+txByte*2, tileY+ty
				x1, y1 := tileX+txByte*2+1, tileY+ty

				//获取最近的索引
				idx1_p0 := findColorIdx(img1.At(x0, y0))
				idx2_p0 := findColorIdx(img2.At(x0, y0))
				idx1_p1 := findColorIdx(img1.At(x1, y1))
				idx2_p1 := findColorIdx(img2.At(x1, y1))

				//合并
				val_p0 := (idx2_p0 << 2) | idx1_p0
				val_p1 := (idx2_p1 << 2) | idx1_p1

				//把两个像素打包进一个字节里面 (低位优先)
				b := (val_p0 & 0x0F) | ((val_p1 & 0x0F) << 4)
				currentTileData[ty*(tileW/2)+txByte] = b
			}
		}
		repackData = append(repackData, currentTileData...)
		tilesProcessed++
	}

	origBytes, err := os.ReadFile(origPath)
	if err != nil {
		log.Fatal(err)
	}

	endOffset := int(offset) + len(repackData)
	var finalData []byte

	if endOffset > len(origBytes) {
		fmt.Printf("Warning: New data larger than original file. Truncating to fit.\n")
		validLen := len(origBytes) - int(offset)
		if validLen < 0 {
			log.Fatal("Offset out of bounds")
		}
		repackData = repackData[:validLen]
	}

	finalData = make([]byte, len(origBytes))
	copy(finalData, origBytes)
	copy(finalData[offset:], repackData)

	if err := os.WriteFile(outPath, finalData, 0644); err != nil {
		log.Fatal(err)
	}

	fmt.Printf("Success! Processed %d tiles. Saved to %s\n", tilesProcessed, outPath)
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

	if nc.A < 10 {
		return 0
	}

	minDist := math.MaxFloat64
	bestIdx := 0

	for i, sc := range StandardColors {
		dr := int(nc.R) - int(sc.R)
		dg := int(nc.G) - int(sc.G)
		db := int(nc.B) - int(sc.B)
		dist := float64(dr*dr + dg*dg + db*db)
		if dist < minDist {
			minDist = dist
			bestIdx = i
		}
	}
	return uint8(bestIdx)
}