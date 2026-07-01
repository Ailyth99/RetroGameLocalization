package main

import (
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Printf("Usage: %s <input.dat> [output_dir]\n", os.Args[0])
		os.Exit(1)
	}

	datPath := os.Args[1]
	var outDir string
	if len(os.Args) >= 3 {
		outDir = os.Args[2]
	} else {
		ext := filepath.Ext(datPath)
		base := filepath.Base(datPath)
		name := strings.TrimSuffix(base, ext)
		outDir = filepath.Join(filepath.Dir(datPath), name)
	}

	err := os.MkdirAll(outDir, 0755)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to create output directory: %v\n", err)
		os.Exit(1)
	}

	f, err := os.Open(datPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to open DAT file: %v\n", err)
		os.Exit(1)
	}
	defer f.Close()

	stat, err := f.Stat()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to stat file: %v\n", err)
		os.Exit(1)
	}
	fsize := stat.Size()

	var fcount uint32
	err = binary.Read(f, binary.LittleEndian, &fcount)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to read file count: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Total files in DAT: %d\n", fcount)

	offsets := make([]uint32, fcount)
	err = binary.Read(f, binary.LittleEndian, &offsets)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to read offset table: %v\n", err)
		os.Exit(1)
	}

	for i := 0; i < int(fcount); i++ {
		offset := int64(offsets[i])
		var nextOffset int64
		if i < int(fcount)-1 {
			nextOffset = int64(offsets[i+1])
		} else {
			nextOffset = fsize
		}

		size := nextOffset - offset
		if size < 0 {
			fmt.Fprintf(os.Stderr, "Invalid size %d for file %d (offset %d, next %d)\n", size, i, offset, nextOffset)
			continue
		}

		_, err = f.Seek(offset, io.SeekStart)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Failed to seek to offset %d: %v\n", offset, err)
			continue
		}

		var magic uint32
		ext := ".bin"
		if size >= 4 {
			err = binary.Read(f, binary.LittleEndian, &magic)
			if err == nil && magic == 0x10 {
				ext = ".TIM"
			}
			f.Seek(offset, io.SeekStart)
		}

		outName := fmt.Sprintf("%03d%s", i, ext)
		outPath := filepath.Join(outDir, outName)

		fmt.Printf("Extracting %s (size: %d bytes)...\n", outName, size)

		outF, err := os.Create(outPath)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Failed to create file %s: %v\n", outPath, err)
			continue
		}

		_, err = io.CopyN(outF, f, size)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Failed to write file data: %v\n", err)
		}
		
		outF.Close()
	}

	fmt.Println("Extraction completed successfully.")
}
