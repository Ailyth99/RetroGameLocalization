package main

import (
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: pak_unpacker <pak_file> [output_directory]")
		return
	}

	filePath := os.Args[1]
	
	var outDir string
	baseName := filepath.Base(filePath)
	ext := filepath.Ext(baseName)
	defaultDirName := strings.TrimSuffix(baseName, ext) + "_unpacked"

	if len(os.Args) >= 3 {
		userDir := os.Args[2]
		outDir = filepath.Join(userDir, defaultDirName)
	} else {
		outDir = defaultDirName
	}

	file, err := os.Open(filePath)
	if err != nil {
		fmt.Printf("Error opening file: %v\n", err)
		return
	}
	defer file.Close()

	fileInfo, err := file.Stat()
	if err != nil {
		fmt.Printf("Error getting file info: %v\n", err)
		return
	}
	fileSize := fileInfo.Size()

	fmt.Printf("Extracting %s to %s ...\n", filePath, outDir)

	reader := io.NewSectionReader(file, 0, fileSize)
	err = extract(reader, outDir)
	if err != nil {
		fmt.Printf("Error during extraction: %v\n", err)
	} else {
		fmt.Println("Done!")
	}
}

//DecompressPK02解压算法
func DecompressPK02(src []byte, decompressedSize int) ([]byte, error) {
	dest := make([]byte, 0, decompressedSize)
	
	sp := 0
	if sp >= len(src) {
		return nil, fmt.Errorf("empty input")
	}

	controlByte := src[sp]
	sp++
	bitCount := 0 

	for len(dest) < decompressedSize {
		if sp > len(src) {
			break 
		}

		if bitCount > 7 {
			if sp >= len(src) {
				break
			}
			controlByte = src[sp]
			sp++
			bitCount = 0
		}

		bit := (controlByte >> (7 - bitCount)) & 1
		bitCount++

		if bit == 1 {
			if sp >= len(src) {
				break
			}
			dest = append(dest, src[sp])
			sp++
		} else {
			if bitCount > 7 {
				if sp >= len(src) { break }
				controlByte = src[sp]
				sp++
				bitCount = 0
			}
			typeBit := (controlByte >> (7 - bitCount)) & 1
			bitCount++

			var offset int
			var length int

			if typeBit == 0 {
				val2bit := 0
				for k := 0; k < 2; k++ {
					if bitCount > 7 {
						if sp >= len(src) { break }
						controlByte = src[sp]
						sp++
						bitCount = 0
					}
					b := (controlByte >> (7 - bitCount)) & 1
					bitCount++
					val2bit = (val2bit << 1) | int(b)
				}
				
				if sp >= len(src) { break }
				offsetByte := int(src[sp])
				sp++
				offset = offsetByte - 0x100 
				length = val2bit + 2
				
			} else {
				if sp+1 >= len(src) { break }
				b1 := int(src[sp])
				b2 := int(src[sp+1])
				sp += 2
				combined := (b1 << 8) | b2
				offsetRaw := (combined >> 5)
				offset = offsetRaw - 0x800
				lengthRaw := b2 & 0x1f
				if lengthRaw == 0 {
					if sp >= len(src) { break }
					b3 := int(src[sp])
					sp++
					length = b3 + 1
				} else {
					length = int(lengthRaw) + 2
				}
			}

			start := len(dest) + offset
			if start < 0 { start = 0 }
			
			for i := 0; i < length; i++ {
				readIdx := start + i
				if readIdx < len(dest) {
					dest = append(dest, dest[readIdx])
				} else {
					dest = append(dest, 0)
				}
			}
		}
	}
	return dest, nil
}

func checkHeader(r io.ReaderAt) (bool, string, uint32, uint32) {
	buf := make([]byte, 16)
	if _, err := r.ReadAt(buf, 0); err != nil {
		return false, "", 0, 0
	}
	magic := string(buf[0:4])
	
	if buf[0] == 0x50 && buf[1] == 0x4B {
		if buf[3] == 0x02 {
			decompSize := binary.LittleEndian.Uint32(buf[4:8])
			return true, "PK02", decompSize, 0
		}
		return true, "PK_UNK", 0, 0
	}

	zeroCheck := binary.LittleEndian.Uint32(buf[4:8])
	filesCount := binary.LittleEndian.Uint32(buf[12:16])
	if zeroCheck == 0 {
		isAscii := true
		for _, b := range buf[0:4] {
			if b < 32 || b > 126 { isAscii = false }
		}
		if isAscii {
			return true, magic, filesCount, 0
		}
	}
	return false, "", 0, 0
}

