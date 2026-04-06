package main

import (
	"bytes"
	"flag"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"os"
)


const (
	TileW         = 24
	TileH         = 24
	BPP           = 2
	BytesPerRow   = (TileW * BPP) / 8 
	BytesPerChar  = TileH * BytesPerRow
	CharsPerRowImg = 32 
)

func main() {
	
	isExport := flag.Bool("e", false, "导出模式 (BIN -> PNG)")
	isImport := flag.Bool("i", false, "导入模式 (PNG -> BIN)")

	flag.Parse()
	args := flag.Args()

	
	if (*isExport == *isImport) || len(args) < 2 {
		printBanner()
		printUsage()
		waitForEnter()
		return
	}

	srcFile := args[0]
	dstFile := args[1]

	if *isExport {
		if err := exportBinToPng(srcFile, dstFile); err != nil {
			fmt.Printf("❌ 导出失败 / Export failed: %v\n", err)
			os.Exit(1)
		}
	} else {
		if err := importPngToBin(srcFile, dstFile); err != nil {
			fmt.Printf("❌ 导入失败 / Import failed: %v\n", err)
			os.Exit(1)
		}
	}
}

func printBanner() {
	fmt.Println("=====================================")
	fmt.Println("PS2 Shakugan no Shana Tools")
	fmt.Println("Font Tool - by aikika, 2026")
	fmt.Println("=====================================")
}

func printUsage() {
	fmt.Println("\n用法 / Usage:")
	fmt.Println("  导出 / Export: shana_font -e <源文件.bin> <输出文件.png>")
	fmt.Println("                 shana_font -e <source.bin> <output.png>")
	fmt.Println("  导入 / Import: shana_font -i <源文件.png> <输出文件.bin>")
	fmt.Println("                 shana_font -i <source.png> <output.bin>")
	fmt.Println("\n示例 / Example:")
	fmt.Println("  shana_font -e font.bin font.png")
	fmt.Println("  shana_font -i font.png new_font.bin")
	fmt.Println("\n这是一个命令行工具，请在终端中使用。")
	fmt.Println("This is a command-line tool, please use it in terminal.")
}

func waitForEnter() {
	fmt.Println("\n按回车键退出... / Press Enter to exit...")
	fmt.Scanln()
}


func exportBinToPng(inputFile, outputFile string) error {
	fmt.Printf("▶ 模式: 导出\n  源: %s\n  至: %s\n", inputFile, outputFile)
	
	data, err := os.ReadFile(inputFile)
	if err != nil { return err }

	numChars := len(data) / BytesPerChar
	fmt.Printf("  包含字符数: %d\n", numChars)

	
	cols := CharsPerRowImg
	rows := (numChars + cols - 1) / cols
	img := image.NewGray(image.Rect(0, 0, cols*TileW, rows*TileH))

	//全白背景
	for i := range img.Pix { img.Pix[i] = 255 }

	for i := 0; i < numChars; i++ {
		charData := data[i*BytesPerChar : (i+1)*BytesPerChar]
		tileX := (i % cols) * TileW
		tileY := (i / cols) * TileH

		for r := 0; r < TileH; r++ {
			rowBytes := charData[r*BytesPerRow : (r+1)*BytesPerRow]
			
			pixelIdx := 0
			for _, b := range rowBytes {
				for bit := 0; bit < 8; bit += 2 {
					val := (b >> bit) & 0x03 //依次取 bit 0-1, 2-3, 4-5, 6-7
					
					//颜色映射: 0->白(255), 3->黑(0)
					gray := uint8(255 - (val * 85))
					img.SetGray(tileX+pixelIdx, tileY+r, color.Gray{Y: gray})
					pixelIdx++
				}
			}
		}
	}

	f, err := os.Create(outputFile)
	if err != nil { return err }
	defer f.Close()
	
	fmt.Println("✅ 完成。")
	return png.Encode(f, img)
}


func importPngToBin(inputFile, outputFile string) error {
	fmt.Printf("▶ 模式: 导入\n  源: %s\n  至: %s\n", inputFile, outputFile)

	f, err := os.Open(inputFile)
	if err != nil { return err }
	defer f.Close()

	img, _, err := image.Decode(f)
	if err != nil { return err }

	bounds := img.Bounds()
	if bounds.Dx()%TileW != 0 || bounds.Dy()%TileH != 0 {
		return fmt.Errorf("图片尺寸 %dx%d 不合规 (必须是24的倍数)", bounds.Dx(), bounds.Dy())
	}

	cols := bounds.Dx() / TileW
	rows := bounds.Dy() / TileH
	numChars := cols * rows
	fmt.Printf("  检测到字符块: %d\n", numChars)

	outBuf := new(bytes.Buffer)

	for i := 0; i < numChars; i++ {
		tileX := (i % cols) * TileW
		tileY := (i / cols) * TileH

		for r := 0; r < TileH; r++ {
			var rowByte byte
			var rowBytes []byte
			
			for x := 0; x < TileW; x++ {
				c := color.GrayModel.Convert(img.At(tileX+x, tileY+r)).(color.Gray)
				
				
				var val byte
				if c.Y >= 212 { val = 0 } else if c.Y >= 128 { val = 1 } else if c.Y >= 42 { val = 2 } else { val = 3 }

				
				shift := (x % 4) * 2
				rowByte |= (val << shift)

				
				if (x+1)%4 == 0 {
					rowBytes = append(rowBytes, rowByte)
					rowByte = 0
				}
			}
			outBuf.Write(rowBytes)
		}
	}

	fmt.Printf("✅ 完成 (文件大小: %d 字节)\n", outBuf.Len())
	return os.WriteFile(outputFile, outBuf.Bytes(), 0644)
}