package main

import (
	"bytes"
	"encoding/binary"
	"flag"
	"fmt"
	"image"
	"image/color"
	"image/draw"
	"image/png"
	"log"
	"os"
)

const (
	W           = 512
	PartH       = 256
	PartRaw     = 65536 //512 * 256 * 0.5 (4bpp)  写死在这里
	DictOff     = 0xFEE
	FirstBlkLim = 0x11800 //第一个资源块的结束边界，扇区到这里
)

var grayPal color.Palette

func init() {
	grayPal = make(color.Palette, 16)
	for i := 0; i < 16; i++ {
		v := uint8(i * 17)
		grayPal[i] = color.RGBA{v, v, v, 255}
	}
}

func main() {
	exp := flag.String("e", "", "Export first image: -e pr.bin")
	imp := flag.String("i", "", "Inject first image: -i pr.png")
	orig := flag.String("ref", "pr.bin", "Original binary file (for injection)")
	flag.Parse()

	if *exp != "" {
		doExp(*exp)
	} else if *imp != "" {
		doImp(*imp, *orig)
	} else {
		printBanner()
		printUsage()
		waitForEnter()
	}
}

func printBanner() {
	fmt.Println("=====================================")
	fmt.Println("PS2 Shakugan no Shana Tools")
	fmt.Println("PR Tool - by aikika, 2026")
	fmt.Println("=====================================")
}

func printUsage() {
	fmt.Println("\n用法 / Usage:")
	fmt.Println("  导出 / Export: pr_tool -e pr.bin")
	fmt.Println("  注入 / Inject: pr_tool -i pr.png -ref pr.bin")
	fmt.Println("\n这是一个命令行工具，请在终端中使用。")
	fmt.Println("This is a command-line tool, please use it in terminal.")
}

func waitForEnter() {
	fmt.Println("\n按回车键退出... / Press Enter to exit...")
	fmt.Scanln()
}


func doExp(path string) {
	data, err := os.ReadFile(path)
	if err != nil {
		log.Fatal(err)
	}

	count := int(binary.LittleEndian.Uint32(data[0:4]))
	offs := make([]uint32, count+1)
	for i := 0; i <= count; i++ {
		offs[i] = binary.LittleEndian.Uint32(data[4+i*4 : 8+i*4])
	}

	allPx := make([]byte, 0)
	for i := 0; i < count; i++ {
		chunk := data[offs[i]:offs[i+1]]
		tSz := int(binary.LittleEndian.Uint32(chunk[0:4]))
		dec := DecompressLZSS(chunk[4:], tSz, DictOff)

		// 4bpp -> 8bpp
		for _, b := range dec {
			allPx = append(allPx, b&0x0F, b>>4)
		}
	}

	h := len(allPx) / W
	img := image.NewPaletted(image.Rect(0, 0, W, h), grayPal)
	img.Pix = allPx

	f, _ := os.Create("pr.png")
	defer f.Close()
	png.Encode(f, img)
	fmt.Printf("Success: pr.png (%dx%d)\n", W, h)
}

