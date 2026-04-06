package main

import (
	"encoding/binary"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf16"
)

func printUsage() {
	fmt.Fprintf(os.Stderr, "Spartan Total Warrior PAK Tool v0.4\n")
	fmt.Fprintf(os.Stderr, "\n用法 (Usage):\n")
	fmt.Fprintf(os.Stderr, "  1. 解包 (Extract):\n")
	fmt.Fprintf(os.Stderr, "     %s -e <file.pak>\n", os.Args[0])
	fmt.Fprintf(os.Stderr, "  2. 重建 (Repack):\n")
	fmt.Fprintf(os.Stderr, "     %s -r <original.pak> <input_dir> <output.pak>\n", os.Args[0])
	flag.PrintDefaults()
}

func main() {
	flag.Usage = printUsage
	extractMode := flag.Bool("e", false, "Extract mode (解包模式)")
	repackMode := flag.Bool("r", false, "Repack mode (重建模式)")
	flag.Parse()
	args := flag.Args()

	if *repackMode {
		if len(args) < 3 { flag.Usage(); return }
		fmt.Println(">>> 模式: PAK 重建 (Repack)")
		if err := repackPak(args[0], args[1], args[2]); err != nil {
			fmt.Printf("\n[错误] 重建失败: %v\n", err)
		} else {
			fmt.Println("\n[成功] 重建完成，二进制数据已对齐。")
		}
	} else if *extractMode || (len(args) == 1 && !*repackMode) {
		inputPath := args[0]
		fmt.Println(">>> 模式: PAK 解包 (Extract)")
		if err := extractPak(inputPath); err != nil {
			fmt.Printf("\n[错误] 解包失败: %v\n", err)
		} else {
			fmt.Println("\n[成功] 所有子文件已提取。")
		}
	} else {
		flag.Usage()
	}
}

func alignUp(val, align int64) int64 {
	if align == 0 { return val }
	if remainder := val % align; remainder != 0 {
		return val + (align - remainder)
	}
	return val
}

func extractPak(pakPath string) error {
	f, err := os.Open(pakPath)
	if err != nil { return err }
	defer f.Close()

	id := make([]byte, 3); io.ReadFull(f, id)
	if string(id) != "PAK" { return fmt.Errorf("不是有效的 PAK 文件") }
	ver := make([]byte, 1); io.ReadFull(f, ver)

	var dummy, fileCount, align uint32
	binary.Read(f, binary.LittleEndian, &dummy)
	binary.Read(f, binary.LittleEndian, &fileCount)
	binary.Read(f, binary.LittleEndian, &align)

	fmt.Printf("文件信息: 版本='%c', 数量=%d, 对齐字节=%d\n", ver[0], fileCount, align)

	names := make([]string, fileCount)
	for i := 0; i < int(fileCount); i++ {
		names[i], _ = readUnicode(f)
	}

	cur, _ := f.Seek(0, io.SeekCurrent)
	if pad := cur % 16; pad != 0 { f.Seek(16-pad, io.SeekCurrent) }
	for {
		var val uint32
		if err := binary.Read(f, binary.LittleEndian, &val); err != nil || val != 0 {
			f.Seek(-4, io.SeekCurrent); break
		}
	}

	tablePos, _ := f.Seek(0, io.SeekCurrent)
	dataBase := tablePos + int64(fileCount*4)
	offsets := make([]int64, fileCount+1)
	offsets[0] = dataBase
	for i := 1; i <= int(fileCount); i++ {
		var off uint32
		binary.Read(f, binary.LittleEndian, &off)
		offsets[i] = int64(off)
	}

	outDir := strings.TrimSuffix(pakPath, filepath.Ext(pakPath))
	os.MkdirAll(outDir, 0755)

	for i := 0; i < int(fileCount); i++ {
		start := alignUp(offsets[i], int64(align))
		size := offsets[i+1] - start
		
		fmt.Printf("[%d/%d] 正在提取: %s (Offset: 0x%X, Size: %d)\n", 
			i+1, fileCount, names[i], start, size)

		if size <= 0 { 
			fmt.Printf("      ! 跳过空文件或占位符\n")
			continue 
		}
		
		if err := save(f, outDir, names[i], start, size); err != nil {
			fmt.Printf("      ! 写入失败: %v\n", err)
		}
	}
	return nil
}

