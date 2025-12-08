package main

import (
	"encoding/binary"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: pklz_maker <input_file>")
		fmt.Println("Creates a non-compressed PK..00 format .pklz file.")
		return
	}

	inputFile := os.Args[1]
	
	data, err := os.ReadFile(inputFile)
	if err != nil {
		fmt.Printf("Error reading file: %v\n", err)
		return
	}
	
	fileSize := uint32(len(data))
	fmt.Printf("Input: %s (Size: %d bytes)\n", filepath.Base(inputFile), fileSize)

	// 构建 16 字节头部
	// 头部格式:PK(2)+00(1)+Type(1)+DecompSize(4)+Padding(8)
	header := make([]byte, 16)
	
	// 0x00 - 0x03: PK\x00\x00
	header[0] = 'P'
	header[1] = 'K'
	header[2] = 0x00
	header[3] = 0x00 // Type 00: No Compression (Memcpy)

	binary.LittleEndian.PutUint32(header[4:8], fileSize)
	

	baseName := filepath.Base(inputFile)
	ext := filepath.Ext(baseName)
	var outName string
	if strings.ToLower(ext) == ".bin" {
		outName = strings.TrimSuffix(baseName, ext) + ".pklz"
	} else {
		outName = baseName + ".pklz"
	}
	
	
	outPath := filepath.Join(filepath.Dir(inputFile), outName)

	
	outFile, err := os.Create(outPath)
	if err != nil {
		fmt.Printf("Error creating output file: %v\n", err)
		return
	}
	defer outFile.Close()

	// 写入头
	if _, err := outFile.Write(header); err != nil {
		fmt.Printf("Error writing header: %v\n", err)
		return
	}
	
	// 写入数据
	if _, err := outFile.Write(data); err != nil {
		fmt.Printf("Error writing data: %v\n", err)
		return
	}

	fmt.Printf("Success! Created: %s\n", outName)
}