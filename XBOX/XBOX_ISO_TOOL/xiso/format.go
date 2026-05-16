package xiso

import (
	"encoding/binary"
	"fmt"
)

const (
	Sector     uint32 = 2048
	SectorU64  uint64 = 2048
	VolSector  uint32 = 32
	MaxNameLen        = 255
)

// magic: MICROSOFT*XBOX*MEDIA
var Magic = [0x14]byte{
	'M', 'I', 'C', 'R', 'O', 'S', 'O', 'F', 'T',
	'*', 'X', 'B', 'O', 'X', '*', 'M', 'E', 'D', 'I', 'A',
}

const (
	AttrReadOnly  uint8 = 1 << 0
	AttrHidden    uint8 = 1 << 1
	AttrSystem    uint8 = 1 << 2
	AttrDirectory uint8 = 1 << 4
	AttrArchive   uint8 = 1 << 5
	AttrNormal    uint8 = 1 << 7
)

type Region struct {
	Sector uint32
	Size   uint32
}

func (r Region) Empty() bool { return r.Size == 0 }

func (r Region) ByteOffset(extra uint64) (uint64, error) {
	if extra >= uint64(r.Size) {
		return 0, fmt.Errorf("offset %d >= size %d", extra, r.Size)
	}
	return SectorU64*uint64(r.Sector) + extra, nil
}

type DirTable struct {
	Region Region
}

func (t DirTable) Empty() bool { return t.Region.Empty() }

// Volume is the XDVDFS volume descriptor at sector 32
type Volume struct {
	Magic0   [0x14]byte
	Root     DirTable
	Filetime uint64
	_        [0x7c8]byte
	Magic1   [0x14]byte
}

func (v *Volume) Valid() bool {
	return v.Magic0 == Magic && v.Magic1 == Magic
}

func (v *Volume) Bytes() []byte {
	buf := make([]byte, Sector)
	le(buf, v)
	return buf
}

func ParseVolume(buf []byte) (*Volume, error) {
	if len(buf) < int(Sector) {
		return nil, fmt.Errorf("volume buffer too small: %d", len(buf))
	}
	v := &Volume{}
	if err := leRead(buf, v); err != nil {
		return nil, err
	}
	if !v.Valid() {
		return nil, fmt.Errorf("invalid XDVDFS magic")
	}
	return v, nil
}

type DiskNode struct {
	Left  uint16
	Right uint16
	Data  Region
	Attr  uint8
	NLen  uint8
}

const DiskNodeSize = 0x0e

func (n *DiskNode) Bytes() [DiskNodeSize]byte {
	var buf [DiskNodeSize]byte
	le(buf[:], n)
	return buf
}

func ParseDiskNode(buf []byte) (*DiskNode, error) {
	if len(buf) < DiskNodeSize {
		return nil, fmt.Errorf("node buffer too small")
	}
	n := &DiskNode{}
	if err := leRead(buf[:DiskNodeSize], n); err != nil {
		return nil, err
	}
	return n, nil
}

type Entry struct {
	Node   DiskNode
	Name   string
	Offset uint64
}

func (e *Entry) IsDir() bool  { return e.Node.Attr&AttrDirectory != 0 }
func (e *Entry) IsFile() bool { return !e.IsDir() }
func (e *Entry) Size() uint32 { return e.Node.Data.Size }


func ReadEntry(r ReaderAt, offset uint64) (*Entry, error) {
	var raw [DiskNodeSize]byte
	if _, err := r.ReadAt(raw[:], int64(offset)); err != nil {
		return nil, fmt.Errorf("read dirent at %d: %w", offset, err)
	}

	allFF, allZero := true, true
	for _, b := range raw {
		if b != 0xff {
			allFF = false
		}
		if b != 0x00 {
			allZero = false
		}
	}
	if allFF || allZero {
		return nil, nil
	}

	node, err := ParseDiskNode(raw[:])
	if err != nil {
		return nil, err
	}

	ent := &Entry{Node: *node, Offset: offset}
	nlen := int(node.NLen)
	if nlen > 0 {
		nameBuf := make([]byte, nlen)
		if _, err := r.ReadAt(nameBuf, int64(offset)+DiskNodeSize); err != nil {
			return nil, fmt.Errorf("read name at %d: %w", offset, err)
		}
		ent.Name = string(nameBuf)
	}
	return ent, nil
}

func WalkTree(r ReaderAt, table DirTable) ([]*Entry, error) {
	if table.Empty() {
		return nil, nil
	}

	var result []*Entry
	stack := []uint64{0}

	for len(stack) > 0 {
		top := stack[len(stack)-1]
		stack = stack[:len(stack)-1]

		offset, err := table.Region.ByteOffset(top)
		if err != nil {
			return nil, err
		}

		ent, err := ReadEntry(r, offset)
		if err != nil {
			return nil, err
		}
		if ent == nil {
			continue
		}

		
		if ent.Node.Right != 0 && ent.Node.Right != 0xffff {
			stack = append(stack, 4*uint64(ent.Node.Right))
		}
		if ent.Node.Left != 0 && ent.Node.Left != 0xffff {
			stack = append(stack, 4*uint64(ent.Node.Left))
		}

		result = append(result, ent)
	}
	return result, nil
}

type FileEntry struct {
	Dir  string
	Entry *Entry
}

func FileTree(r ReaderAt, root DirTable) ([]FileEntry, error) {
	var result []FileEntry
	type task struct {
		dir   string
		table DirTable
	}
	stack := []task{{dir: "", table: root}}

	for len(stack) > 0 {
		cur := stack[len(stack)-1]
		stack = stack[:len(stack)-1]

		entries, err := WalkTree(r, cur.table)
		if err != nil {
			return nil, err
		}

		for _, ent := range entries {
			result = append(result, FileEntry{Dir: cur.dir, Entry: ent})
			if ent.IsDir() {
				sub := DirTable{Region: ent.Node.Data}
				childDir := cur.dir + "/" + ent.Name
				stack = append(stack, task{dir: childDir, table: sub})
			}
		}
	}
	return result, nil
}

func le(buf []byte, v interface{}) {
	w := &bufWriter{buf: buf}
	binary.Write(w, binary.LittleEndian, v)
}

func leRead(buf []byte, v interface{}) error {
	r := &bufReader{buf: buf}
	return binary.Read(r, binary.LittleEndian, v)
}

type bufWriter struct {
	buf []byte
	pos int
}

func (w *bufWriter) Write(p []byte) (int, error) {
	n := copy(w.buf[w.pos:], p)
	w.pos += n
	return n, nil
}

type bufReader struct {
	buf []byte
	pos int
}

func (r *bufReader) Read(p []byte) (int, error) {
	n := copy(p, r.buf[r.pos:])
	r.pos += n
	return n, nil
}
