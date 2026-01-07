package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"io/ioutil"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
)


//掉头pngquant做颜色量化
func Quantize(rawPng []byte, nColors int) ([]byte, error) {
	exePath, err := exec.LookPath("pngquant")
	
	if err != nil {
		executablePath, _ := os.Executable()
		exeDir := filepath.Dir(executablePath)
		localPngquant := filepath.Join(exeDir, "pngquant.exe")
		
		if _, statErr := os.Stat(localPngquant); statErr == nil {
			exePath = localPngquant
		} else {
			return nil, fmt.Errorf("pngquant not found in PATH or alongside executable")
		}
	}

	cmd := exec.Command(exePath, "--force", "--speed", "1", fmt.Sprintf("%d", nColors), "-")
	cmd.Stdin = bytes.NewReader(rawPng)
	var outBuf bytes.Buffer
	var errBuf bytes.Buffer
	cmd.Stdout = &outBuf
	cmd.Stderr = &errBuf

	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("pngquant failed: %v (Stderr: %s)", err, errBuf.String())
	}
	
	if outBuf.Len() == 0 {
		return nil, fmt.Errorf("pngquant produced empty output")
	}
	return outBuf.Bytes(), nil
}

func u16(b []byte) uint16 {
	return binary.LittleEndian.Uint16(b)
}

func ps1ToColor(v uint16) color.RGBA {
	r := (v & 0x1F) << 3
	g := ((v >> 5) & 0x1F) << 3
	b := ((v >> 10) & 0x1F) << 3
	return color.RGBA{uint8(r), uint8(g), uint8(b), 255}
}

func colorToPs1(c color.Color) uint16 {
	r, g, b, _ := c.RGBA()
	r5 := ((r >> 8) >> 3) & 0x1F
	g5 := ((g >> 8) >> 3) & 0x1F
	b5 := ((b >> 8) >> 3) & 0x1F
	return uint16(r5 | (g5 << 5) | (b5 << 10))
}


func Export(path string) {
	data, err := ioutil.ReadFile(path)
	if err != nil {
		log.Fatal(err)
	}

	outDir := path + "_out"
	os.MkdirAll(outDir, 0755)

	size := len(data)
	pos := 0
	count := 0

	fmt.Printf("Scanning %s (Size: %d bytes)...\n", filepath.Base(path), size)

	for pos < size-64 {
		blockStart := pos

		if pos+16 > size { break }
		cx := u16(data[pos : pos+2])
		cy := u16(data[pos+2 : pos+4])
		cw := u16(data[pos+4 : pos+6])
		ch := u16(data[pos+6 : pos+8])
		
		dx := u16(data[pos+8 : pos+10])
		dy := u16(data[pos+10 : pos+12])
		dw := u16(data[pos+12 : pos+14])
		dh := u16(data[pos+14 : pos+16])

		if cx != dx || cy != dy || cw != dw || ch != dh || cw > 256 {
			pos += 2
			continue
		}
		pos += 16

		if pos+32 > size { break }
		palette := make([]color.Color, 16)
		for i := 0; i < 16; i++ {
			pVal := u16(data[pos : pos+2])
			palette[i] = ps1ToColor(pVal)
			pos += 2
		}

		if pos+16 > size { break }
		ix := u16(data[pos : pos+2])
		iy := u16(data[pos+2 : pos+4])
		iw := u16(data[pos+4 : pos+6])
		ih := u16(data[pos+6 : pos+8])
		
		dix := u16(data[pos+8 : pos+10])
		diy := u16(data[pos+10 : pos+12])
		diw := u16(data[pos+12 : pos+14])
		dih := u16(data[pos+14 : pos+16])

		if ix != dix || iy != diy || iw != diw || ih != dih {
			pos = blockStart + 2
			continue
		}
		pos += 16

		realW := int(iw) * 4
		realH := int(ih)
		
		if realW == 0 || realH == 0 || realW > 2048 || realH > 1024 {
			pos = blockStart + 2
			continue
		}

		img := image.NewPaletted(image.Rect(0, 0, realW, realH), palette)
		validBlock := true
		
		for y := 0; y < realH; y++ {
			for x := 0; x < int(iw); x++ {
				if pos+2 > size {
					validBlock = false
					break
				}
				pixVal := u16(data[pos : pos+2])
				pos += 2
				
				baseX := x * 4
				img.SetColorIndex(baseX+3, y, uint8((pixVal>>12)&0xF))
				img.SetColorIndex(baseX+2, y, uint8((pixVal>>8)&0xF))
				img.SetColorIndex(baseX+1, y, uint8((pixVal>>4)&0xF))
				img.SetColorIndex(baseX+0, y, uint8((pixVal>>0)&0xF))
			}
			if !validBlock { break }
		}

		if validBlock {
			fname := fmt.Sprintf("%04d_%08X_%d_%d.png", count, blockStart, realW, realH)
			f, _ := os.Create(filepath.Join(outDir, fname))
			png.Encode(f, img)
			f.Close()
			fmt.Printf("Export: %s\n", fname)
			count++
		} else {
			pos = blockStart + 2
		}
	}
	fmt.Printf("Done. Total exported: %d\n", count)
}

