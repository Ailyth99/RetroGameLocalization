package main

import (
	"encoding/binary"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type pair struct {
	cgr, clr string // 完整路径
	rawName  string // 不含扩展名的原始名(含ID和Offset)
}

func find(d []byte, sig string) int {
	if len(d) < 0x10 { return -1 }
	num := int(binary.LittleEndian.Uint16(d[0x0E:0x10]))
	off := int(binary.LittleEndian.Uint16(d[0x0C:0x0E]))
	for i := 0; i < num; i++ {
		if off+8 > len(d) { break }
		if string(d[off:off+4]) == sig { return off }
		off += int(binary.LittleEndian.Uint32(d[off+4 : off+8]))
	}
	return -1
}

func getPairs(dir string) []pair {
	fs, _ := os.ReadDir(dir)
	ncgrs := make(map[int]string)
	nclrs := make(map[int]string)
	
	// 第一遍扫描：解析 ID 并分类
	for _, f := range fs {
		n := f.Name()
		ext := strings.ToLower(filepath.Ext(n))
		idPart := strings.Split(n, "_")[0]
		id, err := strconv.Atoi(idPart)
		if err != nil { continue }
		if ext == ".ncgr" { ncgrs[id] = n }
		if ext == ".nclr" { nclrs[id] = n }
	}

	var res []pair
	for id, cgrN := range ncgrs {
		if id%2 == 0 { // 偶数 NCGR
			if clrN, ok := nclrs[id+1]; ok { // 匹配奇数 NCLR
				res = append(res, pair{
					filepath.Join(dir, cgrN),
					filepath.Join(dir, clrN),
					strings.TrimSuffix(cgrN, filepath.Ext(cgrN)),
				})
			}
		}
	}
	return res
}

func export(src, out string, tw, th int) {
	os.MkdirAll(out, 0755)
	list := getPairs(src)
	for _, p := range list {
		palD, _ := os.ReadFile(p.clr)
		cgrD, _ := os.ReadFile(p.cgr)
		
		po := find(palD, "PLTT")
		if po == -1 { po = find(palD, "TTLP") }
		do := int(binary.LittleEndian.Uint32(palD[po+8+0x0C : po+8+0x10]))
		rawP := palD[po+8+do:]
		
		var clrs []color.RGBA
		for i := 0; i < len(rawP)/2; i++ {
			v := binary.LittleEndian.Uint16(rawP[i*2:])
			clrs = append(clrs, color.RGBA{uint8((v&0x1F)*8), uint8(((v>>5)&0x1F)*8), uint8(((v>>10)&0x1F)*8), 255})
		}

		co := find(cgrD, "CHAR")
		if co == -1 { co = find(cgrD, "RAHC") }
		b8 := binary.LittleEndian.Uint32(cgrD[co+8+0x04:co+8+0x08]) == 4
		goff := int(binary.LittleEndian.Uint32(cgrD[co+8+0x14:co+8+0x18]))
		pix := cgrD[co+8+goff:]

		img := image.NewRGBA(image.Rect(0, 0, tw*8, th*8))
		for ty := 0; ty < th; ty++ {
			for tx := 0; tx < tw; tx++ {
				tidx := ty*tw + tx
				for py := 0; py < 8; py++ {
					for px := 0; px < 8; px++ {
						var ci int
						if b8 { ci = int(pix[tidx*64+py*8+px])
						} else {
							b := pix[tidx*32+py*4+px/2]
							if px%2 == 0 { ci = int(b & 0xF) } else { ci = int(b >> 4) }
						}
						if ci > 0 && ci < len(clrs) { img.Set(tx*8+px, ty*8+py, clrs[ci]) }
					}
				}
			}
		}
		f, _ := os.Create(filepath.Join(out, p.rawName+".png"))
		png.Encode(f, img)
		f.Close()
	}
	fmt.Printf("[+] Exported %d paired images.\n", len(list))
}

func inject(pngDir, rawDir, outDir string, tw, th int) {
	os.MkdirAll(outDir, 0755)
	list := getPairs(rawDir)
	cache := make(map[color.RGBA]uint8)

	for _, p := range list {
		pngP := filepath.Join(pngDir, p.rawName+".png")
		if _, err := os.Stat(pngP); err != nil { continue }

		palD, _ := os.ReadFile(p.clr)
		po := find(palD, "PLTT"); if po == -1 { po = find(palD, "TTLP") }
		do := int(binary.LittleEndian.Uint32(palD[po+8+0x0C : po+8+0x10]))
		rawP := palD[po+8+do:]
		var pMap []color.RGBA
		for i := 0; i < len(rawP)/2; i++ {
			v := binary.LittleEndian.Uint16(rawP[i*2:])
			pMap = append(pMap, color.RGBA{uint8((v&0x1F)*8), uint8(((v>>5)&0x1F)*8), uint8(((v>>10)&0x1F)*8), 255})
		}

		cgrD, _ := os.ReadFile(p.cgr)
		co := find(cgrD, "CHAR"); if co == -1 { co = find(cgrD, "RAHC") }
		b8 := binary.LittleEndian.Uint32(cgrD[co+8+0x04:co+8+0x08]) == 4
		goff := int(binary.LittleEndian.Uint32(cgrD[co+8+0x14:co+8+0x18]))
		sz := int(binary.LittleEndian.Uint32(cgrD[co+8+0x10:co+8+0x14]))
		t_m := make([]byte, sz)
		copy(t_m, cgrD[co+8+goff:])

		f, _ := os.Open(pngP); img, _ := png.Decode(f); f.Close()
		clear(cache)
		match := func(c color.Color) uint8 {
			r, g, b, a := c.RGBA()
			if a>>8 < 128 { return 0 }
			c8 := color.RGBA{uint8(r >> 8), uint8(g >> 8), uint8(b >> 8), 255}
			if v, ok := cache[c8]; ok { return v }
			bestD, bestI := uint32(999999), uint8(1)
			for i := 1; i < len(pMap); i++ {
				pr, pg, pb := uint32(pMap[i].R), uint32(pMap[i].G), uint32(pMap[i].B)
				d := (uint32(c8.R)-pr)*(uint32(c8.R)-pr) + (uint32(c8.G)-pg)*(uint32(c8.G)-pg) + (uint32(c8.B)-pb)*(uint32(c8.B)-pb)
				if d < bestD { bestD, bestI = d, uint8(i) }
			}
			cache[c8] = bestI
			return bestI
		}

		for ty := 0; ty < th; ty++ {
			for tx := 0; tx < tw; tx++ {
				tidx := ty*tw + tx
				for py := 0; py < 8; py++ {
					for px := 0; px < 8; px++ {
						idx := match(img.At(tx*8+px, ty*8+py))
						if b8 { t_m[tidx*64+py*8+px] = idx
						} else {
							moff := tidx*32 + py*4 + px/2
							if px%2 == 0 { t_m[moff] = (t_m[moff] & 0xF0) | (idx & 0xF)
							} else { t_m[moff] = (t_m[moff] & 0x0F) | (idx << 4) }
						}
					}
				}
			}
		}
		copy(cgrD[co+8+goff:], t_m)
		os.WriteFile(filepath.Join(outDir, p.rawName+".NCGR"), cgrD, 0644)
	}
	fmt.Println("[+] Import done.")
}

func usage() {
	fmt.Println("TENCHU DS INFOBIND TOOL")
	fmt.Println("\nUsage:")
	fmt.Println("  export [raw_dir] [out_png_dir] [-W tilesW] [-H tilesH]")
	fmt.Println("  import [png_dir] [raw_dir] [out_ncgr_dir] [-W tilesW] [-H tilesH]")
	fmt.Println("\nExample:")
	fmt.Println("  pairtool export ./extracted ./png -W 32 -H 12")
	fmt.Println("  pairtool import ./edited ./extracted ./new_ncgr -W 32 -H 12")
}

func main() {
	if len(os.Args) < 4 { usage(); return }
	cmd, tw, th := os.Args[1], 32, 14
	for i, v := range os.Args {
		if v == "-W" { tw, _ = strconv.Atoi(os.Args[i+1]) }
		if v == "-H" { th, _ = strconv.Atoi(os.Args[i+1]) }
	}
	if cmd == "export" { export(os.Args[2], os.Args[3], tw, th)
	} else if cmd == "import" { inject(os.Args[2], os.Args[3], os.Args[4], tw, th)
	} else { usage() }
}