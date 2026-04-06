package main

import (
	"bytes"
	"encoding/binary"
	"flag"
	"fmt"
	"image"
	"image/png"
	"io/ioutil"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"

	"timtool/psxtim"
)

// KF2 Constants
const (
	KF2_HEADER_SIZE = 0x800
	KF2_SEED        = 0x12345678  //FS的PS1游戏的校验增加值
)

func main() {
	checksumFlag := flag.Bool("checksum", false, "Enable dynamic KF2 checksum calculation / 打开文件校验")
	flag.Parse()

	args := flag.Args()
	if len(args) < 2 {
		fmt.Println("Usage:")
		fmt.Println("  tool export <FILE>")
		fmt.Println("  tool [-checksum] import <FILE> [Optional: SinglePngPath]")
		return
	}

	mode, file := args[0], args[1]

	if mode == "export" {
		exportTIMs(file)
	} else if mode == "import" {
		single := ""
		if len(args) >= 3 {
			single = args[2]
		}
		importTIMs(file, single, *checksumFlag)
	}
}

func exportTIMs(path string) {
	data, err := ioutil.ReadFile(path)
	if err != nil { log.Fatal(err) }

	outDir := path + "_out"
	os.MkdirAll(outDir, 0755)

	fmt.Printf("Scanning %s...\n", filepath.Base(path))
	results := psxtim.Scan(data)

	for i, res := range results {
		img, err := res.Info.ToImage(0)
		if err != nil { continue }
		fname := fmt.Sprintf("%04d_%08X_%d_%d_%dbpp.png", 
			i, res.Offset, res.Info.Width, res.Info.Height, res.Info.BPP)
		f, _ := os.Create(filepath.Join(outDir, fname))
		png.Encode(f, img)
		f.Close()
		fmt.Printf("Export: %s\n", fname)
	}
}

func importTIMs(targetPath, singlePng string, forceChecksum bool) {
	binData, err := ioutil.ReadFile(targetPath)
	if err != nil { log.Fatal(err) }

	fName := strings.ToUpper(filepath.Base(targetPath))
	shouldFix := forceChecksum || strings.Contains(fName, "TALK.T") || strings.Contains(fName, "ITEM.T") || strings.Contains(fName, "STALK.T")

	files := []string{}
	if singlePng != "" {
		files = append(files, singlePng)
	} else {
		outDir := targetPath + "_out"
		matches, _ := filepath.Glob(filepath.Join(outDir, "*.png"))
		files = matches
	}

	if len(files) == 0 {
		fmt.Println("No PNGs found.")
		return
	}

	updated := 0
	for _, fpath := range files {
		if err := patchTIM(binData, fpath, shouldFix); err != nil {
			fmt.Printf("Err %s: %v\n", filepath.Base(fpath), err)
		} else {
			updated++
		}
	}

	if updated > 0 {
		ioutil.WriteFile(targetPath, binData, 0644)
		fmt.Printf("Success. Updated %d TIMs in %s.\n", updated, filepath.Base(targetPath))
	}
}


//文件校验部分
func patchTIM(binData []byte, pngPath string, fixChecksum bool) error {
	base := filepath.Base(pngPath)
	parts := strings.Split(strings.TrimSuffix(base, ".png"), "_")
	if len(parts) < 5 { return fmt.Errorf("bad filename fmt") }

	offset64, _ := strconv.ParseInt(parts[1], 16, 64)
	offset := int(offset64)
	bppStr := strings.TrimSuffix(parts[4], "bpp")
	bpp, _ := strconv.Atoi(bppStr)

	rawPng, err := ioutil.ReadFile(pngPath)
	if err != nil { return err }
	var qPngData []byte
	if bpp == 4 || bpp == 8 {
		colors := 16
		if bpp == 8 { colors = 256 }
		qPngData, err = quantize(rawPng, colors)
		if err != nil { return err }
	} else { qPngData = rawPng }

	img, _, err := image.Decode(bytes.NewReader(qPngData))
	if err != nil { return err }
	newTim, err := psxtim.FromImage(img, bpp)
	if err != nil { return err }

	origTimReader := bytes.NewReader(binData[offset:])
	origTim, err := psxtim.Decode(origTimReader)
	if err != nil { return fmt.Errorf("failed to parse orig TIM: %v", err) }
	
	newTim.OrgX = origTim.OrgX; newTim.OrgY = origTim.OrgY
	newTim.ClutOrgX = origTim.ClutOrgX; newTim.ClutOrgY = origTim.ClutOrgY

	var buf bytes.Buffer
	newTim.Encode(&buf)
	newBytes := buf.Bytes()

	blockStart := offset
	blockEnd := len(binData)
	magic := []byte{0x10, 0x00, 0x00, 0x00}
	for searchPos := offset + 16; searchPos <= len(binData)-16; searchPos += 16 {
		if bytes.Equal(binData[searchPos:searchPos+4], magic) {
			blockEnd = searchPos
			break
		}
	}
	checksumPos := blockEnd - 4
	
	if int(offset) + len(newBytes) > checksumPos {
		return fmt.Errorf("new TIM hits checksum area")
	}

	copy(binData[offset:], newBytes)
	for i := offset + len(newBytes); i < checksumPos; i++ {
		binData[i] = 0
	}

	if fixChecksum {
		payload := binData[blockStart : checksumPos]
		sum := uint32(KF2_SEED)
		for i := 0; i < len(payload); i += 4 {
			if i+4 <= len(payload) {
				val := binary.LittleEndian.Uint32(payload[i : i+4])
				sum += val
			}
		}
		binary.LittleEndian.PutUint32(binData[checksumPos:], sum)
		fmt.Printf("Imp: %s -> %X [OK+Checksum]\n", base, offset)
	} else {
		fmt.Printf("Imp: %s -> %X [OK]\n", base, offset)
	}

	return nil
}

func quantize(raw []byte, nColors int) ([]byte, error) {
	exePath, err := exec.LookPath("pngquant")
	
	if err != nil {
		executablePath, _ := os.Executable()
		exeDir := filepath.Dir(executablePath)
		localPngquant := filepath.Join(exeDir, "pngquant.exe")
		
		if _, statErr := os.Stat(localPngquant); statErr == nil {
			exePath = localPngquant
		} else {
			return nil, fmt.Errorf("pngquant not found in PATH or alongside tool")
		}
	}

	cmd := exec.Command(exePath, "--force", "--speed", "1", fmt.Sprintf("%d", nColors), "-")
	cmd.Stdin = bytes.NewReader(raw)
	var out, stderr bytes.Buffer
	cmd.Stdout = &out; cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil { return nil, fmt.Errorf("pngquant: %v (%s)", err, stderr.String()) }
	return out.Bytes(), nil
}