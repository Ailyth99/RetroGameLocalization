"""Build a conservative Chinese start-menu test for the US PS2 release.

python scripts/build_start_menu_zh.py            # build and validate
python scripts/build_start_menu_zh.py --install  # also back up and patch ISO_UNPACK
python scripts/build_start_menu_zh.py --restore  # restore the backed-up files

Requires Pillow and fonttools. All paths are relative to this project.
The original texture, CLUT, glyph records and HTXT allocation sizes are retained.
"""

import argparse
import hashlib
import json
import math
import shutil
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from game_text_resources import OriginalResources


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "SOURCE/ISO_EXTRACT"
TARGET = ROOT / "ISO_UNPACK"
OUTPUT = ROOT / "TEMP/builds/start_menu_zh_20261004"
BACKUP = ROOT / "SOURCE/backups/start_menu_zh_20261004"
TRANSLATIONS = ROOT / "TEXT/translations/start_menu_zh.json"
TTF = ROOT / "FONT/source/IBMPlexSansSC-Regular.ttf"
RUNTIME_RECORD = ROOT / "docs/validation/start_menu_zh_20261004.json"
FONT_PATH = Path("Fonts/ntsc_fon.asr")
MENU_PATH = Path("Misc/Menu/Menu_Am.asr")
ORIGINAL_HASHES = {
    FONT_PATH: "b16cb66d5caf236dcbe0018f2e920e217a6b09c0442d39f42a445f79fba3e2f7",
    MENU_PATH: "d662ae833a01d7c44a86bbe580276da287fe27730f838cb4dcb6ce1db52cd68c",
}
FONT_OFFSET = 0x49AC8
RECORD_OFFSET = 0xF8
TIM2_OFFSET = 0xEC
PAGE_SIZE = 512
SAMPLE_HEIGHT = 32
CELL_STEP_X, CELL_STEP_Y = 28, 36
FIRST_X, FIRST_Y = 4, 256
GLYPH_WIDTH, FONT_PX, BASELINE, SS = 26, 24, 27, 4


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_original(relative):
    path = SOURCE / relative
    if path.exists():
        data = path.read_bytes()
    else:
        with OriginalResources() as original:
            data = original.read(relative)
    require(sha256(data) == ORIGINAL_HASHES[relative],
            f"Source differs from the verified original: {SOURCE / relative}")
    return data


def parse_menu(data):
    require(data[:12] == b"Asura   HTXT", "Not an HTXT resource")
    count = struct.unpack_from("<I", data, 0x18)[0]
    entries, pos = [], 0x24
    for index in range(count):
        require(pos + 8 <= len(data), f"Truncated HTXT record {index}")
        text_id, words = struct.unpack_from("<II", data, pos)
        end = pos + 8 + words * 2
        require(words > 0 and words % 2 == 0 and end <= len(data),
                f"Invalid HTXT allocation at {index}")
        raw = data[pos + 8:end]
        stop = next((i for i in range(0, len(raw), 2)
                     if raw[i:i + 2] == b"\0\0"), None)
        require(stop is not None, f"Missing terminator at {index}")
        entries.append({"index": index, "id": text_id, "offset": pos,
                        "size": words * 2, "text": raw[:stop].decode("utf-16-le")})
        pos = end
    return entries, pos


def patch_menu(source, translations):
    entries, end = parse_menu(source)
    require(struct.unpack_from("<I", source, 0x20)[0] ==
            sum(e["size"] for e in entries), "Unexpected HTXT text-size field")
    require(struct.unpack_from("<I", source, 0x0C)[0] == len(source) - 24,
            "Unexpected HTXT chunk-size field")
    result, seen = bytearray(source), set()
    for item in translations:
        index = item["index"]
        require(index not in seen and 0 <= index < len(entries),
                f"Invalid or duplicate translation index {index}")
        seen.add(index)
        original = entries[index]
        require(original["id"] == int(item["id"], 16) and
                original["text"] == item["en"], f"Translation source mismatch: {index}")
        require(item["zh"] and "\0" not in item["zh"], f"Invalid translation: {index}")
        encoded = item["zh"].encode("utf-16-le") + b"\0\0"
        require(len(encoded) <= original["size"],
                f"Translation {index} exceeds the original allocation")
        start = original["offset"] + 8
        result[start:start + original["size"]] = encoded.ljust(original["size"], b"\0")
    rebuilt, rebuilt_end = parse_menu(result)
    expected = {t["index"]: t["zh"] for t in translations}
    for before, after in zip(entries, rebuilt):
        require(after["text"] == expected.get(before["index"], before["text"]),
                f"HTXT read-back mismatch at {before['index']}")
        require(all(before[k] == after[k] for k in ("id", "offset", "size")),
                "HTXT record layout changed")
    require(len(result) == len(source) and rebuilt_end == end and
            result[end:] == source[end:] and result[:0x24] == source[:0x24],
            "HTXT header, footer or length changed")
    return bytes(result), {"entry_count": len(entries), "translated_entries": len(seen),
                           "file_size": len(result), "footer_offset": end,
                           "footer_size": len(source) - end}


