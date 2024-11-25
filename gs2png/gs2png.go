package main

import (
	"bytes"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"os"
	"path/filepath"
)

type GSHeader struct {
	Magic     [2]byte
	ImageType uint16
	Width     uint16
	Height    uint16
	MipmapNum uint16
	Padding   [6]byte
}

// 新增：图片信息结构体
type GSInfo struct {
	Base64    string `json:"base64"`
	FileName  string `json:"fileName"`
	ImageType string `json:"imageType"`
	Width     int    `json:"width"`
	Height    int    `json:"height"`
	PalSize   int    `json:"palSize"`
	FileSize  int64  `json:"fileSize"`
}

// 新增：将图像转换为base64字符串
func imageToBase64(img image.Image) (string, error) {
	var buf bytes.Buffer
	if err := png.Encode(&buf, img); err != nil {
		return "", fmt.Errorf("PNG编码失败了: %v", err)
	}
	return base64.StdEncoding.EncodeToString(buf.Bytes()), nil
}

// 修改：返回image.Image而不是直接保存
func convertGStoImage(gsPath string) (image.Image, GSInfo, error) {
	var info GSInfo

	// 获取文件信息
	fileInfo, err := os.Stat(gsPath)
	if err != nil {
		return nil, info, fmt.Errorf("获取文件信息失败: %v", err)
	}
	info.FileName = filepath.Base(gsPath)
	info.FileSize = fileInfo.Size()

	// 读取GS文件
	gsFile, err := os.Open(gsPath)
	if err != nil {
		return nil, info, fmt.Errorf("无法打开GS文件: %v", err)
	}
	defer gsFile.Close()

	// 读取头部信息
	var header GSHeader
	if err := binary.Read(gsFile, binary.LittleEndian, &header); err != nil {
		return nil, info, fmt.Errorf("读取文件头失败: %v", err)
	}

	// 设置图片信息
	info.Width = int(header.Width)
	info.Height = int(header.Height)
	if header.ImageType == 0x14 {
		info.ImageType = "4bpp 16色 (0x14)"
		info.PalSize = 16
	} else {
		info.ImageType = "8bpp 256色 (0x13)"
		info.PalSize = 256
	}

	width, height := int(header.Width), int(header.Height)

	// 读取调色板
	gsFile.Seek(0x10, 0) // 跳到调色板位置
	var palette color.Palette
	paletteSize := 16
	if header.ImageType == 0x13 {
		paletteSize = 256
	}

	for i := 0; i < paletteSize; i++ {
		rgba := make([]byte, 4)
		gsFile.Read(rgba)
		r, g, b, a := rgba[0], rgba[1], rgba[2], rgba[3]

		// 4bpp模式下只保留纯黑色的透明度
		if header.ImageType == 0x14 {
			if r == 0 && g == 0 && b == 0 {
				a = 0x00
			} else {
				a = 0xFF
			}
		} else {
			// 8bpp模式下取消所有透明度
			a = 0xFF
		}

		palette = append(palette, color.NRGBA{r, g, b, a})
	}

	// 创建新图像
	img := image.NewPaletted(image.Rect(0, 0, width, height), palette)

	// 读取像素数据
	gsFile.Seek(0x50, 0)
	if header.ImageType == 0x13 { // 8bpp
		raw_data := make([]byte, width*height)
		gsFile.Read(raw_data)

		if width <= 64 {
			// 小图直接复制数据
			copy(img.Pix, raw_data)
		} else {
			// 大图需要特殊处理
			half_width := width / 2
			for y := 0; y < height; y++ {
				for x := 0; x < half_width; x++ {
					// 处理左半边
					src_pos := (y+1)%height*width + x
					dst_pos := y*width + (x + half_width)
					img.Pix[dst_pos] = raw_data[src_pos]

					// 处理右半边
					src_pos = y*width + (x + half_width)
					dst_pos = y*width + x
					img.Pix[dst_pos] = raw_data[src_pos]
				}
			}
		}
	} else { // 4bpp
		raw_data := make([]byte, (width*height)/2)
		gsFile.Read(raw_data)

		pixelIdx := 0
		for y := 0; y < height; y++ {
			rowStart := y * (width / 2)
			for x := 0; x < width; x += 2 {
				b := raw_data[rowStart+x/2]
				// 注意这里改变了解析顺序
				low := (b & 0x0F)
				high := (b & 0xF0) >> 4
				// 先放high再放low
				img.Pix[y*width+x] = low
				if x+1 < width {
					img.Pix[y*width+x+1] = high
				}
				pixelIdx++
			}
		}
	}

	return img, info, nil
}

func main() {
	// 设置控制台输出为UTF-8
	os.Setenv("LANG", "en_US.UTF-8")

	b64Mode := flag.Bool("b64", false, "输出base64编码")
	flag.Parse()

	args := flag.Args()
	if len(args) != 1 {
		fmt.Println("使用方法: gs2png [-b64] <gs文件路径>")
		return
	}

	gsPath := args[0]

	// 转换图像
	img, info, err := convertGStoImage(gsPath)
	if err != nil {
		fmt.Printf("{\"error\": \"%v\"}\n", err)
		return
	}

	if *b64Mode {
		// 生成base64
		b64str, err := imageToBase64(img)
		if err != nil {
			fmt.Printf("{\"error\": \"%v\"}\n", err)
			return
		}
		info.Base64 = b64str

		// 输出JSON格式的信息
		jsonData, err := json.Marshal(info)
		if err != nil {
			fmt.Printf("{\"error\": \"%v\"}\n", err)
			return
		}
		os.Stdout.Write(jsonData) // 直接写入字节，避免fmt.Println的编码转换
		os.Stdout.Write([]byte{'\n'})
	} else {
		// 普通模式：保存为PNG文件
		pngPath := filepath.Join(filepath.Dir(gsPath),
			filepath.Base(gsPath[:len(gsPath)-len(filepath.Ext(gsPath))])+".png")

		outFile, err := os.Create(pngPath)
		if err != nil {
			fmt.Printf("无法创建输出文件呢: %v\n", err)
			return
		}
		defer outFile.Close()

		if err := png.Encode(outFile, img); err != nil {
			fmt.Printf("保存PNG失败了: %v\n", err)
			return
		}

		fmt.Printf("转换成功啦！输出文件: %s\n", pngPath)
	}
}
