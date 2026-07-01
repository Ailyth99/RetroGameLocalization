package main

import (
	"encoding/binary"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type Command struct {
	isLit bool
	dist  int
	len   int
	val   byte
}

func decompress(data []byte) ([]byte, error) {
	if len(data) < 2 {
		return nil, fmt.Errorf("data too short")
	}
	winBits := int(data[0])
	if winBits < 8 || winBits > 16 {
		return nil, fmt.Errorf("invalid window bits: %d", winBits)
	}

	winSize := 1 << winBits
	winMask := winSize - 1
	maxLen := 1 << (16 - winBits)

	inIdx := 1
	outBuf := make([]byte, 0, len(data)*2)
	window := make([]byte, winSize)
	writePtr := 0

	for inIdx < len(data) {
		flagByte := data[inIdx]
		inIdx++

		for flagByte != 0 {
			bit := flagByte & 1
			flagByte >>= 1
			if flagByte == 0 {
				break
			}

			if bit == 0 {
				if inIdx+1 >= len(data) {
					break
				}
				val := (int(data[inIdx]) << 8) | int(data[inIdx+1])
				inIdx += 2

				dist := val & winMask
				length := val >> winBits
				if length == 0 {
					length = maxLen
				}

				for i := 0; i < length; i++ {
					srcIdx := (writePtr - dist) & winMask
					b := window[srcIdx]
					outBuf = append(outBuf, b)
					window[writePtr] = b
					writePtr = (writePtr + 1) & winMask
				}
			} else {
				if inIdx >= len(data) {
					break
				}
				b := data[inIdx]
				inIdx++
				outBuf = append(outBuf, b)
				window[writePtr] = b
				writePtr = (writePtr + 1) & winMask
			}
		}
	}
	return outBuf, nil
}

func compress(data []byte, winBits int) ([]byte, error) {
	if winBits < 8 || winBits > 16 {
		return nil, fmt.Errorf("invalid window bits: %d", winBits)
	}

	winSize := 1 << winBits
	winMask := winSize - 1
	maxLen := 1 << (16 - winBits)

	outBuf := make([]byte, 0, len(data)/2)
	outBuf = append(outBuf, byte(winBits))

	i := 0
	cmds := make([]Command, 0, len(data)/2)

	for i < len(data) {
		bestLen := 0
		bestDist := 0

		start := i - winSize
		if start < 0 {
			start = 0
		}

		for j := start; j < i; j++ {
			length := 0
			for length < maxLen && i+length < len(data) && data[j+length] == data[i+length] {
				length++
			}

			if length >= 2 && length > bestLen {
				bestLen = length
				bestDist = i - j
			}
		}

		if bestLen >= 2 {
			cmds = append(cmds, Command{isLit: false, dist: bestDist, len: bestLen})
			i += bestLen
		} else {
			cmds = append(cmds, Command{isLit: true, val: data[i]})
			i++
		}
	}

	cmdIdx := 0
	for cmdIdx < len(cmds) {
		chunkSize := len(cmds) - cmdIdx
		if chunkSize > 7 {
			chunkSize = 7
		}
		chunk := cmds[cmdIdx : cmdIdx+chunkSize]
		cmdIdx += chunkSize

		flagByte := byte(0x80)
		for k, cmd := range chunk {
			if cmd.isLit {
				flagByte |= (1 << k)
			}
		}
		outBuf = append(outBuf, flagByte)

		for _, cmd := range chunk {
			if !cmd.isLit {
				lenVal := cmd.len
				if lenVal == maxLen {
					lenVal = 0
				}
				val := (lenVal << winBits) | (cmd.dist & winMask)
				outBuf = append(outBuf, byte(val>>8), byte(val&0xFF))
			} else {
				outBuf = append(outBuf, cmd.val)
			}
		}
	}

	// Append EOS (End of Stream) marker byte
	outBuf = append(outBuf, 0x00)

	return outBuf, nil
}

func main() {
	cFlag := flag.Bool("c", false, "compress")
	dFlag := flag.Bool("d", false, "decompress")
	wFlag := flag.Int("w", 12, "window bits")
	flag.Parse()

	args := flag.Args()
	if len(args) < 1 {
		fmt.Println("Usage for file: lz_ac [-c|-d] [-w window_bits] <input_file> <output_file>")
		fmt.Println("Usage for directory: lz_ac -d <input_directory> [output_directory]")
		os.Exit(1)
	}

	inPath := args[0]
	fi, err := os.Stat(inPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Stat error: %v\n", err)
		os.Exit(1)
	}

	if fi.IsDir() {
		if !*dFlag {
			fmt.Println("Error: batch compression (-c) on directory is not supported")
			os.Exit(1)
		}

		outDir := inPath
		if len(args) >= 2 {
			outDir = args[1]
			err = os.MkdirAll(outDir, 0755)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Failed to create output directory: %v\n", err)
				os.Exit(1)
			}
		}

		entries, err := os.ReadDir(inPath)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Read directory error: %v\n", err)
			os.Exit(1)
		}

		for _, entry := range entries {
			if entry.IsDir() {
				continue
			}
			filePath := filepath.Join(inPath, entry.Name())

			data, err := os.ReadFile(filePath)
			if err != nil {
				continue
			}

			if len(data) < 2 {
				continue
			}

			if len(data) >= 4 {
				magic := binary.LittleEndian.Uint32(data[:4])
				if magic == 0x10 {
					// Already a TIM file, skip
					continue
				}
			}

			winBits := int(data[0])
			if winBits < 8 || winBits > 16 {
				continue
			}

			decomp, err := decompress(data)
			if err != nil {
				continue
			}

			ext := ".decomp"
			if len(decomp) >= 4 {
				magic := binary.LittleEndian.Uint32(decomp[:4])
				if magic == 0x10 {
					ext = ".TIM"
				}
			}

			base := entry.Name()
			origExt := filepath.Ext(base)
			name := strings.TrimSuffix(base, origExt)
			outName := name + ext

			outPath := filepath.Join(outDir, outName)
			err = os.WriteFile(outPath, decomp, 0644)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Failed to write %s: %v\n", outPath, err)
			} else {
				fmt.Printf("Decompressed %s -> %s (%d bytes)\n", entry.Name(), outName, len(decomp))
			}
		}
		fmt.Println("Batch decompression completed.")
		return
	}

	if len(args) < 2 {
		fmt.Println("Usage for file: lz_ac [-c|-d] [-w window_bits] <input_file> <output_file>")
		os.Exit(1)
	}
	outPath := args[1]

	data, err := os.ReadFile(inPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Read error: %v\n", err)
		os.Exit(1)
	}

	var outData []byte
	if *cFlag {
		outData, err = compress(data, *wFlag)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Compress error: %v\n", err)
			os.Exit(1)
		}
	} else if *dFlag {
		outData, err = decompress(data)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Decompress error: %v\n", err)
			os.Exit(1)
		}
	} else {
		fmt.Println("Must specify either -c or -d")
		os.Exit(1)
	}

	err = os.WriteFile(outPath, outData, 0644)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Write error: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Success. Written %d bytes.\n", len(outData))
}
