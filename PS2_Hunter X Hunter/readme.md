A conversion tool for the RH2 texture format from the PS2 game Hunter X Hunter: Ryumyaku no Saidan（ハンター×ハンター 龍脈の祭壇）.
It can be used to translate this game.

It supports extracting RH2 files from CVT files, conversion between RH2 and PNG, and directly injecting PNGs into CVT files (PNG->RH2->CVT).

```
Usage:
  Convert RH2 to PNG:      rh2_tool.exe -e <file.rh2> [out.png]
  
  Batch RH2 to PNG:        rh2_tool.exe -e <folder>
  
  Convert PNG to RH2:      rh2_tool.exe -i <src.png> <template.rh2> <out.rh2>
  
  Inject PNG into CVT:     rh2_tool.exe -c <src.png> <target.cvt> [out.cvt]
  
  Extract RH2 from CVT:    rh2_tool.exe -x <file.cvt> [out_folder]
```

Some info about the RH2 format:

It's not really a simple linear bitmap, but a texture container based on stacked tiles.

The structure is as follows:

Header: Starts with `RH2\x00`. The image's color mode is stored around offset `0x50`, and the total width and height after stitching are at `0x54` and `0x56`.

QRS data block: The main body of the file consists of multiple data blocks identified by `Q..R..S..`.

The 1st QRS block: Usually stores palette data (if it's an indexed image).

Subsequent QRS blocks: Store the small image tiles, usually `128x128` or `64x64`. The program needs to reassemble them based on the total width and height.

Based on the identifier above the palette area, four different image formats were found:

| Image Type | Identifier (Marker) | Palette Format         | Pixel Data Characteristics | Notes                                                        |
| ---------- | ------------------- | ---------------------- | -------------------------- | ------------------------------------------------------------ |
| 4bpp       | `0x0280`            | ABGR1555 (32 bytes)    | Nibble Swap                | Mainly used for the font. The high and low 4-bits need to be swapped. |
| 8bpp       | `0x2080`            | ABGR1555 (512 bytes)   | PS2 Swizzled               | Commonly used for menu backgrounds, needs to be unswizzled.  |
| 8bpp       | `0x4080`            | RGBA8888 (1024 bytes)  | PS2 Swizzled               | UI components with an alpha channel.                         |
| 16bit      | None (no palette block) | None                   | Linear ABGR1555            | OPs or full-color cutscenes.                                 |

Some early Konami PS2 games also use the RH2 format, including:
*   7 BLADES (RH2 files are visible after decompression)
*   Reiselied - Ephemeral Fantasia (packed inside BIN files)
*   Yu-Gi-Oh! Shin Duel Monsters II (packed inside MRG files)

This tool can extract and convert the RH2 format from the games mentioned above, but there are many types of RH2, so it can't cover all of them. You'll need to modify the code yourself to support them.
