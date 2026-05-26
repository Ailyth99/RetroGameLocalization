package main

import (
	"bytes"
	"encoding/binary"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func decompressPrs(src []byte, startOffset int) ([]byte, int) {
	var dst []byte
	if startOffset >= len(src) {
		return dst, startOffset
	}

	uVar6 := src[startOffset]
	srcPos := startOffset + 1
	iVar9 := 9

	for {
		var uVar7 byte
		for {
			iVar9--
			if iVar9 == 0 {
				if srcPos >= len(src) {
					return dst, srcPos
				}
				uVar7 = src[srcPos]
				srcPos++
				iVar9 = 8
			} else {
				uVar7 = uVar6
			}

			uVar6 = uVar7 >> 1
			if (uVar7 & 1) == 0 {
				break
			}

			if srcPos >= len(src) {
				return dst, srcPos
			}
			dst = append(dst, src[srcPos])
			srcPos++
		}

		iVar9--
		uVar7 = uVar7 >> 2
		uVar8 := uVar6

		if iVar9 == 0 {
			if srcPos >= len(src) {
				return dst, srcPos
			}
			uVar8 = src[srcPos]
			srcPos++
			iVar9 = 8
			uVar7 = uVar8 >> 1
		}

		uVar6 = uVar7

		var iVar2 int
		var copyOffset int

		if (uVar8 & 1) == 0 {
			iVar9--
			if iVar9 == 0 {
				if srcPos >= len(src) {
					return dst, srcPos
				}
				uVar6 = src[srcPos]
				srcPos++
				iVar9 = 8
			}

			uVar7 = uVar6 & 1
			uVar8 = uVar6 >> 1
			iVar9--
			uVar6 = uVar6 >> 2

			if iVar9 == 0 {
				if srcPos >= len(src) {
					return dst, srcPos
				}
				uVar8 = src[srcPos]
				srcPos++
				iVar9 = 8
				uVar6 = uVar8 >> 1
			}

			bit1 := byte(0)
			if uVar7 != 0 {
				bit1 = 1
			}
			bit2 := byte(0)
			if (uVar8 & 1) != 0 {
				bit2 = 1
			}
			uVar7 = (bit1 << 1) | bit2

			if srcPos >= len(src) {
				return dst, srcPos
			}
			uVar8Val := int(src[srcPos]) | -256
			srcPos++

			iVar2 = int(uVar7) + 2
			copyOffset = len(dst) + uVar8Val
		} else {
			if srcPos+1 >= len(src) {
				return dst, srcPos
			}
			shortVal := binary.LittleEndian.Uint16(src[srcPos : srcPos+2])
			if shortVal == 0 {
				srcPos += 2
				return dst, srcPos
			}

			uVar7 = src[srcPos] & 7
			uVar8Val := int(shortVal>>3) | -8192

			if uVar7 != 0 {
				srcPos += 2
				iVar2 = int(uVar7) + 2
				copyOffset = len(dst) + uVar8Val
			} else {
				if srcPos+2 >= len(src) {
					return dst, srcPos
				}
				bVar1 := src[srcPos+2]
				srcPos += 3
				copyOffset = len(dst) + uVar8Val
				iVar2 = int(bVar1) + 1
			}
		}

		for iVar2 != 0 {
			var val byte
			if copyOffset >= 0 && copyOffset < len(dst) {
				val = dst[copyOffset]
			} else {
				val = 0
			}
			dst = append(dst, val)
			copyOffset++
			iVar2--
		}
	}
}

func main() {
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: %s <input_dir> <output_dir>\n", os.Args[0])
		flag.PrintDefaults()
	}

	flag.Parse()

	if flag.NArg() < 2 {
		flag.Usage()
		os.Exit(1)
	}

	inDir := flag.Arg(0)
	outDir := flag.Arg(1)

	err := os.MkdirAll(outDir, os.ModePerm)
	if err != nil {
		fmt.Printf("Error creating output dir: %v\n", err)
		os.Exit(1)
	}

	files, err := filepath.Glob(filepath.Join(inDir, "*.unk"))
	if err != nil {
		fmt.Printf("Error globbing: %v\n", err)
		os.Exit(1)
	}

	totalExtracted := 0
	sig := []byte("PRESSEDPVRFORMAT")

	fmt.Println("开始执行提取命令...")

	for _, unk := range files {
		data, err := os.ReadFile(unk)
		if err != nil {
			fmt.Printf("Error reading %s: %v\n", unk, err)
			continue
		}

		offset := 0
		count := 0
		baseName := strings.TrimSuffix(filepath.Base(unk), filepath.Ext(unk))

		unkOutDir := filepath.Join(outDir, baseName)
		os.MkdirAll(unkOutDir, os.ModePerm)

		fmt.Printf("Processing %s.unk -> %s ...\n", baseName, unkOutDir)
		
		for offset < len(data)-len(sig) {
			idx := bytes.Index(data[offset:], sig)
			if idx == -1 {
				break
			}
			idx += offset

			decompressed, nextPos := decompressPrs(data, idx+len(sig))

			if nextPos <= idx {
				offset = idx + len(sig)
			} else {
				offset = nextPos
			}

			outPath := filepath.Join(unkOutDir, fmt.Sprintf("%s_%03d.pvr", baseName, count))
			err = os.WriteFile(outPath, decompressed, 0644)
			if err != nil {
				fmt.Printf("  -> Error writing %s: %v\n", outPath, err)
			} else {
				count++
				totalExtracted++
			}
		}

		fmt.Printf("  -> Extracted %d PVRs from %s.unk\n", count, baseName)
	}

	fmt.Printf("\nTotal PVRs extracted from all UNK files: %d\n", totalExtracted)
}
