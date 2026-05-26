package main

import (
	"encoding/binary"
	"fmt"
	"image"
	"image/color"
	_ "image/png"
	"log"
	"os"
	"os/exec"
	"path/filepath"
)



func injectGBIX(targetFile string, pngFile string, offset int64) {
	data, err := os.ReadFile(targetFile)
	if err != nil { log.Fatal(err) }

	hInfo, ok := parseHeader(data, int(offset))
	if !ok { log.Fatal("Not a valid GBIX file at offset") }

	w := hInfo.Width
	h := hInfo.Height

	f, err := os.Open(pngFile)
	if err != nil { log.Fatal(err) }
	
	img, _, err := image.Decode(f)
	f.Close()
	if err != nil { log.Fatal(err) }

	b := img.Bounds()
	if b.Dx() != w || b.Dy() != h {
		log.Fatalf("Dimension mismatch! GBIX expects %dx%d, got %dx%d", w, h, b.Dx(), b.Dy())
	}

	palImg, isPal := img.(*image.Paletted)
	
	// Determine required colors
	reqColors := 256
	flag18_high := hInfo.Flag18 & 0xFF00
	if flag18_high == 0x6600 || flag18_high == 0x6700 || flag18_high == 0x6800 || flag18_high == 0x6900 {
		reqColors = 16
	}

	if !isPal || len(palImg.Palette) > reqColors {
		fmt.Printf("Image requires quantization to %d colors. Invoking pngquant...\n", reqColors)
		
		var quantPath string
		
		// Securely find the directory where svr_converter.exe is located
		exePath, err := os.Executable()
		if err == nil {
			exeDir := filepath.Dir(exePath)
			localQuant := filepath.Join(exeDir, "pngquant.exe")
			if _, err := os.Stat(localQuant); err == nil {
				quantPath = localQuant
			}
		}
		
		if quantPath == "" {
			if _, err := exec.LookPath("pngquant"); err == nil {
				quantPath = "pngquant"
			} else {
				log.Fatal("pngquant.exe not found! Please place pngquant.exe in the same directory as the converter to enable automatic color quantization.")
			}
		}

		outPng := filepath.Join(filepath.Dir(pngFile), "temp_quant_123.png")
		cmd := exec.Command(quantPath, fmt.Sprintf("%d", reqColors), "--force", "--output", outPng, pngFile)
		out, err := cmd.CombinedOutput()
		if err != nil {
			log.Fatalf("pngquant failed: %v\nOutput: %s", err, string(out))
		}

		qf, err := os.Open(outPng)
		if err != nil { log.Fatal(err) }
		qimg, _, err := image.Decode(qf)
		qf.Close()
		os.Remove(outPng) // cleanup
		if err != nil { log.Fatal(err) }
		
		palImg, isPal = qimg.(*image.Paletted)
		if !isPal {
			log.Fatal("pngquant output is not paletted?!")
		}
	}

	// Prepare palette bytes
	var palBytes []byte
	if flag18_high == 0x6600 || flag18_high == 0x6700 || flag18_high == 0x6800 || flag18_high == 0x6900 {
		// 16 colors
		if flag18_high == 0x6600 || flag18_high == 0x6700 {
			palBytes = make([]byte, 32)
			for i := 0; i < 16; i++ {
				var c color.Color = color.Transparent
				if i < len(palImg.Palette) { c = palImg.Palette[i] }
				nrgba, _ := color.NRGBAModel.Convert(c).(color.NRGBA)
				raw := encodeABGR1555(nrgba)
				binary.LittleEndian.PutUint16(palBytes[i*2:], raw)
			}
		} else {
			palBytes = make([]byte, 64)
			for i := 0; i < 16; i++ {
				var c color.Color = color.Transparent
				if i < len(palImg.Palette) { c = palImg.Palette[i] }
				nrgba, _ := color.NRGBAModel.Convert(c).(color.NRGBA)
				raw := encodeRGBA8888(nrgba, true)
				binary.LittleEndian.PutUint32(palBytes[i*4:], raw)
			}
		}
	} else {
		// 256 colors
		if flag18_high == 0x6A00 || flag18_high == 0x6B00 {
			u16Pal := make([]uint16, 256)
			for i := 0; i < 256; i++ {
				var c color.Color = color.Transparent
				if i < len(palImg.Palette) { c = palImg.Palette[i] }
				nrgba, _ := color.NRGBAModel.Convert(c).(color.NRGBA)
				u16Pal[i] = encodeABGR1555(nrgba)
			}
			u16Pal = SwizzleCSM1_16(u16Pal)
			palBytes = make([]byte, 512)
			for i := 0; i < 256; i++ {
				binary.LittleEndian.PutUint16(palBytes[i*2:], u16Pal[i])
			}
		} else {
			u32Pal := make([]uint32, 256)
			for i := 0; i < 256; i++ {
				var c color.Color = color.Transparent
				if i < len(palImg.Palette) { c = palImg.Palette[i] }
				nrgba, _ := color.NRGBAModel.Convert(c).(color.NRGBA)
				u32Pal[i] = encodeRGBA8888(nrgba, true)
			}
			u32Pal = SwizzleCSM1_32(u32Pal)
			palBytes = make([]byte, 1024)
			for i := 0; i < 256; i++ {
				binary.LittleEndian.PutUint32(palBytes[i*4:], u32Pal[i])
			}
		}
	}

	// Prepare pixel bytes
	var pixBytes []byte
	if flag18_high == 0x6600 || flag18_high == 0x6700 || flag18_high == 0x6800 || flag18_high == 0x6900 {
		// 4BPP, need to pack!
		packed := make([]byte, w*h/2)
		for i := 0; i < w*h/2; i++ {
			p1 := palImg.Pix[i*2]
			p2 := palImg.Pix[i*2+1]
			packed[i] = (p1 & 0x0F) | ((p2 & 0x0F) << 4)
		}
		
		if w >= 128 && h >= 128 {
			pixBytes = Swizzle4(packed, w, h)
		} else {
			pixBytes = packed
		}
	} else {
		// 8BPP
		unswizzled := palImg.Pix
		if flag18_high == 0x6A00 || flag18_high == 0x6B00 || flag18_high == 0x6C00 || flag18_high == 0x6D00 {
			if w >= 128 && h >= 64 {
				pixBytes = Swizzle8(unswizzled, w, h)
			} else {
				pixBytes = unswizzled
			}
		}
	}

	// Overwrite File
	targetF, err := os.OpenFile(targetFile, os.O_RDWR, 0644)
	if err != nil { log.Fatal(err) }
	defer targetF.Close()

	_, err = targetF.WriteAt(palBytes, offset+0x20)
	if err != nil { log.Fatal(err) }

	_, err = targetF.WriteAt(pixBytes, offset+0x20+int64(len(palBytes)))
	if err != nil { log.Fatal(err) }

	fmt.Println("Injection successful!")
}
