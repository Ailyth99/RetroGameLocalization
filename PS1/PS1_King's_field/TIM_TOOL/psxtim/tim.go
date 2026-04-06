package psxtim

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"image"
	"image/color"
	"io"
)

const (
	TimTag      = 0x00000010
	Pmode4BPP   = 0
	Pmode8BPP   = 1
	Pmode16BPP  = 2
	Pmode24BPP  = 3
	FlagHasClut = 0x08
)

type TIM struct {
	BPP            int
	HasClut        bool
	OrgX, OrgY     uint16
	Width, Height  uint16
	ClutOrgX, ClutOrgY uint16
	NumCluts       int
	ColorsPerClut  int
	ClutData       []uint16
	PixelData      []byte
}

type ScanResult struct {
	Offset int64
	Size   int64
	Info   TIM
}

func Decode(r io.Reader) (*TIM, error) {
	var tag uint32
	if err := binary.Read(r, binary.LittleEndian, &tag); err != nil { return nil, err }
	if tag != TimTag { return nil, errors.New("not a tim") }

	var flag uint32
	binary.Read(r, binary.LittleEndian, &flag)

	t := &TIM{}
	pmode := flag & 0x03
	t.HasClut = (flag & FlagHasClut) != 0

	switch pmode {
	case Pmode4BPP: t.BPP = 4
	case Pmode8BPP: t.BPP = 8
	case Pmode16BPP: t.BPP = 16
	case Pmode24BPP: t.BPP = 24
	default: return nil, errors.New("invalid mode")
	}

	//索引模式必须有CLUT
	if (pmode == Pmode4BPP || pmode == Pmode8BPP) && !t.HasClut {
		return nil, errors.New("indexed tim must have clut")
	}

	if t.HasClut {
		var clutLen uint32
		binary.Read(r, binary.LittleEndian, &clutLen)
		if clutLen < 12 || clutLen > 1024*1024 { return nil, errors.New("bad clut len") }
		
		var cx, cy, cw, ch uint16
		binary.Read(r, binary.LittleEndian, &cx)
		binary.Read(r, binary.LittleEndian, &cy)
		binary.Read(r, binary.LittleEndian, &cw)
		binary.Read(r, binary.LittleEndian, &ch)
		
		if cx >= 1024 || cy >= 512 || cw == 0 || ch == 0 { return nil, errors.New("bad clut header") }

		t.ClutOrgX, t.ClutOrgY = cx, cy
		t.ColorsPerClut, t.NumCluts = int(cw), int(ch)
		dataSize := (int(clutLen) - 12) / 2
		if dataSize < t.ColorsPerClut * t.NumCluts { return nil, errors.New("clut data too short") }

		t.ClutData = make([]uint16, dataSize)
		binary.Read(r, binary.LittleEndian, &t.ClutData)
	}

	var imgLen uint32
	binary.Read(r, binary.LittleEndian, &imgLen)
	if imgLen < 12 || imgLen > 64*1024*1024 { return nil, errors.New("bad img len") }

	var ix, iy, iw, ih uint16
	binary.Read(r, binary.LittleEndian, &ix)
	binary.Read(r, binary.LittleEndian, &iy)
	binary.Read(r, binary.LittleEndian, &iw)
	binary.Read(r, binary.LittleEndian, &ih)

	if ix >= 1024 || iy >= 512 || iw == 0 || ih == 0 { return nil, errors.New("bad img header") }

	t.OrgX, t.OrgY, t.Height = ix, iy, ih
	var expectedSize int
	switch t.BPP {
	case 4: 
		t.Width = iw * 4
		expectedSize = int(t.Width) * int(t.Height) / 2
	case 8: 
		t.Width = iw * 2
		expectedSize = int(t.Width) * int(t.Height)
	case 16: 
		t.Width = iw
		expectedSize = int(t.Width) * int(t.Height) * 2
	case 24: 
		t.Width = (iw * 2) / 3
		expectedSize = int(t.Width) * int(t.Height) * 3
	}

	pixelBytes := int(imgLen) - 12
	if pixelBytes < expectedSize {
		return nil, fmt.Errorf("pixel data insufficient: has %d, need %d", pixelBytes, expectedSize)
	}

	t.PixelData = make([]byte, pixelBytes)
	_, err := io.ReadFull(r, t.PixelData)
	return t, err
}

func (t *TIM) Encode(w io.Writer) error {
	binary.Write(w, binary.LittleEndian, uint32(TimTag))
	var flag uint32
	switch t.BPP {
	case 4: flag = Pmode4BPP
	case 8: flag = Pmode8BPP
	case 16: flag = Pmode16BPP
	case 24: flag = Pmode24BPP
	}
	if t.HasClut { flag |= FlagHasClut }
	binary.Write(w, binary.LittleEndian, flag)
	if t.HasClut {
		clutLen := uint32(len(t.ClutData)*2 + 12)
		binary.Write(w, binary.LittleEndian, clutLen)
		binary.Write(w, binary.LittleEndian, t.ClutOrgX)
		binary.Write(w, binary.LittleEndian, t.ClutOrgY)
		binary.Write(w, binary.LittleEndian, uint16(t.ColorsPerClut))
		binary.Write(w, binary.LittleEndian, uint16(t.NumCluts))
		binary.Write(w, binary.LittleEndian, t.ClutData)
	}
	imgLen := uint32(len(t.PixelData) + 12)
	var iw uint16
	switch t.BPP {
	case 4: iw = t.Width / 4
	case 8: iw = t.Width / 2
	case 16: iw = t.Width
	case 24: iw = (t.Width * 3) / 2
	}
	binary.Write(w, binary.LittleEndian, imgLen)
	binary.Write(w, binary.LittleEndian, t.OrgX)
	binary.Write(w, binary.LittleEndian, t.OrgY)
	binary.Write(w, binary.LittleEndian, iw)
	binary.Write(w, binary.LittleEndian, t.Height)
	w.Write(t.PixelData)
	return nil
}

