package main

import (
	"bufio"
	"encoding/csv"
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"
)

type TextBlock struct {
	number      string
	startOffset int
	endOffset   int
	jpText      string
	cnText      string
}

type Alignment int

const (
	AlignLeft Alignment = iota
	AlignCenter
)

func main() {
	// 参数
	tblFile := flag.String("tbl", "", "编码表文件 / Character table file (tbl.csv)")
	ebFile := flag.String("eb", "", "目标EB文件 / Target EB file")
	trFile := flag.String("tr", "", "译文文件 / Translation file")
	alignMode := flag.String("align", "left", "文本对齐方式 / Text alignment (left/center)")
	flag.Parse()

	if *tblFile == "" || *ebFile == "" || *trFile == "" {
		fmt.Println("用法 / Usage: eb_importer.exe -tbl font/tbl.csv -eb EV431.EB -tr script.txt -align center")
		return
	}

	alignment := AlignLeft
	if *alignMode == "center" {
		alignment = AlignCenter
	}

	encodeMap := make(map[string][]byte)
	f, err := os.Open(*tblFile)
	if err != nil {
		fmt.Printf("Failed to open character table: %v\n", err)
		return
	}
	defer f.Close()

	reader := csv.NewReader(f)
	records, err := reader.ReadAll()
	if err != nil {
		fmt.Printf("Failed to read character table: %v\n", err)
		return
	}

	for _, row := range records {
		if len(row) >= 2 {
			char := row[0]
			code, err := strconv.ParseUint(row[1], 16, 8)
			if err != nil {
				continue
			}
			encodeMap[char] = []byte{byte(code)}
		}
	}

	// 读取译文
	blocks := make([]TextBlock, 0)
	var currentBlock *TextBlock

	trf, err := os.Open(*trFile)
	if err != nil {
		fmt.Printf("Failed to open translation file: %v\n", err)
		return
	}
	defer trf.Close()

	scanner := bufio.NewScanner(trf)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if strings.HasPrefix(line, "[") {
			if currentBlock != nil {
				blocks = append(blocks, *currentBlock)
			}

			numStr := line[1:5]
			offsetStr := line[6 : len(line)-1]
			offsets := strings.Split(offsetStr, ",")
			start, _ := strconv.ParseInt(strings.TrimSpace(offsets[0]), 16, 32)
			end, _ := strconv.ParseInt(strings.TrimSpace(offsets[1]), 16, 32)

			currentBlock = &TextBlock{
				number:      numStr,
				startOffset: int(start),
				endOffset:   int(end),
			}
		} else if strings.HasPrefix(line, "JP：") {
			if currentBlock != nil {
				currentBlock.jpText = line[3:]
			}
		} else if strings.HasPrefix(line, "CN：") {
			if currentBlock != nil {
				currentBlock.cnText = line[3:]
			}
		}
	}

	if currentBlock != nil {
		blocks = append(blocks, *currentBlock)
	}

	// 导入
	ebData, err := os.OpenFile(*ebFile, os.O_RDWR, 0644)
	if err != nil {
		fmt.Printf("Failed to open target file: %v\n", err)
		return
	}
	defer ebData.Close()

	successCount := 0
	failedBlocks := make([]string, 0)

	for _, block := range blocks {
		if block.cnText == "" {
			continue
		}

		// 编码
		cnBytes := make([]byte, 0)
		encodeFailed := false
		for _, c := range block.cnText {
			if b, ok := encodeMap[string(c)]; ok {
				cnBytes = append(cnBytes, b...)
			} else {
				failedBlocks = append(failedBlocks, fmt.Sprintf("块 %s: 未找到字符 '%c' 的编码 / Block %s: No encoding found for character '%c'",
					block.number, c, block.number, c))
				encodeFailed = true
				break
			}
		}

		if encodeFailed {
			continue
		}

		origLen := block.endOffset - block.startOffset
		if len(cnBytes) > origLen {
			failedBlocks = append(failedBlocks, fmt.Sprintf("块 %s: 译文过长 / Block %s: Translation too long",
				block.number, block.number))
			continue
		}

		// 对齐
		finalBytes := make([]byte, origLen)
		if alignment == AlignCenter {
			// 居中
			leftPad := (origLen - len(cnBytes)) / 2
			copy(finalBytes[leftPad:], cnBytes)
			// 填充20
			for i := 0; i < leftPad; i++ {
				finalBytes[i] = 0x20
			}
			for i := leftPad + len(cnBytes); i < origLen; i++ {
				finalBytes[i] = 0x20
			}
		} else {
			// 左对齐
			copy(finalBytes, cnBytes)
			for i := len(cnBytes); i < origLen; i++ {
				finalBytes[i] = 0x20
			}
		}

		// 写入编码
		ebData.Seek(int64(block.startOffset), 0)
		ebData.Write(finalBytes)
		successCount++
		fmt.Printf("\rImported: %d", successCount)
	}

	fmt.Printf("Success: %d / Failed: %d\n",
		successCount, len(failedBlocks))

	if len(failedBlocks) > 0 {
		fmt.Println("\ndetails:")
		for _, msg := range failedBlocks {
			fmt.Println(msg)
		}
	}

	fmt.Println("\n按回车键退出... / Press Enter to exit...")
	bufio.NewReader(os.Stdin).ReadBytes('\n')
}