func patchImage(binData []byte, fpath string) error {
	base := filepath.Base(fpath)
	parts := strings.Split(strings.TrimSuffix(base, ".png"), "_")
	
	if len(parts) < 4 { 
		return fmt.Errorf("bad filename format: %s", base)
	}

	offsetStr := parts[1]
	wStr := parts[2]
	hStr := parts[3]

	offset, err := strconv.ParseInt(offsetStr, 16, 64)
	if err != nil { return fmt.Errorf("bad offset in filename: %v", err) }
	
	targetW, _ := strconv.Atoi(wStr)
	targetH, _ := strconv.Atoi(hStr)

	fmt.Printf("Imp: %s -> Offset:%X... ", base, offset)

	//读取PNG
	rawPng, err := ioutil.ReadFile(fpath)
	if err != nil { return fmt.Errorf("read file error: %v", err) }

	//量化
	qPngData, err := Quantize(rawPng, 16)
	if err != nil { return fmt.Errorf("quantize error: %v", err) }

	//解码
	img, _, err := image.Decode(bytes.NewReader(qPngData))
	if err != nil { return fmt.Errorf("decode error: %v", err) }

	//尺寸校验
	bounds := img.Bounds()
	if bounds.Dx() != targetW || bounds.Dy() != targetH {
		return fmt.Errorf("size mismatch: PNG is %dx%d, expected %dx%d", bounds.Dx(), bounds.Dy(), targetW, targetH)
	}

	palettedImg, ok := img.(*image.Paletted)
	if !ok {
		return fmt.Errorf("image not paletted after quantize")
	}

	//写入调色板
	pPos := int(offset) + 16
	//边界检查
	if pPos+32 > len(binData) {
		return fmt.Errorf("offset out of range writing palette")
	}

	for i := 0; i < 16; i++ {
		var c color.Color
		if i < len(palettedImg.Palette) {
			c = palettedImg.Palette[i]
		} else {
			c = color.Black
		}
		binary.LittleEndian.PutUint16(binData[pPos:], colorToPs1(c))
		pPos += 2
	}

	//写入像素
	pixelPos := int(offset) + 64
	wWords := targetW / 4
	
	//边界检查
	requiredSize := targetH * wWords * 2
	if pixelPos + requiredSize > len(binData) {
		return fmt.Errorf("offset out of range writing pixels")
	}

	for y := 0; y < targetH; y++ {
		for x := 0; x < wWords; x++ {
			baseX := x * 4
			var idx [4]uint8
			for k := 0; k < 4; k++ {
				if baseX+k < bounds.Dx() {
					idx[k] = palettedImg.ColorIndexAt(baseX+k, y)
				}
			}

			packed := (uint16(idx[3]&0xF) << 12) |
				      (uint16(idx[2]&0xF) << 8) |
				      (uint16(idx[1]&0xF) << 4) |
				      (uint16(idx[0]&0xF))
			
			binary.LittleEndian.PutUint16(binData[pixelPos:], packed)
			pixelPos += 2
		}
	}
	
	fmt.Println("OK")
	return nil
}

func Import(targetPath string, singlePngPath string) {
	//读取目标
	fmt.Printf("Loading target file: %s ... ", targetPath)
	binData, err := ioutil.ReadFile(targetPath)
	if err != nil {
		fmt.Printf("FAILED\nError reading target file: %v\n", err)
		return
	}
	fmt.Printf("OK (%d bytes)\n", len(binData))

	var files []string
	if singlePngPath != "" {
		files = append(files, singlePngPath)
	} else {
		outDir := targetPath + "_out"
		globFiles, err := filepath.Glob(filepath.Join(outDir, "*.png"))
		if err != nil { log.Fatal(err) }
		files = globFiles
	}

	if len(files) == 0 {
		fmt.Println("No png files found to import.")
		return
	}

	successCount := 0
	errorCount := 0

	for _, fpath := range files {
		err := patchImage(binData, fpath)
		if err != nil {
			fmt.Printf("FAILED: %s\nReason: %v\n", filepath.Base(fpath), err)
			errorCount++
		} else {
			successCount++
		}
	}

	if successCount > 0 {
		fmt.Printf("Writing changes to %s ... ", targetPath)
		err = ioutil.WriteFile(targetPath, binData, 0644)
		if err != nil {
			fmt.Printf("FAILED\nFatal Error writing file: %v\n", err)
		} else {
			fmt.Println("DONE")
			fmt.Printf("Summary: %d Success, %d Failed.\n", successCount, errorCount)
		}
	} else {
		fmt.Println("Nothing updated due to errors.")
	}
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage:")
		fmt.Println("  tool export <T_FILE>")
		fmt.Println("  tool import <T_FILE> [Optional: SinglePngPath]")
		return
	}

	mode := os.Args[1]
	file := os.Args[2]

	if mode == "export" {
		Export(file)
	} else if mode == "import" {
		singlePng := ""
		if len(os.Args) >= 4 {
			singlePng = os.Args[3]
		}
		Import(file, singlePng)
	} else {
		fmt.Println("Unknown mode")
	}
}