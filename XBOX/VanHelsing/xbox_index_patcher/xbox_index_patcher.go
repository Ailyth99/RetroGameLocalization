package main

import (
	"bytes"
	"encoding/binary"
	"encoding/csv"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// XBOX index.bin entry layout (same as PS2):
//
// Entry 0 at 0x04 (40 bytes): fid[4] pad[12] size[4] pad[4] lba[4] sect[4] pad[4]
// Entries 1+ at 0x30 (36 bytes each): pad[4] fid[4] pad[4] size[4] pad[4] lba[4] sect[4] pad[4]
//
// String table: null-terminated paths at end of file, fid = absolute offset into data

type xboxRec struct {
	Name   string
	LBA    uint32
	Size   uint32
	Sectors uint32
}

func xboxGetStr(data []byte, off uint32) string {
	start := int(off)
	if start >= len(data) {
		return ""
	}
	end := start
	for end < len(data) && data[end] != 0 {
		end++
	}
	return string(data[start:end])
}

func xboxExtractIndex(binPath, csvPath string) error {
	data, err := os.ReadFile(binPath)
	if err != nil {
		return err
	}
	if len(data) < 4 {
		return fmt.Errorf("file too small")
	}

	count := binary.LittleEndian.Uint32(data[0:4])
	if count == 0 || count > 10000 {
		return fmt.Errorf("invalid entry count: %d", count)
	}

	var items []xboxRec

	// Entry 0 at 0x04 (40 bytes)
	if count > 0 {
		if len(data) < 0x28 {
			return fmt.Errorf("entry 0 out of bounds")
		}
		fid := binary.LittleEndian.Uint32(data[0x04:0x08])
		size := binary.LittleEndian.Uint32(data[0x18:0x1C])
		lba := binary.LittleEndian.Uint32(data[0x20:0x24])
		sect := binary.LittleEndian.Uint32(data[0x24:0x28])

		items = append(items, xboxRec{
			Name:    xboxGetStr(data, fid),
			LBA:     lba,
			Size:    size,
			Sectors: sect,
		})
	}

	// Entries 1+ at 0x30, 36 bytes each
	for i := uint32(1); i < count; i++ {
		off := 0x30 + (i-1)*36
		if int(off+28) > len(data) {
			break
		}

		fid := binary.LittleEndian.Uint32(data[off+4 : off+8])
		size := binary.LittleEndian.Uint32(data[off+12 : off+16])
		lba := binary.LittleEndian.Uint32(data[off+20 : off+24])
		sect := binary.LittleEndian.Uint32(data[off+24 : off+28])

		items = append(items, xboxRec{
			Name:    xboxGetStr(data, fid),
			LBA:     lba,
			Size:    size,
			Sectors: sect,
		})
	}

	f, err := os.Create(csvPath)
	if err != nil {
		return err
	}
	defer f.Close()

	w := csv.NewWriter(f)
	w.Write([]string{"Path", "LBA", "Size", "Sectors"})
	for _, it := range items {
		w.Write([]string{
			it.Name,
			strconv.FormatUint(uint64(it.LBA), 10),
			strconv.FormatUint(uint64(it.Size), 10),
			strconv.FormatUint(uint64(it.Sectors), 10),
		})
	}
	w.Flush()

	fmt.Printf("[+] Exported %d entries -> %s\n", len(items), csvPath)
	return nil
}

func xboxParseCsv(csvPath string) (map[string]xboxRec, error) {
	b, err := os.ReadFile(csvPath)
	if err != nil {
		return nil, err
	}
	if bytes.HasPrefix(b, []byte{0xEF, 0xBB, 0xBF}) {
		b = b[3:]
	}

	reader := csv.NewReader(bytes.NewReader(b))
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) < 2 {
		return nil, fmt.Errorf("csv has no data rows")
	}

	headers := rows[0]
	idxMap := make(map[string]int)
	for i, h := range headers {
		idxMap[strings.TrimSpace(strings.ToLower(h))] = i
	}

	nameIdx, ok := idxMap["path"]
	if !ok {
		nameIdx, ok = idxMap["name"]
	}
	if !ok {
		return nil, fmt.Errorf("missing Path or Name column")
	}
	lbaIdx := idxMap["lba"]
	sizeIdx := idxMap["size"]
	sectIdx := idxMap["sectors"]

	res := make(map[string]xboxRec)
	for _, row := range rows[1:] {
		if len(row) < 4 {
			continue
		}
		base := strings.ToUpper(filepath.Base(strings.TrimSpace(row[nameIdx])))
		lba, _ := strconv.ParseUint(strings.TrimSpace(row[lbaIdx]), 10, 32)
		size, _ := strconv.ParseUint(strings.TrimSpace(row[sizeIdx]), 10, 32)
		sect, _ := strconv.ParseUint(strings.TrimSpace(row[sectIdx]), 10, 32)
		res[base] = xboxRec{Name: base, LBA: uint32(lba), Size: uint32(size), Sectors: uint32(sect)}
	}
	return res, nil
}

