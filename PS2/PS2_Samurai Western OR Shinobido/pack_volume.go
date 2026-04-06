package main

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"hash/fnv"
	"io"
	"log"
	"os"
	"path/filepath"
)

type FileMapping struct {
	ExtractedPath string `json:"extracted_path"`
	OriginalPath  string `json:"original_path"`
}

type PackEntry struct {
	OriginalPath string
	Data         []byte
	NameHash     uint32
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

func computeNameHash(name string) uint32 {
	h := fnv.New32a()
	h.Write([]byte(name))
	return h.Sum32()
}

func writeBEUint32(w io.Writer, val uint32) error {
	return binary.Write(w, binary.BigEndian, val)
}

func collectFiles(inputDir string) ([]PackEntry, error) {
	var entries []PackEntry

	mappingFile := filepath.Join(inputDir, "file_mapping.json")
	extractedToOriginal := make(map[string]string)
	if data, err := os.ReadFile(mappingFile); err == nil {
		var mappings []FileMapping
		if json.Unmarshal(data, &mappings) == nil {
			for _, m := range mappings {
				extractedToOriginal[m.ExtractedPath] = m.OriginalPath
			}
			fmt.Printf("Loaded %d file mappings\n", len(mappings))
		}
	}

	err := filepath.Walk(inputDir, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return err
		}
		if filepath.Base(path) == "file_mapping.json" || filepath.Base(path) == "archive_metadata.json" {
			return nil
		}

		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}

		relPath, _ := filepath.Rel(inputDir, path)
		relPath = filepath.ToSlash(relPath)

		originalPath := relPath
		if mapped, exists := extractedToOriginal[relPath]; exists {
			originalPath = mapped
			fmt.Printf("  [RESTORE] %s -> %s\n", relPath, originalPath)
		}

		entries = append(entries, PackEntry{
			OriginalPath: originalPath,
			Data:         data,
			NameHash:     computeNameHash(originalPath),
		})
		return nil
	})

	return entries, err
}

func packVolume(inputDir string, outputFile string) error {
	fmt.Printf("Collecting files from: %s\n", inputDir)

	entries, err := collectFiles(inputDir)
	if err != nil {
		return fmt.Errorf("failed to collect files: %w", err)
	}
	if len(entries) == 0 {
		return fmt.Errorf("no files found")
	}

	fmt.Printf("Found %d files\n", len(entries))

	metadataFile := filepath.Join(inputDir, "archive_metadata.json")
	if data, err := os.ReadFile(metadataFile); err == nil {
		var metadata ArchiveMetadata
		if json.Unmarshal(data, &metadata) == nil {
			fmt.Printf("Loaded metadata with original order\n")

			entryMap := make(map[string]*PackEntry)
			for i := range entries {
				entryMap[filepath.ToSlash(entries[i].OriginalPath)] = &entries[i]
			}

			orderedEntries := make([]PackEntry, 0, len(metadata.FileOrder))
			for _, fileOrder := range metadata.FileOrder {
				if entry, exists := entryMap[filepath.ToSlash(fileOrder.Filename)]; exists {
					entry.NameHash = fileOrder.NameHash
					orderedEntries = append(orderedEntries, *entry)
				}
			}

			entries = orderedEntries
			fmt.Printf("Reordered %d files\n", len(entries))
		}
	} else {
		fmt.Printf("Warning: No metadata found, files may not work!\n")
	}

	fmt.Println()

	f, err := os.Create(outputFile)
	if err != nil {
		return err
	}
	defer f.Close()

	const alignment = 2048
	magic := []byte{0xfa, 0xde, 0xba, 0xbe}
	headerSize := 4 + 16
	entrySize := 24
	dataOffset := uint32(headerSize + len(entries)*entrySize)

	type EntryOffset struct {
		FileOffset, NameOffset uint32
	}
	offsets := make([]EntryOffset, len(entries))

	currentOffset := uint32(0)
	for i, entry := range entries {
		if currentOffset%alignment != 0 {
			currentOffset = ((currentOffset / alignment) + 1) * alignment
		}
		offsets[i].FileOffset = currentOffset
		currentOffset += uint32(len(entry.Data))
		offsets[i].NameOffset = currentOffset
		currentOffset += uint32(len(entry.OriginalPath)) + 1
	}
	totalDataSize := currentOffset

	f.Write(magic)
	filesCount := uint32(len(entries))
	writeBEUint32(f, filesCount)
	writeBEUint32(f, filesCount)
	writeBEUint32(f, dataOffset)
	writeBEUint32(f, totalDataSize)

	fmt.Printf("Header: count=%d, offset=0x%08X, size=0x%08X (%.2f MB)\n\n",
		filesCount, dataOffset, totalDataSize, float64(totalDataSize)/1024/1024)

	fmt.Printf("Writing entries...\n")
	for i, entry := range entries {
		writeBEUint32(f, entry.NameHash)
		writeBEUint32(f, offsets[i].FileOffset)
		writeBEUint32(f, uint32(len(entry.Data)))
		writeBEUint32(f, 0)
		writeBEUint32(f, offsets[i].NameOffset)
		writeBEUint32(f, uint32(len(entry.OriginalPath))+1)
		fmt.Printf("  [%4d] %-50s (%10d bytes)\n", i, entry.OriginalPath, len(entry.Data))
	}

	fmt.Printf("\nWriting data...\n")
	for _, entry := range entries {
		currentPos, _ := f.Seek(0, io.SeekCurrent)
		if pad := alignment - (uint32(currentPos)-dataOffset)%alignment; pad != alignment {
			f.Write(make([]byte, pad))
		}
		f.Write(entry.Data)
		f.Write(append([]byte(entry.OriginalPath), 0))
	}

	absPath, _ := filepath.Abs(outputFile)
	fmt.Printf("\nComplete: %s\n", absPath)
	return nil
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: pack_volume <input_dir> [output_file]")
		os.Exit(1)
	}

	inputDir := os.Args[1]
	outputFile := "volume_new.dat"
	if len(os.Args) > 2 {
		outputFile = os.Args[2]
	}

	if info, err := os.Stat(inputDir); os.IsNotExist(err) || !info.IsDir() {
		fmt.Printf("Error: Directory not found: %s\n", inputDir)
		os.Exit(1)
	}

	if _, err := os.Stat(outputFile); err == nil {
		fmt.Printf("Warning: %s will be overwritten\n", outputFile)
	}

	if err := packVolume(inputDir, outputFile); err != nil {
		log.Fatalf("Error: %v", err)
	}
}
