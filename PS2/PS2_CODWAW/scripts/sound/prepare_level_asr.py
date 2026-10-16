"""Export remaining AM banks as MP3 for user-run ASR.

Run from any directory: python -X utf8 scripts/sound/prepare_level_asr.py
Optional positional arguments select source AM files. L1 is excluded by default.
No ASR, translation, AM installation, font build, or ISO build is performed.
Original VAG data stays in AM; temporary VAG/WAV files are removed after conversion.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
import json
from pathlib import Path
import re
import sys

from extract_am_vag import extract, parse_container, require, sha256
from prepare_training_asr import convert, digest

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "SOUND/subtitles"
sys.path.insert(0, str(ROOT / "scripts"))
from verify_dynamic_iso import ISO


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def level_number(path):
    match = re.match(r"L(\d+)_", path.name)
    require(match is not None, f"Unrecognized level filename: {path}")
    return int(match[1])


def prepare(source, workers, tool_hashes):
    base = OUTPUT / source.name.replace(".", "_")
    source_bytes = source.read_bytes()
    rows, structure = parse_container(source_bytes, allow_unbanked_dlln=True)
    if not base.exists():
        base, manifest = extract(source, OUTPUT, allow_unbanked_dlln=True, write_vags=False)
    else:
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        require(manifest["source_sha256"] == sha256(source_bytes),
                f"Source differs from existing manifest: {source.name}")
        require(manifest["entries"] == rows and manifest["structure"] == structure,
                f"Existing manifest differs from parsed source: {base}")
    for folder in ("mp3", "asr"):
        (base / folder).mkdir(exist_ok=True)

    report_path = base / "asr/conversion_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        require(report["source_sha256"] == manifest["source_sha256"],
                f"Previous conversion used a different source: {base}")
        entries = report["entries"]
        require([entry["filename"] for entry in entries] ==
                [Path(row["file"]).with_suffix(".mp3").name for row in rows],
                f"Previous conversion file list differs: {base}")
        for entry in entries:
            require(digest(base / entry["audio"]["mp3_file"]) == entry["audio"]["mp3_sha256"],
                    f"Previously validated MP3 has changed: {entry['filename']}")
        print(f"{source.name}: verified existing {len(entries)} conversions", flush=True)
    else:
        entries = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for entry in pool.map(partial(convert, base=base, source_data=source_bytes), rows):
                entries.append(entry)
                if len(entries) % 50 == 0 or len(entries) == len(rows):
                    print(f"{source.name}: converted and checked {len(entries)}/{len(rows)}", flush=True)
        report = {
            "schema_version": 1,
            "container": source.name,
            "source_sha256": manifest["source_sha256"],
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "count": len(entries),
            "wav_bytes": sum(e["audio"]["wav_bytes"] for e in entries),
            "mp3_bytes": sum((base / e["audio"]["mp3_file"]).stat().st_size for e in entries),
            "duration_seconds": sum(e["audio"]["duration_seconds"] for e in entries),
            "vgmstream_options": ["-i"],
            "mp3_bitrate": "64k",
            "sample_rate_and_channels_preserved": True,
            "all_wav_frame_counts_checked": True,
            "all_mp3_decode_checks_passed": True,
            "all_mp3_decoded_frame_counts_checked": True,
            "mp3_frame_count_check": "Absolute delta must be less than one MP3 codec frame; WAV is exact",
            "mp3_files_with_sample_padding_delta": sum(
                e["audio"]["mp3_decoded_frame_delta"] != 0 for e in entries),
            "mp3_max_absolute_sample_delta": max(
                abs(e["audio"]["mp3_decoded_frame_delta"]) for e in entries),
            "dlln_without_audio_in_this_bank": len(structure["unbanked_dlln_entries"]),
            **tool_hashes,
            "entries": entries,
        }
    report.update({"audio_retention": "mp3_only", "retained_vag_bytes": 0,
                   "retained_wav_bytes": 0})
    write_json(report_path, report)

    # These are pending templates, never a fabricated whisper_results.json.
    template = base / "asr/asr_template.json"
    if not template.exists():
        write_json(template, {
            "schema_version": "1.0", "container": source.name,
            "source_sha256": manifest["source_sha256"],
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "asr_run": {"engine": "openai-whisper", "model": "large-v3",
                        "language": None, "task": "transcribe", "completed_utc": None},
            "entries": entries,
        })
    filename_template = base / "asr/whisper_results.template.json"
    if not filename_template.exists():
        write_json(filename_template, {entry["filename"]: "" for entry in entries})

    expected_stems = {Path(row["file"]).stem for row in rows}
    for kind in ("mp3",):
        require({p.stem for p in (base / kind).glob("*." + kind)} == expected_stems,
                f"Missing or unexpected {kind} files: {base}")
    require(source.read_bytes() == source_bytes, f"Source changed during conversion: {source}")
    return {
        "container": source.name,
        "directory": base.relative_to(ROOT).as_posix(),
        "source_sha256": manifest["source_sha256"],
        "source_matches_original_iso": True,
        **{key: report[key] for key in (
            "count", "wav_bytes", "mp3_bytes", "duration_seconds",
            "dlln_without_audio_in_this_bank")},
        "all_vags_match_source_bytes": True,
        "all_wav_and_mp3_frame_counts_checked": True,
        "audio_retention": "mp3_only", "retained_vag_bytes": 0, "retained_wav_bytes": 0,
        "asr_status": "pending_user",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path, nargs="*")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    require(1 <= args.workers <= 16, "Use 1 to 16 conversion workers")
    all_sources = sorted((ROOT / "ISO_UNPACK/Envs/sp").glob("*.am"), key=level_number)
    sources = [p.resolve() for p in args.sources] if args.sources else [
        p for p in all_sources if p.name.lower() != "l1_gcan.am"]
    require(sources and len(set(sources)) == len(sources), "Empty or duplicate source list")
    for source in sources:
        require(source.parent == ROOT / "ISO_UNPACK/Envs/sp",
                f"Expected an AM from ISO_UNPACK/Envs/sp: {source}")
        require(source.name.lower() != "l1_gcan.am", "L1 already has edited ASR and remains separate")

    original_iso = ROOT / "Call of Duty - World at War - Final Fronts (USA, Canada) (En,Fr).iso"
    iso = ISO(original_iso)
    try:
        preflight = []
        for source in sources:
            data = source.read_bytes()
            require(iso.read("Envs/sp/" + source.name) == data,
                    f"Source AM differs from original ISO: {source.name}")
            rows, structure = parse_container(data, allow_unbanked_dlln=True)
            preflight.append({"container": source.name, "count": len(rows),
                              "unbanked_dlln": len(structure["unbanked_dlln_entries"])})
        print(json.dumps({"preflight": preflight, "total": sum(p["count"] for p in preflight)}), flush=True)
    finally:
        iso.fp.close()
    tool_hashes = {"vgmstream_sha256": digest(ROOT / "tools/bin/vgmstream-cli.exe"),
                   "ffmpeg_sha256": digest(ROOT / "tools/ffmpeg.exe"),
                   "converter_sha256": digest(ROOT / "scripts/sound/prepare_training_asr.py"),
                   "batch_script_sha256": digest(Path(__file__))}
    levels = [prepare(source, args.workers, tool_hashes) for source in sources]
    summary = {
        "schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_iso": original_iso.name,
        "available_am_containers": [p.name for p in all_sources],
        "exported_containers": len(levels),
        "count": sum(p["count"] for p in levels),
        "wav_bytes": sum(p["wav_bytes"] for p in levels),
        "mp3_bytes": sum(p["mp3_bytes"] for p in levels),
        "duration_seconds": sum(p["duration_seconds"] for p in levels),
        "dlln_without_audio_in_this_bank": sum(p["dlln_without_audio_in_this_bank"] for p in levels),
        "asr_status": "pending_user", "levels": levels,
        "audio_retention": "mp3_only", "retained_vag_bytes": 0, "retained_wav_bytes": 0,
    }
    write_json(OUTPUT / "audio_export_report.json", summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "levels"}), flush=True)


if __name__ == "__main__":
    main()
