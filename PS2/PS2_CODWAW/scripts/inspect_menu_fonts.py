"""Locate serialized menu text/font bindings using the ELF's name hash."""

import json
import struct
from collections import Counter
from pathlib import Path

from build_start_menu_zh import parse_menu, read_original, MENU_PATH, sha256
from game_text_resources import chunks

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "TEMP/analysis/large_font"
FONTS = ("Times New Roman_20_Bold", "Verdana_20", "Verdana_10")


def name_hash(name):
    # SLUS_217.46: 0x0013F6A0 / 0x0013F710.
    value = 0
    for char in name.lower().replace("\\", "/"):
        value = (31 * value + ord(char)) & 0xFFFFFFFF
    return value


def inspect():
    original, _ = parse_menu(read_original(MENU_PATH))
    current, _ = parse_menu((ROOT / "ISO_UNPACK" / MENU_PATH).read_bytes())
    texts = {entry["id"]: entry for entry in original}
    active = {entry["id"]: entry for entry in current}
    font_hashes = {name_hash("/Fonts/" + name): name for name in FONTS}
    bindings = []
    files = {}
    for path in sorted((ROOT / "ISO_UNPACK/GUIMenu").glob("*.gui")):
        data = path.read_bytes()
        sections = list(chunks(data))
        files[path.name] = sha256(data)
        for font_hash, font in font_hashes.items():
            start = 0
            while (pos := data.find(struct.pack("<I", font_hash), start)) >= 0:
                start = pos + 1
                bank, text_id = struct.unpack_from("<II", data, pos - 8)
                # UITP names Menu/Menu; the bank identifier hashes the basename.
                assert bank == name_hash("menu"), (path.name, hex(pos), hex(bank))
                tag, section, size = next(s for s in sections if s[1] <= pos < s[1] + s[2])
                assert tag == b"UIMP", (path.name, hex(pos))
                screen = data[section + 28:data.index(b"\0", section + 28)].decode("ascii")
                scale = struct.unpack_from("<f", data, pos + 4)[0]
                assert 0 < scale <= 10
                source = texts.get(text_id)
                translated = active.get(text_id)
                bindings.append({
                    "gui": path.relative_to(ROOT / "ISO_UNPACK").as_posix(),
                    "screen": screen,
                    "font": font,
                    "font_hash": f"{font_hash:08X}",
                    "font_hash_offset": pos,
                    "text_id_offset": pos - 4,
                    "text_id": f"{text_id:08X}",
                    "menu_index": source["index"] if source else None,
                    "menu_text_offset": source["offset"] + 8 if source else None,
                    "en": source["text"] if source else None,
                    "current_text": translated["text"] if translated else None,
                    "translated": translated["text"] != source["text"] if source else False,
                    "resolution": "HTXT" if source else "dynamic_or_unresolved",
                    "scale": scale,
                })
    return {"gui_sha256": files, "bindings": sorted(bindings, key=lambda b: (b["gui"], b["font_hash_offset"]))}


def main():
    report = inspect()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "menu_font_bindings.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    big = [b for b in report["bindings"] if b["font"] == FONTS[0]]
    assert all(b["resolution"] == "HTXT" for b in big), "Unresolved large-font text ID"
    by_id = {}
    for binding in big:
        by_id.setdefault(binding["text_id"], []).append(binding)
    lines = [
        "PS2 COD5 大字字库文本位置清单（2026-10-04）",
        "字库：Fonts/ntsc_fon.asr → Times New Roman_20_Bold",
        "字体标识：0xB69E49F0；小字 Verdana_20 为 0x41B7AC04。",
        f"扫描了 {len(report['gui_sha256'])} 个 GUI：大字共 {len(by_id)} 条去重文本、{len(big)} 处控件引用。",
        "范围：GUI 文件中明确保存的字体绑定；运行时动态生成或覆盖的文字需另行跟踪。",
        "同一文本可同时用于大小两种字体；控件的 scale 还会影响最终显示大小。",
        "所有偏移均从文件开头起算；菜单编号对应 Menu_Am.asr 的 HTXT 记录序号（从 0 开始）。",
        "完整大小字绑定及 GUI 文件哈希：TEMP/analysis/large_font/menu_font_bindings.json",
        "",
    ]
    for text_id, uses in sorted(by_id.items(), key=lambda item: item[1][0]["menu_index"]):
        first = uses[0]
        lines.extend([
            f"[HTXT:{first['menu_index']}] ID={text_id}",
            f"英文：{first['en']}",
            f"当前文本：{first['current_text']}",
            f"文本文件：ISO_UNPACK/Misc/Menu/Menu_Am.asr，偏移 0x{first['menu_text_offset']:08X}",
        ])
        for use in uses:
            lines.append(f"  GUI：ISO_UNPACK/{use['gui']}；界面：{use['screen']}；字体字段：0x{use['font_hash_offset']:08X}；缩放：{use['scale']:.3g}")
        lines.append("")
    with (ROOT / "TEXT/大字字库文本清单.txt").open("w", encoding="utf-8-sig", newline="") as output:
        output.write("\r\n".join(lines) + "\r\n")
    print(json.dumps({"all_font_bindings": dict(Counter(b["font"] for b in report["bindings"])), "large_unique_texts": len(by_id), "large_bindings": len(big)}, indent=2))


if __name__ == "__main__":
    main()
