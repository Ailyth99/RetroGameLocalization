package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)


func unpack(inFile string) {
	data, err := os.ReadFile(inFile)
	if err != nil {
		fmt.Println("Error reading file:", err)
		return
	}

	outDir := "OPEN_EXTRACT"
	os.MkdirAll(outDir, 0755)

	pos, idx, size := 0, 0, len(data)

	for pos < size-2 {
		blkSz := int(binary.BigEndian.Uint16(data[pos : pos+2]))
		// Stop if block size is 0 or exceeds remaining data (padding zone)
		if blkSz <= 0 || pos+blkSz > size {
			break
		}

		chunk := data[pos : pos+blkSz]
		dst := decode(chunk)

		// Name files as 01.tim, 02.tim, etc.
		outName := fmt.Sprintf("%02d.tim", idx+1)
		os.WriteFile(filepath.Join(outDir, outName), dst, 0644)
		fmt.Printf("Unpacked %s: Raw=%d -> Dec=%d bytes\n", outName, blkSz, len(dst))

		pos += blkSz
		idx++
	}
	fmt.Println("Unpacking complete. Output directory:", outDir)
}

func decode(chunk []byte) []byte {
	if len(chunk) < 12 {
		return nil
	}
	
	escTbl := chunk[2:12]
	numEsc := 10
	
	for i := 1; i < 10; i++ {
		if escTbl[i] == escTbl[i-1] {
			numEsc = i
			break
		}
	}

	validEsc := make(map[byte]bool)
	for i := 0; i < numEsc; i++ {
		validEsc[escTbl[i]] = true
	}

	var dst []byte
	p := 12
	for p < len(chunk) {
		b := chunk[p]
		if !validEsc[b] {
			dst = append(dst, b)
			p++
		} else {
			if p+1 < len(chunk) {
				count := chunk[p+1]
				for i := 0; i < int(count); i++ {
					dst = append(dst, b)
				}
				p += 2
			} else {
				dst = append(dst, b)
				p++
			}
		}
	}
	return dst
}


type charGain struct {
	b byte
	g int
}

func pack(inDir, outFile string) {
	files, err := os.ReadDir(inDir)
	if err != nil {
		fmt.Println("Error reading directory:", err)
		return
	}

	var timFiles []string
	for _, f := range files {
		if !f.IsDir() && strings.HasSuffix(strings.ToLower(f.Name()), ".tim") {
			timFiles = append(timFiles, f.Name())
		}
	}

	sort.Slice(timFiles, func(i, j int) bool {
		numI, _ := strconv.Atoi(strings.TrimSuffix(timFiles[i], ".tim"))
		numJ, _ := strconv.Atoi(strings.TrimSuffix(timFiles[j], ".tim"))
		return numI < numJ
	})

	if len(timFiles) == 0 {
		fmt.Println("No .tim files found in directory.")
		return
	}

	var outBuf bytes.Buffer

	for _, fname := range timFiles {
		fpath := filepath.Join(inDir, fname)
		raw, err := os.ReadFile(fpath)
		if err != nil {
			fmt.Println("Error reading:", fpath)
			return
		}

		comp, err := encode(raw)
		if err != nil {
			fmt.Printf("Failed to pack %s: %v\n", fname, err)
			return
		}

		outBuf.Write(comp)
		fmt.Printf("Packed %s: Raw=%d -> Comp=%d bytes\n", fname, len(raw), len(comp))
	}

	os.WriteFile(outFile, outBuf.Bytes(), 0644)
	fmt.Println("Packing complete. Output file:", outFile)
}

func encode(raw []byte) ([]byte, error) {
	gains := make(map[byte]int)
	i, sz := 0, len(raw)

	for i < sz {
		b := raw[i]
		run := 1
		for i+run < sz && raw[i+run] == b && run < 255 {
			run++
		}
		gains[b] += (run - 2) 
		i += run
	}

	var cg []charGain
	for k, v := range gains {
		if v > 0 {
			cg = append(cg, charGain{k, v})
		}
	}
	sort.Slice(cg, func(i, j int) bool {
		return cg[i].g > cg[j].g
	})

	var escTbl []byte
	for j := 0; j < len(cg) && j < 10; j++ {
		escTbl = append(escTbl, cg[j].b)
	}
	if len(escTbl) == 0 {
		escTbl = append(escTbl, 0)
	}
	for len(escTbl) < 10 {
		escTbl = append(escTbl, escTbl[len(escTbl)-1])
	}

	validEsc := make(map[byte]bool)
	for _, b := range escTbl {
		validEsc[b] = true
	}

	var dst bytes.Buffer
	i = 0
	for i < sz {
		b := raw[i]
		if validEsc[b] {
			run := 1
			for i+run < sz && raw[i+run] == b && run < 255 {
				run++
			}
			dst.WriteByte(b)
			dst.WriteByte(byte(run))
			i += run
		} else {
			dst.WriteByte(b)
			i++
		}
	}

	blkSz := 12 + dst.Len()
	if blkSz > 65535 {
		return nil, fmt.Errorf("single frame exceeds 64KB limit")
	}

	res := make([]byte, blkSz)
	binary.BigEndian.PutUint16(res[0:2], uint16(blkSz))
	copy(res[2:12], escTbl)
	copy(res[12:], dst.Bytes())

	return res, nil
}


func printUsage() {
	fmt.Println("Zutto Issho OPEN.DAT Tool")
	fmt.Println("Usage:")
	fmt.Println("  zutto_open_tool -u <file.dat>              // Unpack and decompress to OPEN_EXTRACT")
	fmt.Println("  zutto_open_tool -r <dir_path> [-o <name>]  // Pack directory to DAT (Default: NEW_OPEN.DAT)")
}

func main() {
	args := os.Args
	if len(args) < 3 {
		printUsage()
		return
	}

	cmd := args[1]
	if cmd == "-u" {
		unpack(args[2])
	} else if cmd == "-r" {
		inDir := args[2]
		outFile := "NEW_OPEN.DAT"
		if len(args) >= 5 && args[3] == "-o" {
			outFile = args[4]
		}
		pack(inDir, outFile)
	} else {
		printUsage()
	}
}