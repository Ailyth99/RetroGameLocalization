"""Add Chinese to the menu heading font, preserving the installed small font.

python scripts/build_large_menu_font.py
python scripts/build_large_menu_font.py --install
python scripts/build_large_menu_font.py --restore
"""

import argparse
import json
import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

from build_start_menu_zh import TTF, parse_menu, require, sha256
from game_text_resources import chunks

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "ISO_UNPACK/Fonts/ntsc_fon.asr"
MENU = ROOT / "ISO_UNPACK/Misc/Menu/Menu_Am.asr"
OUTPUT = ROOT / "TEMP/builds/large_menu_font_20261004"
BACKUP = ROOT / "SOURCE/backups/large_menu_font_20261004"
FONT_NAME = "Times New Roman_20_Bold.asr"


def fonts(data):
    result = {}
    for tag, pos, size in chunks(data):
        if tag != b"FONT":
            continue
        name = data[pos + 16:data.index(b"\0", pos + 16)].decode("ascii")
        first, last, width, height, count = struct.unpack_from("<HHIII", data, pos + 0xE8)
        require(size == 0xF8 + count * 16, f"Invalid FONT size: {name}")
        records = [struct.unpack_from("<fffHh", data, pos + 0xF8 + i * 16) for i in range(count)]
        codes = [record[3] for record in records]
        require(codes == sorted(set(codes)) and (first, last) == (codes[0], codes[-1]), f"Invalid FONT order/range: {name}")
        result[name] = {"offset": pos, "size": size, "width": width, "height": height,
                        "sample_height": struct.unpack_from("<f", data, pos + 0x74)[0], "records": records}
    return result


def rsfl_entries(data, definitions):
    tag, pos, size = next(ch for ch in chunks(data) if ch[0] == b"RSFL")
    count = struct.unpack_from("<I", data, pos + 16)[0]
    cursor, entries = pos + 20, []
    by_name = {name.lower(): value for name, value in definitions.items()}
    for _ in range(count):
        end = data.index(b"\0", cursor)
        name = data[cursor:end].decode("ascii").replace("\\", "/").split("/")[-1]
        cursor = (end + 4) & ~3
        relative, length, flags = struct.unpack_from("<III", data, cursor)
        definition = by_name[name.lower()]
        base = definition["offset"] - relative
        require(length == definition["size"] and flags == 1, f"Invalid RSFL entry: {name}")
        entries.append((name, cursor, base))
        cursor += 12
    require(cursor == pos + size and len({entry[2] for entry in entries}) == 1, "Unexpected RSFL layout")
    return entries


