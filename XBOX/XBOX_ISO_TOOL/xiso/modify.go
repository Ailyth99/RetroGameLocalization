package xiso

import (
	"fmt"
	"os"
	"strings"
)

type dirModEntry struct {
	Name   string
	Size   uint32
	Attr   uint8
	Sector uint32
}


func rebuildDirTable(entries []dirModEntry) ([]byte, uint32) {
	if len(entries) == 0 {
		buf := make([]byte, Sector)
		for i := range buf {
			buf[i] = 0xff
		}
		return buf, Sector
	}

	tree := NewTree()
	for _, e := range entries {
		tree.Insert(e.Name, e.Size, e.Attr)
	}

	preorder := tree.Preorder()

	offsets := make([]uint32, tree.Len())
	var pos uint32
	for _, idx := range preorder {
		node := tree.Get(idx)
		dl := entryDiskLen(node.Name)
		pos += sectorAlign(pos, dl)
		offsets[idx] = pos
		pos += dl
	}

	tableSize := pos
	bufSize := tableSize
	if bufSize%Sector != 0 {
		bufSize += Sector - bufSize%Sector
	}
	buf := make([]byte, bufSize)
	for i := range buf {
		buf[i] = 0xff
	}

	nameToSector := make(map[string]uint32)
	for _, e := range entries {
		nameToSector[e.Name] = e.Sector
	}

	for _, idx := range preorder {
		node := tree.Get(idx)
		off := offsets[idx]
		sector := nameToSector[node.Name]

		dn := DiskNode{
			Left:  0,
			Right: 0,
			Data:  Region{Sector: sector, Size: node.Size},
			Attr:  node.Attr,
			NLen:  uint8(len(node.Name)),
		}
		if node.Left != -1 {
			dn.Left = uint16(offsets[node.Left] / 4)
		}
		if node.Right != -1 {
			dn.Right = uint16(offsets[node.Right] / 4)
		}

		nodeBytes := dn.Bytes()
		copy(buf[off:], nodeBytes[:])
		copy(buf[off+DiskNodeSize:], []byte(node.Name))
	}

	return buf, tableSize
}

func readParentEntries(r ReaderAt, table DirTable) ([]dirModEntry, error) {
	entries, err := WalkTree(r, table)
	if err != nil {
		return nil, err
	}
	var result []dirModEntry
	for _, ent := range entries {
		result = append(result, dirModEntry{
			Name:   ent.Name,
			Size:   ent.Node.Data.Size,
			Attr:   ent.Node.Attr,
			Sector: ent.Node.Data.Sector,
		})
	}
	return result, nil
}

func findParentDir(r ReaderAt, root DirTable, path string) (DirTable, *Entry, error) {
	path = strings.ReplaceAll(path, "/", "\\")
	path = strings.TrimPrefix(path, "\\")
	parts := strings.Split(path, "\\")

	current := root
	for i, part := range parts {
		entries, err := WalkTree(r, current)
		if err != nil {
			return DirTable{}, nil, err
		}

		for _, ent := range entries {
			if strings.EqualFold(ent.Name, part) {
				if i == len(parts)-1 {
					return current, ent, nil
				}
				if ent.IsDir() {
					current = DirTable{Region: ent.Node.Data}
					break
				}
				return DirTable{}, nil, fmt.Errorf("not a directory: %s", part)
			}
		}
	}
	return DirTable{}, nil, fmt.Errorf("path not found: %s", path)
}