func ps1ToRGBA(v uint16) color.RGBA {
	r, g, b := (v&0x1F)<<3, ((v>>5)&0x1F)<<3, ((v>>10)&0x1F)<<3
	r, g, b = r|r>>5, g|g>>5, b|b>>5
	a := uint8(255)
	if v == 0 { a = 0 }
	return color.RGBA{uint8(r), uint8(g), uint8(b), a}
}

func rgbaToPs1(c color.Color) uint16 {
	r32, g32, b32, a32 := c.RGBA()
	r, g, b, a := uint8(r32>>8), uint8(g32>>8), uint8(b32>>8), uint8(a32>>8)
	if a < 128 { return 0 }
	v := uint16(r>>3) | (uint16(g>>3) << 5) | (uint16(b>>3) << 10)
	return v | 0x8000
}

func (t *TIM) ToImage(clutIdx int) (image.Image, error) {
	rect := image.Rect(0, 0, int(t.Width), int(t.Height))
	switch t.BPP {
	case 4, 8:
		cn := (map[int]int{4:16, 8:256})[t.BPP]
		start := clutIdx * cn
		if start+cn > len(t.ClutData) { return nil, errors.New("clut out of range") }
		pal := make(color.Palette, cn)
		for i := 0; i < cn; i++ { pal[i] = ps1ToRGBA(t.ClutData[start+i]) }
		img := image.NewPaletted(rect, pal)
		if t.BPP == 8 { copy(img.Pix, t.PixelData) } else {
			pIdx := 0
			for _, b := range t.PixelData {
				if pIdx < len(img.Pix) { img.Pix[pIdx] = b & 0x0F; pIdx++ }
				if pIdx < len(img.Pix) { img.Pix[pIdx] = (b >> 4) & 0x0F; pIdx++ }
			}
		}
		return img, nil
	case 16:
		img := image.NewRGBA(rect)
		for y := 0; y < int(t.Height); y++ {
			for x := 0; x < int(t.Width); x++ {
				off := (y*int(t.Width) + x) * 2
				if off+1 < len(t.PixelData) {
					v := binary.LittleEndian.Uint16(t.PixelData[off : off+2])
					img.Set(x, y, ps1ToRGBA(v))
				}
			}
		}
		return img, nil
	case 24:
		img := image.NewRGBA(rect)
		for y := 0; y < int(t.Height); y++ {
			for x := 0; x < int(t.Width); x++ {
				off := (y*int(t.Width) + x) * 3
				if off+2 < len(t.PixelData) {
					img.Set(x, y, color.RGBA{t.PixelData[off], t.PixelData[off+1], t.PixelData[off+2], 255})
				}
			}
		}
		return img, nil
	}
	return nil, errors.New("unsupported bpp")
}

func FromImage(img image.Image, bpp int) (*TIM, error) {
	bounds := img.Bounds()
	w, h := bounds.Dx(), bounds.Dy()
	t := &TIM{BPP: bpp, Width: uint16(w), Height: uint16(h)}
	switch bpp {
	case 4, 8:
		pImg, ok := img.(*image.Paletted)
		if !ok { return nil, errors.New("need paletted png") }
		t.HasClut, t.NumCluts, t.ColorsPerClut = true, 1, (map[int]int{4:16, 8:256})[bpp]
		t.ClutData = make([]uint16, t.ColorsPerClut)
		for i, c := range pImg.Palette { t.ClutData[i] = rgbaToPs1(c) }
		if bpp == 8 {
			t.PixelData = append([]byte{}, pImg.Pix...)
		} else {
			t.PixelData = make([]byte, (w*h)/2)
			for i := 0; i < len(pImg.Pix); i += 2 {
				p0, p1 := pImg.Pix[i], uint8(0)
				if i+1 < len(pImg.Pix) { p1 = pImg.Pix[i+1] }
				t.PixelData[i/2] = (p1 << 4) | (p0 & 0x0F)
			}
		}
	case 16:
		t.PixelData = make([]byte, w*h*2)
		for y := 0; y < h; y++ {
			for x := 0; x < w; x++ {
				binary.LittleEndian.PutUint16(t.PixelData[(y*w+x)*2:], rgbaToPs1(img.At(bounds.Min.X+x, bounds.Min.Y+y)))
			}
		}
	case 24:
		t.PixelData = make([]byte, w*h*3)
		for y := 0; y < h; y++ {
			for x := 0; x < w; x++ {
				r, g, b, _ := img.At(bounds.Min.X+x, bounds.Min.Y+y).RGBA()
				t.PixelData[(y*w+x)*3], t.PixelData[(y*w+x)*3+1], t.PixelData[(y*w+x)*3+2] = uint8(r>>8), uint8(g>>8), uint8(b>>8)
			}
		}
	}
	return t, nil
}

func Scan(data []byte) []ScanResult {
	var res []ScanResult
	magic := uint32(TimTag)
	//16字节对齐扫描
	for off := 0; off <= len(data)-32; off += 16 {
		if binary.LittleEndian.Uint32(data[off:off+4]) == magic {
			t, err := Decode(bytes.NewReader(data[off:]))
			if err == nil {
				cSize := 0
				if t.HasClut { cSize = 12 + len(t.ClutData)*2 }
				tot := 8 + cSize + 12 + len(t.PixelData)
				res = append(res, ScanResult{int64(off), int64(tot), *t})
			}
		}
	}
	return res
}