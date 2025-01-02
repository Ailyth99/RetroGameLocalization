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

func main() {
	// 命令行参数
	tblFile := flag.String("tbl", "", "编码表文件(tbl.csv) / Character table file (tbl.csv)")
	elfFile := flag.String("elf", "", "目标ELF文件(SLPS_250.09) / Target ELF file")
	trFile := flag.String("tr", "", "译文文件(*.txt) / Translation file")
	flag.Parse()

	if *tblFile == "" || *elfFile == "" || *trFile == "" {
		fmt.Println("用法 / Usage:\n elf_text_importer.exe -tbl tbl.csv -elf SLPS_250.09 -tr translation.txt\n elf_text_importer.exe -tbl tbl.csv -elf SLPS_250.09 -tr translation.txt")
		return
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
			code, err := strconv.ParseUint(row[1], 16, 16)
			if err != nil {
				continue
			}
			encodeMap[char] = []byte{byte(code)}
		}
	}

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

	elfData, err := os.OpenFile(*elfFile, os.O_RDWR, 0644)
	if err != nil {
		fmt.Printf("Failed to open target file: %v\n", err)
		return
	}
	defer elfData.Close()

	successCount := 0
	failedBlocks := make([]string, 0)

	for _, block := range blocks {
		if block.cnText == "" {
			continue
		}

		// 对译文进行按照tbl里面的编码进行编码。
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

		// 对空缺部分，直接补00
		for len(cnBytes) < origLen {
			cnBytes = append(cnBytes, 0)
		}

		elfData.Seek(int64(block.startOffset), 0)
		elfData.Write(cnBytes)
		successCount++
		fmt.Printf("\r已导入 / Imported: %d", successCount)
	}

	fmt.Printf("\n\n导入完成/ Import completed!\n")
	fmt.Printf("成功 / Success: %d\n失败 / Failed: %d\n", successCount, len(failedBlocks))

	if len(failedBlocks) > 0 {
		fmt.Println("\ndetails:")
		for _, msg := range failedBlocks {
			fmt.Println(msg)
		}
	}

	fmt.Println("\n按回车键退出... / Press Enter to exit...")
	bufio.NewReader(os.Stdin).ReadBytes('\n')
}
