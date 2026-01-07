package main

import (
	"encoding/binary"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: T_TOOL <file_path>")
		return
	}

	if err := extract(os.Args[1]); err != nil {
		fmt.Println("Error:", err)
	} else {
		fmt.Println("Done.")
	}
}

func extract(path string) error {
	// 读取文件
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}

	// 创建输出目录
	base := filepath.Base(path)
	outDir := filepath.Join(filepath.Dir(path), strings.TrimSuffix(base, filepath.Ext(base)))
	if err := os.MkdirAll(outDir, 0755); err != nil {
		return err
	}

	// 获取文件数量 (前2字节)
	count := binary.LittleEndian.Uint16(data[0:2])
	fmt.Printf("Extracting %d files to: %s\n", count, outDir)

	// 遍历索引表
	for i := 0; i < int(count); i++ {
		// 读取扇区索引 (每项2字节，从offset 2开始)
		p1 := 2 + i*2
		p2 := 2 + (i+1)*2

		sStart := binary.LittleEndian.Uint16(data[p1 : p1+2])
		sEnd := binary.LittleEndian.Uint16(data[p2 : p2+2])

		// 核心转换: 扇区 -> 字节地址 (* 2048)
		start := int(sStart) * 2048
		end := int(sEnd) * 2048

		// 过滤空文件或越界
		if start >= end || end > len(data) {
			continue
		}

		// 写入文件
		name := fmt.Sprintf("file_%03d_0x%X.bin", i, start)
		if err := os.WriteFile(filepath.Join(outDir, name), data[start:end], 0644); err != nil {
			fmt.Printf("Failed to write %s\n", name)
		}
	}

	return nil
}