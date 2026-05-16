package xiso

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
)

type Writer struct {
	alloc Allocator
	out   io.WriteSeeker
}

type fileAlloc struct {
	sector uint32
	size   uint32
}

type dirEntry struct {
	Name  string
	Size  uint32
	IsDir bool
	Index int // index of sub-directory in dirList
}

type dirInfo struct {
	Path     string
	Entries  []dirEntry
	TreeSize uint32 // computed size of the serialized dirent table
}

func Repack(srcDir, isoPath string) error {
	dirs, err := scanDir(srcDir)
	if err != nil {
		return err
	}
	if len(dirs) == 0 {
		return fmt.Errorf("empty source directory")
	}

	// bottom-up: compute each tree's serialized size
	for i := len(dirs) - 1; i >= 0; i-- {
		dirs[i].TreeSize = computeTreeSize(dirs[i].Entries, dirs)
	}

	f, err := os.Create(isoPath)
	if err != nil {
		return err
	}
	defer f.Close()

	w := &Writer{
		alloc: NewAllocator(),
		out:   f,
	}


	dirSectors := make([]uint32, len(dirs))
	for i, d := range dirs {
		dirSectors[i] = w.alloc.Alloc(uint64(d.TreeSize))
	}

	fileSectors := make([][]fileAlloc, len(dirs))
	for i, d := range dirs {
		fileSectors[i] = make([]fileAlloc, len(d.Entries))
		for j, e := range d.Entries {
			if !e.IsDir {
				fileSectors[i][j].size = e.Size
				if e.Size > 0 {
					fileSectors[i][j].sector = w.alloc.Alloc(uint64(e.Size))
				}
			}
		}
	}


	for i, d := range dirs {
		tableBytes, err := serializeDirTable(d, dirs, dirSectors, fileSectors[i])
		if err != nil {
			return fmt.Errorf("serialize dir %q: %w", d.Path, err)
		}
		off := int64(dirSectors[i]) * int64(Sector)
		if _, err := w.out.Seek(off, io.SeekStart); err != nil {
			return err
		}
		if _, err := w.out.Write(tableBytes); err != nil {
			return err
		}
	}

	for i, d := range dirs {
		for j, e := range d.Entries {
			if e.IsDir || e.Size == 0 {
				continue
			}
			fs := fileSectors[i][j]
			off := int64(fs.sector) * int64(Sector)
			if err := copyFileInto(w.out, filepath.Join(d.Path, e.Name), off, e.Size); err != nil {
				return fmt.Errorf("write file %q: %w", e.Name, err)
			}
		}
	}

	vol := Volume{}
	vol.Magic0 = Magic
	vol.Magic1 = Magic
	vol.Root = DirTable{Region: Region{Sector: dirSectors[0], Size: dirs[0].TreeSize}}
	volBuf := vol.Bytes()

	if _, err := w.out.Seek(int64(VolSector)*int64(Sector), io.SeekStart); err != nil {
		return err
	}
	if _, err := w.out.Write(volBuf); err != nil {
		return err
	}

	endOff, err := w.out.Seek(0, io.SeekEnd)
	if err != nil {
		return err
	}
	aligned := ((endOff + int64(32*Sector) - 1) / int64(32*Sector)) * int64(32*Sector)
	if aligned > endOff {
		padding := make([]byte, aligned-endOff)
		w.out.Write(padding)
	}

	return nil
}

func scanDir(srcDir string) ([]dirInfo, error) {
	var dirs []dirInfo

	err := filepath.Walk(srcDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() {
			return nil
		}

		entries, err := readDirEntries(path)
		if err != nil {
			return err
		}

		di := dirInfo{Path: path, Entries: entries}
		dirs = append(dirs, di)
		return nil
	})

	pathIdx := make(map[string]int)
	for i, d := range dirs {
		pathIdx[d.Path] = i
	}

	for i := range dirs {
		for j := range dirs[i].Entries {
			if dirs[i].Entries[j].IsDir {
				subPath := filepath.Join(dirs[i].Path, dirs[i].Entries[j].Name)
				idx, ok := pathIdx[subPath]
				if !ok {
					return nil, fmt.Errorf("subdir not found: %s", subPath)
				}
				dirs[i].Entries[j].Index = idx
			}
		}
	}

	return dirs, err
}

