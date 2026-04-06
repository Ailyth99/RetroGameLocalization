# Aniki_CMP_Tool

A tool for handling `.CMP` `.PAC`compressed assets from the PS2 game **Chou Aniki: Seinaru Protein Densetsu** (超兄貴〜聖なるプロテイン伝説〜).

## Build
```bash
go build Aniki_CMP_Tool.go
```

## Usage

### Decompress
```bash
Decompress: -d <input.cmp or pac> [-o <output>]
```

### Compress
```bash
Aniki_CMP_Tool.exe -c <file> [-o <output>]
```

## Algorithm Specs ("AnikiLZ")
*   **Type**: Custom LZSS Variant
*   **Window Size**: 4096 bytes (`0xFFF` mask)
*   **Initial Ring Pos**: `0xFEE` 
*   **Flags**: LSB First (`1`=Literal, `0`=Reference)
*   **Reference Layout**: 12-bit Offset + 4-bit Length