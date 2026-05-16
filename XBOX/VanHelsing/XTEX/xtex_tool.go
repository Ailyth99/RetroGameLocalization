package main

import (
	"encoding/binary"
	"flag"
	"fmt"
	"io"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

type XtexHeader struct {
	Magic      [4]byte
	U1         uint32
	DataOffset uint32
	U2         uint32
	Format     uint16
	DimW       uint8
	DimH       uint8
	U3         [4]byte
}

func log2(n uint32) uint8 {
	return uint8(math.Log2(float64(n)))
}

func createDdsHeader(w, h uint32, format string) []byte {
	hdr := make([]byte, 128)
	copy(hdr[0:4], "DDS ")
	binary.LittleEndian.PutUint32(hdr[4:8], 124) // Size
	binary.LittleEndian.PutUint32(hdr[8:12], 0x00021007) // Flags
	binary.LittleEndian.PutUint32(hdr[12:16], h)
	binary.LittleEndian.PutUint32(hdr[16:20], w)
	
	linearSize := w * h
	if format == "DXT1" {
		linearSize = (w * h) / 2
	}
	binary.LittleEndian.PutUint32(hdr[20:24], linearSize)
	binary.LittleEndian.PutUint32(hdr[28:32], 1) // MipMapCount

	// Pixel Format
	pf := hdr[76 : 76+32]
	binary.LittleEndian.PutUint32(pf[0:4], 32)
	binary.LittleEndian.PutUint32(pf[4:8], 0x04) // DDPF_FOURCC
	copy(pf[8:12], format)

	binary.LittleEndian.PutUint32(hdr[108:112], 0x1000) // Caps
	return hdr
}

func xtexToPng(xtexPath, outPng string, texconvPath string) error {
	f, err := os.Open(xtexPath)
	if err != nil {
		return err
	}
	defer f.Close()

	var xhdr [32]byte
	if _, err := io.ReadFull(f, xhdr[:]); err != nil {
		return err
	}

	if string(xhdr[0:4]) != "XTEX" {
		return fmt.Errorf("not an XTEX file")
	}

	formatCode := binary.LittleEndian.Uint16(xhdr[16:18])
	w := uint32(1) << (xhdr[18] >> 4)
	h := uint32(1) << (xhdr[19])

	formatStr := "DXT3"
	if formatCode == 0x290C {
		formatStr = "DXT1"
	}

	fmt.Printf("[*] Converting XTEX %dx%d %s to PNG...\n", w, h, formatStr)

	f.Seek(128, io.SeekStart)
	data, err := io.ReadAll(f)
	if err != nil {
		return err
	}

	ddsHdr := createDdsHeader(w, h, formatStr)
	tmpDds := xtexPath + ".tmp.dds"
	outF, _ := os.Create(tmpDds)
	outF.Write(ddsHdr)
	outF.Write(data)
	outF.Close()
	defer os.Remove(tmpDds)

	cmd := exec.Command(texconvPath, "-ft", "png", "-y", "-o", filepath.Dir(outPng), tmpDds)
	if out, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("texconv error: %v\n%s", err, string(out))
	}

 
	generatedPng := strings.TrimSuffix(filepath.Base(tmpDds), filepath.Ext(tmpDds)) + ".png"
	generatedPng = filepath.Join(filepath.Dir(outPng), generatedPng)
	
	if generatedPng != outPng {
		os.Rename(generatedPng, outPng)
	}

	return nil
}

func pngToXtex(pngPath, outXtex string, texconvPath string, forceFormat string) error {
	fmt.Printf("[*] Converting PNG to XTEX...\n")

	format := "DXT3" //默认，字库就是这个
	if forceFormat != "" {
		format = strings.ToUpper(forceFormat)
	}

	tmpDir := filepath.Join(os.TempDir(), "xtex_conv")
	os.MkdirAll(tmpDir, 0755)
	defer os.RemoveAll(tmpDir)

	cmd := exec.Command(texconvPath, "-f", format, "-y", "-o", tmpDir, pngPath)
	if out, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("texconv error: %v\n%s", err, string(out))
	}

	ddsName := strings.TrimSuffix(filepath.Base(pngPath), filepath.Ext(pngPath)) + ".dds"
	ddsPath := filepath.Join(tmpDir, ddsName)

	fDds, err := os.Open(ddsPath)
	if err != nil {
		return err
	}
	defer fDds.Close()

	var ddsHdr [128]byte
	io.ReadFull(fDds, ddsHdr[:])
	
	w := binary.LittleEndian.Uint32(ddsHdr[16:20])
	h := binary.LittleEndian.Uint32(ddsHdr[12:16])
	
 
	pfFourCC := string(ddsHdr[84:88])
	fmt.Printf("  - Detected DDS: %dx%d %s\n", w, h, pfFourCC)

	xhdr := make([]byte, 128)
	copy(xhdr[0:4], "XTEX")
	binary.LittleEndian.PutUint32(xhdr[4:8], 0x00040001)  
 
	xhdr[4] = 0x01; xhdr[6] = 0x04
	
	binary.LittleEndian.PutUint32(xhdr[8:12], 128)  
	
	if pfFourCC == "DXT1" {
		xhdr[16] = 0x29; xhdr[17] = 0x0C
	} else {
		xhdr[16] = 0x29; xhdr[17] = 0x0E
	}
	
	xhdr[18] = (log2(w) << 4) | 1
	xhdr[19] = log2(h)
	
	for i := 24; i < 128; i++ {
		xhdr[i] = 0xFF
	}
	 

	fOut, _ := os.Create(outXtex)
	fOut.Write(xhdr)
	io.Copy(fOut, fDds)
	fOut.Close()

	return nil
}

func main() {
	uPtr := flag.String("u", "", "Unpack XTEX to PNG (XTEX_PATH)")
	pPtr := flag.String("p", "", "Pack PNG to XTEX (PNG_PATH)")
	oPtr := flag.String("o", "", "Output path")
	fPtr := flag.String("f", "", "Force format (DXT1 or DXT3)")
	tcPtr := flag.String("tc", `C:\TRANSLATE\PS2\VANHE\XBOX\XTEX\texconv.exe`, "Path to texconv.exe")

	flag.Parse()

	if *uPtr != "" {
		out := *oPtr
		if out == "" {
			out = strings.TrimSuffix(*uPtr, filepath.Ext(*uPtr)) + ".png"
		}
		if err := xtexToPng(*uPtr, out, *tcPtr); err != nil {
			fmt.Printf("[-] Error: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("[+] Saved to %s\n", out)
	} else if *pPtr != "" {
		out := *oPtr
		if out == "" {
			out = strings.TrimSuffix(*pPtr, filepath.Ext(*pPtr)) + ".DDS"
		}
		if err := pngToXtex(*pPtr, out, *tcPtr, *fPtr); err != nil {
			fmt.Printf("[-] Error: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("[+] Saved to %s\n", out)
	} else {
		flag.Usage()
	}
}
