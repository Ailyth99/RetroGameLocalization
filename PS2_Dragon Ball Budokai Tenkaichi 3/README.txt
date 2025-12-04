PS2 ドラゴンボールZ スパーキング!メテオ (Dragon Ball Z: Budokai Tenkaichi 3) FONT Tool
The font data is located within resi (resident_system.pak) inside pzs3jp1.afs. There are multiple font texture sets.
Each texture uses a single set of pixel data but contains two CLUTs, allowing for two different visual displays.

Tool Build:
go build -o dbzfnt_tool.exe dbzfnt_tool.go swizzle.go utils.go

Usage:
EXTRACT TO PNG: dbzfnt_tool -e <file.fnt>
REBUILD FNT: dbzfnt_tool -r <orig.fnt> <clut1.png> <clut2.png> <out.fnt>