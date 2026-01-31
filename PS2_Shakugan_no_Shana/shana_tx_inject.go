package main

import (
	"bytes"
	"encoding/binary"
	"flag"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"log"
	"os"
)

func main() {
	var pngPath, refPath, outPath string
	var colorCount int
	flag.StringVar(&pngPath, "i", "", "modified png file")
	flag.StringVar(&refPath, "ref", "", "original .obj template")
	flag.StringVar(&outPath, "o", "", "output .obj file")
	flag.IntVar(&colorCount, "c", 0, "colors (16-256). 0 for auto-search.")
	flag.Parse()

	if pngPath == "" || refPath == "" || outPath == "" {
		printBanner()
		printUsage()
		waitForEnter()
		return
	}

	refData, err := os.ReadFile(refPath)
	if err != nil {
		log.Fatal("Read Ref Error:", err)
	}
	targetLimit := len(refData)

	if colorCount > 0 {
		fmt.Printf("Manual Mode: Testing %d colors...\n", colorCount)
		_, effSize := packShana(pngPath, refData, outPath, colorCount, true)
		printResult(effSize, targetLimit)
	} else {
		fmt.Println("Oracle Mode: Searching for the optimal color count...")
		low, high := 16, 256
		bestC := 16
		finalEffSize := 0

		for low <= high {
			mid := (low + high) / 2
			fmt.Printf("  Testing %d colors... ", mid)
			isValid, effSize := packShana(pngPath, refData, outPath, mid, false)
			
			if isValid && effSize <= targetLimit {
				fmt.Printf("SUCCESS (%d bytes)\n", effSize)
				bestC = mid
				finalEffSize = effSize
				low = mid + 1
			} else {
				fmt.Printf("FAILED (Too large)\n")
				high = mid - 1
			}
		}

		fmt.Printf("\n Optimal color count is %d\n", bestC)
		packShana(pngPath, refData, outPath, bestC, true)
		printResult(finalEffSize, targetLimit)
	}
}

func printBanner() {
	fmt.Println("=====================================")
	fmt.Println("PS2 Shakugan no Shana Tools")
	fmt.Println("Texture Inject - by aikika, 2026")
	fmt.Println("=====================================")
}

func printUsage() {
	fmt.Println("\n用法 / Usage:")
	fmt.Println("  shana_tx_inject -i mod.png -ref orig.obj -o new.obj [-c 256]")
	fmt.Println("\n这是一个命令行工具，请在终端中使用。")
	fmt.Println("This is a command-line tool, please use it in terminal.")
}

func waitForEnter() {
	fmt.Println("\n按回车键退出... / Press Enter to exit...")
	fmt.Scanln()
}

func packShana(pngPath string, refData []byte, outPath string, nColors int, verbose bool) (bool, int) {
	
	secOff := 0x400
	isAllZero := true
	checkEnd := 0x450
	if len(refData) < checkEnd { checkEnd = len(refData) }
	for i := 0x400; i < checkEnd; i++ {
		if refData[i] != 0 {
			isAllZero = false
			break
		}
	}
	if isAllZero {
		secOff = 0x1800
	}

	//量化与解码PNG
	pngRaw, err := os.ReadFile(pngPath)
	if err != nil { return false, 999999 }
	qData, err := Quantize(pngRaw, nColors)
	if err != nil { return false, 999999 }
	img, err := png.Decode(bytes.NewReader(qData))
	if err != nil { return false, 999999 }
	palImg := img.(*image.Paletted)

	// RGBA8888 + CSM1
	u32Pal := make([]uint32, 256)
	for i := 0; i < 256; i++ {
		if i < len(palImg.Palette) {
			c := color.NRGBAModel.Convert(palImg.Palette[i]).(color.NRGBA)
			u32Pal[i] = encodeRGBA8888(c, true)
		} else {
			u32Pal[i] = 0
		}
	}
	u32Pal = SwizzleCSM1_32(u32Pal)
	palBuf := new(bytes.Buffer)
	for _, v := range u32Pal {
		binary.Write(palBuf, binary.LittleEndian, v)
	}

	
	numSections := int(binary.LittleEndian.Uint32(refData[secOff : secOff+4]))
	var compressedChunks [][]byte
	pixelPtr := 0

	for i := 0; i < numSections; i++ {

		tblPos := secOff + 4 + (i * 4)
		relOff := int(binary.LittleEndian.Uint32(refData[tblPos : tblPos+4]))
		chunkPos := secOff + relOff
		expectedSize := int(binary.LittleEndian.Uint32(refData[chunkPos : chunkPos+4]))

		if pixelPtr+expectedSize > len(palImg.Pix) {
			return false, 999999
		}

		rawChunk := palImg.Pix[pixelPtr : pixelPtr+expectedSize]
		pixelPtr += expectedSize

		//压缩
		zData := CompressLZSS(rawChunk, 0xFEE)
		
		cBuf := new(bytes.Buffer)
		binary.Write(cBuf, binary.LittleEndian, uint32(expectedSize))
		cBuf.Write(zData)
		
		//4字节对齐
		for cBuf.Len()%4 != 0 {
			cBuf.WriteByte(0)
		}
		compressedChunks = append(compressedChunks, cBuf.Bytes())
	}

	//重组文件
	final := new(bytes.Buffer)
	//拷贝头部替换调色板
	header := make([]byte, secOff)
	copy(header, refData[:secOff])
	copy(header[0:1024], palBuf.Bytes())
	final.Write(header)

	//写入索引表
	binary.Write(final, binary.LittleEndian, uint32(numSections))
	currRelOff := uint32(4 + (numSections * 4))
	for _, c := range compressedChunks {
		binary.Write(final, binary.LittleEndian, currRelOff)
		currRelOff += uint32(len(c))
	}

	//写入压缩块
	for _, c := range compressedChunks {
		final.Write(c)
	}

	effSize := final.Len()

	if verbose {
		//填充至原始大小
		for final.Len() < len(refData) {
			final.WriteByte(0)
		}
		os.WriteFile(outPath, final.Bytes(), 0644)
	}

	return effSize <= len(refData), effSize
}

func printResult(effSize, limit int) {
	if effSize <= limit {
		fmt.Printf("\n✅ COMPRESSION SAFE: %d / %d bytes (%.2f%% used)\n", effSize, limit, float64(effSize)/float64(limit)*100)
	} else {
		fmt.Printf("\n❌ DANGER: %d / %d bytes (EXCEEDED!)\n", effSize, limit)
	}
}