//只修改第一个块，保留后续数据
func doImp(pngPath, binPath string) {
	origBin, err := os.ReadFile(binPath)
	if err != nil {
		log.Fatal("Cannot read original bin:", err)
	}
	if len(origBin) < FirstBlkLim {
		log.Fatal("Original binary is too small!")
	}

	
	fIn, err := os.Open(pngPath)
	if err != nil {
		log.Fatal(err)
	}
	defer fIn.Close()

	src, _ := png.Decode(fIn)
	img := image.NewPaletted(src.Bounds(), grayPal)
	draw.Draw(img, img.Bounds(), src, image.Point{}, draw.Src)

	numParts := img.Bounds().Dy() / PartH
	allDec := make([][]byte, numParts)

	
	for p := 0; p < numParts; p++ {
		raw := make([]byte, PartRaw)
		for i := 0; i < PartRaw; i++ {
			p1 := img.Pix[p*W*PartH+i*2] & 0x0F
			p2 := img.Pix[p*W*PartH+i*2+1] & 0x0F
			raw[i] = p1 | (p2 << 4)
		}
		allDec[p] = raw
	}

	
	newBlock := new(bytes.Buffer)
	
	
	binary.Write(newBlock, binary.LittleEndian, uint32(numParts))

	
	tbl := make([]uint32, numParts+1)
	body := new(bytes.Buffer)
	
	baseOff := uint32(4 + (numParts+1)*4) 
	
	//压缩数据
	for i, raw := range allDec {
		tbl[i] = baseOff + uint32(body.Len())
		zData := CompressLZSS(raw, DictOff)
		binary.Write(body, binary.LittleEndian, uint32(len(raw))) 
		body.Write(zData)
	}
	tbl[numParts] = baseOff + uint32(body.Len()) 

	
	for _, v := range tbl {
		binary.Write(newBlock, binary.LittleEndian, v)
	}
	
	newBlock.Write(body.Bytes())

	
	newDataSize := newBlock.Len()
	fmt.Printf("New block size: 0x%X (Limit: 0x%X)\n", newDataSize, FirstBlkLim)

	if newDataSize > FirstBlkLim {
		log.Fatalf("Error: Compressed data too big! Exceeds first block limit by %d bytes.", newDataSize-FirstBlkLim)
	}

	
	finalOut := new(bytes.Buffer)
	finalOut.Write(newBlock.Bytes())
	
	//填充00直到0x11800，无视校验值
	padding := make([]byte, FirstBlkLim-newDataSize)
	finalOut.Write(padding)

	finalOut.Write(origBin[FirstBlkLim:])

	os.WriteFile("pr_new.bin", finalOut.Bytes(), 0644)
	fmt.Println("Success: pr_new.bin created.")
}



func DecompressLZSS(data []byte, decompSize int, dicOff int) []byte {
	dict := make([]byte, 4096)
	dec := make([]byte, decompSize)
	inOff, outOff := 0, 0
	var mask uint8 = 0
	var cb uint8 = 0

	for outOff < decompSize {
		if mask == 0 {
			if inOff >= len(data) { break }
			cb = data[inOff]
			inOff++
			mask = 1
		}
		if (cb & mask) != 0 {
			if inOff >= len(data) || outOff >= decompSize { break }
			val := data[inOff]
			dec[outOff] = val
			dict[dicOff] = val
			outOff++
			inOff++
			dicOff = (dicOff + 1) & 0xFFF
		} else {
			if inOff+1 >= len(data) { break }
			b1, b2 := data[inOff], data[inOff+1]
			inOff += 2
			length := int(b2&0x0F) + 3
			loc := int(b1) | (int(b2&0xF0) << 4)
			for b := 0; b < length; b++ {
				if outOff >= decompSize { break }
				val := dict[(loc+b)&0xFFF]
				dec[outOff] = val
				dict[dicOff] = val
				outOff++
				dicOff = (dicOff + 1) & 0xFFF
			}
		}
		mask <<= 1
	}
	return dec
}

func CompressLZSS(input []byte, dicOff int) []byte {
	inputLen := len(input)
	if inputLen == 0 { return nil }

	var out []byte
	dict := make([]byte, 4096)
	inPos := 0
	writePos := dicOff

	for inPos < inputLen {
		flagPos := len(out)
		out = append(out, 0)
		var flags uint8 = 0

		for i := 0; i < 8; i++ {
			if inPos >= inputLen { break }

			bestLen, bestDist := 0, 0
			maxMatch := 18
			if inputLen-inPos < maxMatch { maxMatch = inputLen - inPos }

			if maxMatch >= 3 {
				for d := 0; d < 4096; d++ {
					currLen := 0
					for currLen < maxMatch {
						if input[inPos+currLen] != dict[(d+currLen)&0xFFF] {
							break
						}
						currLen++
					}
					if currLen >= bestLen {
						bestLen = currLen
						bestDist = d
						if bestLen == maxMatch { break }
					}
				}
			}

			if bestLen >= 3 {
				b1 := uint8(bestDist & 0xFF)
				b2 := uint8((bestDist>>4)&0xF0) | uint8(bestLen-3)
				out = append(out, b1, b2)
				for j := 0; j < bestLen; j++ {
					dict[writePos] = input[inPos]
					writePos = (writePos + 1) & 0xFFF
					inPos++
				}
			} else {
				flags |= (1 << i)
				val := input[inPos]
				out = append(out, val)
				dict[writePos] = val
				writePos = (writePos + 1) & 0xFFF
				inPos++
			}
		}
		out[flagPos] = flags
	}
	return out
}