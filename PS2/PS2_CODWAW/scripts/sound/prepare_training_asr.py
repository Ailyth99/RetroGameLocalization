"""Read original AM audio, retain 64k MP3, prepare a Colab upload ZIP.

VAG/WAV intermediates live only in a temporary directory under SOUND.
"""
import hashlib
import json
import subprocess
import tempfile
import wave
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "SOUND/subtitles/L1_Gcan_am"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    result = subprocess.run([str(a) for a in args], capture_output=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace") +
                           result.stdout.decode("utf-8", errors="replace"))
    return result


def convert(row, base=BASE, *, source_data):
    base = base.resolve()
    if not base.is_relative_to((ROOT / "SOUND").resolve()):
        raise ValueError("Audio output and temporary files must stay under SOUND")
    for folder in ("mp3", "asr"):
        (base / folder).mkdir(parents=True, exist_ok=True)
    start = row["vag_offset"]
    raw = source_data[start:start + row["vag_size"]]
    if len(raw) != row["vag_size"] or hashlib.sha256(raw).hexdigest() != row["vag_sha256"]:
        raise ValueError(f"Original AM slice hash mismatch: {row['file']}")
    with tempfile.TemporaryDirectory(prefix=".audio_convert_", dir=base / "asr") as temporary:
        work = Path(temporary).resolve()
        # Check the absolute cleanup target before TemporaryDirectory removes it.
        if work.parent != (base / "asr").resolve():
            raise ValueError("Unexpected temporary audio directory")
        vag = work / Path(row["file"]).name
        wav = vag.with_suffix(".wav")
        mp3 = base / "mp3" / (vag.stem + ".mp3")
        vag.write_bytes(raw)
        return convert_files(row, vag, wav, mp3)


def convert_files(row, vag, wav, mp3):
    if digest(vag) != row["vag_sha256"]:
        raise ValueError(f"VAG hash mismatch: {vag.name}")
    run([ROOT / "tools/bin/vgmstream-cli.exe", "-i", "-o", wav, vag])
    with wave.open(str(wav), "rb") as stream:
        rate, frames, channels = stream.getframerate(), stream.getnframes(), stream.getnchannels()
        if (rate != row["sample_rate_hz"] or frames != row["adpcm_frame_count"] * 28
                or channels != 1 or stream.getsampwidth() != 2
                or len(stream.readframes(frames)) != frames * channels * 2):
            raise ValueError(f"Unexpected decoded duration: {wav.name}")
    run([ROOT / "tools/ffmpeg.exe", "-hide_banner", "-loglevel", "error", "-nostdin",
         "-y", "-i", wav, "-map_metadata", "-1", "-codec:a", "libmp3lame",
         "-b:a", "64k", "-threads", "1", mp3])
    # Decode validation, without writing another copy to disk.
    decoded = run([ROOT / "tools/ffmpeg.exe", "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-xerror", "-i", mp3, "-codec:a", "pcm_s16le", "-f", "s16le", "-"])
    decoded_frames, remainder = divmod(len(decoded.stdout), channels * 2)
    # MP3 is framed, and this installed FFmpeg/LAME may leave a few padding
    # samples (observed: +23 at 22050 Hz). WAV remains sample-exact to VAG.
    mp3_frame_samples = 1152 if rate >= 32000 else 576
    if remainder or abs(decoded_frames - frames) >= mp3_frame_samples:
        raise ValueError(f"MP3 decoded duration differs by at least one codec frame: {mp3.name}")
    return {
        "index": row["index"], "sound_id": row["sound_id_hex"],
        "sound_name": row["sound_name"], "filename": mp3.name,
        "audio": {"vag_file": None, "wav_file": None,
                  "intermediates_retained": False,
                  "source_vag_offset": row["vag_offset"], "source_vag_size": row["vag_size"],
                  "wav_bytes": wav.stat().st_size,
                  "mp3_file": "mp3/" + mp3.name, "duration_seconds": frames / rate,
                  "sample_rate_hz": rate, "channels": channels,
                  "decoded_frames": frames, "mp3_decode_check_passed": True,
                  "mp3_decoded_frames": decoded_frames,
                  "mp3_decoded_frame_delta": decoded_frames - frames,
                  "mp3_sample_count_tolerance_exclusive": mp3_frame_samples,
                  "vag_sha256": digest(vag), "wav_sha256": digest(wav),
                  "mp3_sha256": digest(mp3)},
        "embedded_text": {"status": row["text_status"], "text": row["embedded_english"]},
        "asr": {"status": "pending", "language": None, "text": None,
                "segments": [], "error": None},
        "review": {"status": "pending", "text_en": None, "text_zh": None, "notes": ""},
    }


def main():
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    source_data = (ROOT / "SOUND/L1_Gcan.am").read_bytes()
    if hashlib.sha256(source_data).hexdigest() != manifest["source_sha256"]:
        raise ValueError("Original L1 AM differs from manifest")
    for name in ("mp3", "asr"):
        (BASE / name).mkdir(exist_ok=True)
    entries = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for entry in pool.map(partial(convert, source_data=source_data), manifest["entries"]):
            entries.append(entry)
            if len(entries) % 50 == 0:
                print(f"Converted {len(entries)}/508", flush=True)
    result = {"schema_version": "1.0", "container": "L1_Gcan.am",
              "source_sha256": manifest["source_sha256"],
              "created_utc": datetime.now(timezone.utc).isoformat(),
              "asr_run": {"engine": "openai-whisper", "model": "large-v3",
                          "language": "en", "task": "transcribe", "completed_utc": None},
              "entries": entries}
    template = BASE / "asr/asr_template.json"
    template.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive = BASE / "L1_Gcan_Colab_upload.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        output.write(template, "asr_template.json")
        for entry in entries:
            output.write(BASE / entry["audio"]["mp3_file"], entry["audio"]["mp3_file"])
    report = {"count": len(entries), "wav_bytes": sum(e["audio"]["wav_bytes"] for e in entries),
              "audio_retention": "mp3_only", "retained_wav_bytes": 0, "retained_vag_bytes": 0,
              "mp3_bytes": sum(p.stat().st_size for p in (BASE / "mp3").glob("*.mp3")),
              "zip_bytes": archive.stat().st_size,
              "duration_seconds": sum(e["audio"]["duration_seconds"] for e in entries),
              "vgmstream_options": ["-i"], "mp3_bitrate": "64k",
              "sample_rate_and_channels_preserved": True,
              "all_mp3_decode_checks_passed": True,
              "vgmstream_sha256": digest(ROOT / "tools/bin/vgmstream-cli.exe"),
              "ffmpeg_sha256": digest(ROOT / "tools/ffmpeg.exe")}
    (BASE / "asr/conversion_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
