package main

import (
	"bytes"
	"encoding/binary"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

//MPEg常量
const (
	PackStartCode      = 0x000001BA
	SystemHeaderCode   = 0x000001BB
	ProgramEndCode     = 0x000001B9
	PacketStartPrefix  = 0x00000100 
	SectorSize         = 2048
)

func main() {
	scanMode := flag.Bool("scan", false, "Enable scan-only mode")
	verbose := flag.Bool("v", false, "Show detailed parsing logs")
	flag.Parse()

	args := flag.Args()
	if len(args) < 1 {
		fmt.Println("Usage: pss_tool <input_file> [-scan] [-v]")
		return
	}

	inputFile := args[0]
	file, err := os.Open(inputFile)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}
	defer file.Close()

	fileInfo, _ := file.Stat()
	fileSize := fileInfo.Size()
	
	outputDir := filepath.Join(filepath.Dir(inputFile), "extracted_pss")
	if !*scanMode {
		os.MkdirAll(outputDir, 0755)
	}

	bufSize := 1024 * 1024 
	buf := make([]byte, bufSize)
	offset := int64(0)
	pssCount := 0
	targetSig := []byte{0x00, 0x00, 0x01, 0xBA}

	fmt.Printf("Scanning %s...\n\n", inputFile)

	for offset < fileSize {
		n, err := file.ReadAt(buf, offset)
		if err != nil && err != io.EOF { break }
		if n < 4 { break }

		idx := bytes.Index(buf[:n], targetSig)
		if idx != -1 {
			pssStart := offset + int64(idx)
			
			// 发现疑似开头，立即打印（如果开启了 verbose）
			if *verbose {
				fmt.Printf("[DEBUG] Potential PSS start at 0x%X, validating...\n", pssStart)
			}

			// 尝试解析并寻找结尾
			pssEnd, err := findMpegEnd(file, pssStart, *verbose)
			
			if err == nil {
				pssSize := pssEnd - pssStart
				lba := pssStart / SectorSize
				
				fmt.Printf("[FOUND PSS FILE] Index: %03d | LBA: %-7d | Hex: 0x%-9X | Size: %-9d bytes\n", 
					pssCount, lba, pssStart, pssSize)
				
				if !*scanMode {
					outName := filepath.Join(outputDir, fmt.Sprintf("%03d_%X.pss", pssCount, pssStart))
					extractChunk(file, pssStart, pssSize, outName)
				}
				pssCount++
				offset = pssEnd // 成功则跳过整个文件
				continue
			} else {
				if *verbose {
					fmt.Printf("[DEBUG] Validation failed at 0x%X: %v\n", pssStart, err)
				}
				offset += int64(idx) + 1 // 失败则继续向后移动 1 字节
			}
		} else {
			offset += int64(n) - 3
		}
	}
	fmt.Printf("\nDone. Found %d PSS files.\n", pssCount)
}

func findMpegEnd(f *os.File, startAddr int64, verbose bool) (int64, error) {
	curr := startAddr
	headerBuf := make([]byte, 16) 

	maxSearch := startAddr + 1024*1024*1024 

	for curr < maxSearch {
		_, err := f.ReadAt(headerBuf, curr)
		if err != nil { return 0, err }

		code := binary.BigEndian.Uint32(headerBuf[0:4])

		switch code {
		case PackStartCode: // 0xBA
			stuffingLen := int64(headerBuf[13] & 0x07)
			curr += 14 + stuffingLen

		case ProgramEndCode: // 0xB9
			return curr + 4, nil

		case SystemHeaderCode: // 0xBB
			hLen := int64(binary.BigEndian.Uint16(headerBuf[4:6]))
			curr += 6 + hLen

		default:
			
			if (code & 0xFFFFFF00) == PacketStartPrefix {
				pktLen := int64(binary.BigEndian.Uint16(headerBuf[4:6]))
				if pktLen == 0 {
					
					curr += 4 
				} else {
					curr += 6 + pktLen
				}
			} else {
				return 0, fmt.Errorf("sync lost (found 0x%08X)", code)
			}
		}
	}
	return 0, fmt.Errorf("reached search limit")
}

func extractChunk(f *os.File, offset, size int64, outPath string) {
	out, _ := os.Create(outPath)
	defer out.Close()
	f.Seek(offset, 0)
	io.CopyN(out, f, size)
}