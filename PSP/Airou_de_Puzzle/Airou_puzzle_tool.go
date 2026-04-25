package main

import (
	"bytes"
	"compress/zlib"
	"encoding/binary"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type AcHeader struct {
	Magic     [2]byte
	FileCount uint16
	DataStart uint32
}

type AcEntry struct {
	HashID uint32
	Offset uint32
	Size   uint32
}

type ZcHeader struct {
	Magic    [2]byte
	Flag     uint8
	Constant uint8
	DecSize  uint32
}

const coral = "\033[38;2;218;81;92m"
const reset = "\033[0m"

func getExtension(data []byte) string {
	if len(data) < 4 { return ".bin" }
	m2, m4 := string(data[:2]), string(data[:4])
	switch {
	case m2 == "AC": return ".arc"
	case m2 == "SC": return ".sc"
	case m2 == "ND": return ".nd"
	case m4 == "MIG.": return ".gim"
	case m4 == "OMG.": return ".gmo"
	case bytes.HasPrefix(data, []byte("\x89PNG")): return ".png"
	}
	return ".bin"
}

func unpack(input, out string) error {
	f, err := os.Open(input); if err != nil { return err }
	defer f.Close()

	var h AcHeader
	binary.Read(f, binary.LittleEndian, &h)
	if string(h.Magic[:]) != "AC" { return fmt.Errorf("not an AC archive") }
	if out == "" { out = strings.TrimSuffix(input, filepath.Ext(input)) }
	os.MkdirAll(out, 0755)

	entries := make([]AcEntry, h.FileCount)
	binary.Read(f, binary.LittleEndian, &entries)

	fmt.Printf("%s[UNPACK]%s %s (%d files)\n", coral, reset, input, h.FileCount)

	for _, e := range entries {
		f.Seek(int64(e.Offset), 0)
		data := make([]byte, e.Size)
		f.Read(data)

		payload, suffix := data, ""
		if len(data) >= 8 && string(data[:2]) == "ZC" {
			var z ZcHeader
			binary.Read(bytes.NewReader(data), binary.LittleEndian, &z)
			suffix = "_ZC"  
			
			if z.Flag == 1 {
 
				zr, err := zlib.NewReader(bytes.NewReader(data[8:]))
				if err == nil {
					var b bytes.Buffer
					io.Copy(&b, zr)
					payload = b.Bytes()
					zr.Close()
				}
			} else {
 
				payload = data[8:]
				if uint32(len(payload)) > z.DecSize {
					payload = payload[:z.DecSize]
				}
			}
		}

		ext := getExtension(payload)
		fileName := fmt.Sprintf("%08X%s%s", e.HashID, suffix, ext)
		os.WriteFile(filepath.Join(out, fileName), payload, 0644)
		fmt.Printf("  -> %s\n", fileName)
	}
	return nil
}

func pack(folder, out string) error {
	dirEntries, _ := os.ReadDir(folder)
	type Item struct { ID uint32; Path string; ZC bool }
	var items []Item
	for _, ent := range dirEntries {
		if ent.IsDir() { continue }
		var id uint32
		if _, err := fmt.Sscanf(ent.Name()[:8], "%X", &id); err == nil {
			items = append(items, Item{id, filepath.Join(folder, ent.Name()), strings.Contains(ent.Name(), "_ZC")})
		}
	}
	sort.Slice(items, func(i, j int) bool { return items[i].ID < items[j].ID })

	if out == "" { out = strings.TrimSuffix(folder, string(os.PathSeparator)) + ".new" }
	outF, _ := os.Create(out); defer outF.Close()

	cnt := uint16(len(items))
	headSize := uint32(8 + int(cnt)*12)
	if headSize % 16 != 0 { headSize += (16 - (headSize % 16)) }

	curOffset := headSize
	var acEntries []AcEntry
	var dataChunks [][]byte

	fmt.Printf("%s[REPACK]%s Building %s\n", coral, reset, out)

	for _, it := range items {
		raw, _ := os.ReadFile(it.Path)
		var blob []byte
		if it.ZC {
			var buf bytes.Buffer
			zw, _ := zlib.NewWriterLevel(&buf, zlib.DefaultCompression)
			zw.Write(raw); zw.Close()
			zHead := ZcHeader{[2]byte{'Z', 'C'}, 1, 0x94, uint32(len(raw))}
			hBuf := new(bytes.Buffer); binary.Write(hBuf, binary.LittleEndian, zHead)
			blob = append(hBuf.Bytes(), buf.Bytes()...)
		} else {
			blob = raw
		}

		acEntries = append(acEntries, AcEntry{it.ID, curOffset, uint32(len(blob))})
		dataChunks = append(dataChunks, blob)
		curOffset += uint32(len(blob))
		padding := (16 - (curOffset % 16)) % 16
		curOffset += padding
	}

	binary.Write(outF, binary.LittleEndian, [2]byte{'A', 'C'})
	binary.Write(outF, binary.LittleEndian, cnt)
	binary.Write(outF, binary.LittleEndian, headSize)
	for _, e := range acEntries { binary.Write(outF, binary.LittleEndian, e) }
	
	pos, _ := outF.Seek(0, io.SeekCurrent)
	if uint32(pos) < headSize { outF.Write(make([]byte, headSize-uint32(pos))) }

	for i, data := range dataChunks {
		outF.Write(data)
		if i < len(dataChunks)-1 {
			tail := (16 - (uint32(len(data)) % 16)) % 16
			if tail > 0 { outF.Write(make([]byte, tail)) }
		}
	}
	return nil
}

func main() {
	u := flag.String("u", "", "Unpack AC"); r := flag.String("r", "", "Repack Folder"); o := flag.String("o", "", "Output")
	flag.Parse()
	if *u != "" { unpack(*u, *o) } else if *r != "" { pack(*r, *o) }
}