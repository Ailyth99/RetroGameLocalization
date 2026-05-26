package main

import (
	"encoding/binary"
	"encoding/json"
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

const MagicGBIX = "GBIX"

type GBIXInfo struct {
	Index  int    `json:"index"`
	Offset int64  `json:"offset"`
	Size   int    `json:"size"`
	Width  int    `json:"width"`
	Height int    `json:"height"`
	Mode   string `json:"mode"`
	Flag18 uint16 `json:"flag18"`
	Flag14 uint16 `json:"flag14"`
}

var scanMode bool
var extractOffset int64
var outDir string

var injectOffset int64
var inPng string

func init() {
	flag.BoolVar(&scanMode, "scan", false, "Scan file for GBIX and output JSON array")
	flag.Int64Var(&extractOffset, "extract", -1, "Extract GBIX at given offset to PNG (must specify file)")
	flag.StringVar(&outDir, "outdir", "", "Output directory for extract mode (default is same as input)")
	flag.Int64Var(&injectOffset, "inject", -1, "Inject PNG to GBIX at given offset")
	flag.StringVar(&inPng, "png", "", "Input PNG file for injection")
}

func main() {
	flag.Parse()
	args := flag.Args()

	if len(args) < 1 {
		fmt.Println("SVR (GBIX) Advanced Ripper")
		fmt.Println("Usage: svr_ripper [flags] <file_or_folder>")
		flag.PrintDefaults()
		return
	}

	inputPath := args[0]
	info, err := os.Stat(inputPath)
	if err != nil {
		log.Fatal(err)
	}

	if scanMode {
		if info.IsDir() {
			log.Fatal("Scan mode only works on files, not directories.")
		}
		scanFile(inputPath)
		return
	}

	if injectOffset >= 0 {
		if info.IsDir() {
			log.Fatal("Inject mode only works on files, not directories.")
		}
		if inPng == "" {
			log.Fatal("Please provide a PNG file using -png for injection.")
		}
		injectGBIX(inputPath, inPng, injectOffset)
		return
	}

	if extractOffset >= 0 {
		if info.IsDir() {
			log.Fatal("Extract mode only works on files, not directories.")
		}
		od := outDir
		if od == "" {
			od = filepath.Dir(inputPath)
		}
		
		data, err := os.ReadFile(inputPath)
		if err != nil {
			log.Fatal(err)
		}
		
		info, ok := parseHeader(data, int(extractOffset))
		if !ok {
			log.Fatal("Failed to parse GBIX at given offset.")
		}
		
		outName := fmt.Sprintf("%s_offset_%d.png", strings.TrimSuffix(filepath.Base(inputPath), filepath.Ext(inputPath)), extractOffset)
		outPath := filepath.Join(od, outName)
		
		if decodeGBIX(data[info.Offset:info.Offset+int64(info.Size)], outPath) {
			// output the final path to stdout
			fmt.Println(outPath)
		} else {
			log.Fatal("Failed to decode GBIX.")
		}
		return
	}

	// Default behavior (Bulk or Single original processing)
	if info.IsDir() {
		count := 0
		filepath.WalkDir(inputPath, func(path string, d fs.DirEntry, err error) error {
			if err != nil || d.IsDir() {
				return nil
			}
			outDir := filepath.Dir(path)
			data, err := os.ReadFile(path)
			if err != nil { return nil }
			
			hInfo, ok := parseHeader(data, 0)
			if ok {
				outPath := filepath.Join(outDir, strings.TrimSuffix(filepath.Base(path), filepath.Ext(path))+".png")
				if decodeGBIX(data[hInfo.Offset:hInfo.Offset+int64(hInfo.Size)], outPath) {
					fmt.Printf("[0x%04X, 0x%04X] %s: %s (%dx%d)\n", hInfo.Flag18, hInfo.Flag14, hInfo.Mode, filepath.Base(path), hInfo.Width, hInfo.Height)
					count++
				}
			}
			return nil
		})
		fmt.Printf("Done! Successfully converted %d images.\n", count)
	} else {
		outDir := filepath.Dir(inputPath)
		data, err := os.ReadFile(inputPath)
		if err != nil { log.Fatal(err) }
		hInfo, ok := parseHeader(data, 0)
		if ok {
			outPath := filepath.Join(outDir, strings.TrimSuffix(filepath.Base(inputPath), filepath.Ext(inputPath))+".png")
			if decodeGBIX(data[hInfo.Offset:hInfo.Offset+int64(hInfo.Size)], outPath) {
				fmt.Printf("[0x%04X, 0x%04X] %s: %s (%dx%d)\n", hInfo.Flag18, hInfo.Flag14, hInfo.Mode, filepath.Base(inputPath), hInfo.Width, hInfo.Height)
				fmt.Println("Done!")
			}
		} else {
			fmt.Println("Not a valid SVR/GBIX file or parse error.")
		}
	}
}

func scanFile(filepath string) {
	data, err := os.ReadFile(filepath)
	if err != nil {
		log.Fatal(err)
	}

	var results []GBIXInfo
	idx := 1

	for i := 0; i < len(data)-0x20; i++ {
		if string(data[i:i+4]) == MagicGBIX {
			info, ok := parseHeader(data, i)
			if ok {
				info.Index = idx
				idx++
				results = append(results, info)
				i += info.Size - 1 // Skip the block
			}
		}
	}

	jsonBytes, err := json.Marshal(results)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(string(jsonBytes))
}

func parseHeader(data []byte, offset int) (GBIXInfo, bool) {
	var info GBIXInfo

	if offset+0x20 > len(data) {
		return info, false
	}
	if string(data[offset:offset+4]) != MagicGBIX {
		return info, false
	}

	w := int(binary.LittleEndian.Uint16(data[offset+0x1C : offset+0x1E]))
	h := int(binary.LittleEndian.Uint16(data[offset+0x1E : offset+0x20]))

	if w == 0 || h == 0 || w > 4096 || h > 4096 {
		return info, false
	}

	flag18 := binary.LittleEndian.Uint16(data[offset+0x18 : offset+0x1A])
	flag14 := binary.LittleEndian.Uint16(data[offset+0x14 : offset+0x16])
	pvrtSize := int(binary.LittleEndian.Uint32(data[offset+0x14 : offset+0x18]))

	var modeName string
	flag18_high := flag18 & 0xFF00

	switch flag18_high {
	case 0x6800, 0x6900:
		if w >= 128 && h >= 128 {
			modeName = "4BPP RGBA8888 Standard"
		} else {
			modeName = "4BPP RGBA8888 Linear"
		}
	case 0x6600, 0x6700:
		if w >= 128 && h >= 128 {
			modeName = "4BPP ABGR1555 Standard"
		} else {
			modeName = "4BPP ABGR1555 Linear"
		}
	case 0x6A00, 0x6B00:
		if w >= 128 && h >= 64 {
			modeName = "8BPP ABGR1555 Standard"
		} else {
			modeName = "8BPP ABGR1555 Linear"
		}
	case 0x6C00, 0x6D00:
		if w >= 128 && h >= 64 {
			modeName = "8BPP RGBA8888 Standard"
		} else {
			modeName = "8BPP RGBA8888 Linear"
		}
	default:
		return info, false
	}

	size := 0x10 + pvrtSize

	if offset+size > len(data) {
		size = len(data) - offset
	}
	if size < 0x20 {
		return info, false
	}

	info.Offset = int64(offset)
	info.Size = size
	info.Width = w
	info.Height = h
	info.Mode = modeName
	info.Flag18 = flag18
	info.Flag14 = flag14

	return info, true
}

func decodeGBIX(data []byte, outPath string) bool {
	// 1. Check magic
	if len(data) < 0x20 || string(data[0:4]) != MagicGBIX {
		return false
	}

	w := int(binary.LittleEndian.Uint16(data[0x1C:0x1E]))
	h := int(binary.LittleEndian.Uint16(data[0x1E:0x20]))

	flag18 := binary.LittleEndian.Uint16(data[0x18:0x1A])
	_ = binary.LittleEndian.Uint16(data[0x14:0x16]) // flag14 not needed for format logic
	_ = int(binary.LittleEndian.Uint32(data[0x14:0x18]))

	var goPal color.Palette
	var finalPixels []byte
	flag18_high := flag18 & 0xFF00

	switch flag18_high {
	case 0x6600, 0x6700:
		palBytes := 32
		if 0x20+palBytes > len(data) { return false }
		goPal = make(color.Palette, 16)
		palData := data[0x20 : 0x20+palBytes]
		for i := 0; i < 16; i++ {
			raw := binary.LittleEndian.Uint16(palData[i*2 : i*2+2])
			goPal[i] = decodeABGR1555(raw, "ps2")
		}

		pixelBytesExpected := w * h / 2
		pixelBytesAvailable := len(data) - (0x20 + palBytes)
		if pixelBytesAvailable < 0 { pixelBytesAvailable = 0 }
		if pixelBytesAvailable > pixelBytesExpected { pixelBytesAvailable = pixelBytesExpected }
		
		pixData := data[0x20+palBytes : 0x20+palBytes+pixelBytesAvailable]
		fullPixData := make([]byte, pixelBytesExpected)
		copy(fullPixData, pixData)

		if w >= 128 && h >= 128 {
			fullPixData = Unswizzle4(fullPixData, w, h)
		}
		finalPixels = make([]byte, w*h)
		for i, b := range fullPixData {
			finalPixels[i*2] = b & 0x0F
			finalPixels[i*2+1] = (b >> 4) & 0x0F
		}

	case 0x6800, 0x6900:
		palBytes := 64
		if 0x20+palBytes > len(data) { return false }
		goPal = make(color.Palette, 16)
		palData := data[0x20 : 0x20+palBytes]
		for i := 0; i < 16; i++ {
			raw := binary.LittleEndian.Uint32(palData[i*4 : i*4+4])
			goPal[i] = decodeRGBA8888(raw, "ps2")
		}

		pixelBytesExpected := w * h / 2
		pixelBytesAvailable := len(data) - (0x20 + palBytes)
		if pixelBytesAvailable < 0 { pixelBytesAvailable = 0 }
		if pixelBytesAvailable > pixelBytesExpected { pixelBytesAvailable = pixelBytesExpected }
		
		pixData := data[0x20+palBytes : 0x20+palBytes+pixelBytesAvailable]
		fullPixData := make([]byte, pixelBytesExpected)
		copy(fullPixData, pixData)

		if w >= 128 && h >= 128 {
			fullPixData = Unswizzle4(fullPixData, w, h)
		}
		finalPixels = make([]byte, w*h)
		for i, b := range fullPixData {
			finalPixels[i*2] = b & 0x0F
			finalPixels[i*2+1] = (b >> 4) & 0x0F
		}

	case 0x6A00, 0x6B00:
		palBytes := 512
		if 0x20+palBytes > len(data) { return false }
		goPal = make(color.Palette, 256)
		palData := data[0x20 : 0x20+palBytes]
		u16Pal := make([]uint16, 256)
		for i := 0; i < 256; i++ {
			u16Pal[i] = binary.LittleEndian.Uint16(palData[i*2 : i*2+2])
		}
		u16Pal = UnswizzleCSM1_16(u16Pal)
		for i, v := range u16Pal {
			goPal[i] = decodeABGR1555(v, "ps2")
		}

		pixelBytesExpected := w * h
		pixelBytesAvailable := len(data) - (0x20 + palBytes)
		if pixelBytesAvailable < 0 { pixelBytesAvailable = 0 }
		if pixelBytesAvailable > pixelBytesExpected { pixelBytesAvailable = pixelBytesExpected }
		
		pixData := data[0x20+palBytes : 0x20+palBytes+pixelBytesAvailable]
		fullPixData := make([]byte, pixelBytesExpected)
		copy(fullPixData, pixData)

		if w >= 128 && h >= 64 {
			finalPixels = Unswizzle8(fullPixData, w, h)
		} else {
			finalPixels = make([]byte, w*h)
			copy(finalPixels, fullPixData)
		}

	case 0x6C00, 0x6D00:
		palBytes := 1024
		if 0x20+palBytes > len(data) { return false }
		goPal = make(color.Palette, 256)
		palData := data[0x20 : 0x20+palBytes]
		u32Pal := make([]uint32, 256)
		for i := 0; i < 256; i++ {
			u32Pal[i] = binary.LittleEndian.Uint32(palData[i*4 : i*4+4])
		}
		u32Pal = UnswizzleCSM1_32(u32Pal)
		for i, v := range u32Pal {
			goPal[i] = decodeRGBA8888(v, "ps2")
		}

		pixelBytesExpected := w * h
		pixelBytesAvailable := len(data) - (0x20 + palBytes)
		if pixelBytesAvailable < 0 { pixelBytesAvailable = 0 }
		if pixelBytesAvailable > pixelBytesExpected { pixelBytesAvailable = pixelBytesExpected }
		
		pixData := data[0x20+palBytes : 0x20+palBytes+pixelBytesAvailable]
		fullPixData := make([]byte, pixelBytesExpected)
		copy(fullPixData, pixData)

		if w >= 128 && h >= 64 {
			finalPixels = Unswizzle8(fullPixData, w, h)
		} else {
			finalPixels = make([]byte, w*h)
			copy(finalPixels, fullPixData)
		}

	default:
		return false
	}

	img := image.NewPaletted(image.Rect(0, 0, w, h), goPal)
	copy(img.Pix, finalPixels)

	f, err := os.Create(outPath)
	if err != nil {
		return false
	}
	defer f.Close()
	png.Encode(f, img)

	return true
}