"""Build the expanded options translation and the requested rounded heading font.

python scripts/build_options_menu_zh.py [--install | --restore]
"""

import argparse
import json
import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

import build_start_menu_zh as small
from build_large_menu_font import fonts, rsfl_entries
from game_text_resources import chunks

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "TEMP/builds/options_menu_zh_20261004"
BACKUP = ROOT / "SOURCE/backups/options_menu_zh_20261004"
HEADING_FONT = ROOT / "FONT/source/USMCCyuanjiantecu.otf"
ADDITIONS = ROOT / "TEXT/translations/options_additions_zh.json"
FONT_NAME = "Times New Roman_20_Bold.asr"
RUNTIME_RECORD = ROOT / "docs/validation/options_menu_zh_20261004.json"


def custom_heading(source, translations):
    definitions = fonts(source)
    info = definitions[FONT_NAME]
    offset, size = info["offset"], info["size"]
    originals = info["records"]
    require = small.require
    require((info["width"], info["height"], info["sample_height"]) == (512, 512, 31), "Unexpected heading geometry")
    old_lookup = {r[3]: r for r in originals}
    required = {ord(c) for item in translations for c in item["zh"] if c not in "\n\r\t"}
    added = sorted(required - old_lookup.keys())
    all_codes = sorted(old_lookup.keys() | required)
    require(all(c <= 0xFFFF for c in all_codes), "Non-BMP glyph")
    entries = rsfl_entries(source, definitions)
    resource = next((p, s) for tag, p, s in chunks(source) if tag == b"RSCF" and
                    b"times new roman_20_bold_0.tm2" in source[p:p + 128].lower())
    tim2 = source.index(b"TIM2", resource[0], sum(resource))
    picture = tim2 + 128
    _, clut_size, image_size = struct.unpack_from("<III", source, picture)
    image_offset = picture + struct.unpack_from("<H", source, picture + 12)[0]
    require(struct.unpack_from("<HH", source, picture + 20) == (512, 512) and
            source[picture + 19] == 4 and image_size == 512 * 512 // 2, "Unexpected heading texture")
    body = source[image_offset:image_offset + image_size]
    clut = source[image_offset + image_size:image_offset + image_size + clut_size]
    pixels = bytearray(512 * 512)
    pixels[0::2] = bytes(v & 15 for v in body)
    pixels[1::2] = bytes(v >> 4 for v in body)
    original_page = Image.frombytes("P", (512, 512), bytes(pixels))
    page = Image.new("P", (512, 512), 0)
    page.putpalette([c for i in range(16) for c in clut[i * 4:i * 4 + 3]] + [0] * (768 - 48))
    alpha = [min(255, clut[i * 4 + 3] * 2) for i in range(16)]
    page.info["transparency"] = bytes(alpha)
    quantize = [min(range(16), key=lambda i: abs(alpha[i] - v)) for v in range(256)]
    with TTFont(HEADING_FONT) as font:
        cmap = font.getBestCmap()
    require(all(code in cmap for code in added), "Requested OTF is missing new Chinese glyphs")
    font_px, ss, baseline = 24, 4, 26
    font = ImageFont.truetype(str(HEADING_FONT), font_px * ss)
    records, fallback, rendered, placements = [], [], [], []
    x, y = 2, 1
    for code in all_codes:
        old = old_lookup.get(code)
        advance = old[2] if old else 28.0
        tile_width = math.ceil(advance)
        require(tile_width > 0, f"Invalid advance for U+{code:04X}")
        if x + tile_width + 2 > 512:
            x, y = 2, y + 33
        require(y + 31 < 512, "Heading atlas is full")
        if code in cmap:
            left, top, right, bottom = font.getbbox(chr(code), anchor="ls")
            ink = Image.new("L", (max(1, right - left), max(1, bottom - top)))
            ImageDraw.Draw(ink).text((-left, -top), chr(code), font=font, anchor="ls", fill=255)
            target_width = min(ink.width, max(1, tile_width - 2) * ss)
            target_height = min(ink.height, 29 * ss)
            if ink.size != (target_width, target_height):
                ink = ink.resize((target_width, target_height), Image.Resampling.LANCZOS)
            tile = Image.new("L", (tile_width * ss, 31 * ss))
            top_y = max(ss, min(baseline * ss + top, tile.height - ss - ink.height))
            tile.paste(ink, ((tile.width - ink.width) // 2, top_y))
            tile = tile.resize((tile_width, 31), Image.Resampling.LANCZOS).point(quantize)
            require(code in (0x20, 0xA0) or tile.getbbox() is not None, f"Blank custom glyph U+{code:04X}")
            rendered.append(code)
        else:
            require(old is not None, f"No fallback glyph U+{code:04X}")
            u, v = round(old[0] * 512 - .5), round(old[1] * 512 - .5)
            tile = original_page.crop((u, v, u + tile_width, v + 31))
            fallback.append(code)
        page.paste(tile, (x, y))
        records.append(((x + .5) / 512, (y + .5) / 512, advance, code, old[4] if old else 0))
        placements.append({"code": code, "x": x, "y": y, "width": tile_width,
                           "source": "requested_otf" if code in cmap else "original_glyph"})
        x += tile_width + 2
    pixels = page.tobytes()
    new_body = bytes(a | b << 4 for a, b in zip(pixels[0::2], pixels[1::2]))
    block = bytearray(source[offset:offset + 0xF8])
    for record in records:
        block.extend(struct.pack("<fffHh", *record))
    struct.pack_into("<I", block, 4, len(block))
    struct.pack_into("<HH", block, 0xE8, all_codes[0], all_codes[-1])
    struct.pack_into("<I", block, 0xF4, len(records))
    result = bytearray(source[:offset]) + block + source[offset + size:]
    result[image_offset:image_offset + image_size] = new_body
    after = fonts(result)
    names = {name.lower(): value for name, value in after.items()}
    for name, cursor, base in entries:
        target = names[name.lower()]
        struct.pack_into("<II", result, cursor, target["offset"] - base, target["size"])
    rsfl_entries(result, after)
    require(required <= {r[3] for r in after[FONT_NAME]["records"]}, "Heading coverage gap")
    original_chunks, rebuilt_chunks = list(chunks(source)), list(chunks(result))
    require(len(original_chunks) == len(rebuilt_chunks), "Chunk count changed")
    for (tag, p, s), (tag2, q, t) in zip(original_chunks, rebuilt_chunks):
        require(tag == tag2, "Chunk order changed")
        if tag == b"RSFL" or p == offset:
            continue
        expected = bytearray(source[p:p + s])
        if p == resource[0]:
            expected[image_offset - p:image_offset - p + image_size] = new_body
        require(expected == result[q:q + t], f"Unexpected edit to {tag!r}")
    require(source[-4:] == result[-4:] == b"\0" * 4, "Footer changed")
    # Re-read actual packed pixels and table to verify glyphs survived serialization.
    for record, placement in zip(after[FONT_NAME]["records"], placements):
        require(round(record[0] * 512 - .5) == placement["x"] and
                round(record[1] * 512 - .5) == placement["y"], "Glyph UV mismatch")
    roundtrip = bytearray(512 * 512)
    packed = result[image_offset:image_offset + image_size]
    roundtrip[0::2] = bytes(v & 15 for v in packed)
    roundtrip[1::2] = bytes(v >> 4 for v in packed)
    require(bytes(roundtrip) == pixels, "Heading texture round-trip mismatch")
    return bytes(result), page, records, {
        "font_identity": FONT_NAME, "source": HEADING_FONT.relative_to(ROOT).as_posix(),
        "source_sha256": small.sha256(HEADING_FONT.read_bytes()), "font_px": font_px,
        "dimensions": [512, 512], "sample_height": 31, "total_chars": len(records),
        "added_chars": len(added), "custom_rendered_chars": len(rendered),
        "original_fallback_codes": [f"U+{code:04X}" for code in fallback],
        "atlas_bottom": y + 31, "glyphs": placements,
        "original_advance_and_extra_fields_preserved": True, "clut_preserved": True,
    }


def preview(page, records, translations):
    texts = {e["index"]: e["zh"] for e in translations}
    lookup = {r[3]: r for r in records}
    selected = [42, 109, 212, 401, 44, 45, 46, 47]
    image = Image.new("RGB", (800, 50 + 46 * len(selected)), (25, 28, 31))
    draw, atlas = ImageDraw.Draw(image), page.convert("RGBA")
    draw.text((12, 12), "USMCCyuanjiantecu heading atlas sample (not emulator capture)", fill="white")
    for row, index in enumerate(selected):
        x, y = 110, 45 + row * 46
        draw.text((12, y + 7), f"HTXT:{index}", fill="white")
        for char in texts[index]:
            u, v, width, _, _ = lookup[ord(char)]
            left, top = round(u * 512 - .5), round(v * 512 - .5)
            tile = atlas.crop((left, top, left + math.ceil(width), top + 31))
            image.paste(tile, (x, y), tile)
            x += math.ceil(width)
    image.save(OUTPUT / "heading_preview.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    manifest_path = BACKUP / "manifest.json"
    paths = (small.FONT_PATH, small.MENU_PATH)
    if args.restore:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for path in paths:
            entry = manifest[path.as_posix()]
            small.require(small.sha256((BACKUP / path).read_bytes()) == entry["before_sha256"], "Backup mismatch")
            small.require(small.sha256((small.TARGET / path).read_bytes()) in (entry["before_sha256"], entry["after_sha256"]), "Target contains later edits")
        for path in paths:
            (small.TARGET / path).write_bytes((BACKUP / path).read_bytes())
        print("Restored the user-verified 44-entry, two-font menu version.")
        return
    previous = {path: (small.TARGET / path).read_bytes() for path in paths}
    source_font = small.read_original(small.FONT_PATH)
    source_menu = small.read_original(small.MENU_PATH)
    original_entries, _ = small.parse_menu(source_menu)
    translations = json.loads(small.TRANSLATIONS.read_text(encoding="utf-8"))["entries"]
    for addition in json.loads(ADDITIONS.read_text(encoding="utf-8"))["entries"]:
        entry = original_entries[addition["index"]]
        small.require(entry["text"] == addition["en"], "New translation source mismatch")
        translations.append({**addition, "id": f"{entry['id']:08X}"})
    translations.sort(key=lambda e: e["index"])
    menu, menu_report = small.patch_menu(source_menu, translations)
    base_font, small_page, _, small_report = small.patch_font(source_font, translations)
    font, page, records, heading_report = custom_heading(base_font, translations)
    outputs = {small.FONT_PATH: font, small.MENU_PATH: menu}
    # Preserve any independently edited text instead of silently overwriting it.
    old_entries, _ = small.parse_menu(previous[small.MENU_PATH])
    planned, _ = small.parse_menu(menu)
    old_spec = {e["index"]: e["zh"] for e in json.loads(small.TRANSLATIONS.read_text(encoding="utf-8"))["entries"]}
    for original, old, new in zip(original_entries, old_entries, planned):
        small.require(old["id"] == original["id"] and old["text"] in
                      (original["text"], old_spec.get(old["index"]), new["text"]), f"Unrelated menu edit: {old['index']}")
    known_fonts = {"3b01e805cb889c29fb091b84bee48974916c3e9314dd7eec44dc743a165dd482", small.sha256(font)}
    small.require(small.sha256(previous[small.FONT_PATH]) in known_fonts, "Font has unrelated changes")
    for path, data in outputs.items():
        destination = OUTPUT / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    page.save(OUTPUT / "heading_atlas.png")
    small_page.save(OUTPUT / "small_atlas.png")
    preview(page, records, translations)
    (OUTPUT / "translations.json").write_text(json.dumps(translations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    runtime = {"status": "pending"}
    if RUNTIME_RECORD.exists():
        verified = json.loads(RUNTIME_RECORD.read_text(encoding="utf-8"))
        if all(verified["sha256"].get(p.as_posix()) == small.sha256(d) for p, d in outputs.items()):
            runtime = verified
    report = {"menu": menu_report, "small_font": small_report, "heading_font": heading_report,
              "sha256": {p.as_posix(): small.sha256(d) for p, d in outputs.items()},
              "runtime_verification": runtime, "installed": args.install}
    (OUTPUT / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.install:
        for path in paths:
            small.require((small.TARGET / path).read_bytes() == previous[path], "Target changed during build")
        old_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
        for path in paths:
            saved = BACKUP / path
            if saved.exists():
                small.require(old_manifest and small.sha256(saved.read_bytes()) == old_manifest[path.as_posix()]["before_sha256"], "Existing backup is invalid")
            else:
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(previous[path])
        manifest = {p.as_posix(): {"before_sha256": small.sha256((BACKUP / p).read_bytes()), "after_sha256": small.sha256(outputs[p])} for p in paths}
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        try:
            for path, data in outputs.items():
                (small.TARGET / path).write_bytes(data)
                small.require((small.TARGET / path).read_bytes() == data, "Install readback mismatch")
        except Exception:
            for path, data in previous.items():
                (small.TARGET / path).write_bytes(data)
            raise
    print(json.dumps({"translated_entries": len(translations), "small_added_chars": small_report["added_chars"],
                      "heading_custom_glyphs": heading_report["custom_rendered_chars"], "heading_fallback_glyphs": len(heading_report["original_fallback_codes"]),
                      "heading_atlas_bottom": heading_report["atlas_bottom"], "sha256": report["sha256"], "installed": args.install}, indent=2))


if __name__ == "__main__":
    main()
