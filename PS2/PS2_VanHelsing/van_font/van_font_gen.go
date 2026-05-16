package main

import (
	"encoding/binary"
	"flag"
	"fmt"
	"image"
	"image/draw"
	"image/png"
	"os"
	"sort"

	"golang.org/x/image/font"
	"golang.org/x/image/font/opentype"
	"golang.org/x/image/math/fixed"
)

type glyph struct {
	r      rune
	code   uint32
	w, h   int
	bear   float32
	isCJK  bool
	tx, ty int
}

 
type Rect struct{ x, y, w, h int }
type BinPacker struct {
	freeRects     []Rect
	width, height int
}

func NewBinPacker(w, h int) *BinPacker {
	return &BinPacker{freeRects: []Rect{{0, 0, w, h}}, width: w, height: h}
}
func (bp *BinPacker) Insert(w, h int) (int, int, bool) {
	bestIdx, bestY, bestX := -1, bp.height+1, bp.width+1
	for i, r := range bp.freeRects {
		if r.w >= w && r.h >= h {
			if r.y < bestY || (r.y == bestY && r.x < bestX) {
				bestY, bestX, bestIdx = r.y, r.x, i
			}
		}
	}
	if bestIdx == -1 { return 0, 0, false }
	node := bp.freeRects[bestIdx]
	bp.freeRects = append(bp.freeRects[:bestIdx], bp.freeRects[bestIdx+1:]...)
	wLeft, hLeft := node.w-w, node.h-h
	var r1, r2 Rect
	if wLeft > hLeft {
		r1 = Rect{node.x, node.y + h, w, hLeft}
		r2 = Rect{node.x + w, node.y, wLeft, node.h}
	} else {
		r1 = Rect{node.x + w, node.y, wLeft, h}
		r2 = Rect{node.x, node.y + h, node.w, hLeft}
	}
	if r1.w > 0 && r1.h > 0 { bp.freeRects = append(bp.freeRects, r1) }
	if r2.w > 0 && r2.h > 0 { bp.freeRects = append(bp.freeRects, r2) }
	return bestX, bestY, true
}

//根据缩放后的参数绘制贴图
func drawAtlas(glyphs []glyph, ttfData []byte, texW, texH, drawSize int, outName string) {
	f, err := opentype.Parse(ttfData)
	if err != nil {
		fmt.Printf("[-] Error parsing TTF in drawAtlas: %v\n", err)
		return
	}
	face, _ := opentype.NewFace(f, &opentype.FaceOptions{
		Size: float64(drawSize), DPI: 72, Hinting: font.HintingNone,
	})
	defer face.Close()

	metrics := face.Metrics()
	ascent := metrics.Ascent.Ceil()

	img := image.NewRGBA(image.Rect(0, 0, texW, texH))
	draw.Draw(img, img.Bounds(), image.Transparent, image.Point{}, draw.Src)
	dr := &font.Drawer{Dst: img, Src: image.White, Face: face}
	
	for _, g := range glyphs {
		if g.code == 0x20 { continue }
		
		//动态基线计算，防止HD缩放后的微小偏移
		drawBaseY := g.ty + ascent 
		if ascent > drawSize { drawBaseY = g.ty + drawSize - 1 }

		if !g.isCJK {
			dr.Dot = fixed.P(g.tx, drawBaseY)
			dr.DrawString(string(g.r))
		} else {
			adv, _ := face.GlyphAdvance(g.r)
			ox := (g.w - adv.Ceil()) / 2
			if ox < 0 { ox = 0 }
			dr.Dot = fixed.P(g.tx+ox, drawBaseY)
			dr.DrawString(string(g.r))
		}
	}

	pngF, _ := os.Create(outName + ".png")
	png.Encode(pngF, img)
	pngF.Close()
	fmt.Printf("[+] Atlas Saved: %s.png (%dx%d, FontSize: %d)\n", outName, texW, texH, drawSize)
}

func isPow2(n int) bool { return n > 0 && (n&(n-1)) == 0 }

