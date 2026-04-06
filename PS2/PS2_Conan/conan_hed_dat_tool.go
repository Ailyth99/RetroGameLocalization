package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

var extList = []string{
	".tm2", ".uad", ".upm", ".dat", ".db", ".irx", ".txt",
	".vly", ".ag", ".ipu", ".lb", ".ups", ".upl", ".ico",
}

type Entry struct {
	Name string `json:"name"`
	Ofs  uint32 `json:"offset"`
	Size uint32 `json:"size"` 
}

type Manifest struct {
	BaseDat string  `json:"base_dat"`
	Files   []Entry `json:"files"`
}

func isNameChar(b byte) bool {
	return (b >= 'a' && b <= 'z') || (b >= 'A' && b <= 'Z') ||
		(b >= '0' && b <= '9') || b == '.' || b == '_' || b == '-'
}

func unpack(hedPath, datPath, outDir string) {
	hed, err := os.ReadFile(hedPath)
	if err != nil {
		fmt.Println("Err read HED:", err)
		return
	}

	datF, err := os.Open(datPath)
	if err != nil {
		fmt.Println("Err open DAT:", err)
		return
	}
	defer datF.Close()

	dStat, _ := datF.Stat()
	datSz := uint32(dStat.Size())

	if len(hed) < 8 {
		return
	}
	cnt := binary.LittleEndian.Uint32(hed[4:8])
	fmt.Printf("Scanning %s (Size: %d, Count: ~%d)...\n", datPath, datSz, cnt)

	os.MkdirAll(outDir, 0755)

	var found []Entry
	for _, extStr := range extList {
		ext := []byte(extStr)
		pos := 0
		for {
			idx := bytes.Index(hed[pos:], ext)
			if idx == -1 {
				break
			}
			rPos := pos + idx
			nStart := rPos - 30
			if nStart < 0 {
				nStart = 0
			}
			for i := nStart; i < rPos; i++ {
				if b := hed[i]; b == 0 || b < 32 || b > 126 {
					nStart = i + 1
				}
			}
			name := string(hed[nStart : rPos+len(ext)])
			
			valid := len(name) >= 5
			if valid {
				for i := 0; i < len(name); i++ {
					if !isNameChar(name[i]) {
						valid = false
						break
					}
				}
			}

			if valid && nStart >= 8 {
				ofsPos := nStart - 8
				ofs := binary.LittleEndian.Uint32(hed[ofsPos:])
				sz := binary.LittleEndian.Uint32(hed[ofsPos+4:])

				if ofs > 0 && sz > 0 && ofs < datSz && (ofs+sz) <= datSz {
					found = append(found, Entry{Name: name, Ofs: ofs, Size: sz})
				}
			}
			pos = rPos + 1
		}
	}

	seen := make(map[uint32]bool)
	var final []Entry
	for _, r := range found {
		if !seen[r.Ofs] {
			seen[r.Ofs] = true
			final = append(final, r)
		}
	}
	sort.Slice(final, func(i, j int) bool { return final[i].Ofs < final[j].Ofs })

	man := Manifest{
		BaseDat: filepath.Base(datPath),
		Files:   make([]Entry, 0, len(final)),
	}

	for _, f := range final {
		outName := f.Name
		base := strings.TrimSuffix(f.Name, filepath.Ext(f.Name))
		ext := filepath.Ext(f.Name)
		c := 1
		for {
			testPath := filepath.Join(outDir, outName)
			if _, err := os.Stat(testPath); os.IsNotExist(err) {
				break
			}
			outName = fmt.Sprintf("%s_%d%s", base, c, ext)
			c++
		}

		entry := Entry{Name: outName, Ofs: f.Ofs, Size: f.Size}
		man.Files = append(man.Files, entry)

		datF.Seek(int64(f.Ofs), 0)
		buf := make([]byte, f.Size)
		io.ReadFull(datF, buf)
		os.WriteFile(filepath.Join(outDir, outName), buf, 0644)
		
		fmt.Printf("Extracted: %s\n", outName)
	}

	jsonBytes, _ := json.MarshalIndent(man, "", "  ")
	os.WriteFile(filepath.Join(outDir, "manifest.json"), jsonBytes, 0644)
	fmt.Printf("\nDone! Extracted %d files. Manifest saved.\n", len(final))
}

func repack(datPath, inDir string) {
	jsonPath := filepath.Join(inDir, "manifest.json")
	jsonRaw, err := os.ReadFile(jsonPath)
	if err != nil {
		fmt.Println("Err: manifest.json not found in", inDir)
		return
	}

	var man Manifest
	if err := json.Unmarshal(jsonRaw, &man); err != nil {
		fmt.Println("Err parsing JSON:", err)
		return
	}

	f, err := os.OpenFile(datPath, os.O_RDWR, 0644)
	if err != nil {
		fmt.Println("Err opening DAT (RW):", err)
		return
	}
	defer f.Close()

	fmt.Printf("Injecting files from %s into %s...\n", inDir, datPath)
	
	count := 0
	skipped := 0

	for _, entry := range man.Files {
		localPath := filepath.Join(inDir, entry.Name)
		
		info, err := os.Stat(localPath)
		if os.IsNotExist(err) {
			continue // No replacement file, keep original
		}

		newSz := uint32(info.Size())
		
		if newSz > entry.Size {
			fmt.Printf("[SKIP] %s is too big! (New: %d > Max: %d)\n", entry.Name, newSz, entry.Size)
			skipped++
			continue
		}

		data, err := os.ReadFile(localPath)
		if err != nil {
			fmt.Printf("Err reading %s: %v\n", entry.Name, err)
			continue
		}

		f.Seek(int64(entry.Ofs), 0)
		f.Write(data)

		if newSz < entry.Size {
			padSz := entry.Size - newSz
			pad := make([]byte, padSz) // Zero initialized
			f.Write(pad)
		}

		fmt.Printf("[OK] Injected %s (%d/%d bytes)\n", entry.Name, newSz, entry.Size)
		count++
	}

	fmt.Printf("\nFinished. Injected: %d, Skipped (Too Big): %d\n", count, skipped)
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage:")
		fmt.Println("  1. Unpack: conan_tool unpack <hed> <dat> <out_dir>")
		fmt.Println("  2. Repack: conan_tool repack <target_dat> <in_dir>")
		fmt.Println("     (Repack requires manifest.json in in_dir)")
		return
	}

	mode := os.Args[1]
	
	if mode == "unpack" && len(os.Args) >= 5 {
		unpack(os.Args[2], os.Args[3], os.Args[4])
	} else if mode == "repack" && len(os.Args) >= 4 {
		repack(os.Args[2], os.Args[3])
	} else {
		fmt.Println("Invalid arguments.")
	}
}