def decode_page(data):
    require(data[TIM2_OFFSET:TIM2_OFFSET + 4] == b"TIM2", "Missing TIM2")
    picture = TIM2_OFFSET + 128
    _, clut_size, image_size = struct.unpack_from("<III", data, picture)
    header_size = struct.unpack_from("<H", data, picture + 12)[0]
    width, height = struct.unpack_from("<HH", data, picture + 20)
    require((width, height) == (PAGE_SIZE, PAGE_SIZE) and
            data[picture + 19] == 4 and image_size == width * height // 2,
            "Expected original 512x512 IDTEX4 page")
    image_offset = picture + header_size
    body = data[image_offset:image_offset + image_size]
    clut = data[image_offset + image_size:image_offset + image_size + clut_size]
    pixels = bytearray(width * height)
    pixels[0::2] = bytes(b & 15 for b in body)
    pixels[1::2] = bytes(b >> 4 for b in body)
    page = Image.frombytes("P", (width, height), bytes(pixels))
    page.putpalette([v for i in range(16) for v in clut[i * 4:i * 4 + 3]] +
                    [0] * (768 - 48))
    page.info["transparency"] = bytes(min(255, clut[i * 4 + 3] * 2) for i in range(16))
    return page, image_offset, image_size, clut


def read_font_records(data):
    require(data[FONT_OFFSET:FONT_OFFSET + 4] == b"FONT", "Unexpected FONT offset")
    first, last, width, height, count = struct.unpack_from("<HHIII", data, FONT_OFFSET + 0xE8)
    size = struct.unpack_from("<I", data, FONT_OFFSET + 4)[0]
    require(size == RECORD_OFFSET + 16 * count, "Invalid FONT size/count")
    records = [struct.unpack_from("<fffHh", data, FONT_OFFSET + RECORD_OFFSET + i * 16)
               for i in range(count)]
    codes = [r[3] for r in records]
    require(codes == sorted(set(codes)) and (first, last) == (codes[0], codes[-1]),
            "FONT table is not sorted or range does not match")
    require((width, height) == (PAGE_SIZE, PAGE_SIZE), "FONT page size changed")
    return records


