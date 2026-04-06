package main

import (
	"bufio"
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"unicode/utf16"
)


var (
	tagRe  = regexp.MustCompile(`<[^>]+>`)
	rubyRe = regexp.MustCompile(`(?i)^<RUBY:([0-9A-Fa-f]{1,4}),(\d+),(\d+)>$`)
	hexRe  = regexp.MustCompile(`(?i)^<([0-9A-Fa-f]{1,4})>$`)
	idRe   = regexp.MustCompile(`^\[(\d+)\]`)
)

const (
	cnPfx = "CN："
	jpPfx = "JP："
)


func readStrBytes(f *os.File, addr int64) []byte {
	f.Seek(addr, 0)
	var raw []byte
	buf := make([]byte, 2)
	for {
		_, err := io.ReadFull(f, buf)
		if err != nil {
			break
		}
		val := binary.LittleEndian.Uint16(buf)
		if val == 0x0000 {
			break
		}
		raw = append(raw, buf[0], buf[1])
		if val == 0x000D {
			args := make([]byte, 4)
			_, err := io.ReadFull(f, args)
			if err != nil {
				break
			}
			raw = append(raw, args...)
		}
	}
	return raw
}

func decodeNDS(raw []byte, keepRuby bool) string {
	var sb strings.Builder
	i := 0
	ln := len(raw)
	for i+2 <= ln {
		val := binary.LittleEndian.Uint16(raw[i : i+2])
		switch {
		case val == 0x000A:
			sb.WriteByte('\n')
			i += 2
		case val == 0x000D:
			if i+6 <= ln {
				if keepRuby {
					rid := binary.LittleEndian.Uint16(raw[i+2 : i+4])
					fl := raw[i+4]
					kl := raw[i+5]
					fmt.Fprintf(&sb, "<RUBY:%04X,%d,%d>", rid, fl, kl)
				}
				i += 6
			} else {
				fmt.Fprintf(&sb, "<%04X>", val)
				i += 2
			}
		case val < 0x0020:
			fmt.Fprintf(&sb, "<%04X>", val)
			i += 2
		default:
			sb.WriteRune(rune(val))
			i += 2
		}
	}
	return sb.String()
}

func exportDat(fpath string, keepRuby bool) {
	outPath := strings.TrimSuffix(fpath, filepath.Ext(fpath)) + ".txt"
	f, err := os.Open(fpath)
	if err != nil {
		fmt.Printf("Error: cannot open %s\n", fpath)
		return
	}
	defer f.Close()

	hdr := make([]byte, 12)
	n, _ := f.Read(hdr)
	if n < 12 {
		return
	}
	offPtr := binary.LittleEndian.Uint32(hdr[0:4])
	idxPtr := binary.LittleEndian.Uint32(hdr[4:8])
	txtPtr := binary.LittleEndian.Uint32(hdr[8:12])
	if offPtr != 0x0C {
		return
	}
	numStr := int((idxPtr - offPtr) / 4)
	fmt.Printf("[*] Export: %s (%d entries)\n", filepath.Base(fpath), numStr)

	f.Seek(int64(offPtr), 0)
	offsets := make([]uint32, numStr)
	for i := 0; i < numStr; i++ {
		var v uint32
		binary.Read(f, binary.LittleEndian, &v)
		offsets[i] = v * 2
	}

	out, err := os.Create(outPath)
	if err != nil {
		fmt.Printf("Error: cannot create %s\n", outPath)
		return
	}
	defer out.Close()

	w := bufio.NewWriter(out)
	for i := 0; i < numStr; i++ {
		addr := int64(txtPtr) + int64(offsets[i])
		raw := readStrBytes(f, addr)
		text := decodeNDS(raw, keepRuby)
		fmt.Fprintf(w, "[%04d]\nJP：%s\nCN：\n\n", i, text)
	}
	w.Flush()
}


