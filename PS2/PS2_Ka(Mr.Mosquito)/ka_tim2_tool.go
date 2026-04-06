// TIM2 document
// https://openkh.dev/common/tm2.html

package main

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type TIM2Header struct {
	MagicCode    [4]byte
	Version      uint8
	Format       uint8
	PictureCount uint16
	Reserved1    uint32
	Reserved2    uint32
}

type PictureHeader struct {
	TotalSize   uint32
	PictureSize uint32
	HeaderSize  uint16
	ColorCount  uint16
}

type ExtractInfo struct {
	Index       int    `json:"index"`
	Filename    string `json:"filename"`
	OffsetStart string `json:"offset_start"`
	OffsetEnd   string `json:"offset_end"`
	Size        int    `json:"size"`
}

type ExtractRecord struct {
	ExtractFiles []ExtractInfo `json:"extract_files"`
}

func extractTIM2(file *os.File, offset int64, outDir string, index int) (ExtractInfo, error) {
	startOffset := offset

	magicBytes := make([]byte, 4)
	if _, err := file.ReadAt(magicBytes, offset); err != nil {
		return ExtractInfo{}, fmt.Errorf("reading magic failed: %v", err)
	}

	fmt.Printf("\n=== TIM2 Details ===\n")
	fmt.Printf("Offset: 0x%X\n", offset)
	fmt.Printf("Magic bytes: % X\n", magicBytes)

	if string(magicBytes) != "TIM2" {
		return ExtractInfo{}, fmt.Errorf("invalid TIM2 magic")
	}

	headerData := make([]byte, 12)
	if _, err := file.ReadAt(headerData, offset+4); err != nil {
		return ExtractInfo{}, fmt.Errorf("reading header data failed: %v", err)
	}

	version := headerData[0]
	format := headerData[1]
	pictureCount := binary.LittleEndian.Uint16(headerData[2:4])

	fmt.Printf("Version: 0x%X\n", version)
	fmt.Printf("Format: 0x%X\n", format)
	fmt.Printf("PictureCount: 0x%X\n", pictureCount)

	picHeaderData := make([]byte, 16)
	if _, err := file.ReadAt(picHeaderData, offset+16); err != nil {
		return ExtractInfo{}, fmt.Errorf("reading picture header failed: %v", err)
	}

	totalSize := binary.LittleEndian.Uint32(picHeaderData[0:4])
	pictureSize := binary.LittleEndian.Uint32(picHeaderData[4:8])
	headerSize := binary.LittleEndian.Uint16(picHeaderData[8:10])
	colorCount := binary.LittleEndian.Uint16(picHeaderData[10:12])

	fmt.Printf("Total Size: %d (0x%X)\n", totalSize, totalSize)
	fmt.Printf("Picture Size: %d (0x%X)\n", pictureSize, pictureSize)
	fmt.Printf("Header Size: %d (0x%X)\n", headerSize, headerSize)
	fmt.Printf("Color Count: %d (0x%X)\n", colorCount, colorCount)

	if totalSize < 32 || totalSize > 10*1024*1024 {
		return ExtractInfo{}, fmt.Errorf("suspicious file size: %d", totalSize)
	}

	outPath := filepath.Join(outDir, fmt.Sprintf("%03d.tm2", index))
	outFile, err := os.Create(outPath)
	if err != nil {
		return ExtractInfo{}, fmt.Errorf("create output file failed: %v", err)
	}
	defer outFile.Close()

	data := make([]byte, totalSize)
	if _, err := file.ReadAt(data, startOffset); err != nil {
		return ExtractInfo{}, fmt.Errorf("reading data failed: %v", err)
	}

	if _, err := outFile.Write(data); err != nil {
		return ExtractInfo{}, fmt.Errorf("writing data failed: %v", err)
	}

	fmt.Printf("Successfully extracted to: %s\n", outPath)
	fmt.Printf("=== Extraction complete ===\n")

	return ExtractInfo{
		Index:       index,
		Filename:    fmt.Sprintf("%03d.tm2", index),
		OffsetStart: fmt.Sprintf("0x%X", startOffset),
		OffsetEnd:   fmt.Sprintf("0x%X", startOffset+int64(totalSize)),
		Size:        int(totalSize),
	}, nil
}

