package main

import (
	"bytes"
	"encoding/binary"
	"encoding/csv"
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"
)

type rec struct {
	name string
	lba  uint32
	size uint32
	sect uint32
	typ  string
}

func getStr(data []byte, off uint32) string {
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

func parseCsv(path string) (map[string]rec, error) {
	b, err := os.ReadFile(path)
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
	if len(rows) < 1 {
		return nil, fmt.Errorf("empty csv")
	}

	headers := rows[0]
	idxMap := make(map[string]int)
	for i, h := range headers {
		idxMap[strings.TrimSpace(h)] = i
	}

	nameIdx := -1
	if i, ok := idxMap["Path"]; ok {
		nameIdx = i
	} else if i, ok := idxMap["Name"]; ok {
		nameIdx = i
	}
	if nameIdx == -1 {
		return nil, fmt.Errorf("missing Path or Name column")
	}

	lbaIdx := idxMap["LBA"]
	sizeIdx := idxMap["Size"]
	sectIdx := idxMap["Sectors"]

	res := make(map[string]rec)
	for i := 1; i < len(rows); i++ {
		row := rows[i]
		if len(row) < 4 {
			continue
		}

		// Normalize path for matching:
		// 1. Convert to uppercase
		// 2. Convert backslashes to forward slashes
		// 3. Trim leading slashes
		// 4. Remove "DATA/" prefix if present
		fullPath := strings.ToUpper(strings.ReplaceAll(row[nameIdx], "\\", "/"))
		fullPath = strings.TrimPrefix(fullPath, "/")
		fullPath = strings.TrimPrefix(fullPath, "DATA/")

		lba, _ := strconv.ParseUint(row[lbaIdx], 10, 32)
		size, _ := strconv.ParseUint(row[sizeIdx], 10, 32)
		sect, _ := strconv.ParseUint(row[sectIdx], 10, 32)

		res[fullPath] = rec{
			name: fullPath,
			lba:  uint32(lba),
			size: uint32(size),
			sect: uint32(sect),
		}
	}
	return res, nil
}

func extract(inBin, outCsv string) error {
	data, err := os.ReadFile(inBin)
	if err != nil {
		return err
	}

	if len(data) < 4 {
		return fmt.Errorf("file too small")
	}

	count := binary.LittleEndian.Uint32(data[0:4])
	var items []rec

	if count > 0 {
		if len(data) < 0x28 {
			return fmt.Errorf("entry 0 out of bounds")
		}
		fid := binary.LittleEndian.Uint32(data[0x04:0x08])
		size := binary.LittleEndian.Uint32(data[0x18:0x1C])
		lba := binary.LittleEndian.Uint32(data[0x20:0x24])
		sect := binary.LittleEndian.Uint32(data[0x24:0x28])

		items = append(items, rec{
			name: getStr(data, fid),
			lba:  lba,
			size: size,
			sect: sect,
			typ:  "Entry0",
		})
	}

	for i := uint32(1); i < count; i++ {
		off := uint32(0x30 + (i-1)*36)
		if int(off+28) > len(data) {
			break
		}

		fid := binary.LittleEndian.Uint32(data[off+4 : off+8])
		size := binary.LittleEndian.Uint32(data[off+12 : off+16])
		lba := binary.LittleEndian.Uint32(data[off+20 : off+24])
		sect := binary.LittleEndian.Uint32(data[off+24 : off+28])

		items = append(items, rec{
			name: getStr(data, fid),
			lba:  lba,
			size: size,
			sect: sect,
			typ:  fmt.Sprintf("Entry%d", i),
		})
	}

	f, err := os.Create(outCsv)
	if err != nil {
		return err
	}
	defer f.Close()

	writer := csv.NewWriter(f)
	writer.Write([]string{"Name", "LBA", "Size", "Sectors", "Type"})

	for _, it := range items {
		writer.Write([]string{
			it.name,
			strconv.FormatUint(uint64(it.lba), 10),
			strconv.FormatUint(uint64(it.size), 10),
			strconv.FormatUint(uint64(it.sect), 10),
			it.typ,
		})
	}
	writer.Flush()

	fmt.Printf("[+] Table extracted -> %s (%d files)\n", outCsv, len(items))
	return nil
}

func patch(origBin, layoutCsv, outBin string) error {
	newMap, err := parseCsv(layoutCsv)
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
	var missing []string

	for i := uint32(0); i < count; i++ {
		var off, fid uint32

		if i == 0 {
			off = 0x04
			if int(off+4) > len(data) {
				break
			}
			fid = binary.LittleEndian.Uint32(data[off : off+4])
		} else {
			off = 0x30 + (i-1)*36
			if int(off+8) > len(data) {
				break
			}
			fid = binary.LittleEndian.Uint32(data[off+4 : off+8])
		}

		rawName := getStr(data, fid)
		// Normalize index path similarly: uppercase, forward slashes, trim leading slashes/DATA prefix
		fullKey := strings.ToUpper(strings.ReplaceAll(rawName, "\\", "/"))
		fullKey = strings.TrimPrefix(fullKey, "/")
		fullKey = strings.TrimPrefix(fullKey, "DATA/")

		if info, ok := newMap[fullKey]; ok {
			if i == 0 {
				if int(0x28) > len(data) {
					continue
				}
				binary.LittleEndian.PutUint32(data[0x18:0x1C], info.size)
				binary.LittleEndian.PutUint32(data[0x20:0x24], info.lba)
				binary.LittleEndian.PutUint32(data[0x24:0x28], info.sect)
			} else {
				if int(off+28) > len(data) {
					continue
				}
				binary.LittleEndian.PutUint32(data[off+12:off+16], info.size)
				binary.LittleEndian.PutUint32(data[off+20:off+24], info.lba)
				binary.LittleEndian.PutUint32(data[off+24:off+28], info.sect)
			}
			patched++
		} else {
			missing = append(missing, rawName)
		}
	}

	if err := os.WriteFile(outBin, data, 0644); err != nil {
		return err
	}

	fmt.Printf("[+] Patched %d/%d entries -> %s\n", patched, count, outBin)
	if len(missing) > 0 {
		fmt.Printf("[!] Missing entries (%d):\n", len(missing))
		for _, m := range missing {
			fmt.Printf("  - '%s'\n", m)
		}
	}
	return nil
}

func main() {
	ePtr := flag.Bool("e", false, "Extract mode")
	pPtr := flag.Bool("p", false, "Patch mode")
	iPtr := flag.String("i", "", "Input CSV or BIN")
	bPtr := flag.String("b", "", "Original BIN to patch")
	oPtr := flag.String("o", "", "Output CSV or BIN")
	flag.Parse()

	if *ePtr && *iPtr != "" && *oPtr != "" {
		if err := extract(*iPtr, *oPtr); err != nil {
			fmt.Printf("[-] Extract err: %v\n", err)
			os.Exit(1)
		}
	} else if *pPtr && *iPtr != "" && *bPtr != "" && *oPtr != "" {
		if err := patch(*bPtr, *iPtr, *oPtr); err != nil {
			fmt.Printf("[-] Patch err: %v\n", err)
			os.Exit(1)
		}
	} else {
		fmt.Println("Usage:")
		fmt.Println("  Extract : tool -e -i INDEX.BIN -o TABLE.CSV")
		fmt.Println("  Patch   : tool -p -b INDEX.BIN -i NEW_TBL.CSV -o INDEX_PATCHED.BIN")
		os.Exit(1)
	}
}