func countChars(dir string) {
	info, err := os.Stat(dir)
	if err != nil || !info.IsDir() {
		fmt.Printf("Error: %s is not a valid folder.\n", dir)
		return
	}
	files, _ := filepath.Glob(filepath.Join(dir, "*.txt"))
	if len(files) == 0 {
		return
	}

	var chars []rune
	seen := make(map[rune]bool)

	fmt.Printf("[*] Counting chars in: %s\n", dir)
	for _, fp := range files {
		f, err := os.Open(fp)
		if err != nil {
			continue
		}
		sc := bufio.NewScanner(f)
		collect := false
		for sc.Scan() {
			line := sc.Text()
			if strings.HasPrefix(line, cnPfx) {
				collect = true
				content := line[len(cnPfx):]
				for _, ch := range content {
					if !seen[ch] {
						seen[ch] = true
						chars = append(chars, ch)
					}
				}
			} else if idRe.MatchString(line) {
				collect = false
			} else if collect {
				for _, ch := range line {
					if !seen[ch] {
						seen[ch] = true
						chars = append(chars, ch)
					}
				}
			}
		}
		f.Close()
	}

	fmt.Println()
	fmt.Println(strings.Repeat("=", 30))
	fmt.Printf("Unique chars: %d\n", len(chars))
	fmt.Println(string(chars))
	fmt.Println(strings.Repeat("=", 30))
	fmt.Println()
}


func parseTxt(path string) map[int]string {
	trans := make(map[int]string)
	f, err := os.Open(path)
	if err != nil {
		return trans
	}
	defer f.Close()

	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1024*1024), 1024*1024)

	curID := -1
	state := ""

	for sc.Scan() {
		line := sc.Text()
		line = strings.ReplaceAll(line, "\r", "")

		if m := idRe.FindStringSubmatch(line); m != nil {
			id, _ := strconv.Atoi(m[1])
			curID = id
			trans[curID] = ""
			state = "WAIT"
			continue
		}
		if curID < 0 {
			continue
		}
		if strings.HasPrefix(line, jpPfx) {
			state = "JP"
			continue
		}
		if strings.HasPrefix(line, cnPfx) {
			state = "CN"
			trans[curID] += line[len(cnPfx):]
			continue
		}
		if state == "CN" {
			trans[curID] += "\n" + line
		}
	}

	for k, v := range trans {
		trans[k] = strings.TrimRight(v, "\n")
	}
	return trans
}

func encodeNDS(text string) []byte {
	var res []byte
	locs := tagRe.FindAllStringIndex(text, -1)

	encChar := func(ch rune) {
		if ch == '\n' {
			res = append(res, 0x0A, 0x00)
		} else {
			for _, u := range utf16.Encode([]rune{ch}) {
				res = append(res, byte(u), byte(u>>8))
			}
		}
	}
	encStr := func(s string) {
		for _, ch := range s {
			encChar(ch)
		}
	}

	pos := 0
	for _, loc := range locs {
		if pos < loc[0] {
			encStr(text[pos:loc[0]])
		}
		tag := text[loc[0]:loc[1]]

		if m := rubyRe.FindStringSubmatch(tag); m != nil {
			rid, _ := strconv.ParseUint(m[1], 16, 16)
			fl, _ := strconv.Atoi(m[2])
			kl, _ := strconv.Atoi(m[3])
			buf := make([]byte, 6)
			binary.LittleEndian.PutUint16(buf[0:2], 0x000D)
			binary.LittleEndian.PutUint16(buf[2:4], uint16(rid))
			buf[4] = byte(fl)
			buf[5] = byte(kl)
			res = append(res, buf...)
		} else if m := hexRe.FindStringSubmatch(tag); m != nil {
			v, _ := strconv.ParseUint(m[1], 16, 16)
			buf := make([]byte, 2)
			binary.LittleEndian.PutUint16(buf, uint16(v))
			res = append(res, buf...)
		} else {
			encStr(tag)
		}
		pos = loc[1]
	}
	if pos < len(text) {
		encStr(text[pos:])
	}
	return res
}

