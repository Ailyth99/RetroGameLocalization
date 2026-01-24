package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

const (
	MagHead = "MB11CDVD"
	MagArc  = "ARCC"
	MagEnd  = "AEXC"
	Align   = 0x800
	RecSize = 0x2C // 32(name) + 4(ofs) + 4(size) + 4(pad)
)

func getAlign(n uint32) uint32 {
	return (n + Align - 1) / Align * Align
}

func unpack(src, dst string) error {
	f, err := os.Open(src)
	if err != nil {
		return err
	}
	defer f.Close()

	head := make([]byte, 8)
	if f.Read(head); string(head) != MagHead {
		return fmt.Errorf("invalid magic")
	}

	var count, pad, baseOfs, unk uint32
	binary.Read(f, binary.LittleEndian, &count)
	binary.Read(f, binary.LittleEndian, &pad)
	binary.Read(f, binary.LittleEndian, &baseOfs)
	binary.Read(f, binary.LittleEndian, &unk) // ARCC

	fmt.Printf("Files: %d, BaseOfs: 0x%X\n", count, baseOfs)
	os.MkdirAll(dst, 0755)

	type Rec struct {
		Name string
		Ofs  uint32
		Size uint32
	}
	list := make([]Rec, count)
	
	f.Seek(24, 0) // Skip header to index
	for i := uint32(0); i < count; i++ {
		nameBuf := make([]byte, 32)
		f.Read(nameBuf)
		
		var relOfs, size, z uint32
		binary.Read(f, binary.LittleEndian, &relOfs)
		binary.Read(f, binary.LittleEndian, &size)
		binary.Read(f, binary.LittleEndian, &z)

		list[i] = Rec{
			Name: strings.TrimRight(string(nameBuf), "\x00"),
			Ofs:  relOfs*Align + baseOfs,
			Size: size,
		}
	}

	for _, item := range list {
		fmt.Printf("Extracting: %s\n", item.Name)
		f.Seek(int64(item.Ofs), 0)
		
		buf := make([]byte, item.Size)
		io.ReadFull(f, buf)
		os.WriteFile(filepath.Join(dst, item.Name), buf, 0644)
	}
	
	return nil
}

func pack(src, dst string) error {
	entries, err := os.ReadDir(src)
	if err != nil {
		return err
	}

	var list []string
	for _, e := range entries {
		if !e.IsDir() {
			list = append(list, e.Name())
		}
	}

	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()

	nFiles := uint32(len(list))
	
	rawBase := uint32(24 + nFiles*RecSize + 4)
	baseOfs := getAlign(rawBase)

	out.Write([]byte(MagHead))
	binary.Write(out, binary.LittleEndian, nFiles)
	binary.Write(out, binary.LittleEndian, uint32(0))
	binary.Write(out, binary.LittleEndian, baseOfs)
	out.Write([]byte(MagArc))

	var curOfs uint32 = 0
	for _, name := range list {
		info, _ := os.Stat(filepath.Join(src, name))
		size := uint32(info.Size())

		// Name (32 bytes)
		nBuf := make([]byte, 32)
		copy(nBuf, name)
		out.Write(nBuf)

		// Metadata
		binary.Write(out, binary.LittleEndian, curOfs/Align)
		binary.Write(out, binary.LittleEndian, size)
		binary.Write(out, binary.LittleEndian, uint32(0))

		curOfs = getAlign(curOfs + size)
	}

	out.Write([]byte(MagEnd))
	pos, _ := out.Seek(0, 1)
	out.Write(make([]byte, int64(baseOfs)-pos))

	for _, name := range list {
		fmt.Printf("Packing: %s\n", name)
		data, _ := os.ReadFile(filepath.Join(src, name))
		out.Write(data)

		padLen := getAlign(uint32(len(data))) - uint32(len(data))
		out.Write(make([]byte, padLen))
	}

	return nil
}

func main() {
	if len(os.Args) < 4 {
		fmt.Println("Usage:")
		fmt.Println("  unpack <input.mb> <out_dir>")
		fmt.Println("  repack <in_dir> <output.mb>")
		return
	}

	op, arg1, arg2 := os.Args[1], os.Args[2], os.Args[3]
	var err error

	if op == "unpack" {
		err = unpack(arg1, arg2)
	} else if op == "repack" {
		err = pack(arg1, arg2)
	} else {
		fmt.Println("Unknown command")
		return
	}

	if err != nil {
		fmt.Println("Error:", err)
	} else {
		fmt.Printf("Done! Output: %s\n", arg2)
	}
}