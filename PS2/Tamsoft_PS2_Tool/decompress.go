package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
)

// DecompressTamsoftLZSS decompress data using a LZSS algorithm reverse-engineered from a   TAMSOFT PS2 game.
//
// params:
//   compressedData: The raw compressed byte stream (without the 4-byte header).
//    decompressedSize: The target size of the decompressed data.
//
// returns:
//   A byte slice containing the decompressed data.
//   An error if the compressed data stream ends prematurely.
func DecompressTamsoftLZSS(compressedData []byte, decompressedSize uint32) ([]byte, error) {
	// Initialize a 4KB (4096-byte) dictionary, which acts as a sliding window.
	dictionary := make([]byte, 4096)

	// This is a key parameter: the initial write position in the dictionary.
	// Reverse engineering shows it's hardcoded to 0xFEE.
	dictPos := 0xFEE

	srcPos := 0
	decompressedData := make([]byte, 0, decompressedSize)

	for len(decompressedData) < int(decompressedSize) {
		// 1. Read an 8-bit control byte.
		// Each bit of this byte determines if the next block is a literal or a match pair.
		if srcPos >= len(compressedData) {
			return nil, fmt.Errorf("warning: compressed data ended unexpectedly")
		}
		controlByte := compressedData[srcPos]
		srcPos++

		// 2. Process the 8 bits of the control byte (from LSB to MSB).
		for i := 0; i < 8; i++ {
			if len(decompressedData) >= int(decompressedSize) {
				break
			}

			// Check if the current bit is a '1' or '0'.
			if (controlByte>>i)&1 == 1 {
				// --- Case A: Control bit is 1 (uncompressed literal byte) ---
				if srcPos >= len(compressedData) {
					return nil, fmt.Errorf("warning: compressed data ended unexpectedly while reading a raw byte")
				}
				b := compressedData[srcPos]
				srcPos++

				decompressedData = append(decompressedData, b)
				dictionary[dictPos] = b
				dictPos = (dictPos + 1) & 0xFFF // Use & 0xFFF for a circular buffer.

			} else {
				// --- Case B: Control bit is 0 (compressed offset/length pair) ---
				if srcPos+1 >= len(compressedData) {
					return nil, fmt.Errorf("warning: compressed data ended unexpectedly while reading an offset/length pair")
				}
				byte1 := compressedData[srcPos]
				byte2 := compressedData[srcPos+1]
				srcPos += 2

				// Decode the offset and length from the 2 bytes.
				offset := int(byte1) | (int(byte2&0xF0) << 4)
				length := int(byte2&0x0F) + 3

				// Copy data from the dictionary.
				for j := 0; j < length; j++ {
					if len(decompressedData) >= int(decompressedSize) {
						break
					}
					copyPos := (offset + j) & 0xFFF
					copyByte := dictionary[copyPos]

					decompressedData = append(decompressedData, copyByte)
					dictionary[dictPos] = copyByte
					dictPos = (dictPos + 1) & 0xFFF
				}
			}
		}
	}

	return decompressedData, nil
}

func main() {
	if len(os.Args) < 2 || len(os.Args) > 3 {
		fmt.Println("TAMSOFT PS2 GAME decompressor")
		fmt.Println("Usage: decompress.exe <input.cmp> [output_file]")
		
		os.Exit(1)
	}

	inputFile := os.Args[1]
	var outputFile string
	autoGenerateOutputName := (len(os.Args) == 2)

	if !autoGenerateOutputName {
		outputFile = os.Args[2]
	}

	fileBytes, err := os.ReadFile(inputFile)
	if err != nil {
		log.Fatalf("Error: Could not read input file %s: %v", inputFile, err)
	}

	if len(fileBytes) < 4 {
		log.Fatal("Error: File is too small to contain a valid header.")
	}

	decompressedSize := binary.LittleEndian.Uint32(fileBytes[0:4])
	compressedData := fileBytes[4:]

	fmt.Printf("Decompressing %s (%d bytes) -> %d bytes...\n", filepath.Base(inputFile), len(compressedData), decompressedSize)

	result, err := DecompressTamsoftLZSS(compressedData, decompressedSize)
	if err != nil {
		log.Fatalf("Decompression failed: %v", err)
	}

	// If the output name needs to be generated, do it now.
	if autoGenerateOutputName {
		base := strings.TrimSuffix(inputFile, filepath.Ext(inputFile))
		extension := ".decmp" 
		// The magic number for .ti files,ti是tamsoft的默认贴图格式，存在D3的simple系列和一些tamsoft开发的其他PS2游戏里面，比如巨大机器人之类的
		magicTI := []byte{0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00}
		if len(result) >= 8 && bytes.Equal(result[:8], magicTI) {
			extension = ".ti"
		}
		outputFile = base + extension
	}

	err = os.WriteFile(outputFile, result, 0644)
	if err != nil {
		log.Fatalf("Error: Could not write to output file %s: %v", outputFile, err)
	}

	fmt.Printf("Success! Decompressed %d bytes to %s\n", len(result), outputFile)

	if len(result) != int(decompressedSize) {
		fmt.Printf("Warning: Final size (%d) does not match header size (%d).\n", len(result), decompressedSize)
	}
}