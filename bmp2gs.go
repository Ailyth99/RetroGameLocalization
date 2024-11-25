package main

import (
	"encoding/binary"
	"fmt"
	"image"
	_ "image/png"
	"io"
	"os"
	"path/filepath"

	"github.com/anthonynsimon/bild/imgio"
)

type GSHeader struct {
	Magic     [2]byte
	ImageType uint16
	Width     uint16
	Height    uint16
	MipmapNum uint16
	Padding   [6]byte
}

// go的图片库不支持4bppBMP文件头结构，包括x/image/bmp也不行，
// 判断称4bpp的时候就用这个结构

type BMPHeader struct {
	Signature   [2]byte
	FileSize    uint32
	Reserved    uint32
	DataOffset  uint32
	InfoSize    uint32
	Width       int32
	Height      int32
	Planes      uint16
	BitCount    uint16
	Compression uint32
	ImageSize   uint32
	XPixelsPerM int32
	YPixelsPerM int32
	ColorsUsed  uint32
	ColorsImp   uint32
}

// 读取4bpp BMP文件
func read4bppBMP(filepath string) (width, height int, palette []byte, pixels []byte, err error) {
	file, err := os.Open(filepath)
	if err != nil {
		return 0, 0, nil, nil, err
	}
	defer file.Close()

	var header BMPHeader
	if err := binary.Read(file, binary.LittleEndian, &header); err != nil {
		return 0, 0, nil, nil, err
	}

	if header.BitCount != 4 {
		return 0, 0, nil, nil, fmt.Errorf("not 4bpp BMP file")
	}

	// 读调色板
	paletteSize := 16 * 4 // 16色，每色4字节(排列是BGRA)
	palette = make([]byte, paletteSize)
	if _, err := file.Read(palette); err != nil {
		return 0, 0, nil, nil, err
	}

	// 从BGRA到RGBA，转换一次调色板
	for i := 0; i < paletteSize; i += 4 {
		palette[i], palette[i+2] = palette[i+2], palette[i]
	}

	// 跳到像素数据
	if _, err := file.Seek(int64(header.DataOffset), io.SeekStart); err != nil {
		return 0, 0, nil, nil, err
	}

	width = int(header.Width)
	height = int(header.Height)
	rowSize := ((width + 7) / 8) * 4 // 4字节对齐
	pixels = make([]byte, rowSize*height)

	if _, err := file.Read(pixels); err != nil {
		return 0, 0, nil, nil, err
	}

	return width, height, palette, pixels, nil
}

