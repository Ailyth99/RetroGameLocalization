package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Text entry structure for export
type TextEntry struct {
	Offset string
	End    string
	Text   string
}

// Load character table
func readEUCJPTable(tablePath string) (map[string]string, error) {
	table := make(map[string]string)

	file, err := os.Open(tablePath)
	if err != nil {
		return nil, fmt.Errorf("can't find table file: %v", err)
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.Contains(line, "=") {
			parts := strings.Split(line, "=")
			table[parts[0]] = parts[1]
		}
	}

	//fmt.Printf("Table loaded!\n%d character mappings loaded\n", len(table))
	return table, nil
}

// Extract text
func extractText(filePath string, table map[string]string) ([]TextEntry, error) {
	var texts []TextEntry

	data, err := os.ReadFile(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to read file: %v", err)
	}

	//fmt.Printf("Processing file: %s\n", filePath)
	//fmt.Printf("File size: %d bytes\n", len(data))

	for i := 0; i < len(data)-3; i++ {
		// Check for text start marker 06000000
		if data[i] == 0x06 && data[i+1] == 0x00 &&
			data[i+2] == 0x00 && data[i+3] == 0x00 {

			startPos := i
			text := ""
			i += 4

			// Read until end marker 0000
			for i < len(data)-1 {
				if data[i] == 0x00 && data[i+1] == 0x00 {
					break
				}

				if data[i] != 0x00 {
					if i+1 < len(data) {
						hexStr := fmt.Sprintf("%02X%02X", data[i], data[i+1])
						if char, ok := table[hexStr]; ok {
							text += char
						}
						i += 2
					} else {
						i++
					}
				} else {
					i++
				}
			}

			endPos := i
			if text != "" {
				texts = append(texts, TextEntry{
					Offset: fmt.Sprintf("%08X", startPos),
					End:    fmt.Sprintf("%08X", endPos),
					Text:   text,
				})
			}
		}
	}

	//fmt.Printf("Found %d text blocks\n", len(texts))
	return texts, nil
}

// Save extracted text
func saveTexts(texts []TextEntry, outputPath string) error {
	file, err := os.Create(outputPath)
	if err != nil {
		return fmt.Errorf("generate TXT fail: %v", err)
	}
	defer file.Close()

	writer := bufio.NewWriter(file)
	for _, entry := range texts {
		writer.WriteString(fmt.Sprintf("[首:%s]\n", entry.Offset)) //Start
		writer.WriteString(fmt.Sprintf("[尾:%s]\n", entry.End))    //End
		writer.WriteString(fmt.Sprintf("[原]%s\n", entry.Text))    //Original TEXT
		writer.WriteString("[译]\n\n")                             //Translation TEXT
	}
	writer.Flush()

	fmt.Printf("Text saved! %d entries written\n", len(texts))
	return nil
}

func main() {
	if len(os.Args) != 2 {
		fmt.Println("usage: script_dumper <EB file path>")
		os.Exit(1)
	}

	ebPath := os.Args[1]
	txtPath := strings.TrimSuffix(ebPath, filepath.Ext(ebPath)) + ".txt"

	// Load table
	table, err := readEUCJPTable("EUC_JP.tbl")
	if err != nil {
		fmt.Printf("ERR: %v\n", err)
		os.Exit(1)
	}

	// Extract
	texts, err := extractText(ebPath, table)
	if err != nil {
		fmt.Printf("ERR: %v\n", err)
		os.Exit(1)
	}

	// Check if any text found
	if len(texts) == 0 {
		fmt.Printf("No text found in %s\n", filepath.Base(ebPath))
		return
	}

	// Save
	err = saveTexts(texts, txtPath)
	if err != nil {
		fmt.Printf("ERR: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("COMPLETE")
}