func importDat(txtPath, datPath, outPath string) {
	if outPath == "" {
		ext := filepath.Ext(datPath)
		base := strings.TrimSuffix(datPath, ext)
		outPath = base + "_new" + ext
	}

	fmt.Println("\n[*] Preparing to pack...")
	fmt.Printf("[*] Translation: %s\n", txtPath)
	fmt.Printf("[*] Original DAT: %s\n", datPath)

	trans := parseTxt(txtPath)

	f, err := os.Open(datPath)
	if err != nil {
		fmt.Printf("Error: cannot open %s\n", datPath)
		return
	}
	defer f.Close()

	hdr := make([]byte, 12)
	f.Read(hdr)
	offPtr := binary.LittleEndian.Uint32(hdr[0:4])
	idxPtr := binary.LittleEndian.Uint32(hdr[4:8])
	txtPtr := binary.LittleEndian.Uint32(hdr[8:12])
	numStr := int((idxPtr - offPtr) / 4)

	f.Seek(int64(offPtr), 0)
	oldOff := make([]uint32, numStr)
	for i := 0; i < numStr; i++ {
		var v uint32
		binary.Read(f, binary.LittleEndian, &v)
		oldOff[i] = v * 2
	}

	origStrs := make([][]byte, numStr)
	for i := 0; i < numStr; i++ {
		addr := int64(txtPtr) + int64(oldOff[i])
		origStrs[i] = readStrBytes(f, addr)
	}

	f.Seek(int64(idxPtr), 0)
	idxSize := int(txtPtr - idxPtr)
	idxData := make([]byte, idxSize)
	f.Read(idxData)

	var newText []byte
	newOff := make([]uint32, numStr)
	done := 0

	for i := 0; i < numStr; i++ {
		newOff[i] = uint32(len(newText) / 2)
		cn := trans[i]
		var sBytes []byte
		if cn == "" {
			sBytes = origStrs[i]
		} else {
			sBytes = encodeNDS(cn)
			done++
		}
		newText = append(newText, sBytes...)
		newText = append(newText, 0x00, 0x00) 
	}

	nIdxPtr := uint32(0x0C + numStr*4)
	nTxtPtr := nIdxPtr + uint32(len(idxData))

	out, err := os.Create(outPath)
	if err != nil {
		fmt.Printf("Error: cannot create %s\n", outPath)
		return
	}
	defer out.Close()

	binary.Write(out, binary.LittleEndian, uint32(0x0C))
	binary.Write(out, binary.LittleEndian, nIdxPtr)
	binary.Write(out, binary.LittleEndian, nTxtPtr)
	for _, off := range newOff {
		binary.Write(out, binary.LittleEndian, off)
	}
	out.Write(idxData)
	out.Write(newText)

	fmt.Println("[+] Import & pack successful!")
	fmt.Printf("    - Total entries: %d\n", numStr)
	fmt.Printf("    - Translated: %d\n", done)
	fmt.Printf("    - Original kept: %d\n", numStr-done)
	fmt.Printf("[+] Output: %s\n\n", outPath)
}


func main() {
	args := os.Args[1:]

	if len(args) == 0 {
		fmt.Println("【NDS Sangokuden Text Tool v1.0 (Go)】")
		fmt.Println("1. Export file/folder:  tool [-ruby] <path>")
		fmt.Println("2. Count unique chars:  tool -count <txt_folder>")
		fmt.Println("3. Import translation:  tool -import <text.txt> <original.dat> [output.dat]")
		os.Exit(1)
	}

	switch args[0] {
	case "-import":
		if len(args) < 3 {
			fmt.Println("Usage: tool -import <text.txt> <original.dat> [output.dat]")
		} else {
			outPath := ""
			if len(args) > 3 {
				outPath = args[3]
			}
			importDat(args[1], args[2], outPath)
		}

	case "-count":
		if len(args) < 2 {
			fmt.Println("Usage: tool -count <folder>")
		} else {
			countChars(args[1])
		}

	default:
		keepRuby := false
		var targets []string
		for _, a := range args {
			if a == "-ruby" {
				keepRuby = true
			} else {
				targets = append(targets, a)
			}
		}
		if len(targets) == 0 {
			fmt.Println("Error: no target path specified.")
			return
		}
		tgt := targets[0]
		info, err := os.Stat(tgt)
		if err != nil {
			fmt.Printf("Error: %s not found.\n", tgt)
			return
		}
		if info.IsDir() {
			files, _ := filepath.Glob(filepath.Join(tgt, "*.dat"))
			for _, fp := range files {
				exportDat(fp, keepRuby)
			}
			fmt.Println("[+] Batch export done!")
		} else {
			exportDat(tgt, keepRuby)
		}
	}
}
