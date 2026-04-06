package main

import (
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type PackItem struct {
	Path     string
	Name     string
	Size     int64
	Offset   uint32
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: pak_packer <input_folder> <MAGIC_TYPE>")
		fmt.Println("Example: pak_packer m_title_j MENU")
		return
	}

	inputDir := os.Args[1]
	magicStr := os.Args[2]

	if len(magicStr) != 4 {
		fmt.Println("Error: MAGIC_TYPE must be exactly 4 characters.")
		return
	}

	var files []PackItem
	entries, err := os.ReadDir(inputDir)
	if err != nil {
		fmt.Printf("Error reading directory: %v\n", err)
		return
	}

	for _, entry := range entries {
		if entry.IsDir() {
			continue 
		}
		
		name := entry.Name()
		lowerName := strings.ToLower(name)


		//只打包.bin和.pklz文件
		ext := filepath.Ext(lowerName)
		if ext != ".bin" && ext != ".pklz" {
			continue
		}

		info, err := entry.Info()
		if err != nil {
			continue
		}

		files = append(files, PackItem{
			Path: filepath.Join(inputDir, name),
			Name: name,
			Size: info.Size(),
		})
	}

	if len(files) == 0 {
		fmt.Println("Error: No valid (.bin/.pklz) files found in directory.")
		return
	}

	sort.Slice(files, func(i, j int) bool {
		return files[i].Name < files[j].Name
	})

	fmt.Printf("Found %d valid files. Packing...\n", len(files))

	//计算偏移量
	fileCount := uint32(len(files))
	headerSize := uint32(16)
	offsetTableSize := (fileCount + 1) * 4
	
	currentOffset := headerSize + offsetTableSize
	currentOffset = alignTo16(currentOffset)

	for i := range files {
		files[i].Offset = currentOffset
		nextOffset := currentOffset + uint32(files[i].Size)
		currentOffset = alignTo16(nextOffset)
	}
	totalSize := currentOffset

	//创建PAK
	outName := filepath.Base(inputDir) + ".pak"
	outFile, err := os.Create(outName)
	if err != nil {
		fmt.Printf("Error creating output file: %v\n", err)
		return
	}
	defer outFile.Close()

	//写入头
	outFile.WriteString(magicStr) 
	outFile.Write([]byte{0, 0, 0, 0})
	outFile.Write([]byte{0, 0, 0, 0})
	binary.Write(outFile, binary.LittleEndian, fileCount)

	//写入子文件的偏移表，数量为N+1
	for _, f := range files {
		binary.Write(outFile, binary.LittleEndian, f.Offset)
	}
	binary.Write(outFile, binary.LittleEndian, totalSize)


	currentPos, _ := outFile.Seek(0, io.SeekCurrent)

	for _, f := range files {
		paddingNeeded := int64(f.Offset) - currentPos
		if paddingNeeded > 0 {
			outFile.Write(make([]byte, paddingNeeded))
		}

		data, err := os.ReadFile(f.Path)
		if err != nil {
			fmt.Printf("Error reading source file %s: %v\n", f.Name, err)
			return
		}
		outFile.Write(data)
		fmt.Printf("  Packed: %s (Offset: 0x%X, Size: %d)\n", f.Name, f.Offset, len(data))

		currentPos, _ = outFile.Seek(0, io.SeekCurrent)
	}

	finalPadding := int64(totalSize) - currentPos
	if finalPadding > 0 {
		outFile.Write(make([]byte, finalPadding))
	}

	fmt.Printf("Success! Created %s (Total Size: %d)\n", outName, totalSize)
}

func alignTo16(n uint32) uint32 {
	return (n + 15) & ^uint32(15)
}