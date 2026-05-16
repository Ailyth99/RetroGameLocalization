package xiso

import (
	"fmt"
	"io"
	"os"
	"strings"
)


func InjectFile(isoPath, internalPath, localPath string) error {
	internalPath = strings.ReplaceAll(internalPath, "/", "\\")
	internalPath = strings.ToUpper(strings.TrimPrefix(internalPath, "\\"))

	localData, err := os.ReadFile(localPath)
	if err != nil {
		return fmt.Errorf("read local file: %w", err)
	}

	f, err := os.OpenFile(isoPath, os.O_RDWR, 0)
	if err != nil {
		return fmt.Errorf("open ISO: %w", err)
	}
	defer f.Close()

	stat, err := f.Stat()
	if err != nil {
		return err
	}

	vol, err := ParseVolume(readSector(f, VolSector))
	if err != nil {
		return fmt.Errorf("parse volume: %w", err)
	}

	target := findEntry(f, vol.Root, internalPath)
	if target == nil {
		return fmt.Errorf("file not found in ISO: %s", internalPath)
	}

	origSize := target.Size()
	newSize := uint32(len(localData))

	if newSize > origSize {
		return fmt.Errorf("new file (%d bytes) is larger than original (%d bytes)", newSize, origSize)
	}

	dataOff, err := target.Node.Data.ByteOffset(0)
	if err != nil {
		return fmt.Errorf("get data offset: %w", err)
	}

	allocSize := uint64(origSize)
	endOff := dataOff + allocSize
	if endOff > uint64(stat.Size()) {
		return fmt.Errorf("data region extends past end of ISO")
	}

	writeBuf := make([]byte, allocSize)
	copy(writeBuf, localData)

	if _, err := f.WriteAt(writeBuf, int64(dataOff)); err != nil {
		return fmt.Errorf("write file data: %w", err)
	}


	sizeOff := int64(target.Offset) + 8
	sizeBuf := make([]byte, 4)
	le(sizeBuf, newSize)
	if _, err := f.WriteAt(sizeBuf, sizeOff); err != nil {
		return fmt.Errorf("update size field: %w", err)
	}

	fmt.Printf("[+] Injected %s -> %s (%d -> %d bytes)\n", localPath, internalPath, origSize, newSize)
	return nil
}

func findEntry(r ReaderAt, root DirTable, target string) *Entry {
	parts := strings.Split(target, "\\")
	if len(parts) == 0 {
		return nil
	}

	current := root
	for i, part := range parts {
		entries, err := WalkTree(r, current)
		if err != nil {
			return nil
		}

		found := false
		for _, ent := range entries {
			if strings.ToUpper(ent.Name) == strings.ToUpper(part) {
				if i == len(parts)-1 {
					return ent
				}
				if ent.IsDir() {
					current = DirTable{Region: ent.Node.Data}
					found = true
					break
				}
				return nil
			}
		}
		if !found {
			return nil
		}
	}
	return nil
}


func InjectFileWithPadding(isoPath, internalPath, localPath string) error {
	return InjectFile(isoPath, internalPath, localPath)
}

var _ io.Reader