func convertBMPtoGS(bmpPath, gsPath string) error {
	// 先尝试用标准方式打开看是不是8bpp
	img, err := imgio.Open(bmpPath)
	if err != nil {
		// 如果失败，尝试作为4bpp处理
		width, height, palette, pixels, err := read4bppBMP(bmpPath)
		if err != nil {
			return fmt.Errorf("can't open image: %v", err)
		}

		// 处理4bpp图像
		imgType := uint16(0x14)

		// 创建GS文件
		gsFile, err := os.Create(gsPath)
		if err != nil {
			return fmt.Errorf("can't create GS file: %v", err)
		}
		defer gsFile.Close()

		// 写入GS图片header

		//GS规格：
		//[0x00-0x01] Magic Number: 'GS' (0x47,0x53)
		//[0x02-0x03] Image Type:
		//- 0x13: 8bpp (256色)
		//- 0x14: 4bpp (16色)
		//[0x04-0x05] Width:  图片宽度
		//[0x06-0x07] Height: 图片高度
		//[0x08-0x09] Mipmap Number: 通常为0
		//[0x0A-0x0F] Padding: 6字节填充000000

		header := GSHeader{
			Magic:     [2]byte{'G', 'S'},
			ImageType: imgType,
			Width:     uint16(width),
			Height:    uint16(height),
			MipmapNum: 0,
		}
		if err := binary.Write(gsFile, binary.LittleEndian, &header); err != nil {
			return fmt.Errorf("failed to write GS header: %v", err)
		}

		// 写入调色板数据

		for i := 0; i < 16*4; i += 4 {
			r, g, b := palette[i], palette[i+1], palette[i+2]
			a := uint8(0x80)
			if r == 0 && g == 0 && b == 0 {
				a = 0x00
			}
			gsFile.Write([]byte{r, g, b, a})
		}

		// 写入填充
		paddingSize := 0x50 - (16 + 16*4)
		padding := make([]byte, paddingSize)
		gsFile.Write(padding)

		// 写入像素数据

		rowSize := ((width + 7) / 8) * 4
		for y := height - 1; y >= 0; y-- { // BMP原始存储是上下颠倒的，要翻过来
			row := pixels[y*rowSize : (y+1)*rowSize]
			for x := 0; x < width/2; x++ {
				b := row[x]
				high := (b >> 4) & 0x0F
				low := b & 0x0F
				gsFile.Write([]byte{(low << 4) | high})
			}
		}

		return nil
	}

	// 8bpp的处理
	bounds := img.Bounds()
	width, height := bounds.Dx(), bounds.Dy()
	paletted, ok := img.(*image.Paletted)
	if !ok {
		return fmt.Errorf("bmp must be 4bpp or 8bpp")
	}

	// 确定bmp类型
	var imgType uint16
	var paletteSize int
	if len(paletted.Palette) <= 16 {
		imgType = 0x14 // 4bpp
		paletteSize = 16
	} else {
		imgType = 0x13 // 8bpp
		paletteSize = 256
	}

	// 创建GS文件
	gsFile, err := os.Create(gsPath)
	if err != nil {
		return fmt.Errorf("can't create GS file: %v", err)
	}
	defer gsFile.Close()

	header := GSHeader{
		Magic:     [2]byte{'G', 'S'},
		ImageType: imgType,
		Width:     uint16(width),
		Height:    uint16(height),
		MipmapNum: 0,
	}
	if err := binary.Write(gsFile, binary.LittleEndian, &header); err != nil {
		return fmt.Errorf("failed to write GS header: %v", err)
	}

	for i := 0; i < paletteSize; i++ {
		var r, g, b, a uint8 = 0, 0, 0, 0x80
		if i < len(paletted.Palette) {
			c := paletted.Palette[i]
			r32, g32, b32, _ := c.RGBA()
			r, g, b = uint8(r32>>8), uint8(g32>>8), uint8(b32>>8)

			if imgType == 0x14 && r == 0 && g == 0 && b == 0 {
				a = 0x00
			}
		}
		gsFile.Write([]byte{r, g, b, a})
	}

	// 写入填充数据，确保从文件头到像素数据之间的偏移是0x50

	headerSize := 16 // GSHeader的实际大小
	paletteDataSize := paletteSize * 4
	paddingSize := 0x50 - (headerSize + paletteDataSize)
	if paddingSize > 0 {
		padding := make([]byte, paddingSize)
		gsFile.Write(padding)
	}

	// 写入像素数据
	if imgType == 0x14 { // 4bpp
		for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
			for x := bounds.Min.X; x < bounds.Max.X; x += 2 {
				low := paletted.ColorIndexAt(x, y) & 0x0F
				high := uint8(0)
				if x+1 < bounds.Max.X {
					high = paletted.ColorIndexAt(x+1, y) & 0x0F
				}
				gsFile.Write([]byte{(low << 4) | high})
			}
		}
	} else { // 8bpp
		for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
			rowData := make([]byte, width)
			for x := bounds.Min.X; x < bounds.Max.X; x++ {
				rowData[x-bounds.Min.X] = paletted.ColorIndexAt(x, y)
			}
			gsFile.Write(rowData)
		}
	}

	return nil
}

func main() {
	if len(os.Args) != 2 {
		fmt.Println("usage: bmp2gs <bmp file path>")
		return
	}

	bmpPath := os.Args[1]
	gsPath := filepath.Join(filepath.Dir(bmpPath),
		filepath.Base(bmpPath[:len(bmpPath)-len(filepath.Ext(bmpPath))])+".gs")

	if err := convertBMPtoGS(bmpPath, gsPath); err != nil {
		fmt.Printf("convert failed: %v\n", err)
		return
	}

	fmt.Printf("Convert success: %s\n", gsPath)
}
