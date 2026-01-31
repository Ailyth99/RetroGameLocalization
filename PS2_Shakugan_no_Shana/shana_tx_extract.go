package main

import (
	"encoding/binary"
	"flag"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"io/fs"
	"log"
	"os"
	"path/filepath"
	"strings"
)

const (
	SecOff   = 0x1800 // 像素分段表偏移
	DefaultW = 640
	DefaultH = 448
)

func main() {
	var inPath string
	var outPath string
	flag.StringVar(&inPath, "i", "", "input .obj file or folder")
	flag.StringVar(&outPath, "o", "", "output .png (only for single file mode)")
	flag.Parse()

	if inPath == "" {
		printBanner()
		printUsage()
		waitForEnter()
		return
	}

	// 检查是文件还是文件夹
	info, err := os.Stat(inPath)
	if err != nil {
		log.Fatal(err)
	}

	if info.IsDir() {
		doBatch(inPath)
	} else {
		if outPath == "" {
			outPath = strings.TrimSuffix(inPath, filepath.Ext(inPath)) + ".png"
		}
		ripShana(inPath, outPath)
	}
}

func printBanner() {
	fmt.Println("=====================================")
	fmt.Println("PS2 Shakugan no Shana Tools")
	fmt.Println("Texture Extract - by aikika, 2026")
	fmt.Println("=====================================")
}

func printUsage() {
	fmt.Println("\n用法 / Usage:")
	fmt.Println("  单文件 / Single: shana_tx_extract -i <file.obj> [-o out.png]")
	fmt.Println("  批量 / Batch:    shana_tx_extract -i <folder>")
	fmt.Println("\n这是一个命令行工具，请在终端中使用。")
	fmt.Println("This is a command-line tool, please use it in terminal.")
}

func waitForEnter() {
	fmt.Println("\n按回车键退出... / Press Enter to exit...")
	fmt.Scanln()
}


func doBatch(root string) {
	fmt.Printf("Scanning folder: %s\n", root)
	count := 0

	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		
		if !d.IsDir() && strings.ToLower(filepath.Ext(path)) == ".obj" {
			dst := strings.TrimSuffix(path, filepath.Ext(path)) + ".png"
			fmt.Printf("[%d] Processing: %s\n", count+1, filepath.Base(path))
			
			
			success := ripShana(path, dst)
			if success {
				count++
			}
		}
		return nil
	})

	if err != nil {
		fmt.Printf("Error walking folder: %v\n", err)
	}
	fmt.Printf("\nBatch finished! Successfully converted %d files.\n", count)
}


func ripShana(src, dst string) bool {
	data, err := os.ReadFile(src)
	if err != nil {
		fmt.Printf("  Fail: %v\n", err)
		return false
	}
	if len(data) < 0x1000 { return false }

	//自动判定偏移位置 (secOff)
	secOff := 0x400
	isAllZero := true
	checkEnd := 0x450
	if len(data) < checkEnd { checkEnd = len(data) }
	for i := 0x400; i < checkEnd; i++ {
		if data[i] != 0 {
			isAllZero = false
			break
		}
	}
	if isAllZero {
		secOff = 0x1800
	}

	//调色板始终在0x00)
	rawPal := data[0:1024]
	u32Pal := make([]uint32, 256)
	for i := 0; i < 256; i++ {
		u32Pal[i] = binary.LittleEndian.Uint32(rawPal[i*4 : i*4+4])
	}
	u32Pal = UnswizzleCSM1_32(u32Pal) //应用CSM1swizlle
	goPal := make(color.Palette, 256)
	for i, v := range u32Pal {
		goPal[i] = decodeRGBA8888(v, "ps2")
	}

	//分段解压缩
	numSec := int(binary.LittleEndian.Uint32(data[secOff : secOff+4]))
	if numSec > 256 || numSec <= 0 { return false }

	var allPx []byte
	offTbl := secOff + 4
	for i := 0; i < numSec; i++ {
		pos := offTbl + (i * 4)
		if pos+4 > len(data) { break }
		
		pOff := int(binary.LittleEndian.Uint32(data[pos:pos+4])) + secOff
		var nextOff int
		if i == numSec-1 {
			nextOff = len(data)
		} else {
			nextOff = int(binary.LittleEndian.Uint32(data[pos+4:pos+8])) + secOff
		}
		
		zSize := nextOff - pOff
		if zSize <= 4 { continue }

		decSize := int(binary.LittleEndian.Uint32(data[pOff : pOff+4]))
		if decSize > 1024*1024*16 { continue } 
		
		zData := data[pOff+4 : pOff+zSize]
		decData := DecompressLZSS(zData, decSize, 0xFEE)
		allPx = append(allPx, decData...)
	}

	if len(allPx) == 0 { return false }

	//分辨率判定逻辑
	w, h := 0, 0
	totalPx := len(allPx)

	if secOff == 0x400 {
		//不知道具体逻辑，直接硬编码这几种，反正种类少
		switch totalPx {
		case 98304:
			w, h = 512, 192
		case 344064:
			w, h = 768, 448
		default:
			w = 256
			h = totalPx / 256
		}
	} else {
		//0x1800类型优先读取MAP标记
		w, h = 640, 448 
		if len(data) > 0x420 && string(data[0x400:0x403]) == "MAP" {
			w = int(binary.LittleEndian.Uint16(data[0x41C : 0x41E]))
			h = int(binary.LittleEndian.Uint16(data[0x41E : 0x420]))
		}
		if totalPx < w*h {
			h = totalPx / w
		}
	}

	if w <= 0 || h <= 0 { return false }
	img := image.NewPaletted(image.Rect(0, 0, w, h), goPal)
	if len(allPx) >= w*h {
		copy(img.Pix, allPx[:w*h])
	} else {
		copy(img.Pix, allPx)
	}

	fOut, _ := os.Create(dst)
	defer fOut.Close()
	png.Encode(fOut, img)
	
	fmt.Printf("  [Mode:%X] %dx%d (%d bytes) -> %s\n", secOff, w, h, totalPx, filepath.Base(dst))
	return true
}