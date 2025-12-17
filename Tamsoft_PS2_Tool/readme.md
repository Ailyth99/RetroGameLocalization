# TAMSOFT PS2 Game File Processing Tool

This tool is designed to handle game files from TAMSOFT-developed PlayStation 2 titles. TAMSOFT developed a large number of games in the SIMPLE 2000 series, as well as a few non-SIMPLE series games, such as "Future Boy Conan" and "Giant Robo."

Some of these games utilize compression formats, such as SIMPLE 2000 Vol. 50, Vol. 114, and others.

The texture format used in these games is marked as TI. These are generally 8bpp or 4bpp bitmaps with swizzling.

**Note:** Some games feature variations of the TI format. You may need to analyze and process these manually, although they typically do not differ significantly from the standard TI format. An example is the TIT.TI format found in Vol. 114.

TIViewerGUI can scan various files for TI textures and utilize `ti-converter` for importing and exporting TI files. You can edit the exported PNGs and re-import them back into the game files.

<!-- 请在这里插入您的图片，例如上传到仓库后使用相对路径 -->
<!-- ![](./images/your-image-name.png) -->
<!-- 如果您坚持使用外部链接，请确认其可用性 -->
![](https://pic1.imgdb.cn/item/69008aab3203f7be00abb650.png)

---

## 📜 File Format Documentation

### CMP LZSS Compression

A standard LZSS implementation with a 4096-byte sliding window.

*   The file begins with a 4-byte little-endian integer representing the decompressed size.
*   The rest of the file is the compressed data stream.

### .ti (Texture)

**Header:** A 48-byte header containing metadata.

*   `0x16`: BPP type (1 byte). `0x00` = 4bpp, `0x01` = 8bpp.
*   `0x22`: Width (2 bytes, little-endian).
*   `0x24`: Height (2 bytes, little-endian).

**CLUT (Palette):** Starts at offset `0x30`.

*   Each color is 4 bytes (RGBX).
*   8bpp palettes have their color blocks reordered in a specific pattern.

**Pixel Data:** Image data is linear (not swizzled).

*   For 4bpp images, each byte contains two pixels. The low nibble is the first pixel, and the high nibble is the second pixel