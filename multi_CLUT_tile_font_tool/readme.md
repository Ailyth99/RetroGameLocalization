
A specialized tool for extracting and repacking PS2 tiled linear fonts (4bpp dual-layer).

Sample：

![](https://pic1.imgdb.cn/item/694e5a91b34383fd59c5d831.png)

Extracts font data into two PNG

![](https://pic1.imgdb.cn/item/694e59f9b34383fd59c5d02e.png)


![](https://pic1.imgdb.cn/item/694e59f9b34383fd59c5d02d.png)


## Build
```bash
go build tilefont_tool.go
```

## Usage

### 1. Extract (BIN -> PNGs)
Extracts font data into two PNG layers (`_layer1.png` & `_layer2.png`).

```bash
# Basic (24x24 tiles)
tilefont_tool -i font.bin -o 0x800 

# Custom size (e.g. 16x16 tiles, 32 per row)
tilefont_tool -i font.bin -o 0x800 -tw 16 -th 16 -cols 32
```

### 2. Repack (PNGs -> BIN)
Injects modified PNG layers back into the binary file.

*Note: Ensure input PNGs use the standard 4-color grayscale palette (Black, DarkGray, LightGray, White).*

```bash
tilefont_tool -i font.bin -o 0x800 -img1 mod_layer1.png -img2 mod_layer2.png -out font_new.bin
```

## Parameters
*   `-i`: Input binary file.
*   `-o`: Start offset (Decimal or Hex `0x...`).
*   `-tw`: Tile width (default: 24).
*   `-th`: Tile height (default: 24).
*   `-cols`: Tiles per row in output PNG (default: 16).
*   `-img1`: (Repack) Layer 1 PNG path.
*   `-img2`: (Repack) Layer 2 PNG path.
*   `-out`: (Repack) Output filename.