def patch_font(source, translations):
    original_records = read_font_records(source)
    original_codes = {r[3] for r in original_records}
    required_codes = {ord(c) for t in translations for c in t["zh"] if c not in "\r\n\t"}
    added_codes = sorted(required_codes - original_codes)
    require(all(0x2019 < c <= 0xFFFF for c in added_codes),
            "This smoke test only appends BMP code points after the original table")
    with TTFont(TTF) as font:
        cmap = font.getBestCmap()
        require(all(c in cmap for c in added_codes), "TTF is missing required characters")
    page, image_offset, image_size, clut = decode_page(source)
    original_pixels = page.tobytes()
    require(not any(original_pixels[FIRST_Y * PAGE_SIZE:]), "Expected empty lower half")
    for u, v, width, code, _ in original_records:
        require(round(v * PAGE_SIZE - 0.5) + SAMPLE_HEIGHT < FIRST_Y,
                f"Original glyph U+{code:04X} samples the new area")
    # Match alpha to the actual, non-linear original CLUT; retain all CLUT bytes.
    alpha = list(page.info["transparency"])
    quantization = [min(range(16), key=lambda i: abs(alpha[i] - a)) for a in range(256)]
    font = ImageFont.truetype(str(TTF), FONT_PX * SS)
    columns = (PAGE_SIZE - FIRST_X * 2) // CELL_STEP_X
    rows = 1 + (PAGE_SIZE - FIRST_Y - SAMPLE_HEIGHT) // CELL_STEP_Y
    require(len(added_codes) <= columns * rows, "New glyphs exceed the 512x512 spare area")
    added_records, placements = [], []
    for index, code in enumerate(added_codes):
        x = FIRST_X + index % columns * CELL_STEP_X
        y = FIRST_Y + index // columns * CELL_STEP_Y
        glyph = Image.new("L", (GLYPH_WIDTH * SS, SAMPLE_HEIGHT * SS), 0)
        left, top, right, bottom = font.getbbox(chr(code), anchor="ls")
        require(left + SS >= 0 and right + SS <= glyph.width and
                top + BASELINE * SS >= 0 and bottom + BASELINE * SS <= glyph.height,
                f"Glyph U+{code:04X} would be clipped")
        ImageDraw.Draw(glyph).text((SS, BASELINE * SS), chr(code), font=font,
                                  anchor="ls", fill=255)
        glyph = glyph.resize((GLYPH_WIDTH, SAMPLE_HEIGHT), Image.Resampling.LANCZOS)
        indices = glyph.point(quantization)
        require(indices.getbbox() is not None, f"Blank glyph U+{code:04X}")
        page.paste(indices, (x, y))
        added_records.append(((x + 0.5) / PAGE_SIZE, (y + 0.5) / PAGE_SIZE,
                              float(GLYPH_WIDTH), code, 0))
        placements.append({"char": chr(code), "code": f"U+{code:04X}",
                           "x": x, "y": y, "width": GLYPH_WIDTH,
                           "sample_height": SAMPLE_HEIGHT})
    pixels = page.tobytes()
    require(pixels[:FIRST_Y * PAGE_SIZE] == original_pixels[:FIRST_Y * PAGE_SIZE],
            "Original atlas pixels changed")
    body = bytes(a | (b << 4) for a, b in zip(pixels[0::2], pixels[1::2]))
    require(len(body) == image_size, "Texture payload size changed")
    original_size = struct.unpack_from("<I", source, FONT_OFFSET + 4)[0]
    tail = source[FONT_OFFSET + original_size:]
    result = bytearray(source[:FONT_OFFSET + original_size])
    result[image_offset:image_offset + image_size] = body
    for record in added_records:
        result.extend(struct.pack("<fffHh", *record))
    new_size = original_size + 16 * len(added_records)
    struct.pack_into("<I", result, FONT_OFFSET + 4, new_size)
    struct.pack_into("<H", result, FONT_OFFSET + 0xEA,
                     added_codes[-1] if added_codes else original_records[-1][3])
    struct.pack_into("<I", result, FONT_OFFSET + 0xF4,
                     len(original_records) + len(added_records))
    # The final RSFL entry holds Verdana_20's offset, size, flags at 0x88.
    require(struct.unpack_from("<III", source, 0x88) ==
            (FONT_OFFSET - 0x8C, original_size, 1), "Unexpected RSFL font entry")
    struct.pack_into("<I", result, 0x8C, new_size)
    result.extend(tail)
    rebuilt_records = read_font_records(result)
    require(rebuilt_records[:len(original_records)] == original_records,
            "Original glyph records changed")
    require(required_codes <= {r[3] for r in rebuilt_records}, "Translation glyph coverage gap")
    decoded, _, _, rebuilt_clut = decode_page(result)
    require(decoded.tobytes() == pixels and rebuilt_clut == clut,
            "Texture round-trip or CLUT mismatch")
    # Only texture pixels and three FONT metadata fields plus RSFL size may change.
    expected_prefix = bytearray(source[:FONT_OFFSET + original_size])
    expected_prefix[image_offset:image_offset + image_size] = body
    for start, size in ((0x8C, 4), (FONT_OFFSET + 4, 4),
                        (FONT_OFFSET + 0xEA, 2), (FONT_OFFSET + 0xF4, 4)):
        expected_prefix[start:start + size] = result[start:start + size]
    require(result[:len(expected_prefix)] == expected_prefix and
            result[FONT_OFFSET + new_size:] == tail, "Unexpected ASR changes")
    # Walk actual chunk boundaries; chunk size includes the tag and size fields.
    pos = 8
    while pos < len(result) - len(tail):
        size = struct.unpack_from("<I", result, pos + 4)[0]
        require(size >= 8 and pos + size <= len(result) - len(tail), "Invalid ASR chunk")
        pos += size
    require(pos == len(result) - len(tail), "ASR chunk walk did not reach the footer")
    return bytes(result), decoded, rebuilt_records, {
        "page_size": [PAGE_SIZE, PAGE_SIZE], "sample_height": SAMPLE_HEIGHT,
        "original_chars": len(original_records), "added_chars": len(added_codes),
        "total_chars": len(rebuilt_records), "new_glyphs": placements,
        "font_px": FONT_PX, "ttf_sha256": sha256(TTF.read_bytes()),
        "original_clut_preserved": True, "original_glyphs_preserved": True,
        "file_size": len(result), "spare_area_capacity": columns * rows,
    }