func parseOffset(offset int64) int64 {
	return offset
}

func isValidFileSize(size uint32) bool {
	return size >= 32 && size <= 10*1024*1024
}

func createOutputDir(inputPath string) (string, error) {
	baseDir := filepath.Base(inputPath)
	baseDir = baseDir[:len(baseDir)-len(filepath.Ext(baseDir))]

	err := os.MkdirAll(baseDir, 0755)
	if err != nil {
		return "", fmt.Errorf("failed to create output directory: %v", err)
	}

	return baseDir, nil
}

func saveJsonRecord(record ExtractRecord, outDir string) error {
	jsonData, err := json.MarshalIndent(record, "", "  ")
	if err != nil {
		return fmt.Errorf("JSON serialization error: %v", err)
	}

	jsonPath := filepath.Join(outDir, "extract_info.json")
	if err := os.WriteFile(jsonPath, jsonData, 0644); err != nil {
		return fmt.Errorf("failed to write JSON file: %v", err)
	}

	return nil
}

func readJsonRecord(jsonPath string) (ExtractRecord, error) {
	var record ExtractRecord

	jsonData, err := os.ReadFile(jsonPath)
	if err != nil {
		return record, fmt.Errorf("failed to read JSON file: %v", err)
	}

	if err := json.Unmarshal(jsonData, &record); err != nil {
		return record, fmt.Errorf("JSON parsing error: %v", err)
	}

	return record, nil
}

func findTargetFileInfo(record ExtractRecord, filename string) (ExtractInfo, bool) {
	for _, info := range record.ExtractFiles {
		if info.Filename == filename {
			return info, true
		}
	}
	return ExtractInfo{}, false
}

func validateFileSize(file *os.File, expectedSize int) error {
	fileInfo, err := file.Stat()
	if err != nil {
		return fmt.Errorf("failed to get file info: %v", err)
	}

	if int(fileInfo.Size()) != expectedSize {
		return fmt.Errorf("file size mismatch! Expected: %d, Actual: %d", expectedSize, fileInfo.Size())
	}

	return nil
}

func importTIM2(sourceFile *os.File, targetFile *os.File, offset int64, size int) error {
	data := make([]byte, size)
	if _, err := sourceFile.Read(data); err != nil {
		return fmt.Errorf("failed to read source file: %v", err)
	}

	if _, err := targetFile.WriteAt(data, offset); err != nil {
		return fmt.Errorf("failed to write target file: %v", err)
	}

	return nil
}

