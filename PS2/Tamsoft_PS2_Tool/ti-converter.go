// Filename: ti-converter.go
// 用于TAMSOFT的PS2游戏的TI格式贴图处理
//这种贴图广泛存在于TAMSOFT开发的PS2 SIMPLE 2000系列游戏，以及《未来少年柯南》，《GIANTROBO地球最后之日》等游戏。另外这些游戏可能包含一些无头位图，本程序无法处理。需要手动调试这些图。
//This program handles TI format textures from TAMSOFT's PlayStation 2 games.
// This texture format is widely found in TAMSOFT-developed PS2 SIMPLE 2000 series games, as well as titles like 'Future Boy Conan' and 'Giant Robo: The Day the Earth Stood Still.' Additionally, these games may contain some headless bitmaps,
// which this program cannot process. These textures will require manual debugging.

package main

import (
	"encoding/binary"
	"flag"
	"fmt"
	"image"
	"image/color"
	"image/png"
	_ "image/gif"
	_ "image/jpeg"
	"io"
	"log"
	"math"
	"os"
	"path/filepath"
	"strings"
)

//  Constants 
const (
	offBPP  = 0x16
	offW    = 0x22
	offH    = 0x24
	offCLUT = 0x30
)

//  Structs 
type TIInfo struct {
	Width, Height, BPP int
}

//  Common Functions 
func parseHdr(r io.ReadSeeker) (TIInfo, error) {
	var info TIInfo
	var buf [2]byte
	if _, err := r.Seek(offBPP, io.SeekStart); err != nil { return info, fmt.Errorf("seek BPP: %w", err) }
	b := make([]byte, 1)
	if _, err := io.ReadFull(r, b); err != nil { return info, fmt.Errorf("read BPP: %w", err) }
	switch b[0] {
	case 0: info.BPP = 4
	case 1: info.BPP = 8
	default: return info, fmt.Errorf("invalid BPP type: %d", b[0])
	}
	if _, err := r.Seek(offW, io.SeekStart); err != nil { return info, fmt.Errorf("seek Width: %w", err) }
	if _, err := io.ReadFull(r, buf[:]); err != nil { return info, fmt.Errorf("read Width: %w", err) }
	info.Width = int(binary.LittleEndian.Uint16(buf[:]))
	if _, err := r.Seek(offH, io.SeekStart); err != nil { return info, fmt.Errorf("seek Height: %w", err) }
	if _, err := io.ReadFull(r, buf[:]); err != nil { return info, fmt.Errorf("read Height: %w", err) }
	info.Height = int(binary.LittleEndian.Uint16(buf[:]))
	if info.Width <= 0 || info.Height <= 0 { return info, fmt.Errorf("invalid dimensions: W=%d, H=%d", info.Width, info.Height) }
	return info, nil
}

func calcSizes(info TIInfo) (clutSize int, pixSize int) {
	if info.BPP == 4 {
		clutSize = 16 * 4
		pixSize = (info.Width*info.Height + 1) / 2
	} else {
		clutSize = 256 * 4
		pixSize = info.Width * info.Height
	}
	return
}

//  TI to PNG Functions 
func processCLUT(r io.Reader, bpp int) (color.Palette, error) {
	numColors := 16
	if bpp == 8 { numColors = 256 }
	clutSize := numColors * 4
	rawCLUT := make([]byte, clutSize)
	if _, err := io.ReadFull(r, rawCLUT); err != nil { return nil, fmt.Errorf("reading CLUT: %w", err) }

	if bpp == 8 {
		tempBlock := make([]byte, 32)
		for i := 0; i < len(rawCLUT)/128; i++ {
			blockStart := i * 128
			sub2Start, sub3Start := blockStart+32, blockStart+64
			copy(tempBlock, rawCLUT[sub2Start:sub2Start+32])
			copy(rawCLUT[sub2Start:sub2Start+32], rawCLUT[sub3Start:sub3Start+32])
			copy(rawCLUT[sub3Start:sub3Start+32], tempBlock)
		}
	}
	palette := make(color.Palette, numColors)
	for i := 0; i < numColors; i++ {
		idx := i * 4
		r, g, b, aPS2 := rawCLUT[idx], rawCLUT[idx+1], rawCLUT[idx+2], rawCLUT[idx+3]
		aPNG := uint8(math.Min(255, float64(aPS2)*(255.0/128.0)))
		palette[i] = color.RGBA{R: r, G: g, B: b, A: aPNG}
	}
	return palette, nil
}

