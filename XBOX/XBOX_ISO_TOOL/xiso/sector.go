package xiso

type Allocator struct {
	Next uint32
}

func NewAllocator() Allocator {
	return Allocator{Next: 33}
}

func (a *Allocator) Alloc(bytes uint64) uint32 {
	sectors := SectorsNeeded(bytes)
	start := a.Next
	a.Next += sectors
	return start
}

func SectorsNeeded(n uint64) uint32 {
	if n == 0 {
		return 1
	}
	s := uint32(n / SectorU64)
	if n%SectorU64 > 0 {
		s++
	}
	return s
}