func extractMode(inputPath string) {
	outDir, err := createOutputDir(inputPath)
	if err != nil {
		fmt.Println(err)
		return
	}

	file, err := os.Open(inputPath)
	if err != nil {
		fmt.Printf("failed to open file: %v\n", err)
		return
	}
	defer file.Close()

	fileInfo, err := file.Stat()
	if err != nil {
		fmt.Printf("failed to get file info: %v\n", err)
		return
	}
	fileSize := fileInfo.Size()

	var record ExtractRecord
	currentOffset := int64(0)
	index := 0

	var tim2Positions []int64
	buffer := make([]byte, 4)
	for currentOffset < fileSize {
		_, err := file.ReadAt(buffer, currentOffset)
		if err != nil {
			break
		}

		if string(buffer) == "TIM2" {
			tim2Positions = append(tim2Positions, currentOffset)
		}
		currentOffset += 16
	}

	for i, startOffset := range tim2Positions {
		var endOffset int64
		if i < len(tim2Positions)-1 {
			endOffset = tim2Positions[i+1] - 1
		} else {
			endOffset = fileSize - 1
		}

		size := endOffset - startOffset + 1

		outPath := filepath.Join(outDir, fmt.Sprintf("%03d.tm2", index))
		outFile, err := os.Create(outPath)
		if err != nil {
			fmt.Printf("failed to create output file: %v\n", err)
			continue
		}

		data := make([]byte, size)
		if _, err := file.ReadAt(data, startOffset); err != nil {
			fmt.Printf("failed to read data: %v\n", err)
			outFile.Close()
			continue
		}

		if _, err := outFile.Write(data); err != nil {
			fmt.Printf("failed to write data: %v\n", err)
			outFile.Close()
			continue
		}
		outFile.Close()

		info := ExtractInfo{
			Index:       index,
			Filename:    fmt.Sprintf("%03d.tm2", index),
			OffsetStart: fmt.Sprintf("0x%X", startOffset),
			OffsetEnd:   fmt.Sprintf("0x%X", endOffset),
			Size:        int(size),
		}
		record.ExtractFiles = append(record.ExtractFiles, info)

		fmt.Printf("\nExtract TIM2: %s\n", info.Filename)
		fmt.Printf("Start Offset: %s\n", info.OffsetStart)
		fmt.Printf("End Offset: %s\n", info.OffsetEnd)
		fmt.Printf("File Size: %d bytes\n", info.Size)

		index++
	}

	if err := saveJsonRecord(record, outDir); err != nil {
		fmt.Println(err)
		return
	}

	fmt.Printf("\nExtraction complete! Found %d TIM2 files\n", index)
}

func importMode(tm2Path, jsonPath, binPath string) {
	tm2Filename := filepath.Base(tm2Path)

	record, err := readJsonRecord(jsonPath)
	if err != nil {
		fmt.Println(err)
		return
	}

	targetInfo, found := findTargetFileInfo(record, tm2Filename)
	if !found {
		fmt.Printf("record for file %s not found in JSON\n", tm2Filename)
		return
	}

	sourceFile, err := os.Open(tm2Path)
	if err != nil {
		fmt.Printf("failed to open source file: %v\n", err)
		return
	}
	defer sourceFile.Close()

	startOffset, err := strconv.ParseInt(targetInfo.OffsetStart[2:], 16, 64)
	if err != nil {
		fmt.Printf("failed to parse start offset: %v\n", err)
		return
	}

	endOffset, err := strconv.ParseInt(targetInfo.OffsetEnd[2:], 16, 64)
	if err != nil {
		fmt.Printf("failed to parse end offset: %v\n", err)
		return
	}

	expectedSize := int(endOffset - startOffset + 1)
	if err := validateFileSize(sourceFile, expectedSize); err != nil {
		fmt.Println(err)
		return
	}

	targetFile, err := os.OpenFile(binPath, os.O_RDWR, 0644)
	if err != nil {
		fmt.Printf("failed to open target file: %v\n", err)
		return
	}
	defer targetFile.Close()

	if err := importTIM2(sourceFile, targetFile, startOffset, expectedSize); err != nil {
		fmt.Println(err)
		return
	}
		fmt.Printf("Successfully imported %s to %s at position 0x%X\n", tm2Filename, binPath, startOffset)
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: tim2_extractor -e <input.bin>")
		fmt.Println("       tim2_extractor -i <input.tm2> -j <info.json> -b <target.bin>")
		return
	}

	mode := os.Args[1]

	switch mode {
	case "-e":
		if len(os.Args) != 3 {
			fmt.Println("Usage: ka_tim2_tool -e <input.bin>")
			return
		}
		extractMode(os.Args[2])
	case "-i":
		if len(os.Args) != 7 || os.Args[3] != "-j" || os.Args[5] != "-b" {
			fmt.Println("Usage: ka_tim2_tool -i <input.tm2> -j <info.json> -b <target.bin>")
			return
		}
		importMode(os.Args[2], os.Args[4], os.Args[6])
	default:
		fmt.Println("Invalid mode. Use -e for extract or -i for import")
	}
}