func xboxPatchIndex(origBin, csvPath, outBin string) error {
	newMap, err := xboxParseCsv(csvPath)
	if err != nil {
		return err
	}

	data, err := os.ReadFile(origBin)
	if err != nil {
		return err
	}
	if len(data) < 4 {
		return fmt.Errorf("file too small")
	}

	count := binary.LittleEndian.Uint32(data[0:4])
	patched := 0

	for i := uint32(0); i < count; i++ {
		var fid uint32

		if i == 0 {
			if len(data) < 0x28 {
				break
			}
			fid = binary.LittleEndian.Uint32(data[0x04:0x08])
		} else {
			off := 0x30 + (i-1)*36
			if int(off+8) > len(data) {
				break
			}
			fid = binary.LittleEndian.Uint32(data[off+4 : off+8])
		}

		rawName := xboxGetStr(data, fid)
		base := strings.ToUpper(filepath.Base(rawName))

		if info, ok := newMap[base]; ok {
			if i == 0 {
				binary.LittleEndian.PutUint32(data[0x18:0x1C], info.Size)
				binary.LittleEndian.PutUint32(data[0x20:0x24], info.LBA)
				binary.LittleEndian.PutUint32(data[0x24:0x28], info.Sectors)
			} else {
				off := 0x30 + (i-1)*36
				binary.LittleEndian.PutUint32(data[off+12:off+16], info.Size)
				binary.LittleEndian.PutUint32(data[off+20:off+24], info.LBA)
				binary.LittleEndian.PutUint32(data[off+24:off+28], info.Sectors)
			}
			patched++
		}
	}

	if err := os.WriteFile(outBin, data, 0644); err != nil {
		return err
	}
	fmt.Printf("[+] Patched %d/%d entries -> %s\n", patched, count, outBin)
	return nil
}

func main() {
	ePtr := flag.Bool("e", false, "Extract index.bin -> CSV")
	pPtr := flag.Bool("p", false, "Patch index.bin from CSV")
	iPtr := flag.String("i", "", "Input: CSV (patch) or BIN (extract)")
	bPtr := flag.String("b", "", "Original index.bin to patch")
	oPtr := flag.String("o", "", "Output: CSV or BIN path")
	flag.Parse()

	if *ePtr && *iPtr != "" {
		out := *oPtr
		if out == "" {
			out = strings.TrimSuffix(*iPtr, filepath.Ext(*iPtr)) + ".csv"
		}
		if err := xboxExtractIndex(*iPtr, out); err != nil {
			fmt.Fprintf(os.Stderr, "[-] Extract error: %v\n", err)
			os.Exit(1)
		}
	} else if *pPtr && *iPtr != "" && *bPtr != "" {
		out := *oPtr
		if out == "" {
			out = *bPtr + ".patched"
		}
		if err := xboxPatchIndex(*bPtr, *iPtr, out); err != nil {
			fmt.Fprintf(os.Stderr, "[-] Patch error: %v\n", err)
			os.Exit(1)
		}
	} else {
		fmt.Println("XBOX Index Patcher - index.bin extract/patch tool")
		fmt.Println()
		fmt.Println("Commands:")
		fmt.Println()
		fmt.Println("  Extract index.bin to CSV:")
		fmt.Println("    xbox_index_patcher -e -i INDEX.BIN")
		fmt.Println("    xbox_index_patcher -e -i INDEX.BIN -o table.csv")
		fmt.Println()
		fmt.Println("  Patch index.bin from CSV:")
		fmt.Println("    xbox_index_patcher -p -b INDEX.BIN -i table.csv")
		fmt.Println("    xbox_index_patcher -p -b INDEX.BIN -i table.csv -o INDEX_PATCHED.BIN")
		os.Exit(1)
	}
}