def patch(source, texts):
    before = fonts(source)
    definition = before[FONT_NAME]
    pos, size = definition["offset"], definition["size"]
    width, height = definition["width"], definition["height"]
    sample_height = int(definition["sample_height"])
    require((width, height, sample_height) == (512, 512, 31), "Unexpected heading font geometry")
    entries = rsfl_entries(source, before)
    originals = definition["records"]
    needed = {ord(c) for text in texts for c in text if c not in "\r\n\t"}
    added = sorted(needed - {r[3] for r in originals})
    require(all(0 < code <= 0xFFFF for code in added), "Only BMP characters are supported")
    with TTFont(TTF) as font:
        require(all(code in font.getBestCmap() for code in added), "Source TTF lacks a required glyph")
    resource_pos, resource_size = next((p, s) for tag, p, s in chunks(source)
                                      if tag == b"RSCF" and b"times new roman_20_bold_0.tm2" in source[p:p + 128].lower())
    tim2 = source.index(b"TIM2", resource_pos, resource_pos + resource_size)
    picture = tim2 + 128
    _, clut_size, image_size = struct.unpack_from("<III", source, picture)
    header_size = struct.unpack_from("<H", source, picture + 12)[0]
    require(struct.unpack_from("<HH", source, picture + 20) == (width, height) and
            source[picture + 19] == 4 and image_size == width * height // 2, "Unexpected TIM2")
    image_offset = picture + header_size
    body = source[image_offset:image_offset + image_size]
    clut = source[image_offset + image_size:image_offset + image_size + clut_size]
    pixels = bytearray(width * height)
    pixels[0::2] = bytes(value & 15 for value in body)
    pixels[1::2] = bytes(value >> 4 for value in body)
    original_pixels = bytes(pixels)
    first_y, step_x, step_y, glyph_width, font_px, baseline, ss = 256, 28, 35, 26, 24, 26, 4
    columns = (width - 8) // step_x
    rows = 1 + (height - first_y - sample_height) // step_y
    require(len(added) <= columns * rows, "Heading font spare area is full")
    require(not any(pixels[first_y * width:]), "Heading atlas spare area is occupied")
    require(all(round(r[1] * height - .5) + sample_height < first_y for r in originals), "Original glyph samples overlap spare area")
    alpha = [min(255, clut[i * 4 + 3] * 2) for i in range(16)]
    quantize = [min(range(16), key=lambda i: abs(alpha[i] - value)) for value in range(256)]
    page = Image.frombytes("P", (width, height), bytes(pixels))
    page.putpalette([c for i in range(16) for c in clut[i * 4:i * 4 + 3]] + [0] * (768 - 48))
    page.info["transparency"] = bytes(alpha)
    font = ImageFont.truetype(str(TTF), font_px * ss)
    new_records, placements = [], []
    for index, code in enumerate(added):
        x, y = 4 + index % columns * step_x, first_y + index // columns * step_y
        glyph = Image.new("L", (glyph_width * ss, sample_height * ss))
        left, top, right, bottom = font.getbbox(chr(code), anchor="ls")
        require(left + ss >= 0 and right + ss <= glyph.width and top + baseline * ss >= 0 and
                bottom + baseline * ss <= glyph.height, f"Clipped glyph U+{code:04X}")
        ImageDraw.Draw(glyph).text((ss, baseline * ss), chr(code), font=font, anchor="ls", fill=255)
        glyph = glyph.resize((glyph_width, sample_height), Image.Resampling.LANCZOS).point(quantize)
        require(glyph.getbbox() is not None, f"Empty glyph U+{code:04X}")
        page.paste(glyph, (x, y))
        new_records.append(((x + .5) / width, (y + .5) / height, float(glyph_width), code, 0))
        placements.append({"char": chr(code), "code": code, "x": x, "y": y})
    pixels = page.tobytes()
    require(pixels[:first_y * width] == original_pixels[:first_y * width], "Original pixels changed")
    new_body = bytes(a | b << 4 for a, b in zip(pixels[0::2], pixels[1::2]))
    merged = sorted(originals + new_records, key=lambda r: r[3])
    font_block = bytearray(source[pos:pos + 0xF8])
    for record in merged:
        font_block.extend(struct.pack("<fffHh", *record))
    struct.pack_into("<I", font_block, 4, len(font_block))
    struct.pack_into("<HH", font_block, 0xE8, merged[0][3], merged[-1][3])
    struct.pack_into("<I", font_block, 0xF4, len(merged))
    result = bytearray(source[:pos]) + font_block + source[pos + size:]
    result[image_offset:image_offset + image_size] = new_body
    after = fonts(result)
    by_name = {name.lower(): value for name, value in after.items()}
    for name, cursor, base in entries:
        info = by_name[name.lower()]
        struct.pack_into("<II", result, cursor, info["offset"] - base, info["size"])
    rsfl_entries(result, after)
    require(needed <= {r[3] for r in after[FONT_NAME]["records"]}, "Missing heading glyphs")
    # Verify every original glyph record byte-for-byte, including float bits.
    old_raw = {struct.unpack_from("<H", source, pos + 0xF8 + i * 16 + 12)[0]:
               source[pos + 0xF8 + i * 16:pos + 0xF8 + (i + 1) * 16] for i in range(len(originals))}
    new_raw = {struct.unpack_from("<H", font_block, 0xF8 + i * 16 + 12)[0]:
               bytes(font_block[0xF8 + i * 16:0xF8 + (i + 1) * 16]) for i in range(len(merged))}
    require(all(new_raw[code] == value for code, value in old_raw.items()), "Original glyph records changed")
    for name, old in before.items():
        if name != FONT_NAME:
            new = after[name]
            require(source[old["offset"]:old["offset"] + old["size"]] ==
                    result[new["offset"]:new["offset"] + new["size"]], f"Other FONT changed: {name}")
    # Verify every non-FONT chunk; only heading pixel data and RSFL entries may differ.
    before_chunks, after_chunks = list(chunks(source)), list(chunks(result))
    require(len(before_chunks) == len(after_chunks), "Chunk count changed")
    for (tag, p, s), (new_tag, q, t) in zip(before_chunks, after_chunks):
        require(tag == new_tag, "Chunk order changed")
        if tag == b"RSFL" or p == pos:
            continue
        expected = bytearray(source[p:p + s])
        if p == resource_pos:
            expected[image_offset - p:image_offset - p + image_size] = new_body
        require(expected == result[q:q + t], f"Unexpected chunk edit at {p:#x}")
    require(result[-4:] == source[-4:] == b"\0" * 4, "Footer changed")
    report = {"font": FONT_NAME, "original_chars": len(originals), "added_chars": len(added),
              "total_chars": len(merged), "dimensions": [width, height], "sample_height": sample_height,
              "font_px": font_px, "baseline": baseline, "spare_capacity": columns * rows,
              "glyphs": placements, "input_sha256": sha256(source), "output_sha256": sha256(result),
              "source_ttf_sha256": sha256(TTF.read_bytes()), "original_glyphs_preserved": True,
              "other_font_chunks_preserved": True, "clut_preserved": True,
              "rsfl_relocated": True, "runtime_verification": "pending"}
    return bytes(result), page, merged, report


def preview(page, records, menu):
    by_code = {r[3]: r for r in records}
    atlas = page.convert("RGBA")
    selected = [42, 109, 212, 33, 37, 44, 45, 46, 47]
    image = Image.new("RGB", (900, 55 + 45 * len(selected)), (25, 28, 31))
    draw = ImageDraw.Draw(image)
    draw.text((12, 12), "Heading FONT atlas samples (not an emulator screenshot)", fill="white")
    for row, index in enumerate(selected):
        y, x = 45 + row * 45, 110
        draw.text((12, y + 8), f"HTXT:{index}", fill="white")
        for char in menu[index]["text"]:
            u, v, advance, _, _ = by_code[ord(char)]
            left, top = round(u * 512 - .5), round(v * 512 - .5)
            tile = atlas.crop((left, top, left + math.ceil(advance), top + 31))
            image.paste(tile, (x, y), tile)
            x += math.ceil(advance)
    image.save(OUTPUT / "large_menu_preview.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    saved = BACKUP / "Fonts/ntsc_fon.asr"
    if args.restore:
        manifest = json.loads((BACKUP / "manifest.json").read_text(encoding="utf-8"))
        original = saved.read_bytes()
        require(sha256(original) == manifest["input_sha256"], "Backup hash mismatch")
        require(sha256(TARGET.read_bytes()) in (manifest["input_sha256"], manifest["output_sha256"]), "Target has subsequent edits")
        TARGET.write_bytes(original)
        require(TARGET.read_bytes() == original, "Restore failed")
        print("Restored heading-font patch; previous small-font translation retained.")
        return
    current = TARGET.read_bytes()
    baseline = saved.read_bytes() if saved.exists() else current
    menu_bytes = MENU.read_bytes()
    menu, _ = parse_menu(menu_bytes)
    original_menu, _ = parse_menu((ROOT / "SOURCE/backups/start_menu_zh_20261004/Misc/Menu/Menu_Am.asr").read_bytes())
    require([e["id"] for e in menu] == [e["id"] for e in original_menu], "Menu IDs changed")
    changed = [e["text"] for e, orig in zip(menu, original_menu) if e["text"] != orig["text"]]
    require(changed, "No installed translations found")
    result, page, records, report = patch(baseline, changed)
    require(current in (baseline, result), "Target contains edits after this patch; preserve them before rebuilding")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "Fonts").mkdir(exist_ok=True)
    (OUTPUT / "Fonts/ntsc_fon.asr").write_bytes(result)
    page.save(OUTPUT / "times20_zh.png")
    preview(page, records, menu)
    report.update({"menu_sha256": sha256(menu_bytes), "installed_translation_count": len(changed), "installed": args.install})
    (OUTPUT / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.install:
        require(TARGET.read_bytes() == current and MENU.read_bytes() == menu_bytes, "Inputs changed during build")
        saved.parent.mkdir(parents=True, exist_ok=True)
        if not saved.exists():
            saved.write_bytes(baseline)
        require(saved.read_bytes() == baseline, "Backup differs")
        (BACKUP / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            TARGET.write_bytes(result)
            require(TARGET.read_bytes() == result, "Install readback failed")
        except Exception:
            TARGET.write_bytes(current)
            raise
    require(MENU.read_bytes() == menu_bytes, "Menu unexpectedly changed")
    print(json.dumps({k: report[k] for k in ("font", "added_chars", "total_chars", "sample_height", "output_sha256", "installed", "runtime_verification")}, indent=2))


if __name__ == "__main__":
    main()