func main() {
	tPtr := flag.String("t", "", "TTF Font Path")
	sPtr := flag.Int("s", 12, "SD Physical Size")
	fPtr := flag.Int("f", 30, "Game Render Size")
	cPtr := flag.String("c", "", "Chars TXT Path")
	wPtr := flag.Int("w", 512, "Texture Width")
	hPtr := flag.Int("h", 512, "Texture Height")
	oPtr := flag.String("o", "font_final", "Output Name")
	hdPtr := flag.Int("hd", 0, "HD Multiplier (e.g. 4 for 2048px)")

	lhPtr := flag.Float64("lh", 30.0, "FNT: Line Height")
	bhPtr := flag.Float64("bh", 32.0, "FNT: Base Height")
	bwPtr := flag.Float64("bw", 32.0, "FNT: Base Width")
	spPtr := flag.Float64("space", 3.0, "FNT: Spacing")
	flag.Parse()

	if *tPtr == "" || *sPtr <= 0 || *cPtr == "" || !isPow2(*wPtr) {
		fmt.Println("Usage: van_font_gen -t font.ttf -s 12 -f 30 -c chars.txt -w 512 -hd 4")
		os.Exit(1)
	}

	realSize, fakeSize := *sPtr, *fPtr
	scaleRatio := float32(fakeSize) / float32(realSize)

	ttfData, err := os.ReadFile(*tPtr)
	if err != nil {
		fmt.Printf("[-] Error reading TTF: %v\n", err)
		os.Exit(1)
	}

 
	f, _ := opentype.Parse(ttfData)
	faceSD, _ := opentype.NewFace(f, &opentype.FaceOptions{Size: float64(realSize), DPI: 72, Hinting: font.HintingNone})
	ascentSD := faceSD.Metrics().Ascent.Ceil()

 
	finalCharSet := make(map[rune]bool)
	allowedASCII := " !\"%&'(),-./0123456789:;?ABCDEFGHIJKLMNOPQRSTUVWXYZ[]abcdefghijklmnopqrstuvwxyz"
	for _, r := range allowedASCII { finalCharSet[r] = true }
	
	txtData, _ := os.ReadFile(*cPtr)
	for _, r := range string(txtData) {
		if r >= 0x20 && r != '\n' && r != '\r' && r != '\t' { finalCharSet[r] = true }
	}

	var glyphs []glyph
	for r := range finalCharSet {
		code := uint32(r)
		var w int
		if code <= 0x7E {
			adv, _ := faceSD.GlyphAdvance(r)
			w = adv.Ceil()
			if code == 0x20 {
				advM, _ := faceSD.GlyphAdvance('M')
				w = advM.Ceil() / 3
			}
			if w <= 0 { w = 1 }
		} else {
			w = realSize
		}
		glyphs = append(glyphs, glyph{
			r: r, code: code, w: w, h: realSize,
			bear: float32(-ascentSD), isCJK: code > 0x7E,
		})
	}
	faceSD.Close()

 
	sort.Slice(glyphs, func(i, j int) bool {
		if glyphs[i].h == glyphs[j].h { return glyphs[i].w > glyphs[j].w }
		return glyphs[i].h > glyphs[j].h
	})
	packer := NewBinPacker(*wPtr, *hPtr)
	pad := 1 
	for i := range glyphs {
		x, y, ok := packer.Insert(glyphs[i].w+pad, glyphs[i].h+pad)
		if !ok {
			fmt.Printf("[-] FAILED: Out of space at %d chars\n", i)
			os.Exit(1)
		}
		glyphs[i].tx, glyphs[i].ty = x, y
	}

	//绘制贴图
	drawAtlas(glyphs, ttfData, *wPtr, *hPtr, realSize, *oPtr)

	//绘制HD伴生贴图
	if *hdPtr > 0 {
		mul := *hdPtr
		hdW, hdH := *wPtr * mul, *hPtr * mul
		hdSize := realSize * mul
		hdGlyphs := make([]glyph, len(glyphs))
		copy(hdGlyphs, glyphs)
		for i := range hdGlyphs {
			hdGlyphs[i].tx *= mul; hdGlyphs[i].ty *= mul
			hdGlyphs[i].w *= mul; hdGlyphs[i].h *= mul
		}
		drawAtlas(hdGlyphs, ttfData, hdW, hdH, hdSize, *oPtr+"_HD")
	}

	//写入FNT(基于基础贴图的坐标)
	sort.Slice(glyphs, func(i, j int) bool { return glyphs[i].code < glyphs[j].code })
	fntF, _ := os.Create(*oPtr + ".FNT")
	defer fntF.Close()
	count := uint16(len(glyphs))
	fntF.Write([]byte{0x50, 0x32})
	binary.Write(fntF, binary.LittleEndian, count)
	binary.Write(fntF, binary.LittleEndian, []float32{float32(*lhPtr), float32(*bhPtr), float32(*bwPtr), float32(*spPtr)})
	for _, g := range glyphs {
		binary.Write(fntF, binary.LittleEndian, g.code)
		u0, u1 := float32(g.tx)/float32(*wPtr), float32(g.tx+g.w)/float32(*wPtr)
		v0, v1 := float32(g.ty)/float32(*hPtr), float32(g.ty+g.h)/float32(*hPtr)
		fw, fh, fb := float32(g.w)*scaleRatio, float32(g.h)*scaleRatio, g.bear*scaleRatio
		binary.Write(fntF, binary.LittleEndian, []float32{0.0, fw, fh, 0.0, fb, u0, u1, v0, v1})
	}

	fmt.Printf("[*] MISSION COMPLETE! Generated %d glyphs.\n", count)
}