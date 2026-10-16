"""Build/install three native Chinese subtitles; no emulator or ISO automation.

Run: python -X utf8 scripts/build_training_subtitles_zh.py [--install]
"""
import argparse
import json
import struct
import sys
from pathlib import Path

import build_start_menu_zh as small
import build_options_menu_zh as options
from build_large_menu_font import fonts

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sound"))
from extract_am_vag import parse_container

WORK = ROOT / "SOUND/subtitles/training_zh_test_20261004"
BACKUP = ROOT / "SOURCE/backups/training_zh_test_20261004"
SPEC = ROOT / "SOUND/subtitles/L1_Gcan_am/subtitle_test_zh.json"
AM = Path("Envs/sp/L1_Gcan.am")
ELF = Path("slus_217.46")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    require = small.require
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    translations = spec["entries"]
    # Native newlines select timed segments; leave visual wrapping to renderer.
    for item in translations:
        item["zh"] = item["zh"].replace("\n", "")
    paths = (AM, ELF, small.FONT_PATH)
    previous = {p: (small.TARGET / p).read_bytes() for p in paths}
    source = {p: (BACKUP / p).read_bytes() if (BACKUP / p).exists() else previous[p]
              for p in paths}
    require(small.sha256(source[AM]) ==
            "462c976164bd112e30f237adbbc7d3497fb80e50afeaab242a999f1f1b9ce9fe",
            "Unexpected original training container")
    rows, structure = parse_container(source[AM])
    am = bytearray(source[AM])
    edits = []
    for item in translations:
        row = rows[item["index"]]
        require(row["sound_id_hex"] == item["sound_id"] and
                row["sound_name"] == item["sound_name"] and
                row["embedded_english"] == item["en"], "Dialogue source mismatch")
        offset, size = row["embedded_text_offset"], row["embedded_text_utf16_units"] * 2
        raw = item["zh"].encode("utf-16-le") + b"\0\0"
        require(len(raw) <= size, "Translation exceeds allocation")
        am[offset:offset + size] = raw.ljust(size, b"\0")
        edits.append({**item, "text_offset": offset, "allocation_bytes": size})
    after, after_structure = parse_container(am)
    expected = {item["index"]: item["zh"] for item in translations}
    require(structure == after_structure and len(am) == len(source[AM]), "AM layout changed")
    for before, current in zip(rows, after):
        require(current["embedded_english"] == expected.get(before["index"], before["embedded_english"]),
                "Subtitle readback failed")
        require(all(before[k] == current[k] for k in before if k != "embedded_english"),
                "Unexpected metadata/audio change")

    # Replace renderer's flag load with constant true. This remains enabled even
    # if game initialization rewrites its data flag. Original drawing ABI intact.
    elf = bytearray(source[ELF])
    require(elf[:4] == b"\x7fELF", "Not an ELF")
    va = 0x003D19C4
    offset = va - 0x00100000 + 0x80
    require(struct.unpack_from("<I", elf, offset)[0] == 0x93829271,
            "Unexpected subtitle renderer instruction")
    struct.pack_into("<I", elf, offset, 0x24020001)  # addiu v0,zero,1

    menu = json.loads(small.TRANSLATIONS.read_text(encoding="utf-8"))["entries"]
    menu += json.loads(options.ADDITIONS.read_text(encoding="utf-8"))["entries"]
    menu.sort(key=lambda item: item["index"])
    original_font = small.read_original(small.FONT_PATH)
    old_base, _, _, _ = small.patch_font(original_font, menu)
    old_font, _, _, _ = options.custom_heading(old_base, menu)
    require(old_font == source[small.FONT_PATH], "Existing font has unrelated edits")
    small.FIRST_Y, small.CELL_STEP_Y = 248, 33
    base, page, _, font_report = small.patch_font(original_font, menu + translations)
    font, _, _, _ = options.custom_heading(base, menu)
    before_fonts, after_fonts = fonts(old_font), fonts(font)
    for name, info in before_fonts.items():
        if name == "Verdana_20.asr":
            continue
        other = after_fonts[name]
        require(old_font[info["offset"]:info["offset"] + info["size"]] ==
                font[other["offset"]:other["offset"] + other["size"]], "Other FONT changed")
    outputs = {AM: bytes(am), ELF: bytes(elf), small.FONT_PATH: font}
    for p in paths:
        require(previous[p] in (source[p], outputs[p]), f"Unrelated target edits: {p}")
    WORK.mkdir(parents=True, exist_ok=True)
    for p, data in outputs.items():
        destination = WORK / "rebuilt" / p
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    page.save(WORK / "verdana20_atlas.png")
    report = {
        "scope": "Native subtitles globally enabled; three training lines translated",
        "runtime_validation": "pending_user_test",
        "elf_patch": {"virtual_address": hex(va), "file_offset": hex(offset),
                      "before_word": "93829271", "after_word": "24020001",
                      "before": "lbu v0,-0x6d8f(gp)", "after": "addiu v0,zero,1"},
        "entries": edits, "font": font_report,
        "all_508_vag_hashes_and_container_layout_preserved": True,
        "files": {p.as_posix(): {"before_sha256": small.sha256(source[p]),
                                "after_sha256": small.sha256(d)} for p, d in outputs.items()},
        "installed": False,
    }
    if args.install:
        for p in paths:
            require((small.TARGET / p).read_bytes() == previous[p], "Target changed during build")
            saved = BACKUP / p
            saved.parent.mkdir(parents=True, exist_ok=True)
            if not saved.exists():
                saved.write_bytes(source[p])
            require(saved.read_bytes() == source[p], "Backup mismatch")
        try:
            for p, data in outputs.items():
                (small.TARGET / p).write_bytes(data)
                require((small.TARGET / p).read_bytes() == data, "Install readback failed")
        except Exception:
            for p, data in previous.items():
                (small.TARGET / p).write_bytes(data)
            raise
        report["installed"] = True
        spec["entries"] = translations
        spec["status"] = "installed_pending_user_iso_test"
        SPEC.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (WORK / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"installed": report["installed"], "font_total": font_report["total_chars"],
                      "translated_lines": len(edits), "report": str(WORK / "build_report.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
