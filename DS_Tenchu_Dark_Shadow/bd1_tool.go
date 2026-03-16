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

var magics = map[string]string{
	"RGCN": ".NCGR", "RCSN": ".NSCR", "RLCN": ".NCLR",
	"RNAN": ".NANR", "RECN": ".NCER", "RMAR": ".NAMR",
	"RTXT": ".NTXR", "BGPK": ".BGPK", "SSEQ": ".SSEQ",
	"SSAR": ".SSAR", "STRM": ".STRM", "BMD0": ".NSBMD",
	"BTX0": ".NSBTX",
}

func getExt(p []byte) string {
	if len(p) < 4 {
		return ".bin"
	}
	sig := string(p[:4])
	if e, ok := magics[sig]; ok {
		return e
	}
	if p[0] == 0x10 {
		return ".lz"
	}
	return ".bin"
}

func unpack(src string) {
	f, err := os.Open(src)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}
	defer f.Close()

	head := make([]byte, 4)
	f.Read(head)
	if !bytes.Equal(head, []byte("BD1\x02")) {
		fmt.Printf("Warning: magic mismatch %v\n", head)
	}

	f.Seek(0x10, 0)
	var cnt uint32
	binary.Read(f, binary.LittleEndian, &cnt)

	dir := strings.TrimSuffix(src, filepath.Ext(src)) + "_extracted"
	os.MkdirAll(dir, 0755)

	fmt.Printf("[*] Files: %d, Target: %s\n", cnt, dir)

	type entry struct{ off, sz uint32 }
	list := make([]entry, cnt)
	f.Seek(0x14, 0)
	for i := uint32(0); i < cnt; i++ {
		binary.Read(f, binary.LittleEndian, &list[i].off)
		binary.Read(f, binary.LittleEndian, &list[i].sz)
	}

	for i, e := range list {
		if e.sz == 0 {
			continue
		}
		f.Seek(int64(e.off), 0)
		buf := make([]byte, e.sz)
		f.Read(buf)

		name := fmt.Sprintf("%04d_0x%08X%s", i, e.off, getExt(buf))
		os.WriteFile(filepath.Join(dir, name), buf, 0644)
	}
	fmt.Println("[+] Unpack done.")
}

func inject(base, dir, out string) {
	data, err := os.ReadFile(base)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	fs, _ := os.ReadDir(dir)
	succ := 0

	for _, info := range fs {
		n := info.Name()
		if !strings.Contains(n, "_0x") {
			continue
		}

		parts := strings.Split(n, "_0x")
		offStr := strings.Split(parts[1], ".")[0]
		var off uint32
		fmt.Sscanf(offStr, "%X", &off)

		sub, _ := os.ReadFile(filepath.Join(dir, n))
		
		// boundary check
		if int(off)+len(sub) > len(data) {
			continue
		}

		copy(data[off:], sub)
		succ++
	}

	os.WriteFile(out, data, 0644)
	fmt.Printf("[+] Inject done. Files: %d, Out: %s\n", succ, out)
}

func usage() {
	fmt.Println("BD1 tool")
	fmt.Println("\nUsage:")
	fmt.Println("  unpack [file.bd1]")
	fmt.Println("  inject [base.bd1] [mod_dir] [out.bd1]")
}

func main() {
	if len(os.Args) < 2 {
		usage()
		return
	}

	cmd := os.Args[1]
	switch cmd {
	case "unpack":
		if len(os.Args) < 3 {
			usage()
			return
		}
		unpack(os.Args[2])
	case "inject":
		if len(os.Args) < 5 {
			usage()
			return
		}
		inject(os.Args[2], os.Args[3], os.Args[4])
	default:
		usage()
	}
}