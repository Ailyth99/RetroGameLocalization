package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

// 配置常量 (基于你的逆向结果)
const (
	TableStart   = 0x11E580 //表格起始
	TableEnd     = 0x11FA80 //表格结束
	EntrySize    = 64       //单条记录字节数
	AddrModifier = 0xFEFF8  //内存地址 -> ELF地址的差值
	SectorSize   = 2048     //ISO扇区大小
)

func main() {
	if len(os.Args) < 4 {
		printUsage()
		return
	}

	mode := os.Args[1]
	
	switch mode {
	case "-export":
		if len(os.Args) < 4 {
			printUsage()
			return
		}
		runExport(os.Args[2], os.Args[3])
	case "-import":
		if len(os.Args) < 5 {
			fmt.Println("Usage: tool -import <game.elf> <game.iso> <new_file_path>")
			return
		}
		runImport(os.Args[2], os.Args[3], os.Args[4])
	default:
		printUsage()
	}
}

func printUsage() {
	fmt.Println("Usage:")
	fmt.Println("  Export: tool -export <game.elf> <game.iso>")
	fmt.Println("  Import: tool -import <game.elf> <game.iso> <new_file_path>")
}

//导出模式
func runExport(elfPath, isoPath string) {
	elfFile, err := os.Open(elfPath)
	if err != nil { panic(err) }
	defer elfFile.Close()

	isoFile, err := os.Open(isoPath)
	if err != nil { panic(err) }
	defer isoFile.Close()

	outDir := "extract"
	os.MkdirAll(outDir, 0755)

	fmt.Println("[EXPORT MODE]")
	iterateTable(elfFile, func(entryOffset int64, name string, lba, size uint32) {
		cleanName := cleanPath(name)
		fullPath := filepath.Join(outDir, cleanName)

		fmt.Printf("Extracting: %s (LBA: %d, Size: %d)\n", cleanName, lba, size)
		
		os.MkdirAll(filepath.Dir(fullPath), 0755)
		
		
		outFile, _ := os.Create(fullPath)
		defer outFile.Close()
		isoFile.Seek(int64(lba)*SectorSize, 0)
		io.CopyN(outFile, isoFile, int64(size))
	})
	fmt.Println("Done.")
}

//导入模式
func runImport(elfPath, isoPath, importFilePath string) {
	elfFile, err := os.OpenFile(elfPath, os.O_RDWR, 0644)
	if err != nil { panic(err) }
	defer elfFile.Close()

	isoFile, err := os.OpenFile(isoPath, os.O_RDWR, 0644)
	if err != nil { panic(err) }
	defer isoFile.Close()

	newData, err := os.ReadFile(importFilePath)
	if err != nil { panic(err) }
	newSize := int64(len(newData))
	
	targetName := filepath.Base(importFilePath)
	fmt.Printf("[IMPORT MODE] Target: %s (New Size: %d)\n", targetName, newSize)

	found := false

	iterateTable(elfFile, func(entryOffset int64, name string, lba, oldSize uint32) {
		if found { return } 

		 
		elfBaseName := filepath.Base(cleanPath(name))
		
		if strings.EqualFold(elfBaseName, targetName) {
			found = true
			fmt.Printf("Found match in ELF table!\n")
			fmt.Printf("  Internal Name: %s\n", name)
			fmt.Printf("  Original Size: %d bytes\n", oldSize)
			fmt.Printf("  LBA: %d (Offset: 0x%X)\n", lba, int64(lba)*SectorSize)

			
			if newSize > int64(oldSize) {
				fmt.Printf("ERROR: New file is too big! Max allowed: %d\n", oldSize)
				return
			}

			
			fmt.Println("  -> Writing data to ISO...")
			isoOffset := int64(lba) * SectorSize
			isoFile.Seek(isoOffset, 0)
			isoFile.Write(newData)

		
			paddingSize := int64(oldSize) - newSize
			if paddingSize > 0 {
				fmt.Printf("  -> Padding %d bytes with zeros...\n", paddingSize)
			
				zeroBuf := make([]byte, 1024)
				remaining := paddingSize
				for remaining > 0 {
					writeSize := int64(len(zeroBuf))
					if remaining < writeSize {
						writeSize = remaining
					}
					isoFile.Write(zeroBuf[:writeSize])
					remaining -= writeSize
				}
			}

		
			fmt.Printf("  -> Updating ELF Size record to %d...\n", newSize)
			sizeOffset := entryOffset + 0x10
			elfFile.Seek(sizeOffset, 0)
			binary.Write(elfFile, binary.LittleEndian, uint32(newSize))

			fmt.Println("Import successful!")
		}
	})

	if !found {
		fmt.Printf("Error: File '%s' not found in ELF file table.\n", targetName)
	}
}

func iterateTable(f *os.File, callback func(int64, string, uint32, uint32)) {
	currentOffset := int64(TableStart)
	entryBuf := make([]byte, EntrySize)

	for currentOffset < TableEnd {
		_, err := f.ReadAt(entryBuf, currentOffset)
		if err != nil { break }

		namePtr := binary.LittleEndian.Uint32(entryBuf[0:4])
		lba := binary.LittleEndian.Uint32(entryBuf[8:12])
		size := binary.LittleEndian.Uint32(entryBuf[16:20])

		if namePtr != 0 && size > 0 {
			nameOffset := int64(namePtr) - AddrModifier
			fileName := readString(f, nameOffset)
			
			
			callback(currentOffset, fileName, lba, size)
		}
		currentOffset += EntrySize
	}
}

func readString(f *os.File, offset int64) string {
	var buf bytes.Buffer
	b := make([]byte, 1)
	for {
		f.ReadAt(b, offset)
		if b[0] == 0x00 || b[0] == ';' { break }
		buf.WriteByte(b[0])
		offset++
	}
	return buf.String()
}

func cleanPath(raw string) string {
	s := strings.Replace(raw, "cdrom0:", "", 1)
	s = strings.ReplaceAll(s, "\\", "/")
	s = strings.TrimPrefix(s, "/")
	// 去掉目录里面的文件名后头的版本号 ;1 
	if idx := strings.Index(s, ";"); idx != -1 {
		s = s[:idx]
	}
	return s
}