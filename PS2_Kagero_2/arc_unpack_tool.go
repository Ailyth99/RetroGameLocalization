package main

import (
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

const Mag = "ARC\x00" //Trapt/Kagero 2 ARC Magic

func readStr(f *os.File) string {
	var b []byte
	t := make([]byte, 1)
	for {
		if _, err := f.Read(t); err != nil || t[0] == 0 {
			break
		}
		b = append(b, t[0])
	}
	return string(b)
}

func unpack(src, dst string) bool {
	f, err := os.Open(src)
	if err != nil {
		return false
	}
	defer f.Close()

	head := make([]byte, 4)
	if f.Read(head); string(head) != Mag {
		return false
	}

	var cnt, base, s1, s2, z uint32
	binary.Read(f, binary.LittleEndian, &cnt)
	binary.Read(f, binary.LittleEndian, &base)
	binary.Read(f, binary.LittleEndian, &s1)
	binary.Read(f, binary.LittleEndian, &s2)
	binary.Read(f, binary.LittleEndian, &z)

	sub := strings.TrimSuffix(filepath.Base(src), filepath.Ext(src))
	dir := filepath.Join(dst, sub)
	os.MkdirAll(dir, 0755)

	fmt.Printf("Unpacking %s: %d files\n", filepath.Base(src), cnt)

	for i := uint32(0); i < cnt; i++ {
		var sz, sz2, nOfs, dOfs uint32
		binary.Read(f, binary.LittleEndian, &sz)
		binary.Read(f, binary.LittleEndian, &sz2)
		binary.Read(f, binary.LittleEndian, &nOfs)
		binary.Read(f, binary.LittleEndian, &dOfs)

		if i < cnt-1 {
			f.Seek(4, 1)
		}

		cur, _ := f.Seek(0, 1)

		f.Seek(int64(nOfs), 0)
		name := readStr(f)

		f.Seek(int64(base+dOfs), 0)
		buf := make([]byte, sz)
		io.ReadFull(f, buf)

		path := filepath.Join(dir, name)
		os.MkdirAll(filepath.Dir(path), 0755)
		os.WriteFile(path, buf, 0644)

		f.Seek(cur, 0)
	}
	return true
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: arcunpacker <in_path> <out_dir>")
		return
	}

	src, dst := os.Args[1], os.Args[2]
	info, err := os.Stat(src)
	if err != nil {
		fmt.Println("Error:", err)
		return
	}

	if !info.IsDir() {
		unpack(src, dst)
	} else {
		filepath.Walk(src, func(p string, d os.DirEntry, e error) error {
			if e == nil && !d.IsDir() {
				unpack(p, dst)
			}
			return nil
		})
	}
	fmt.Println("Done.")
}