func readDirEntries(dir string) ([]dirEntry, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}

	var result []dirEntry
	for _, e := range entries {
		name := e.Name()
		info, err := e.Info()
		if err != nil {
			return nil, err
		}

		if e.IsDir() {
			result = append(result, dirEntry{Name: name, IsDir: true})
		} else {
			result = append(result, dirEntry{Name: name, Size: uint32(info.Size())})
		}
	}
	return result, nil
}

func entryDiskLen(name string) uint32 {
	l := uint32(DiskNodeSize) + uint32(len(name))
	// align to 4 bytes
	return (l + 3) &^ 3
}

func sectorAlign(offset, size uint32) uint32 {
	used := SectorsNeeded(uint64(offset))
	needed := SectorsNeeded(uint64(offset + size))
	if offset%Sector != 0 && needed > used {
		return ((offset+Sector-1)/Sector)*Sector - offset
	}
	return 0
}

func computeTreeSize(entries []dirEntry, dirs []dirInfo) uint32 {
	if len(entries) == 0 {
		return Sector // empty dirs are 2048 bytes of 0xff
	}

	tree := NewTree()
	for _, e := range entries {
		var attr uint8
		var size uint32
		if e.IsDir {
			attr = AttrDirectory
			subSize := dirs[e.Index].TreeSize
			// round up to sector boundary
			size = subSize
			if size%Sector != 0 {
				size += Sector - size%Sector
			}
		} else {
			attr = AttrArchive
			size = e.Size
		}
		tree.Insert(e.Name, size, attr)
	}

	preorder := tree.Preorder()
	var total uint32
	for _, idx := range preorder {
		node := tree.Get(idx)
		dl := entryDiskLen(node.Name)
		total += sectorAlign(total, dl) + dl
	}
	return total
}

func serializeDirTable(di dirInfo, dirs []dirInfo, dirSectors []uint32, fAlloc []fileAlloc) ([]byte, error) {
	if len(di.Entries) == 0 {
		buf := make([]byte, Sector)
		for i := range buf {
			buf[i] = 0xff
		}
		return buf, nil
	}

	// build AVL tree
	tree := NewTree()
	for _, e := range di.Entries {
		var attr uint8
		var size uint32
		if e.IsDir {
			attr = AttrDirectory
			subSize := dirs[e.Index].TreeSize
			size = subSize
			if size%Sector != 0 {
				size += Sector - size%Sector
			}
		} else {
			attr = AttrArchive
			size = e.Size
		}
		tree.Insert(e.Name, size, attr)
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
	if tableSize == 0 {
		tableSize = Sector
	}
	bufSize := tableSize
	if bufSize%Sector != 0 {
		bufSize += Sector - bufSize%Sector
	}
	buf := make([]byte, bufSize)
	for i := range buf {
		buf[i] = 0xff
	}


	nameToSector := make(map[string]uint32)
	for j, e := range di.Entries {
		if e.IsDir {
			nameToSector[e.Name] = dirSectors[e.Index]
		} else {
			nameToSector[e.Name] = fAlloc[j].sector
		}
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

	return buf, nil
}

func copyFileInto(w io.WriteSeeker, path string, off int64, size uint32) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	if _, err := w.Seek(off, io.SeekStart); err != nil {
		return err
	}

	buf := make([]byte, 256*1024)
	remain := int64(size)
	for remain > 0 {
		toread := int64(len(buf))
		if toread > remain {
			toread = remain
		}
		n, err := f.Read(buf[:toread])
		if n > 0 {
			if _, werr := w.Write(buf[:n]); werr != nil {
				return werr
			}
			remain -= int64(n)
		}
		if err != nil {
			if err == io.EOF {
				break
			}
			return err
		}
	}

	if remain > 0 {
		zeros := make([]byte, remain)
		w.Write(zeros)
	}

	return nil
}
