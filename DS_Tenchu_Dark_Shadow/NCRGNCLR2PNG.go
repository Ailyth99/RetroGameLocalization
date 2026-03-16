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

func getPalette(path string) []color.RGBA {
	d, _ := os.ReadFile(path)
	o := find(d, "PLTT"); if o == -1 { o = find(d, "TTLP") }
	do := int(binary.LittleEndian.Uint32(d[o+8+0x0C : o+8+0x10]))
	raw := d[o+8+do:]
	var res []color.RGBA
	for i := 0; i < len(raw)/2; i++ {
		v := binary.LittleEndian.Uint16(raw[i*2:])
		res = append(res, color.RGBA{uint8((v&0x1F)*8), uint8(((v>>5)&0x1F)*8), uint8(((v>>10)&0x1F)*8), 255})
	}
	return res
}

func export(nclr, dir, out string, tw, th int) {
	os.MkdirAll(out, 0755)
	pal := getPalette(nclr)
	fs, _ := os.ReadDir(dir)
	for _, f := range fs {
		if strings.ToLower(filepath.Ext(f.Name())) != ".ncgr" { continue }
		data, _ := os.ReadFile(filepath.Join(dir, f.Name()))
		co := find(data, "CHAR"); if co == -1 { co = find(data, "RAHC") }
		b8 := binary.LittleEndian.Uint32(data[co+8+0x04:co+8+0x08]) == 4
		goff := int(binary.LittleEndian.Uint32(data[co+8+0x14:co+8+0x18]))
		pix := data[co+8+goff:]

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
						if ci > 0 && ci < len(pal) { img.Set(tx*8+px, ty*8+py, pal[ci]) }
					}
				}
			}
		}
		outName := strings.TrimSuffix(f.Name(), filepath.Ext(f.Name())) + ".png"
		outF, _ := os.Create(filepath.Join(out, outName))
		png.Encode(outF, img)
		outF.Close()
	}
	fmt.Println("[+] Export done.")
}

func inject(nclr, pngDir, rawDir, outDir string, tw, th int) {
	os.MkdirAll(outDir, 0755)
	pal := getPalette(nclr)
	cache := make(map[color.RGBA]uint8)
	fs, _ := os.ReadDir(pngDir)

	for _, f := range fs {
		if strings.ToLower(filepath.Ext(f.Name())) != ".png" { continue }
		base := strings.TrimSuffix(f.Name(), ".png")
		rawP := filepath.Join(rawDir, base+".NCGR")
		if _, err := os.Stat(rawP); err != nil {
			rawP = filepath.Join(rawDir, base+".ncgr")
			if _, err := os.Stat(rawP); err != nil { continue }
		}

		data, _ := os.ReadFile(rawP)
		co := find(data, "CHAR"); if co == -1 { co = find(data, "RAHC") }
		b8 := binary.LittleEndian.Uint32(data[co+8+0x04:co+8+0x08]) == 4
		goff := int(binary.LittleEndian.Uint32(data[co+8+0x14:co+8+0x18]))
		sz := int(binary.LittleEndian.Uint32(data[co+8+0x10:co+8+0x14]))
		t_m := make([]byte, sz)
		copy(t_m, data[co+8+goff:])

		pf, _ := os.Open(filepath.Join(pngDir, f.Name()))
		img, _ := png.Decode(pf); pf.Close()

		match := func(c color.Color) uint8 {
			r, g, b, a := c.RGBA()
			if a>>8 < 128 { return 0 }
			c8 := color.RGBA{uint8(r >> 8), uint8(g >> 8), uint8(b >> 8), 255}
			if v, ok := cache[c8]; ok { return v }
			bestD, bestI := uint32(999999), uint8(1)
			for i := 1; i < len(pal); i++ {
				pr, pg, pb := uint32(pal[i].R), uint32(pal[i].G), uint32(pal[i].B)
				d := (uint32(c8.R)-pr)*(uint32(c8.R)-pr) + (uint32(c8.G)-pg)*(uint32(c8.G)-pg) + (uint32(c8.B)-pb)*(uint32(c8.B)-pb)
				if d < bestD { bestD, bestI = d, uint8(i) }
			}
			cache[c8] = bestI; return bestI
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
		copy(data[co+8+goff:], t_m)
		os.WriteFile(filepath.Join(outDir, base+".NCGR"), data, 0644)
	}
	fmt.Println("[+] Import done.")
}

func usage() {
	fmt.Println("NDS NCGR+NCLR TO PNG , withou NSCR")
	fmt.Println("\nUsage:")
	fmt.Println("  export [shared.nclr] [ncgr_dir] [out_png_dir] [-W tilesW] [-H tilesH]")
	fmt.Println("  import [shared.nclr] [png_dir] [ncgr_dir] [out_ncgr_dir] [-W tilesW] [-H tilesH]")
	fmt.Println("\nExample:")
	fmt.Println("  batchlinear export icon.NCLR ./raw ./png -W 19 -H 5")
	fmt.Println("  batchlinear import icon.NCLR ./mod ./raw ./new -W 19 -H 5")
}

func main() {
	if len(os.Args) < 5 { usage(); return }
	tw, th := 19, 5
	for i, v := range os.Args {
		if v == "-W" { tw, _ = strconv.Atoi(os.Args[i+1]) }
		if v == "-H" { th, _ = strconv.Atoi(os.Args[i+1]) }
	}
	cmd := os.Args[1]
	if cmd == "export" { export(os.Args[2], os.Args[3], os.Args[4], tw, th)
	} else if cmd == "import" { inject(os.Args[2], os.Args[3], os.Args[4], os.Args[5], tw, th)
	} else { usage() }
}