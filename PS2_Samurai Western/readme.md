## VOLUME.DAT Format Specification

## Samurai Western (PS2) - Way of the Samurai 2

### File Structure

```
[Header]
[File Table]
[Data Section]
```

### Header (20 bytes)

| Offset | Type   | Description           |
|--------|--------|-----------------------|
| 0x00   | uint32 | Magic: 0xFADEBABE (BE)|
| 0x04   | uint32 | File count (BE)       |
| 0x08   | uint32 | File count (duplicate)|
| 0x0C   | uint32 | Data offset (BE)      |
| 0x10   | uint32 | Data size (BE)        |

### File Table Entry (24 bytes each)

| Offset | Type   | Description              |
|--------|--------|--------------------------|
| 0x00   | uint32 | Filename hash            |
| 0x04   | uint32 | File offset (relative)   |
| 0x08   | uint32 | File size                |
| 0x0C   | uint32 | Zero padding             |
| 0x10   | uint32 | Filename offset (relative)|
| 0x14   | uint32 | Filename length          |

**Note:** All offsets are relative to `Data offset` from header.

### Data Section

Contains file data and null-terminated ASCII filenames.

- File data starts at: `Header.DataOffset + Entry.FileOffset`
- Filename starts at: `Header.DataOffset + Entry.FilenameOffset`
