The game's primary archive format is **AFS**, which contains numerous **PAK** files. Inside these PAK files lies a custom compression format I have named **PKLZ**. You must decompress these PKLZ files to access the actual texture files.

Below are the usage instructions for each tool:

### **pak_unpacker**
Used for unpacking `.pak` files. It also handles the decompression of enclosed `.pklz` files automatically.
**Usage:**
`pak_unpacker <pak_file> [output_directory]`

### **pklz_decmp**
A standalone tool for decompressing `.pklz` files.
**Usage:**
`pklz_decmp <path_to_pklz_file>`

### **pklz_maker.exe**
There are two variants of the PKLZ format: headers starting with **PK02** indicate compressed data, while **PK00** indicates uncompressed data. Since the game engine supports uncompressed data, re-compression is not strictly necessary. You can simply use this tool to create a `.pklz` file with a **PK00** header (raw data) and pack it back into a PAK file.
**Usage:**
`pklz_maker <input_file>`

### **pak_packer**
A tool for rebuilding/repacking `.pak` files.
**Usage:**
`pak_packer <input_folder> <MAGIC_TYPE>`
**Example:**
`pak_packer m_title_j MENU`

### **ms3dTx_tool**
**Texture Tool** *(Note: Please include `swizzle.go` and `utils.go` when compiling)*.
This tool is used to export textures as PNGs from texture containers and inject PNGs back into them. These texture containers (`.bin`) are obtained after decompressing the PKLZ files.
**Usage:**
*   **Scan a file:** `ms3dTx_tool.exe -scan <file.bin>`
*   **Extract from a dir:** `ms3dTx_tool.exe -ex <folder_path>`
*   **Inject into a file:** `ms3dTx_tool.exe -inject <in.png> <in.bin> <tex_id> [-o <out.bin>]`



### 1. PAK Container Format
A standard archive format consisting of a header, an offset table, and file data.

*   **Header (16 Bytes):**
    *   `0x00`: **Magic** (String, e.g., "DATA", "MENU", "FONT","STRD").
    *   `0x04`: **Zero Check** (Always `00 00 00 00`).
    *   `0x08`: **Reserved** (Usually 0).
    *   `0x0C`: **File Count** ($N$) (Uint32, Little Endian).
*   **Offset Table:**
    *   Located immediately after the header.
    *   Contains **$N + 1$** entries (Uint32).
    *   Entries $0$ to $N-1$: Start offsets of files.
    *   Entry $N$: End offset (Total archive size).
*   **Data:**
    *   File data follows the offset table.
    *   Each file is typically aligned to a **16-byte** boundary (padded with `00`).

---

### 2. PKLZ Compression Format
A custom compression format based on the **LZSS** algorithm.

*   **Header (16 Bytes):**
    *   `0x00`: **Signature** (`PK\x00\x02` for Compressed, `PK\x00\x00` for Raw).
    *   `0x04`: **Decompressed Size** (Uint32).
    *   `0x08`: **Padding** (8 bytes of zeros).
*   **Data Stream (Starts at 0x10):**
    *   Driven by **Control Bytes**. Bits are read from MSB to LSB.
    *   **Bit = 1**: **Literal Copy**. Read 1 byte from input and output it.
    *   **Bit = 0**: **Reference Copy** (LZSS).
        *   **Type 0 (Short)**: Uses 2 bits for length + 1 byte for offset.
        *   **Type 1 (General)**: Uses 2 bytes to encode a larger offset and length.
        
 