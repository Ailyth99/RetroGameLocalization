package main

import (
	"encoding/binary"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

func unpack(binPath, outDir string) error {
	if _, err := os.Stat(binPath); os.IsNotExist(err) {
		return fmt.Errorf("input file '%s' not found", binPath)
	}

	if outDir == "" {
		outDir = binPath + "_extracted"
	}

	if err := os.MkdirAll(outDir, 0755); err != nil {
		return fmt.Errorf("failed to create output dir: %v", err)
	}

	fmt.Printf("[*] Unpacking (XBOX) '%s' to '%s'...\n", binPath, outDir)

	f, err := os.Open(binPath)
	if err != nil {
		return err
	}
	defer f.Close()

	var hdr [16]byte
	if _, err := io.ReadFull(f, hdr[:]); err != nil {
		return fmt.Errorf("invalid file header: %v", err)
	}

	fileCount := binary.LittleEndian.Uint32(hdr[0:4])
	dataOffset := binary.LittleEndian.Uint32(hdr[4:8])
	blockSize := binary.LittleEndian.Uint32(hdr[8:12])

	fmt.Printf("  - File count: %d\n", fileCount)
	fmt.Printf("  - Data offset: %d\n", dataOffset)
	fmt.Printf("  - Block size: %d\n", blockSize)

	type Entry struct {
		Name       string
		Size       uint32
		FileOffset uint32
	}

	var entries []Entry
	var found uint32

	for found < fileCount {
		var entryData [36]byte
		if _, err := io.ReadFull(f, entryData[:]); err != nil {
			return err
		}

		nameOff := binary.LittleEndian.Uint32(entryData[0:4])
		size := binary.LittleEndian.Uint32(entryData[8:12])
		blockOffset := binary.LittleEndian.Uint32(entryData[16:20])

		pos, _ := f.Seek(0, io.SeekCurrent)

		f.Seek(int64(nameOff), io.SeekStart)
		var nameBytes []byte
		buf := make([]byte, 1)
		for {
			_, err := f.Read(buf)
			if err != nil || buf[0] == 0 {
				break
			}
			nameBytes = append(nameBytes, buf[0])
		}

		name := string(nameBytes)
		name = strings.ReplaceAll(name, "\\", "/")
		name = strings.ReplaceAll(name, "\x00", "")

		entries = append(entries, Entry{
			Name:       name,
			Size:       size,
			FileOffset: dataOffset + (blockOffset * blockSize),
		})

		f.Seek(pos, io.SeekStart)
		found++
	}

	fmt.Printf("  - Found %d valid entries.\n", len(entries))

	for _, entry := range entries {
		outPath := filepath.Join(outDir, entry.Name)
		if err := os.MkdirAll(filepath.Dir(outPath), 0755); err != nil {
			return err
		}

		f.Seek(int64(entry.FileOffset), io.SeekStart)
		fileData := make([]byte, entry.Size)
		if _, err := io.ReadFull(f, fileData); err != nil {
			if err != io.ErrUnexpectedEOF && err != io.EOF {
				return err
			}
		}

		if err := os.WriteFile(outPath, fileData, 0644); err != nil {
			return err
		}

		fmt.Printf("  -> Extracted: %s (%d bytes)\n", entry.Name, entry.Size)
	}

	return nil
}

func repack(resDir, outBin, origBin string) error {
	if _, err := os.Stat(resDir); os.IsNotExist(err) {
		return fmt.Errorf("resource directory '%s' not found", resDir)
	}

	if outBin == "" {
		outBin = resDir + ".GRP.bin.new"
	}

	if origBin == "" {
		if strings.HasSuffix(resDir, "_extracted") {
			origBin = strings.TrimSuffix(resDir, "_extracted")
		} else {
			origBin = resDir + ".GRP.bin"
		}
	}

	if _, err := os.Stat(origBin); os.IsNotExist(err) {
		return fmt.Errorf("original GRP.bin template '%s' not found", origBin)
	}

	fmt.Printf("[*] Repacking (XBOX) '%s' into '%s'...\n", resDir, outBin)
	fmt.Printf("  - Using original header template: %s\n", origBin)

	fOrig, err := os.Open(origBin)
	if err != nil {
		return err
	}
	defer fOrig.Close()

	var hdr [16]byte
	if _, err := io.ReadFull(fOrig, hdr[:]); err != nil {
		return err
	}

	fileCount := binary.LittleEndian.Uint32(hdr[0:4])
	dataOffset := binary.LittleEndian.Uint32(hdr[4:8])
	blockSize := binary.LittleEndian.Uint32(hdr[8:12])

	fOrig.Seek(0, io.SeekStart)
	headerData := make([]byte, dataOffset)
	if _, err := io.ReadFull(fOrig, headerData); err != nil {
		return err
	}

	type RepackEntry struct {
		Name     string
		EntryPos int64
		NameOff  uint32
		Hash     uint32
		U1       uint32
		U2       uint32
		U3       uint32
		U4       uint32
	}

	var entries []RepackEntry
	fOrig.Seek(16, io.SeekStart)

	for i := uint32(0); i < fileCount; i++ {
		entryPos, _ := fOrig.Seek(0, io.SeekCurrent)
		var entryData [36]byte
		if _, err := io.ReadFull(fOrig, entryData[:]); err != nil {
			return err
		}

		nameOff := binary.LittleEndian.Uint32(entryData[0:4])
		hash := binary.LittleEndian.Uint32(entryData[4:8])
		u1 := binary.LittleEndian.Uint32(entryData[12:16])
		u2 := binary.LittleEndian.Uint32(entryData[24:28])
		u3 := binary.LittleEndian.Uint32(entryData[28:32])
		u4 := binary.LittleEndian.Uint32(entryData[32:36])

		pos, _ := fOrig.Seek(0, io.SeekCurrent)

		fOrig.Seek(int64(nameOff), io.SeekStart)
		var nameBytes []byte
		buf := make([]byte, 1)
		for {
			_, err := fOrig.Read(buf)
			if err != nil || buf[0] == 0 {
				break
			}
			nameBytes = append(nameBytes, buf[0])
		}

		name := string(nameBytes)
		name = strings.ReplaceAll(name, "\\", "/")
		name = strings.ReplaceAll(name, "\x00", "")

		entries = append(entries, RepackEntry{
			Name:     name,
			EntryPos: entryPos,
			NameOff:  nameOff,
			Hash:     hash,
			U1:       u1,
			U2:       u2,
			U3:       u3,
			U4:       u4,
		})

		fOrig.Seek(pos, io.SeekStart)
	}

	currentBlockOffset := uint32(0)
	var fileDataBlocks [][]byte

	for _, entry := range entries {
		filePath := filepath.Join(resDir, entry.Name)
		data, err := os.ReadFile(filePath)
		if err != nil {
			return fmt.Errorf("file missing: %s", filePath)
		}

		newSize := uint32(len(data))
		newBlockCount := (newSize + blockSize - 1) / blockSize

		patchedEntry := make([]byte, 36)
		binary.LittleEndian.PutUint32(patchedEntry[0:4], entry.NameOff)
		binary.LittleEndian.PutUint32(patchedEntry[4:8], entry.Hash)
		binary.LittleEndian.PutUint32(patchedEntry[8:12], newSize)
		binary.LittleEndian.PutUint32(patchedEntry[12:16], entry.U1)
		binary.LittleEndian.PutUint32(patchedEntry[16:20], currentBlockOffset)
		binary.LittleEndian.PutUint32(patchedEntry[20:24], newBlockCount)
		binary.LittleEndian.PutUint32(patchedEntry[24:28], entry.U2)
		binary.LittleEndian.PutUint32(patchedEntry[28:32], entry.U3)
		binary.LittleEndian.PutUint32(patchedEntry[32:36], entry.U4)

		copy(headerData[entry.EntryPos:entry.EntryPos+36], patchedEntry)

		padLen := newBlockCount*blockSize - newSize
		paddedData := make([]byte, int(newSize+padLen))
		for i := uint32(0); i < padLen; i++ {
			paddedData[newSize+i] = 0x90
		}
		copy(paddedData, data)
		fileDataBlocks = append(fileDataBlocks, paddedData)

		fmt.Printf("  -> Packed: %s (%d bytes)\n", entry.Name, newSize)

		currentBlockOffset += newBlockCount
	}

	fOut, err := os.Create(outBin)
	if err != nil {
		return err
	}
	defer fOut.Close()

	if _, err := fOut.Write(headerData); err != nil {
		return err
	}
	for _, block := range fileDataBlocks {
		if _, err := fOut.Write(block); err != nil {
			return err
		}
	}

	fmt.Printf("[*] Repack complete! Saved to %s\n", outBin)
	return nil
}

func main() {
	uPtr := flag.String("u", "", "Unpack GRP.bin (XBOX)")
	rPtr := flag.String("r", "", "Repack directory to GRP.bin (XBOX)")
	oPtr := flag.String("o", "", "Output path")
	tPtr := flag.String("t", "", "Original GRP.bin template")

	flag.Parse()

	if *uPtr != "" {
		if err := unpack(*uPtr, *oPtr); err != nil {
			fmt.Printf("[-] Error: %v\n", err)
			os.Exit(1)
		}
	} else if *rPtr != "" {
		if err := repack(*rPtr, *oPtr, *tPtr); err != nil {
			fmt.Printf("[-] Error: %v\n", err)
			os.Exit(1)
		}
	} else {
		flag.Usage()
	}
}
