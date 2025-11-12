package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
)

// FileEntry stores metadata for each file within the volume.dat archive.
type FileEntry struct {
	Index      int
	NameHash   uint32
	Offset     int64 // Use int64 to match Go's file I/O standards
	Size       int64
	NameOffset int64
	NameSize   int64
}

// readBEUint32 is a helper to read a 4-byte big-endian unsigned integer.
func readBEUint32(r io.Reader) (uint32, error) {
	var val uint32
	err := binary.Read(r, binary.BigEndian, &val)
	return val, err
}

// unpackVolume is the core unpacking function.
func unpackVolume(volumePath string, outputDir string) error {
	// Create the output directory if it doesn't exist.
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return fmt.Errorf("failed to create output directory %s: %w", outputDir, err)
	}

	// Open the volume.dat file for reading.
	f, err := os.Open(volumePath)
	if err != nil {
		return fmt.Errorf("failed to open file %s: %w", volumePath, err)
	}
	defer f.Close()

	// 1. Verify the magic number.
	magic := make([]byte, 4)
	if _, err := io.ReadFull(f, magic); err != nil {
		return fmt.Errorf("failed to read magic number: %w", err)
	}

	expectedMagic := []byte{0xfa, 0xde, 0xba, 0xbe}
	if !bytes.Equal(magic, expectedMagic) {
		fmt.Printf("Invalid magic: %x\n", magic)
		fmt.Printf("   Expected: %x\n", expectedMagic)
		return fmt.Errorf("magic number mismatch")
	}
	fmt.Printf("Magic verified: %x\n", magic)

	// 2. Read the archive header.
	filesCount1, err := readBEUint32(f)
	if err != nil {
		return err
	}
	filesCount2, err := readBEUint32(f)
	if err != nil {
		return err
	}
	dataOff, err := readBEUint32(f)
	if err != nil {
		return err
	}
	dataSize, err := readBEUint32(f)
	if err != nil {
		return err
	}

	fmt.Printf("Files count: %d (second: %d)\n", filesCount1, filesCount2)
	fmt.Printf("Data offset: 0x%08X\n", dataOff)
	fmt.Printf("Data size: 0x%08X (%.2f MB)\n", dataSize, float64(dataSize)/1024/1024)
	fmt.Println()

	// 3. Read the file entries.
	entries := make([]FileEntry, 0, filesCount1)
	for i := 0; i < int(filesCount1); i++ {
		nameHash, err := readBEUint32(f)
		if err != nil {
			return fmt.Errorf("failed to read name_hash for entry %d: %w", i, err)
		}
		offset, err := readBEUint32(f)
		if err != nil {
			return fmt.Errorf("failed to read offset for entry %d: %w", i, err)
		}
		size, err := readBEUint32(f)
		if err != nil {
			return fmt.Errorf("failed to read size for entry %d: %w", i, err)
		}
		_, err = readBEUint32(f) // Read and discard the zero field.
		if err != nil {
			return fmt.Errorf("failed to read zero field for entry %d: %w", i, err)
		}
		nameOff, err := readBEUint32(f)
		if err != nil {
			return fmt.Errorf("failed to read name_off for entry %d: %w", i, err)
		}
		namesz, err := readBEUint32(f)
		if err != nil {
			return fmt.Errorf("failed to read namesz for entry %d: %w", i, err)
		}

		entries = append(entries, FileEntry{
			Index:      i,
			NameHash:   nameHash,
			Offset:     int64(offset) + int64(dataOff),
			Size:       int64(size),
			NameOffset: int64(nameOff) + int64(dataOff),
			NameSize:   int64(namesz),
		})
	}

	// 4. Extract files.
	fmt.Printf("Extracting %d files...\n\n", len(entries))

	for _, entry := range entries {
		// Read the filename.
		if _, err := f.Seek(entry.NameOffset, io.SeekStart); err != nil {
			fmt.Printf("  [ERROR] Cannot seek to filename for entry %d: %v\n", entry.Index, err)
			continue
		}
		nameBytes := make([]byte, entry.NameSize)
		if _, err := io.ReadFull(f, nameBytes); err != nil {
			fmt.Printf("  [ERROR] Cannot read filename for entry %d: %v\n", entry.Index, err)
			continue
		}
		// Trim trailing null bytes.
		filename := string(bytes.TrimRight(nameBytes, "\x00"))

		// Read the file data.
		if _, err := f.Seek(entry.Offset, io.SeekStart); err != nil {
			fmt.Printf("  [ERROR] Cannot seek to file data for %s: %v\n", filename, err)
			continue
		}
		data := make([]byte, entry.Size)
		if _, err := io.ReadFull(f, data); err != nil {
			fmt.Printf("  [ERROR] Cannot read file data for %s: %v\n", filename, err)
			continue
		}

		// Write the file to disk.
		outputFile := filepath.Join(outputDir, filename)

		// Skip if a directory with the same name already exists.
		if info, err := os.Stat(outputFile); err == nil && info.IsDir() {
			fmt.Printf("  [SKIP] %s (conflicts with an existing directory)\n", filename)
			continue
		}

		// Create parent directories as needed.
		parentDir := filepath.Dir(outputFile)
		if err := os.MkdirAll(parentDir, 0755); err != nil {
			fmt.Printf("  [ERROR] %s: Failed to create directory %s: %v\n", filename, parentDir, err)
			continue
		}

		// Write data to the file.
		if err := os.WriteFile(outputFile, data, 0644); err != nil {
			fmt.Printf("  [ERROR] %s: Failed to write file: %v\n", filename, err)
			continue
		}

		fmt.Printf("  [%4d] %-50s (%10d bytes)\n", entry.Index, filename, entry.Size)
	}

	absPath, _ := filepath.Abs(outputDir)
	fmt.Printf("\nExtraction complete! Files saved to: %s\n", absPath)
	return nil
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: unpack_volume <volume.dat> [output_dir]")
		os.Exit(1)
	}

	volumeFile := os.Args[1]
	outputDir := "extracted"
	if len(os.Args) > 2 {
		outputDir = os.Args[2]
	}

	if _, err := os.Stat(volumeFile); os.IsNotExist(err) {
		fmt.Printf("Error: File not found: %s\n", volumeFile)
		os.Exit(1)
	}

	if err := unpackVolume(volumeFile, outputDir); err != nil {
		// Specific error messages are printed within the function.
		log.Fatalf("A fatal error occurred during unpacking: %v", err)
	}
}