func extract(reader *io.SectionReader, currentPath string) error {
	isValid, magic, param1, _ := checkHeader(reader)
	if !isValid {
		return fmt.Errorf("invalid format")
	}

	
	if magic == "PK02" {
		//先读取完整的原始数据
		fullSize := reader.Size()
		rawData := make([]byte, fullSize)
		_, err := reader.ReadAt(rawData, 0)
		if err != nil { return err }

		fmt.Printf("  -> Saving raw PKLZ: %s\n", filepath.Base(currentPath))
		if err := os.WriteFile(currentPath, rawData, 0644); err != nil {
			return fmt.Errorf("failed to save pklz: %v", err)
		}

		//开始解压
		decompSize := int(param1)
		//压缩数据部分从16字节开始的
		if int64(len(rawData)) <= 16 {
			return fmt.Errorf("file too small")
		}
		fmt.Printf("  -> Decompressing: %s (Size: %d -> %d)\n", filepath.Base(currentPath), fullSize-16, decompSize)
		
		data, err := DecompressPK02(rawData[16:], decompSize)
		if err != nil { return err }
		
		//保存
		binPath := currentPath
		if strings.HasSuffix(binPath, ".pklz") {
			binPath = strings.TrimSuffix(binPath, ".pklz") + ".bin"
		} else if !strings.HasSuffix(binPath, ".bin") {
			binPath += ".bin"
		}
		return os.WriteFile(binPath, data, 0644)
	}

	//处理容器
	filesCount := param1
	fmt.Printf("Found container type [%s] with %d files at %s\n", magic, filesCount, filepath.Base(currentPath))

	offsetCount := int(filesCount) + 1
	offsets := make([]uint32, offsetCount)
	offsetBuf := make([]byte, offsetCount*4)
	if _, err := reader.ReadAt(offsetBuf, 16); err != nil { return err }
	for i := 0; i < offsetCount; i++ {
		offsets[i] = binary.LittleEndian.Uint32(offsetBuf[i*4 : (i+1)*4])
	}

	currentSectionSize := uint32(reader.Size())
	lastIdx := len(offsets) - 1
	if offsets[lastIdx] > currentSectionSize || (lastIdx > 0 && offsets[lastIdx] < offsets[lastIdx-1]) {
		offsets[lastIdx] = currentSectionSize
	}
	sort.Slice(offsets, func(i, j int) bool { return offsets[i] < offsets[j] })

	if err := os.MkdirAll(currentPath, 0755); err != nil { return err }

	for i := 0; i < int(filesCount); i++ {
		startOffset := offsets[i]
		endOffset := offsets[i+1]
		
		if startOffset == 0 { continue } // 再次确认：保留此修复，防止无限递归
		if startOffset >= endOffset { continue }

		chunkSize := int64(endOffset - startOffset)
		baseFileName := fmt.Sprintf("%08x", startOffset)
		
		subReader := io.NewSectionReader(reader, int64(startOffset), chunkSize)
		
		isSub, subMagic, _, _ := checkHeader(subReader)
		fullPath := filepath.Join(currentPath, baseFileName)

		if isSub {
			if subMagic == "PK02" {
				err := extract(subReader, fullPath + ".pklz") 
				if err != nil { fmt.Printf("Failed to decompress %s: %v\n", fullPath, err) }
			} else if subMagic == "DATA" || subMagic == "MENU" || subMagic == "FONT" {
				if err := extract(subReader, fullPath); err != nil {
					fmt.Printf("Failed sub-pak %s: %v\n", fullPath, err)
				}
			} else if strings.HasPrefix(subMagic, "PK") {
				saveFile(subReader, fullPath + ".pklz")
			} else {
				saveFile(subReader, fullPath + ".bin")
			}
		} else {
			saveFile(subReader, fullPath + ".bin")
		}
	}
	return nil
}

func saveFile(reader *io.SectionReader, path string) error {
	out, err := os.Create(path)
	if err != nil { return err }
	defer out.Close()
	reader.Seek(0, 0)
	_, err = io.Copy(out, reader)
	return err
}