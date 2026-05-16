package xiso

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

type ReaderAt interface {
	ReadAt(p []byte, off int64) (n int, err error)
}

func Extract(r ReaderAt, size int64, outDir string) error {
	vol, err := ParseVolume(readSector(r, VolSector))
	if err != nil {
		return fmt.Errorf("parse volume: %w", err)
	}

	tree, err := FileTree(r, vol.Root)
	if err != nil {
		return fmt.Errorf("walk file tree: %w", err)
	}

	if err := os.MkdirAll(outDir, 0755); err != nil {
		return err
	}

	for _, fe := range tree {
		dir := filepath.Join(outDir, filepath.FromSlash(fe.Dir))
		name := fe.Entry.Name
		full := filepath.Join(dir, name)

		if fe.Entry.IsDir() {
			fmt.Printf("  [DIR]  %s\n", filepath.Join(fe.Dir, name))
			if err := os.MkdirAll(full, 0755); err != nil {
				return err
			}
			continue
		}

		fmt.Printf("  [FILE] %s\n", filepath.Join(fe.Dir, name))
		if err := os.MkdirAll(dir, 0755); err != nil {
			return err
		}
		if err := extractFile(r, fe.Entry, full); err != nil {
			return err
		}
	}
	return nil
}

func extractFile(r ReaderAt, ent *Entry, dest string) error {
	f, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer f.Close()

	size := ent.Size()
	if size == 0 {
		return nil
	}

	off, err := ent.Node.Data.ByteOffset(0)
	if err != nil {
		return err
	}

	remain := int64(size)
	buf := make([]byte, 256*1024)
	for remain > 0 {
		toread := int64(len(buf))
		if toread > remain {
			toread = remain
		}
		n, err := r.ReadAt(buf[:toread], int64(off))
		if n > 0 {
			if _, werr := f.Write(buf[:n]); werr != nil {
				return werr
			}
			off += uint64(n)
			remain -= int64(n)
		}
		if err != nil {
			if err == io.EOF && remain == 0 {
				break
			}
			return err
		}
	}
	return nil
}

func GetFile(r ReaderAt, isoSize int64, internalPath, dest string) error {
	internalPath = strings.ReplaceAll(internalPath, "/", "\\")
	internalPath = strings.TrimPrefix(internalPath, "\\")

	vol, err := ParseVolume(readSector(r, VolSector))
	if err != nil {
		return fmt.Errorf("parse volume: %w", err)
	}

	ent := findEntry(r, vol.Root, internalPath)
	if ent == nil {
		return fmt.Errorf("file not found: %s", internalPath)
	}
	if ent.IsDir() {
		return fmt.Errorf("is a directory: %s", internalPath)
	}

	if err := extractFile(r, ent, dest); err != nil {
		return fmt.Errorf("extract: %w", err)
	}

	fmt.Printf("[+] Extracted %s -> %s (%d bytes)\n", internalPath, dest, ent.Size())
	return nil
}

func readSector(r ReaderAt, sector uint32) []byte {
	buf := make([]byte, Sector)
	r.ReadAt(buf, int64(uint64(sector)*SectorU64))
	return buf
}