func repackPak(refPath, inDir, outPath string) error {
	ref, err := os.Open(refPath)
	if err != nil { return err }
	defer ref.Close()

	ref.Seek(4, io.SeekStart)
	var dummy, fileCount, align uint32
	binary.Read(ref, binary.LittleEndian, &dummy)
	binary.Read(ref, binary.LittleEndian, &fileCount)
	binary.Read(ref, binary.LittleEndian, &align)

	names := make([]string, fileCount)
	for i := 0; i < int(fileCount); i++ {
		names[i], _ = readUnicode(ref)
	}

	out, _ := os.Create(outPath)
	defer out.Close()

	out.WriteString("PAK1")
	binary.Write(out, binary.LittleEndian, dummy)
	binary.Write(out, binary.LittleEndian, fileCount)
	binary.Write(out, binary.LittleEndian, align)

	for _, n := range names { writeUnicode(out, n) }

	afterNames, _ := out.Seek(0, io.SeekCurrent)
	tableSize := int64(fileCount * 4)
	firstFileStart := alignUp(afterNames + tableSize, int64(align))
	tableStart := firstFileStart - tableSize
	
	gapSize := tableStart - afterNames
	out.Write(make([]byte, gapSize))

	fmt.Printf("结构布局: 文件名结束于=0x%X, 偏移表起始=0x%X, 数据起始=0x%X\n", 
		afterNames, tableStart, firstFileStart)

	out.Write(make([]byte, tableSize))

	table := make([]uint32, fileCount)
	currentEnd := firstFileStart

	for i, n := range names {
		path := filepath.Join(inDir, n)
		data, err := os.ReadFile(path)
		if err != nil {
			data, _ = os.ReadFile(filepath.Join(inDir, filepath.Base(n)))
		}

		if data == nil {
			fmt.Printf("[%d/%d] 警告: 找不到本地文件 %s，将写入空数据。\n", i+1, fileCount, n)
			data = []byte{}
		}

		physStart := alignUp(currentEnd, int64(align))
		padding := physStart - currentEnd
		out.Write(make([]byte, padding))
		out.Write(data)

		currentEnd = physStart + int64(len(data))
		table[i] = uint32(currentEnd)
		
		fmt.Printf("[%d/%d] 正在压入: %s (新大小: %d, Padding: %d)\n", 
			i+1, fileCount, n, len(data), padding)
	}

	out.Seek(tableStart, io.SeekStart)
	binary.Write(out, binary.LittleEndian, table)

	return nil
}


func readUnicode(r io.Reader) (string, error) {
	var u16s []uint16
	for {
		var val uint16
		if err := binary.Read(r, binary.LittleEndian, &val); err != nil { return "", err }
		if val == 0 { break }
		u16s = append(u16s, val)
	}
	return string(utf16.Decode(u16s)), nil
}

func writeUnicode(w io.Writer, s string) {
	binary.Write(w, binary.LittleEndian, utf16.Encode([]rune(s)))
	binary.Write(w, binary.LittleEndian, uint16(0))
}

func save(f *os.File, dir, name string, off, sz int64) error {
	name = strings.ReplaceAll(name, "\\", "/")
	path := filepath.Join(dir, name)
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil { return err }
	dst, err := os.Create(path)
	if err != nil { return err }
	defer dst.Close()
	if _, err := f.Seek(off, io.SeekStart); err != nil { return err }
	_, err = io.CopyN(dst, f, sz)
	return err
}