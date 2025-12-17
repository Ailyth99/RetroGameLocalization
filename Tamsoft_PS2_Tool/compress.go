package main

import (
	"encoding/binary"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
)

const (
	DICTIONARY_SIZE    = 4096 // 4096字节滑动窗口范围
	MAX_MATCH_LENGTH   = 18   // Maximum match length (0x0F + 3)
	MIN_MATCH_LENGTH   = 3    // Minimum match length
	INITIAL_DICT_POS = 0xFEE // Initial dictionary write position
)

// findLongestMatch searches the dictionary for the longest match for the data at the current position.

func findLongestMatch(data []byte, currentPos int, dictionary []byte) (bestOffset int, bestLength int) {
	// We only care about the longest possible match we can encode.
	endOfBuffer := currentPos + MAX_MATCH_LENGTH
	if endOfBuffer > len(data) {
		endOfBuffer = len(data)
	}

	// Iterate through every possible starting point in the dictionary.
	for offsetCandidate := 0; offsetCandidate < DICTIONARY_SIZE; offsetCandidate++ {
		currentLength := 0
		// Compare byte by byte to see how long the match is.
		for i := 0; i < endOfBuffer-currentPos; i++ {
			dictIdx := (offsetCandidate + i) & (DICTIONARY_SIZE - 1)
			if dictionary[dictIdx] == data[currentPos+i] {
				currentLength++
			} else {
				break
			}
		}

		// If  found a longer match, record it.
		if currentLength > bestLength {
			bestLength = currentLength
			bestOffset = offsetCandidate
		}
	}
	return
}

// CompressTamsoftLZSS compresses data using the reverse-engineered tamsoft game LZSS algorithm.
func CompressTamsoftLZSS(dataToCompress []byte) ([]byte, error) {
	dictionary := make([]byte, DICTIONARY_SIZE)
	dictPos := INITIAL_DICT_POS
	srcPos := 0

	compressedData := make([]byte, 0, len(dataToCompress)/2) // Pre-allocate for efficiency
	totalSize := len(dataToCompress)

	fmt.Println("Compression started...")

	for srcPos < totalSize {
		// For every 8 blocks, we need a new control byte.
		var controlByte byte
		// Temporary storage for the data of these 8 blocks.
		chunkBlocks := make([]byte, 0, 16) // Max size is 8 blocks * 2 bytes/block = 16

		// Loop 8 times to generate one control byte and its corresponding data blocks.
		for i := 0; i < 8; i++ {
			if srcPos%1024 == 0 {
				fmt.Printf("Processing... %d/%d (%.2f%%)\r", srcPos, totalSize, float64(srcPos)*100.0/float64(totalSize))
			}

			if srcPos >= totalSize {
				break // Stop if we've processed all the data.
			}

			// --- Find the best match 
			offset, length := findLongestMatch(dataToCompress, srcPos, dictionary)

			if length >= MIN_MATCH_LENGTH {
				// --- Case B: Found a valid match, encode as (offset/length) pair ---
				// The control bit is 0, so we do nothing to control_byte (its ith bit is already 0).

				// Encode offset and length (this is the reverse of the decompression logic).
				lengthEncoded := length - MIN_MATCH_LENGTH

				byte1 := byte(offset & 0xFF)
				byte2 := byte(((offset >> 4) & 0xF0) | lengthEncoded)

				chunkBlocks = append(chunkBlocks, byte1, byte2)

				// Update the dictionary with the matched data.
				for j := 0; j < length; j++ {
					b := dataToCompress[srcPos+j]
					dictionary[dictPos] = b
					dictPos = (dictPos + 1) & (DICTIONARY_SIZE - 1)
				}

				srcPos += length
			} else {
				// --- Case A: No good match found, output a literal byte ---
				// Set the ith bit of the control byte to 1.
				controlByte |= (1 << i)

				rawByte := dataToCompress[srcPos]
				chunkBlocks = append(chunkBlocks, rawByte)

				// Update the dictionary with this literal byte.
				dictionary[dictPos] = rawByte
				dictPos = (dictPos + 1) & (DICTIONARY_SIZE - 1)

				srcPos++
			}
		}
		// Write the combined chunk for these 8 blocks to the final result.
		compressedData = append(compressedData, controlByte)
		compressedData = append(compressedData, chunkBlocks...)
	}

	fmt.Printf("\nCompression finished.                                 \n")
	return compressedData, nil
}

func main() {
	if len(os.Args) < 2 || len(os.Args) > 3 {
		fmt.Println("TAMSOFT PS2 GAME compressor")
		fmt.Println("Usage: compress.exe <input_file> [output.cmp]")
		os.Exit(1)
	}

	inputFile := os.Args[1]
	var outputFile string

	if len(os.Args) == 3 {
		outputFile = os.Args[2]
	} else {
		// Auto generate output name
		base := strings.TrimSuffix(inputFile, filepath.Ext(inputFile))
		outputFile = base + ".cmp"
	}

	fmt.Printf("Reading file: %s\n", inputFile)
	dataToCompress, err := os.ReadFile(inputFile)
	if err != nil {
		log.Fatalf("Error: Could not read input file %s: %v", inputFile, err)
	}
	decompressedSize := len(dataToCompress)

	//调用压缩函数
	compressedData, err := CompressTamsoftLZSS(dataToCompress)
	if err != nil {
		log.Fatalf("Compression failed: %v", err)
	}

	// 写入输出文件
	f_out, err := os.Create(outputFile)
	if err != nil {
		log.Fatalf("Error: Could not create output file %s: %v", outputFile, err)
	}
	defer f_out.Close()

	// 写入压缩前大小 4字节到开头
	header := make([]byte, 4)
	binary.LittleEndian.PutUint32(header, uint32(decompressedSize))
	_, err = f_out.Write(header)
	if err != nil {
		log.Fatalf("Error: Failed to write header: %v", err)
	}

	
	_, err = f_out.Write(compressedData)
	if err != nil {
		log.Fatalf("Error: Failed to write compressed data: %v", err)
	}

	fmt.Printf("\nSuccess! Compressed %d bytes into %d bytes.\n", decompressedSize, len(compressedData)+4)
	fmt.Printf("Output saved to: %s\n", outputFile)
}