package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type op struct {
	isLit bool
	byte  byte
	off   int
	len   int
}

func main() {
	var mode, in, out string
	args := os.Args[1:]

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-d", "-c":
			mode = args[i]
			if i+1 < len(args) {
				in = args[i+1]
				i++
			}
		case "-o":
			if i+1 < len(args) {
				out = args[i+1]
				i++
			}
		}
	}

	if mode == "" || in == "" {
		printUsage()
		return
	}

	switch mode {
	case "-d":
		decompress(in, out)
	case "-c":
		compress(in, out)
	}
}

func printUsage() {
	fmt.Println("Aniki_CMP_Tool (Chou Aniki PS2),2025 aikika")
	fmt.Println("Usage:")
	fmt.Println("  Decompress: -d <input> [-o <output>]")
	fmt.Println("  Compress:   -c <input> [-o <output>]")
}

func decompress(fPath, outPath string) {
	dat, err := os.ReadFile(fPath)
	if err != nil {
		fmt.Println("Read err:", err)
		return
	}

	if len(dat) < 0xC {
		fmt.Println("Err: File too small")
		return
	}

	magic := binary.LittleEndian.Uint32(dat[:4])
	decSz := int(binary.LittleEndian.Uint32(dat[4:8]))
	
	if magic != 1 {
		fmt.Println("Warn: Magic not 1, unpacking anyway...")
	}
	fmt.Printf("Unpacking: %s -> Size: %d\n", fPath, decSz)

	ring := make([]byte, 4096)
	rIdx := 0xFEE

	out := make([]byte, 0, decSz)
	src := 0x08 

	flags := 0
	fBit := 0

	for len(out) < decSz && src < len(dat) {
		if fBit == 0 {
			if src >= len(dat) {
				break
			}
			flags = int(dat[src])
			src++
			fBit = 8
		}

		isLit := (flags & 1) != 0
		flags >>= 1
		fBit--

		if isLit {
			v := dat[src]
			src++
			out = append(out, v)
			ring[rIdx] = v
			rIdx = (rIdx + 1) & 0xFFF
		} else {
			if src+1 >= len(dat) {
				break
			}
			b1 := int(dat[src])
			b2 := int(dat[src+1])
			src += 2

			off := b1 | ((b2 & 0xF0) << 4)
			ln := (b2 & 0x0F) + 3

			for i := 0; i < ln; i++ {
				v := ring[(off+i)&0xFFF]
				out = append(out, v)
				ring[rIdx] = v
				rIdx = (rIdx + 1) & 0xFFF
				if len(out) >= decSz {
					break
				}
			}
		}
	}

	// 确定输出文件名
	if outPath == "" {
		ext := ".bin"
		if len(out) > 4 && string(out[:4]) == "TIM2" {
			ext = ".tm2"
		}
		base := strings.TrimSuffix(fPath, filepath.Ext(fPath))
		outPath = base + ext
	}
	
	os.WriteFile(outPath, out, 0644)
	fmt.Println("Saved:", outPath)
}

func compress(fPath, outPath string) {
	src, err := os.ReadFile(fPath)
	if err != nil {
		fmt.Println("Read err:", err)
		return
	}

	fmt.Printf("Packing: %s (%d bytes)...\n", fPath, len(src))

	dst := new(bytes.Buffer)
	binary.Write(dst, binary.LittleEndian, uint32(1))
	binary.Write(dst, binary.LittleEndian, uint32(len(src)))

	rBuf := make([]byte, 4096)
	rIdx := 0xFEE
	srcPos := 0
	ops := make([]op, 0, 8)

	for srcPos < len(src) {
		bestLen := 0
		bestOff := 0
		maxMatch := 18
		
		rem := len(src) - srcPos
		if rem < maxMatch {
			maxMatch = rem
		}

		if maxMatch >= 3 {
			for i := 0; i < 4096; i++ {
				matchLen := 0
				for l := 0; l < maxMatch; l++ {
					// RLE Overlap Logic
					dist := (rIdx - i + 4096) & 0xFFF
					var b byte
					if dist != 0 && l >= dist {
						b = src[srcPos + l - dist]
					} else {
						b = rBuf[(i+l)&0xFFF]
					}

					if b != src[srcPos+l] {
						break
					}
					matchLen++
				}

				if matchLen > bestLen {
					bestLen = matchLen
					bestOff = i
					if bestLen == maxMatch {
						break
					}
				}
			}
		}

		curr := op{}
		if bestLen >= 3 {
			curr.isLit = false
			curr.off = bestOff
			curr.len = bestLen
			for k := 0; k < bestLen; k++ {
				rBuf[rIdx] = src[srcPos+k]
				rIdx = (rIdx + 1) & 0xFFF
			}
			srcPos += bestLen
		} else {
			curr.isLit = true
			curr.byte = src[srcPos]
			rBuf[rIdx] = src[srcPos]
			rIdx = (rIdx + 1) & 0xFFF
			srcPos++
		}
		
		ops = append(ops, curr)
		if len(ops) == 8 {
			flushOps(dst, ops)
			ops = ops[:0]
		}
	}

	if len(ops) > 0 {
		flushOps(dst, ops)
	}

	if outPath == "" {
		base := strings.TrimSuffix(fPath, filepath.Ext(fPath))
		outPath = base + ".CMP"
	}
	
	os.WriteFile(outPath, dst.Bytes(), 0644)
	
	ratio := float64(dst.Len()) / float64(len(src)) * 100
	fmt.Printf("Done! Saved: %s (Ratio: %.2f%%)\n", outPath, ratio)
}

func flushOps(buf *bytes.Buffer, ops []op) {
	var fByte byte = 0
	for i, o := range ops {
		if o.isLit {
			fByte |= (1 << i)
		}
	}
	buf.WriteByte(fByte)

	for _, o := range ops {
		if o.isLit {
			buf.WriteByte(o.byte)
		} else {
			b1 := byte(o.off & 0xFF)
			ln := o.len - 3
			offHi := (o.off >> 8) & 0x0F
			b2 := byte(ln | (offHi << 4))
			buf.WriteByte(b1)
			buf.WriteByte(b2)
		}
	}
}