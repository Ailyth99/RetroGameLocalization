package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
)

type FileEntry struct {
	Index      int
	NameHash   uint32
	Offset     int64
	Size       int64
	NameOffset int64
	NameSize   int64
}

type FileMapping struct {
	ExtractedPath string `json:"extracted_path"`
	OriginalPath  string `json:"original_path"`
}

type ArchiveMetadata struct {
	FilesCount1 uint32      `json:"files_count_1"`
	FilesCount2 uint32      `json:"files_count_2"`
	DataOffset  uint32      `json:"data_offset"`
	DataSize    uint32      `json:"data_size"`
	FileOrder   []FileOrder `json:"file_order"`
}

type FileOrder struct {
	Index    int    `json:"index"`
	Filename string `json:"filename"`
	NameHash uint32 `json:"name_hash"`
	Size     int64  `json:"size"`
}

func readBEUint32(r io.Reader) (uint32, error) {
	var val uint32
	err := binary.Read(r, binary.BigEndian, &val)
	return val, err
}

func unpackVolume(volumePath string, outputDir string) error {
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return fmt.Errorf("failed to create output directory: %w", err)
	}

	f, err := os.Open(volumePath)
	if err != nil {
		return fmt.Errorf("failed to open file: %w", err)
	}
	defer f.Close()

	magic := make([]byte, 4)
	if _, err := io.ReadFull(f, magic); err != nil {
		return fmt.Errorf("failed to read magic: %w", err)
	}

	expectedMagic := []byte{0xfa, 0xde, 0xba, 0xbe}
	if !bytes.Equal(magic, expectedMagic) {
		return fmt.Errorf("magic mismatch")
	}
	fmt.Printf("Magic verified: %x\n", magic)

	filesCount1, _ := readBEUint32(f)
	filesCount2, _ := readBEUint32(f)
	dataOff, _ := readBEUint32(f)
	dataSize, _ := readBEUint32(f)

	fmt.Printf("Files: %d (second: %d)\n", filesCount1, filesCount2)
	fmt.Printf("Data offset: 0x%08X, size: 0x%08X (%.2f MB)\n\n", dataOff, dataSize, float64(dataSize)/1024/1024)

	entries := make([]FileEntry, 0, filesCount1)
	for i := 0; i < int(filesCount1); i++ {
		nameHash, _ := readBEUint32(f)
		offset, _ := readBEUint32(f)
		size, _ := readBEUint32(f)
		readBEUint32(f)
		nameOff, _ := readBEUint32(f)
		namesz, _ := readBEUint32(f)

		entries = append(entries, FileEntry{
			Index:      i,
			NameHash:   nameHash,
			Offset:     int64(offset) + int64(dataOff),
			Size:       int64(size),
			NameOffset: int64(nameOff) + int64(dataOff),
			NameSize:   int64(namesz),
		})
	}

	fmt.Printf("Extracting %d files...\n\n", len(entries))

	var fileMappings []FileMapping
	var metadata ArchiveMetadata
	metadata.FilesCount1 = filesCount1
	metadata.FilesCount2 = filesCount2
	metadata.DataOffset = dataOff
	metadata.DataSize = dataSize
	metadata.FileOrder = make([]FileOrder, 0, len(entries))

	var stats struct {
		extracted, skipped, errors int
		totalSize, skippedSize     int64
	}

	for _, entry := range entries {
		f.Seek(entry.NameOffset, io.SeekStart)
		nameBytes := make([]byte, entry.NameSize)
		io.ReadFull(f, nameBytes)
		filename := string(bytes.TrimRight(nameBytes, "\x00"))

		if filename == "" {
			fmt.Printf("  [SKIP] Entry %d (empty filename, %d bytes)\n", entry.Index, entry.Size)
			stats.skipped++
			stats.skippedSize += entry.Size
			continue
		}

		f.Seek(entry.Offset, io.SeekStart)
		data := make([]byte, entry.Size)
		io.ReadFull(f, data)

		outputFile := filepath.Join(outputDir, filename)
		extractedFilename := filename

		if info, err := os.Stat(outputFile); err == nil && info.IsDir() {
			outputFile += ".file"
			extractedFilename += ".file"
			fmt.Printf("  [RENAME] %s -> %s\n", filename, filepath.Base(outputFile))
			fileMappings = append(fileMappings, FileMapping{extractedFilename, filename})
		}

		os.MkdirAll(filepath.Dir(outputFile), 0755)
		if err := os.WriteFile(outputFile, data, 0644); err != nil {
			fmt.Printf("  [ERROR] %s: %v\n", filename, err)
			stats.errors++
			continue
		}

		fmt.Printf("  [%4d] %-50s (%10d bytes)\n", entry.Index, filename, entry.Size)
		stats.extracted++
		stats.totalSize += entry.Size

		metadata.FileOrder = append(metadata.FileOrder, FileOrder{
			Index:    entry.Index,
			Filename: filename,
			NameHash: entry.NameHash,
			Size:     entry.Size,
		})
	}

	metadataFile := filepath.Join(outputDir, "archive_metadata.json")
	if data, err := json.MarshalIndent(metadata, "", "  "); err == nil {
		os.WriteFile(metadataFile, data, 0644)
		fmt.Printf("\nSaved metadata: %s\n", metadataFile)
	}

	if len(fileMappings) > 0 {
		mappingFile := filepath.Join(outputDir, "file_mapping.json")
		if data, err := json.MarshalIndent(fileMappings, "", "  "); err == nil {
			os.WriteFile(mappingFile, data, 0644)
			fmt.Printf("Saved %d mappings: %s\n", len(fileMappings), mappingFile)
		}
	}

	absPath, _ := filepath.Abs(outputDir)
	fmt.Printf("\n=== Summary ===\n")
	fmt.Printf("Total: %d | Extracted: %d (%.2f MB) | Skipped: %d | Errors: %d\n",
		len(entries), stats.extracted, float64(stats.totalSize)/1024/1024, stats.skipped, stats.errors)
	fmt.Printf("Output: %s\n", absPath)
	return nil
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: unpack_volume <volume.dat> [output_dir]")
		os.Exit(1)
	}

	volumeFile := os.Args[1]
	outputDir := "volume_extracted"
	if len(os.Args) > 2 {
		outputDir = os.Args[2]
	}

	if _, err := os.Stat(volumeFile); os.IsNotExist(err) {
		fmt.Printf("Error: File not found: %s\n", volumeFile)
		os.Exit(1)
	}

	if err := unpackVolume(volumeFile, outputDir); err != nil {
		log.Fatalf("Error: %v", err)
	}
}