def save_preview(page, records, translations):
    """Sample the generated texture through its FONT table, not through the TTF."""
    record_map = {r[3]: r for r in records}
    selected = [42, 43, 44, 214, 31, 32, 33, 37, 38, 39, 40, 213, 16, 17]
    texts = {t["index"]: t for t in translations}
    preview = Image.new("RGB", (900, 60 + len(selected) * 42), (25, 28, 31))
    draw = ImageDraw.Draw(preview)
    draw.text((16, 16), "FONT texture sample preview (not an emulator screenshot)", fill="white")
    atlas = page.convert("RGBA")
    for line, index in enumerate(selected):
        item, x, y = texts[index], 345, 52 + line * 42
        draw.text((16, y + 9), f"[{index:04d}] {item['en']}", fill=(170, 180, 190))
        for char in item["zh"]:
            u, v, width, _, _ = record_map[ord(char)]
            left, top = round(u * PAGE_SIZE - 0.5), round(v * PAGE_SIZE - 0.5)
            width = math.ceil(width)
            tile = atlas.crop((left, top, left + width, top + SAMPLE_HEIGHT))
            preview.paste(tile, (x, y), tile)
            x += width
    preview.save(OUTPUT / "menu_text_preview.png")


def install(outputs):
    # Preflight both files before changing either. Re-running is idempotent.
    for relative, data in outputs.items():
        current = (TARGET / relative).read_bytes()
        saved = BACKUP / relative
        if saved.exists():
            require(sha256(saved.read_bytes()) == ORIGINAL_HASHES[relative],
                    f"Backup is not the original: {saved}")
        else:
            require(sha256(current) == ORIGINAL_HASHES[relative],
                    f"Cannot back up a modified target: {TARGET / relative}")
        require(sha256(current) == ORIGINAL_HASHES[relative] or current == data,
                f"Target has unrelated edits: {TARGET / relative}")
    for relative in outputs:
        saved = BACKUP / relative
        if not saved.exists():
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(TARGET / relative, saved)
    manifest = {str(p): {"original_sha256": ORIGINAL_HASHES[p], "patched_sha256": sha256(d)}
                for p, d in outputs.items()}
    (BACKUP / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    try:
        for relative, data in outputs.items():
            (TARGET / relative).write_bytes(data)
            require((TARGET / relative).read_bytes() == data, f"Install verification failed: {relative}")
    except Exception:
        for relative in outputs:
            shutil.copy2(BACKUP / relative, TARGET / relative)
        raise
    print(f"Installed {len(outputs)} files in {TARGET}")
    print(f"Original files backed up in {BACKUP}")


def restore():
    manifest = json.loads((BACKUP / "manifest.json").read_text(encoding="utf-8"))
    for relative, original_hash in ORIGINAL_HASHES.items():
        require(sha256((BACKUP / relative).read_bytes()) == original_hash,
                f"Backup hash mismatch: {relative}")
        require(sha256((TARGET / relative).read_bytes()) in
                (original_hash, manifest[str(relative)]["patched_sha256"]),
                f"Target changed after installation; preserve those edits first: {relative}")
    for relative in ORIGINAL_HASHES:
        shutil.copy2(BACKUP / relative, TARGET / relative)
        require(sha256((TARGET / relative).read_bytes()) == ORIGINAL_HASHES[relative],
                f"Restore verification failed: {relative}")
    print("Restored both ISO_UNPACK files from verified backups.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--install", action="store_true")
    modes.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.restore:
        restore()
        return
    spec = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    require(spec["source_sha256"] == ORIGINAL_HASHES[MENU_PATH], "Translation version mismatch")
    translations = spec["entries"]
    menu, menu_report = patch_menu(read_original(MENU_PATH), translations)
    font, page, records, font_report = patch_font(read_original(FONT_PATH), translations)
    outputs = {FONT_PATH: font, MENU_PATH: menu}
    for relative, data in outputs.items():
        destination = OUTPUT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    page.save(OUTPUT / "verdana20_zh.png")
    save_preview(page, records, translations)
    runtime_verification = {"status": "pending"}
    if RUNTIME_RECORD.exists():
        verified = json.loads(RUNTIME_RECORD.read_text(encoding="utf-8"))
        if all(verified["sha256"].get(p.as_posix()) == sha256(d) for p, d in outputs.items()):
            runtime_verification = verified
    report = {"build": "start_menu_zh_20261004", "menu": menu_report, "font": font_report,
              "validation": "passed: source hashes, HTXT layout/read-back, FONT sorting/coverage, "
                            "CLUT/pixel round-trip, original glyphs, ASR chunks and footer",
              "runtime_verification": runtime_verification,
              "files": {str(p): {"original_sha256": ORIGINAL_HASHES[p],
                                  "patched_sha256": sha256(d)} for p, d in outputs.items()}}
    (OUTPUT / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Validated {len(translations)} translations and {font_report['added_chars']} added glyphs.")
    print(f"FONT: {font_report['original_chars']} -> {font_report['total_chars']} chars; 512x512 retained.")
    print(f"Outputs and texture preview: {OUTPUT}")
    if args.install:
        install(outputs)


if __name__ == "__main__":
    main()
