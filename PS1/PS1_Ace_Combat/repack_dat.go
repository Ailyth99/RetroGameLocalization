package main

import (
	"encoding/binary"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type Command struct {
	isLit bool
	dist  int
	len   int
	val   byte
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
	cFlag := flag.String("c", "", "comma-separated list of file prefixes to compress (e.g. '013' or '013,014')")
	allFlag := flag.Bool("all", false, "compress all files")
	wFlag := flag.Int("w", 12, "window bits for compression")
	flag.Parse()

	args := flag.Args()
	if len(args) < 2 {
		fmt.Println("Usage: repack_dat [-c compress_list] [-all] [-w window_bits] <input_dir> <output_dat>")
		os.Exit(1)
	}

	inputDir := args[0]
	outputDat := args[1]

	toCompress := make(map[string]bool)
	if *cFlag != "" {
		parts := strings.Split(*cFlag, ",")
		for _, p := range parts {
			trimmed := strings.TrimSpace(p)
			if val, err := strconv.Atoi(trimmed); err == nil {
				normalized := fmt.Sprintf("%03d", val)
				toCompress[normalized] = true
			} else {
				toCompress[trimmed] = true
			}
		}
	}

	var fileDatas [][]byte

	for i := 0; ; i++ {
		prefix := fmt.Sprintf("%03d", i)
		shouldCompress := *allFlag || toCompress[prefix]

		var data []byte
		var readPath string

		if shouldCompress {
			timPath := filepath.Join(inputDir, prefix+".TIM")
			decompPath := filepath.Join(inputDir, prefix+".decomp")

			if _, err := os.Stat(timPath); err == nil {
				readPath = timPath
			} else if _, err := os.Stat(decompPath); err == nil {
				readPath = decompPath
			}

			if readPath != "" {
				uncompressedData, err := os.ReadFile(readPath)
				if err != nil {
					fmt.Fprintf(os.Stderr, "Failed to read %s: %v\n", readPath, err)
					os.Exit(1)
				}
				
				winBits := *wFlag
				binPath := filepath.Join(inputDir, prefix+".bin")
				if binData, err := os.ReadFile(binPath); err == nil && len(binData) > 0 {
					winBits = int(binData[0])
					fmt.Printf("Detected original window bits for %s: %d\n", prefix, winBits)
				} else {
					fmt.Printf("Using default window bits for %s: %d\n", prefix, winBits)
				}

				fmt.Printf("Compressing %s...\n", filepath.Base(readPath))
				compressed, err := compress(uncompressedData, winBits)
				if err != nil {
					fmt.Fprintf(os.Stderr, "Failed to compress %s: %v\n", readPath, err)
					os.Exit(1)
				}
				data = compressed

				// Pad to original size to maintain offsets if smaller
				if binInfo, err := os.Stat(binPath); err == nil {
					originalSize := int(binInfo.Size())
					if len(data) < originalSize {
						paddingSize := originalSize - len(data)
						fmt.Printf("Padding %s.bin from %d to %d bytes (+%d bytes padding)\n", prefix, len(data), originalSize, paddingSize)
						padding := make([]byte, paddingSize)
						data = append(data, padding...)
					} else if len(data) > originalSize {
						fmt.Printf("Warning: Compressed %s.bin size (%d) is larger than original size (%d)!\n", prefix, len(data), originalSize)
					}
				}

				err = os.WriteFile(binPath, data, 0644)
				if err != nil {
					fmt.Fprintf(os.Stderr, "Warning: failed to update %s: %v\n", binPath, err)
				}
			}
		}

		if len(data) == 0 {
			binPath := filepath.Join(inputDir, prefix+".bin")
			if _, err := os.Stat(binPath); err == nil {
				readPath = binPath
				data, err = os.ReadFile(binPath)
				if err != nil {
					fmt.Fprintf(os.Stderr, "Failed to read %s: %v\n", binPath, err)
					os.Exit(1)
				}
			}
		}

		if len(data) == 0 {
			if i == 0 {
				fmt.Fprintf(os.Stderr, "No files found in directory %s\n", inputDir)
				os.Exit(1)
			}
			break
		}

		fmt.Printf("Packing %s (size: %d bytes)\n", filepath.Base(readPath), len(data))
		fileDatas = append(fileDatas, data)
	}

	fcount := len(fileDatas)
	fmt.Printf("Total files to pack: %d\n", fcount)

	startOffset := uint32(4 + 4*fcount)
	offsets := make([]uint32, fcount)

	currentOffset := startOffset
	for i, data := range fileDatas {
		offsets[i] = currentOffset
		currentOffset += uint32(len(data))
	}

	outF, err := os.Create(outputDat)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to create output file: %v\n", err)
		os.Exit(1)
	}
	defer outF.Close()

	err = binary.Write(outF, binary.LittleEndian, uint32(fcount))
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to write fcount: %v\n", err)
		os.Exit(1)
	}

	err = binary.Write(outF, binary.LittleEndian, offsets)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to write offsets: %v\n", err)
		os.Exit(1)
	}

	for i, data := range fileDatas {
		_, err = outF.Write(data)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Failed to write file data for index %d: %v\n", i, err)
			os.Exit(1)
		}
	}

	fmt.Printf("Successfully repacked to %s\n", outputDat)
}
