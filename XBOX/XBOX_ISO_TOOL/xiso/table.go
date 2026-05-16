package xiso

import (
	"encoding/csv"
	"fmt"
	"os"
	"strconv"
	"strings"
)

func ExportTable(r ReaderAt, size int64, csvPath string) error {
	vol, err := ParseVolume(readSector(r, VolSector))
	if err != nil {
		return fmt.Errorf("parse volume: %w", err)
	}

	tree, err := FileTree(r, vol.Root)
	if err != nil {
		return fmt.Errorf("walk file tree: %w", err)
	}

	f, err := os.Create(csvPath)
	if err != nil {
		return err
	}
	defer f.Close()

	w := csv.NewWriter(f)
	w.Write([]string{"Path", "LBA", "Size", "Sectors"})

	count := 0
	for _, fe := range tree {
		if fe.Entry.IsDir() {
			continue
		}

		fullPath := fe.Dir + "\\" + fe.Entry.Name
		fullPath = strings.ReplaceAll(fullPath, "/", "\\")
		for strings.HasPrefix(fullPath, "\\\\") {
			fullPath = fullPath[1:]
		}

		lba := fe.Entry.Node.Data.Sector
		fsize := fe.Entry.Size()
		sectors := SectorsNeeded(uint64(fsize))

		w.Write([]string{
			fullPath,
			strconv.FormatUint(uint64(lba), 10),
			strconv.FormatUint(uint64(fsize), 10),
			strconv.FormatUint(uint64(sectors), 10),
		})
		count++
	}
	w.Flush()

	fmt.Printf("[+] Exported %d files -> %s\n", count, csvPath)
	return nil
}
