package main

import (
	"bufio"
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

func splitWithMatches(s string, re *regexp.Regexp) []string {
	idxs := re.FindAllStringIndex(s, -1)
	out := make([]string, 0, len(idxs)*2+1)
	last := 0
	for _, p := range idxs {
		out = append(out, s[last:p[0]])
		out = append(out, s[p[0]:p[1]])
		last = p[1]
	}
	out = append(out, s[last:])
	return out
}

func stripExt(p string) string {
	ext := filepath.Ext(p)
	return strings.TrimSuffix(p, ext)
}

func exportBin(filePath string) {
	if _, err := os.Stat(filePath); err != nil {
		fmt.Printf("Error: Cannot find file %s\n", filePath)
		return
	}

	outPath := stripExt(filePath) + ".txt"
	fmt.Printf("[*] Exporting text from original BIN: %s\n", filepath.Base(filePath))

	f, err := os.Open(filePath)
	if err != nil {
		fmt.Printf("Failed to open file: %v\n", err)
		return
	}
	defer f.Close()

	header := make([]byte, 4)
	if n, _ := io.ReadFull(f, header); n < 4 {
		return
	}
	totalEntries := binary.LittleEndian.Uint32(header)
	fmt.Printf("[*] Found valid entries: %d\n", totalEntries)

	outF, err := os.Create(outPath)
	if err != nil {
		fmt.Printf("Failed to create output file: %v\n", err)
		return
	}
	defer outF.Close()

	w := bufio.NewWriter(outF)
	defer w.Flush()

	for i := uint32(0); i < totalEntries; i++ {
		p1Bytes := make([]byte, 2)
		p2Bytes := make([]byte, 2)
		if _, err := io.ReadFull(f, p1Bytes); err != nil {
			break
		}
		if _, err := io.ReadFull(f, p2Bytes); err != nil {
			break
		}
		p1 := binary.LittleEndian.Uint16(p1Bytes)
		p2 := binary.LittleEndian.Uint16(p2Bytes)

		var rawText []byte
		for {
			word := make([]byte, 2)
			n, err := io.ReadFull(f, word)
			if err != nil || n < 2 {
				break
			}
			if word[0] == 0 && word[1] == 0 {
				break
			}
			rawText = append(rawText, word...)
		}

		var sb strings.Builder
		for idx := 0; idx+2 <= len(rawText); idx += 2 {
			val := binary.LittleEndian.Uint16(rawText[idx : idx+2])
			switch {
			case val == 0x000A:
				sb.WriteByte('\n')
			case val < 0x0020:
				sb.WriteString(fmt.Sprintf("<%04X>", val))
			case val >= 0xD800 && val <= 0xDFFF:
				sb.WriteString(fmt.Sprintf("<%04X>", val))
			default:
				sb.WriteRune(rune(val))
			}
		}

		fmt.Fprintf(w, "[ID:%04d] [P1:%04X] [P2:%04X]\n", i, p1, p2)
		fmt.Fprintf(w, "JP：%s\n", sb.String())
		fmt.Fprintf(w, "CN：\n\n")
	}

	fmt.Printf("[+] Export successful: %s\n", outPath)
}

func loadCharsetMap(csvPath string) (map[string][]byte, error) {
	charMap := make(map[string][]byte)
	fmt.Printf("[*] Loading charset mapping table: %s\n", csvPath)

	data, err := os.ReadFile(csvPath)
	if err != nil {
		return nil, err
	}
	content := strings.TrimPrefix(string(data), "\ufeff")

	for _, line := range strings.Split(content, "\n") {
		line = strings.TrimRight(line, "\r\n")
		if line == "" {
			continue
		}
		parts := strings.Split(line, ",")
		if len(parts) < 2 {
			continue
		}
		char := parts[0]
		if char == "" && strings.HasPrefix(line, ",") {
			char = ","
		}
		hexStr := strings.TrimSpace(parts[1])
		b, err := hex.DecodeString(hexStr)
		if err != nil {
			continue
		}
		charMap[char] = b
	}

	fmt.Printf("[+] Mapping table loaded, total %d characters.\n", len(charMap))
	return charMap, nil
}

type Entry struct {
	P1 uint16
	P2 uint16
	CN string
}

var (
	idRe = regexp.MustCompile(`\[ID:(\d+)\]`)
	p1Re = regexp.MustCompile(`\[P1:([0-9A-Fa-f]+)\]`)
	p2Re = regexp.MustCompile(`\[P2:([0-9A-Fa-f]+)\]`)
	cnRe = regexp.MustCompile(`(?s)CN：(.*)`)
)

func parseTxt(txtPath string) (map[int]*Entry, error) {
	data, err := os.ReadFile(txtPath)
	if err != nil {
		return nil, err
	}
	content := string(data)

	matches := idRe.FindAllStringSubmatchIndex(content, -1)
	entries := make(map[int]*Entry)

	for i, m := range matches {
		idVal, _ := strconv.Atoi(content[m[2]:m[3]])
		bodyStart := m[1]
		bodyEnd := len(content)
		if i+1 < len(matches) {
			bodyEnd = matches[i+1][0]
		}
		body := content[bodyStart:bodyEnd]

		var p1, p2 uint16
		if mm := p1Re.FindStringSubmatch(body); mm != nil {
			v, _ := strconv.ParseUint(mm[1], 16, 16)
			p1 = uint16(v)
		}
		if mm := p2Re.FindStringSubmatch(body); mm != nil {
			v, _ := strconv.ParseUint(mm[1], 16, 16)
			p2 = uint16(v)
		}
		cnText := ""
		if mm := cnRe.FindStringSubmatch(body); mm != nil {
			cnText = strings.TrimRight(mm[1], "\r\n")
		}
		if cnText != "" {
			entries[idVal] = &Entry{P1: p1, P2: p2, CN: cnText}
		}
	}
	return entries, nil
}

func getOriginalBinaryEntry(f *os.File, entryID int) []byte {
	if _, err := f.Seek(4, 0); err != nil {
		return nil
	}
	for j := 0; j < entryID; j++ {
		skip := make([]byte, 4)
		if _, err := io.ReadFull(f, skip); err != nil {
			return nil
		}
		for {
			word := make([]byte, 2)
			n, err := io.ReadFull(f, word)
			if err != nil || n < 2 {
				break
			}
			if word[0] == 0 && word[1] == 0 {
				break
			}
		}
	}
	p1p2 := make([]byte, 4)
	if _, err := io.ReadFull(f, p1p2); err != nil {
		return nil
	}
	var textData []byte
	for {
		word := make([]byte, 2)
		n, err := io.ReadFull(f, word)
		if err != nil || n < 2 {
			break
		}
		if word[0] == 0 && word[1] == 0 {
			break
		}
		textData = append(textData, word...)
	}
	out := make([]byte, 0, len(p1p2)+len(textData)+2)
	out = append(out, p1p2...)
	out = append(out, textData...)
	out = append(out, 0x00, 0x00)
	return out
}

var (
	chunkSplitRe = regexp.MustCompile(`(<[0-9A-Fa-f]{4}>|\\n|\n)`)
	tagOnlyRe    = regexp.MustCompile(`^<[0-9A-Fa-f]{4}>$`)
)

func compileEntry(cnText string, p1, p2 uint16, charMap map[string][]byte) ([]byte, []string) {
	var missing []string
	hasMissing := func(c string) bool {
		for _, x := range missing {
			if x == c {
				return true
			}
		}
		return false
	}

	var bin []byte
	chunks := splitWithMatches(cnText, chunkSplitRe)

	for _, chunk := range chunks {
		if chunk == "" {
			continue
		}
		if chunk == "\n" || chunk == `\n` {
			bin = append(bin, 0x0A, 0x00)
		} else if tagOnlyRe.MatchString(chunk) {
			val, _ := strconv.ParseUint(chunk[1:5], 16, 16)
			buf := make([]byte, 2)
			binary.LittleEndian.PutUint16(buf, uint16(val))
			bin = append(bin, buf...)
		} else {
			for _, r := range chunk {
				cs := string(r)
				if b, ok := charMap[cs]; ok {
					bin = append(bin, b...)
				} else if r < 128 {
					buf := make([]byte, 2)
					binary.LittleEndian.PutUint16(buf, uint16(r))
					bin = append(bin, buf...)
				} else {
					if !hasMissing(cs) {
						missing = append(missing, cs)
					}
				}
			}
		}
	}

	if len(missing) > 0 {
		return nil, missing
	}

	out := make([]byte, 4, 4+len(bin)+2)
	binary.LittleEndian.PutUint16(out[0:2], p1)
	binary.LittleEndian.PutUint16(out[2:4], p2)
	out = append(out, bin...)
	out = append(out, 0x00, 0x00)
	return out, nil
}

func mainImport(txtPath, origBinPath, csvPath string) {
	charMap, err := loadCharsetMap(csvPath)
	if err != nil || charMap == nil {
		fmt.Printf("💥 Error: Failed to read CSV: %v\n", err)
		return
	}
	patchEntries, err := parseTxt(txtPath)
	if err != nil {
		fmt.Printf("💥 Error: Failed to parse TXT: %v\n", err)
		return
	}

	outPath := stripExt(origBinPath) + "_new.bin"

	hdrFile, err := os.Open(origBinPath)
	if err != nil {
		fmt.Printf("Failed to open original BIN: %v\n", err)
		return
	}
	header := make([]byte, 4)
	if _, err := io.ReadFull(hdrFile, header); err != nil {
		hdrFile.Close()
		fmt.Printf("Failed to read header: %v\n", err)
		return
	}
	hdrFile.Close()
	totalCount := binary.LittleEndian.Uint32(header)

	fOrig, err := os.Open(origBinPath)
	if err != nil {
		fmt.Printf("Failed to open original BIN: %v\n", err)
		return
	}
	defer fOrig.Close()

	fNew, err := os.Create(outPath)
	if err != nil {
		fmt.Printf("Failed to create output file: %v\n", err)
		return
	}
	defer fNew.Close()

	if err := binary.Write(fNew, binary.LittleEndian, totalCount); err != nil {
		fmt.Printf("Failed to write header: %v\n", err)
		return
	}

	success := 0
	globalMissing := make(map[string]struct{})

	for i := uint32(0); i < totalCount; i++ {
		if e, ok := patchEntries[int(i)]; ok {
			binData, missing := compileEntry(e.CN, e.P1, e.P2, charMap)
			if len(missing) > 0 {
				for _, m := range missing {
					globalMissing[m] = struct{}{}
				}
				fNew.Write(getOriginalBinaryEntry(fOrig, int(i)))
			} else {
				fNew.Write(binData)
				success++
			}
		} else {
			fNew.Write(getOriginalBinaryEntry(fOrig, int(i)))
		}
	}

	fmt.Printf("[+] Import complete. Success: %d | Original kept: %d\n", success, int(totalCount)-success)
	if len(globalMissing) > 0 {
		list := make([]string, 0, len(globalMissing))
		for k := range globalMissing {
			list = append(list, k)
		}
		sort.Strings(list)
		fmt.Printf("🚨 Missing characters summary: %q\n", strings.Join(list, ""))
	}
}

var cleanRe = regexp.MustCompile(`<[0-9A-Fa-f]{4}>|\\n|\n`)

func countTxtChars(txtPath string) {
	fmt.Printf("[*] Counting translated characters: %s\n", txtPath)
	entries, err := parseTxt(txtPath)
	if err != nil {
		fmt.Printf("Failed to parse TXT: %v\n", err)
		return
	}
	allUsed := make(map[rune]struct{})
	for _, e := range entries {
		clean := cleanRe.ReplaceAllString(e.CN, "")
		for _, r := range clean {
			allUsed[r] = struct{}{}
		}
	}
	rs := make([]rune, 0, len(allUsed))
	for r := range allUsed {
		rs = append(rs, r)
	}
	sort.Slice(rs, func(i, j int) bool { return rs[i] < rs[j] })

	bar := strings.Repeat("=", 30)
	fmt.Printf("\n%s\nTotal Unique Characters: %d \n%s\n%s\n", bar, len(allUsed), string(rs), bar)
}

func main() {
	args := os.Args[1:]
	if len(args) == 0 {
		fmt.Println("Usage:")
		fmt.Println("Export: text_tool -export <bin>")
		fmt.Println("Import: text_tool -import <txt> <bin> <csv>")
		fmt.Println("Count:  text_tool -count <txt>")
		os.Exit(1)
	}

	switch args[0] {
	case "-export":
		if len(args) < 2 {
			fmt.Println("Error: Missing parameter <bin>")
			os.Exit(1)
		}
		exportBin(args[1])
	case "-import":
		if len(args) < 4 {
			fmt.Println("Error: Missing parameters <txt> <bin> <csv>")
			os.Exit(1)
		}
		mainImport(args[1], args[2], args[3])
	case "-count":
		if len(args) < 2 {
			fmt.Println("Error: Missing parameter <txt>")
			os.Exit(1)
		}
		countTxtChars(args[1])
	default:
		fmt.Printf("Unknown command: %s\n", args[0])
		os.Exit(1)
	}
}