func processPix(r io.Reader, info TIInfo) ([]uint8, error) {
	_, pixSize := calcSizes(info)
	rawPix := make([]byte, pixSize)
	if _, err := io.ReadFull(r, rawPix); err != nil { return nil, fmt.Errorf("reading Pixels: %w", err) }

	if info.BPP == 8 {
		return rawPix, nil
	}

	// Correct 4bpp logic: low nibble is first pixel, high nibble is second.
	// 正确的4bpp unswizzle的逻辑：低4位是第一个像素，高4位是第二个像素。
	expandedPix := make([]uint8, 0, info.Width*info.Height)
	for _, b := range rawPix {
		pixel1 := b & 0x0F
		pixel2 := (b >> 4) & 0x0F
		expandedPix = append(expandedPix, pixel1)
		expandedPix = append(expandedPix, pixel2)
	}
	return expandedPix[:info.Width*info.Height], nil
}

//  PNG to TI Functions (Exact inverse of the above) 
func validatePNG(pngImg image.Image, tiInfo TIInfo) (*image.Paletted, error) {
	palettedImg, ok := pngImg.(*image.Paletted)
	if !ok { return nil, fmt.Errorf("input PNG is not paletted") }
	bounds := palettedImg.Bounds()
	if bounds.Dx() != tiInfo.Width || bounds.Dy() != tiInfo.Height {
		return nil, fmt.Errorf("PNG dimensions (%dx%d) mismatch TI (%dx%d)", bounds.Dx(), bounds.Dy(), tiInfo.Width, tiInfo.Height)
	}
	expectedColors := 16
	if tiInfo.BPP == 8 { expectedColors = 256 }
	if len(palettedImg.Palette) > expectedColors {
		return nil, fmt.Errorf("PNG palette size (%d) exceeds limit for %d bpp TI (%d)", len(palettedImg.Palette), tiInfo.BPP, expectedColors)
	}
	return palettedImg, nil
}

func reverseCLUT(pal color.Palette, bpp int) []byte {
	expectedColors := 16
	if bpp == 8 { expectedColors = 256 }
	rawCLUT := make([]byte, expectedColors*4)
	for i, c := range pal {
		if i >= expectedColors { break }
		rgba := color.RGBAModel.Convert(c).(color.RGBA)
		aPS2 := uint8(math.Min(128, math.Round(float64(rgba.A)*(128.0/255.0))))
		idx := i * 4
		rawCLUT[idx], rawCLUT[idx+1], rawCLUT[idx+2], rawCLUT[idx+3] = rgba.R, rgba.G, rgba.B, aPS2
	}
	if bpp == 8 {
		tempBlock := make([]byte, 32)
		for i := 0; i < len(rawCLUT)/128; i++ {
			blockStart := i * 128
			sub2Start, sub3Start := blockStart+32, blockStart+64
			copy(tempBlock, rawCLUT[sub2Start:sub2Start+32])
			copy(rawCLUT[sub2Start:sub2Start+32], rawCLUT[sub3Start:sub3Start+32])
			copy(rawCLUT[sub3Start:sub3Start+32], tempBlock)
		}
	}
	return rawCLUT
}

func reversePix(pix []uint8, info TIInfo) []byte {
	if info.BPP == 8 {
		return pix
	}

	// Correct inverse 4bpp logic: first pixel to low nibble, second to high.
	// 逆向4bpp逻辑：第一个像素放入低4位，第二个像素放入高4位。
	tiPixSize := (info.Width*info.Height + 1) / 2
	tiPix := make([]byte, tiPixSize)
	for i := 0; i < len(tiPix); i++ {
		pixel1, pixel2 := uint8(0), uint8(0)
		if i*2 < len(pix) {
			pixel1 = pix[i*2] & 0x0F
		}
		if i*2+1 < len(pix) {
			pixel2 = pix[i*2+1] & 0x0F
		}
		tiPix[i] = (pixel2 << 4) | pixel1
	}
	return tiPix
}