func RenameFile(isoPath, internalPath, newName string) error {
	newName = strings.ToUpper(newName)
	if len(newName) > MaxNameLen {
		return fmt.Errorf("name too long: %d > %d", len(newName), MaxNameLen)
	}

	f, err := os.OpenFile(isoPath, os.O_RDWR, 0)
	if err != nil {
		return fmt.Errorf("open ISO: %w", err)
	}
	defer f.Close()

	vol, err := ParseVolume(readSector(f, VolSector))
	if err != nil {
		return fmt.Errorf("parse volume: %w", err)
	}

	parent, target, err := findParentDir(f, vol.Root, internalPath)
	if err != nil {
		return err
	}
	if target.IsDir() {
		return fmt.Errorf("cannot rename directory")
	}

	oldName := target.Name
	if oldName == newName {
		return nil // no change needed
	}

	oldPadded := entryDiskLen(oldName)
	newPadded := entryDiskLen(newName)

	if newPadded <= oldPadded {
		nameOff := int64(target.Offset) + DiskNodeSize
		nameBuf := make([]byte, oldPadded-DiskNodeSize)
		copy(nameBuf, []byte(newName))
		if _, err := f.WriteAt(nameBuf, nameOff); err != nil {
			return fmt.Errorf("write name: %w", err)
		}
		nlenBuf := []byte{uint8(len(newName))}
		if _, err := f.WriteAt(nlenBuf, int64(target.Offset)+13); err != nil {
			return fmt.Errorf("write nlen: %w", err)
		}
		fmt.Printf("[+] Renamed %s -> %s (in-place)\n", oldName, newName)
		return nil
	}

	entries, err := readParentEntries(f, parent)
	if err != nil {
		return fmt.Errorf("read parent entries: %w", err)
	}

	for i, e := range entries {
		if strings.EqualFold(e.Name, oldName) {
			entries[i].Name = newName
			break
		}
	}

	buf, tableSize := rebuildDirTable(entries)
	allocSize := SectorsNeeded(uint64(tableSize)) * Sector
	parentSize := parent.Region.Size
	if parentSize%Sector != 0 {
		parentSize += Sector - parentSize%Sector
	}

	if allocSize > parentSize {
		return fmt.Errorf("new table (%d bytes) exceeds allocated space (%d bytes)", allocSize, parentSize)
	}

	tableOff := int64(parent.Region.Sector) * int64(Sector)
	if _, err := f.WriteAt(buf, tableOff); err != nil {
		return fmt.Errorf("write dir table: %w", err)
	}

	// update parent region size in grandparent (or volume root)
	// skip for now — size increase is within allocated space

	fmt.Printf("[+] Renamed %s -> %s (table rebuilt, %d bytes)\n", oldName, newName, tableSize)
	return nil
}


func AppendFile(isoPath, localPath, internalDir, fileName string) error {
	fileName = strings.ToUpper(fileName)
	if len(fileName) > MaxNameLen {
		return fmt.Errorf("name too long: %d > %d", len(fileName), MaxNameLen)
	}

	localData, err := os.ReadFile(localPath)
	if err != nil {
		return fmt.Errorf("read local file: %w", err)
	}
	if len(localData) == 0 {
		return fmt.Errorf("local file is empty")
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

	internalDir = strings.ReplaceAll(internalDir, "/", "\\")
	internalDir = strings.TrimPrefix(internalDir, "\\")
	internalDir = strings.TrimSuffix(internalDir, "\\")

	var parentTable DirTable
	if internalDir == "" || internalDir == "." {
		parentTable = vol.Root
	} else {
		parent, dirEntry, err := findParentDir(f, vol.Root, internalDir)
		if err != nil {
			return fmt.Errorf("find directory: %w", err)
		}
		if !dirEntry.IsDir() {
			return fmt.Errorf("not a directory: %s", internalDir)
		}
		_ = parent // we use dirEntry's data region
		parentTable = DirTable{Region: dirEntry.Node.Data}
	}

	eof := stat.Size()
	if eof%int64(Sector) != 0 {
		eof += int64(Sector) - eof%int64(Sector)
	}

	if _, err := f.WriteAt(localData, eof); err != nil {
		return fmt.Errorf("write file data: %w", err)
	}

	fileSize := uint32(len(localData))
	allocSize := SectorsNeeded(uint64(fileSize)) * Sector
	if uint32(len(localData)) < allocSize {
		zeros := make([]byte, allocSize-uint32(len(localData)))
		f.WriteAt(zeros, eof+int64(len(localData)))
	}

	newLBA := uint32(eof / int64(Sector))

	entries, err := readParentEntries(f, parentTable)
	if err != nil {
		return fmt.Errorf("read directory: %w", err)
	}

	for _, e := range entries {
		if strings.EqualFold(e.Name, fileName) {
			return fmt.Errorf("file already exists: %s", fileName)
		}
	}

	entries = append(entries, dirModEntry{
		Name:   fileName,
		Size:   fileSize,
		Attr:   AttrArchive,
		Sector: newLBA,
	})

	buf, tableSize := rebuildDirTable(entries)
	allocTableSize := SectorsNeeded(uint64(tableSize)) * Sector
	parentSize := parentTable.Region.Size
	if parentSize%Sector != 0 {
		parentSize += Sector - parentSize%Sector
	}

	if allocTableSize > parentSize {
		return fmt.Errorf("directory table full: need %d bytes, have %d", allocTableSize, parentSize)
	}

	tableOff := int64(parentTable.Region.Sector) * int64(Sector)
	if _, err := f.WriteAt(buf, tableOff); err != nil {
		return fmt.Errorf("write dir table: %w", err)
	}

	fmt.Printf("[+] Appended %s -> %s\\%s (LBA=%d, %d bytes)\n", localPath, internalDir, fileName, newLBA, fileSize)
	return nil
}
