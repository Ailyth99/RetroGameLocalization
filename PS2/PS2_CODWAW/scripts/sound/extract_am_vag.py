#!/usr/bin/env python3
"""Extract original VAG bytes and speech metadata from this game's Asura .am.

Usage: python -X utf8 scripts/sound/extract_am_vag.py SOUND/L1_Gcan.am [output_root]
Output: output_root/<container_stem>_am/{vag/, manifest.json, manifest.csv,
                                      embedded_english.txt}
This parser validates the uncompressed DLLN v2 / streamed-sounds RSCF layout
observed in L1_Gcan.am. Unsupported layouts fail instead of being guessed.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_name(data, start, end, alignment_base):
    terminator = data.index(b"\0", start, end)
    name = data[start:terminator].decode("ascii")
    # Padding is relative to the chunk, not the absolute file offset.
    next_offset = alignment_base + ((terminator + 1 - alignment_base + 3) // 4) * 4
    return name, next_offset


def parse_container(data, *, allow_unbanked_dlln=False):
    require(data[:8] == b"Asura   ", "Expected an uncompressed Asura container")
    chunks = []
    cursor = 8
    while cursor + 16 <= len(data):
        tag, size, version, flags = struct.unpack_from("<4sIII", data, cursor)
        require(size >= 16 and cursor + size <= len(data), f"Invalid chunk at {cursor:#x}")
        chunks.append((tag, cursor, size, version, flags))
        cursor += size
    require(data[cursor:] in (b"", b"\0\0\0\0"), "Unexpected container trailer")

    names = {}
    banks = []
    for tag, offset, size, version, flags in chunks:
        end = offset + size
        if tag == b"DLLN":
            require(version == 2, f"Unsupported DLLN version at {offset:#x}")
            name, fields = read_name(data, offset + 16, end, offset)
            require(fields + 24 <= end, f"Truncated DLLN fields: {name}")
            values = struct.unpack_from("<6I", data, fields)
            sound_id, text_units = values[2], values[5]
            require(fields + 24 + text_units * 2 == end, f"DLLN text length mismatch: {name}")
            raw_text = data[fields + 24:end]
            if raw_text:
                require(raw_text.endswith(b"\0\0"), f"Unterminated DLLN text: {name}")
            text = raw_text.decode("utf-16-le").rstrip("\0")
            require(sound_id not in names, f"Duplicate DLLN sound ID: {sound_id:#x}")
            names[sound_id] = {
                "sound_name": name,
                "dlln_offset": offset,
                "dlln_size": size,
                "dlln_float_at_fields_plus_16": struct.unpack_from("<f", data, fields + 16)[0],
                "embedded_text_utf16_units": text_units,
                "embedded_text_offset": fields + 24 if text_units else None,
                "embedded_english": text,
                "text_status": "absent" if not text else (
                    "placeholder" if text.strip().lower() == "subtitle_missing" else "present"
                ),
            }
        elif tag == b"RSCF":
            require(size >= 29, f"Truncated RSCF at {offset:#x}")
            name, body = read_name(data, offset + 28, end, offset)
            if name == "streamed sounds":
                require(version == 0 and flags == 1, "Unsupported streamed-sounds RSCF version")
                require(struct.unpack_from("<I", data, offset + 20)[0] == 9,
                        "Unsupported streamed-sounds resource type")
                require(struct.unpack_from("<I", data, offset + 24)[0] == end - body,
                        "RSCF body size mismatch")
                banks.append((offset, end, body))

    require(len(banks) == 1, "Expected exactly one streamed-sounds RSCF bank")
    rscf_offset, bank_end, body = banks[0]
    require(body + 8 <= bank_end, "Truncated sound-bank header")
    bank_version, count = struct.unpack_from("<II", data, body)
    require(bank_version == 1 and count > 0, "Unsupported or empty sound bank")
    table = body + 8
    require(table + count * 24 <= bank_end, "Truncated sound table")
    expected_offset = table + count * 24
    rows = []
    used_ids = set()
    for index in range(count):
        table_offset = table + index * 24
        sound_id, rate, unknown1, unknown2, vag_offset, vag_size = struct.unpack_from(
            "<6I", data, table_offset
        )
        require(sound_id not in used_ids, f"Duplicate bank sound ID: {sound_id:#x}")
        require(sound_id in names, f"No DLLN for sound ID: {sound_id:#x}")
        require(vag_offset == expected_offset, f"Non-contiguous VAG entry {index}")
        require(vag_size >= 48 and vag_offset + vag_size <= bank_end,
                f"VAG entry {index} exceeds its bank")
        require(data[vag_offset:vag_offset + 4] == b"VAGp", f"Missing VAGp at entry {index}")
        version, reserved, payload_size, header_rate = struct.unpack_from(
            ">4I", data, vag_offset + 4
        )
        require(version == 0x20, f"Unsupported VAG version at entry {index}")
        require(payload_size > 0 and payload_size % 16 == 0 and payload_size + 48 == vag_size,
                f"VAG size mismatch at entry {index}")
        require(rate == header_rate and 0 < rate <= 96000, f"VAG rate mismatch at entry {index}")
        metadata = names[sound_id]
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", metadata["sound_name"])
        filename = f"{index:04d}__{safe_name}__{sound_id:08X}.vag"
        raw_vag = data[vag_offset:vag_offset + vag_size]
        rows.append({
            "index": index,
            "sound_id": sound_id,
            "sound_id_hex": f"0x{sound_id:08X}",
            **metadata,
            "file": f"vag/{filename}",
            "table_entry_offset": table_offset,
            "table_unknown_1": unknown1,
            "table_unknown_2": unknown2,
            "vag_offset": vag_offset,
            "vag_offset_hex": f"0x{vag_offset:08X}",
            "vag_size": vag_size,
            "header_size": 48,
            "payload_offset": vag_offset + 48,
            "payload_size": payload_size,
            "sample_rate_hz": rate,
            "adpcm_frame_count": payload_size // 16,
            "frame_based_duration_seconds": payload_size // 16 * 28 / rate,
            "last_frame_flag": raw_vag[-15],
            "vag_sha256": sha256(raw_vag),
            "payload_sha256": sha256(raw_vag[48:]),
        })
        used_ids.add(sound_id)
        expected_offset = vag_offset + vag_size
    require(expected_offset == bank_end, "Unaccounted data at the end of the sound bank")
    unbanked = [{"sound_id": sound_id, "sound_id_hex": f"0x{sound_id:08X}", **metadata}
                for sound_id, metadata in names.items() if sound_id not in used_ids]
    require(allow_unbanked_dlln or not unbanked,
            "DLLN and sound-table IDs do not match exactly")
    structure = {
        "chunk_counts": dict(Counter(tag.decode("ascii") for tag, *_ in chunks)),
        "rscf_offset": rscf_offset,
        "bank_header_offset": body,
        "sound_table_offset": table,
        "sound_table_entry_size": 24,
        "bank_end_offset": bank_end,
        "container_trailer_hex": data[cursor:].hex(),
    }
    if allow_unbanked_dlln:
        structure["unbanked_dlln_entries"] = unbanked
    return rows, structure


def extract(source, output_root, *, allow_unbanked_dlln=False, write_vags=True):
    source = source.resolve()
    data = source.read_bytes()
    rows, structure = parse_container(data, allow_unbanked_dlln=allow_unbanked_dlln)
    output = output_root.resolve() / source.name.replace(".", "_")
    require(not output.exists(), f"Output already exists; choose another output_root: {output}")
    output.mkdir(parents=True)
    if write_vags:
        (output / "vag").mkdir()
        for row in rows:
            start = row["vag_offset"]
            raw_vag = data[start:start + row["vag_size"]]
            target = output / row["file"]
            target.write_bytes(raw_vag)
            require(target.read_bytes() == raw_vag, f"Written bytes differ: {target}")

    stats = {
        "vag_count": len(rows),
        "vag_total_bytes": sum(row["vag_size"] for row in rows),
        "payload_total_bytes": sum(row["payload_size"] for row in rows),
        "sample_rate_counts": dict(Counter(row["sample_rate_hz"] for row in rows)),
        "text_status_counts": dict(Counter(row["text_status"] for row in rows)),
        "frame_based_total_duration_seconds": sum(row["frame_based_duration_seconds"] for row in rows),
        "written_vags_match_source_bytes": True if write_vags else None,
        "vag_files_retained": write_vags,
        "dlln_without_audio_in_this_bank": len(structure.get("unbanked_dlln_entries", [])),
    }
    manifest = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "source_size": len(data),
        "source_sha256": sha256(data),
        "extractor": str(Path(__file__).resolve()),
        "extractor_sha256": sha256(Path(__file__).read_bytes()),
        "extraction": ("Exact original 48-byte VAG header plus unmodified ADPCM payload"
                       if write_vags else "Metadata only; VAG offsets and hashes refer to original AM bytes"),
        "structure": structure,
        "statistics": stats,
        "entries": rows,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    text_lines = [
        f"{source.stem} / Asura DLLN 内嵌英文文本（原样导出，尚未校对音频）",
        "索引和 sound_id 对应 manifest.json；subtitle_missing 是原始占位文本。",
        "空文本条目也记录在 manifest 中。本文件不是已完成的字幕或 ASR 结果。",
        "",
    ]
    for row in rows:
        if row["embedded_english"]:
            text_lines.extend([
                f'[{row["index"]:04d}] {row["sound_name"]} | {row["sound_id_hex"]} | {row["text_status"]}',
                row["embedded_english"],
                "",
            ])
    (output / "embedded_english.txt").write_text("\n".join(text_lines), encoding="utf-8")
    require(source.read_bytes() == data, "Source changed during extraction")
    return output, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output_root", type=Path, nargs="?",
                        default=Path(__file__).resolve().parents[2] / "SOUND/subtitles")
    parser.add_argument("--allow-unbanked-dlln", action="store_true",
                        help="Record DLLN entries with no audio in this bank; extract bank entries only")
    args = parser.parse_args()
    output, manifest = extract(args.source, args.output_root,
                               allow_unbanked_dlln=args.allow_unbanked_dlln)
    print(json.dumps({"output": str(output), "source_sha256": manifest["source_sha256"],
                      **manifest["statistics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