//  Handlers for Main 
func handleTiToPng(tiPath, outputPath string) {
	file, err := os.Open(tiPath)
	if err != nil { log.Fatalf("Error opening TI file '%s': %v", tiPath, err) }
	defer file.Close()
	info, err := parseHdr(file)
	if err != nil { log.Fatalf("Error parsing TI header: %v", err) }
	if _, err := file.Seek(offCLUT, io.SeekStart); err != nil { log.Fatalf("Error seeking to CLUT: %v", err) }
	palette, err := processCLUT(file, info.BPP)
	if err != nil { log.Fatalf("Error processing CLUT: %v", err) }
	pixels, err := processPix(file, info)
	if err != nil { log.Fatalf("Error processing pixels: %v", err) }
	img := image.NewPaletted(image.Rect(0, 0, info.Width, info.Height), palette)
	img.Pix = pixels
	if outputPath == "" {
		outputPath = strings.TrimSuffix(tiPath, filepath.Ext(tiPath)) + ".png"
	}
	outFile, err := os.Create(outputPath)
	if err != nil { log.Fatalf("Error creating output PNG '%s': %v", outputPath, err) }
	defer outFile.Close()
	if err := png.Encode(outFile, img); err != nil { log.Fatalf("Error encoding PNG: %v", err) }
	fmt.Printf("Successfully converted '%s' to '%s'\n", filepath.Base(tiPath), filepath.Base(outputPath))
}

func handlePngToTi(tiPath, pngPath, outputPath string) {
	tiFile, err := os.Open(tiPath)
	if err != nil { log.Fatalf("Error opening original TI file '%s': %v", tiPath, err) }
	tiInfo, err := parseHdr(tiFile)
	if err != nil { tiFile.Close(); log.Fatalf("Error parsing TI header: %v", err) }
	tiFile.Seek(0, io.SeekStart)
	originalTiData, err := io.ReadAll(tiFile)
	tiFile.Close()
	if err != nil { log.Fatalf("Error reading original TI data: %v", err) }
	pngFile, err := os.Open(pngPath)
	if err != nil { log.Fatalf("Error opening PNG file '%s': %v", pngPath, err) }
	defer pngFile.Close()
	pngImg, _, err := image.Decode(pngFile)
	if err != nil { log.Fatalf("Error decoding PNG file: %v", err) }
	palettedImg, err := validatePNG(pngImg, tiInfo)
	if err != nil { log.Fatalf("PNG validation failed: %v", err) }
	clutSize, pixSize := calcSizes(tiInfo)
	newRawCLUT := reverseCLUT(palettedImg.Palette, tiInfo.BPP)
	newRawPix := reversePix(palettedImg.Pix, tiInfo)
	if len(newRawCLUT) != clutSize || len(newRawPix) != pixSize {
		log.Fatalf("Internal error: generated data size mismatch.")
	}
	modifiedTiData := make([]byte, len(originalTiData))
	copy(modifiedTiData, originalTiData)
	copy(modifiedTiData[offCLUT:offCLUT+clutSize], newRawCLUT)
	copy(modifiedTiData[offCLUT+clutSize:offCLUT+clutSize+pixSize], newRawPix)
	if outputPath == "" {
		tiBase := strings.TrimSuffix(filepath.Base(tiPath), filepath.Ext(tiPath))
		pngBase := strings.TrimSuffix(filepath.Base(pngPath), filepath.Ext(pngPath))
		outputPath = filepath.Join(filepath.Dir(tiPath), fmt.Sprintf("%s_%s.ti", tiBase, pngBase))
	}
	err = os.WriteFile(outputPath, modifiedTiData, 0644)
	if err != nil { log.Fatalf("Error writing output TI file: %v", err) }
	fmt.Printf("Successfully created new TI file: %s\n", filepath.Base(outputPath))
}

func main() {
	log.SetFlags(0)
	output := flag.String("o", "", "Optional output file path.")
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage of %s:\n", os.Args[0])
		fmt.Fprintln(os.Stderr, "  ti-converter <input.ti> [-o <output.png>]      (Converts TI to PNG)")
		fmt.Fprintln(os.Stderr, "  ti-converter <original.ti> <new.png> [-o <output.ti>] (Converts PNG to TI)")
		flag.PrintDefaults()
	}
	flag.Parse()
	args := flag.Args()
	switch len(args) {
	case 1:
		inputPath := args[0]
		if !strings.HasSuffix(strings.ToLower(inputPath), ".ti") {
			log.Fatal("Error: For single argument, input must be a .ti file.")
		}
		handleTiToPng(inputPath, *output)
	case 2:
		path1, path2 := args[0], args[1]
		ext1, ext2 := strings.ToLower(filepath.Ext(path1)), strings.ToLower(filepath.Ext(path2))
		if ext1 == ".ti" && (ext2 == ".png" || ext2 == ".gif" || ext2 == ".jpg" || ext2 == ".jpeg") {
			handlePngToTi(path1, path2, *output)
		} else {
			log.Fatal("Error: For two arguments, inputs must be <original.ti> and a valid image file.")
		}
	default:
		flag.Usage()
		os.Exit(1)
	}
}