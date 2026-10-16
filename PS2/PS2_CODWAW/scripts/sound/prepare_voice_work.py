"""Prepare common voice and per-level story MP3 folders for review / Colab.

Never changes existing level JSON or existing workspace edits. Run from any CWD.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parents[2] / "SOUND"
FACTIONS = {"US": "美军通用", "JA": "日军通用", "GE": "德军通用", "UK": "英军通用"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def faction(name):
    parts = name.upper().split("_")
    if parts[0] in ("US", "JA", "GE"):
        return parts[0]
    if parts[0] == "BC" and len(parts) > 1:
        if parts[1] == "JAP":
            return "JA"
        if parts[1] in ("UK1", "UK2"):
            return "UK"
    return None


def prepare(subtitles=HERE / "subtitles", workspace=HERE / "voice_work", evidence=None):
    subtitles, workspace = Path(subtitles).resolve(), Path(workspace).resolve()
    if not workspace.is_relative_to(HERE.resolve()):
        raise ValueError("Voice work must remain under SOUND")
    workspace.mkdir(parents=True, exist_ok=True)
    sources, by_key, story, documents = [], defaultdict(list), {}, {}
    manifests = sorted(subtitles.glob("L*_am/manifest.json"),
                       key=lambda p: int(re.match(r"L(\d+)", p.parent.name)[1]))
    for path in manifests:
        level, manifest = path.parent.name, read(path)
        json_path = path.parent / "whisper_results.json"
        documents[level] = read(json_path) if json_path.exists() else {}
        sources.append({"level": level, "manifest_sha256": digest(path)})
        story[level] = []
        for entry in manifest["entries"]:
            filename = Path(entry["file"]).with_suffix(".mp3").name
            item = dict(entry, level=level, filename=filename)
            if faction(entry["sound_name"]):
                by_key[(entry["sound_name"], entry["sound_id"])].append(item)
            else:
                story[level].append([item])
    evidence_groups = {}
    if evidence is not None:
        report = read(Path(evidence))
        expected = {s["level"]: s["manifest_sha256"] for s in report["sources"]}
        if any(expected.get(s["level"]) != s["manifest_sha256"] for s in sources):
            raise ValueError("PCM evidence does not match current manifests; rerun analyze_shared_voice.py")
        evidence_groups = {(g["sound_name"], int(g["sound_id"], 16)): g for g in report["groups"]}
    collections = []
    for tag, label in FACTIONS.items():
        groups = [g for g in by_key.values() if faction(g[0]["sound_name"]) == tag]
        if groups:
            collections.append((f"common_{tag}", f"common/{tag}", label, "common", groups))
    for level, groups in story.items():
        if groups:
            collections.append((f"story_{level}", f"story/{level}", "剧情 · " + level[:-3], "story", groups))
    inventory = []
    for collection_id, relative, label, kind, groups in collections:
        folder = workspace / relative
        (folder / "mp3").mkdir(parents=True, exist_ok=True)
        if folder.resolve().parent.parent != workspace:
            raise ValueError(f"Unexpected work path: {folder}")
        entries, seed = [], {}
        for group in groups:
            representative = group[0]
            filename = representative["filename"]
            source = subtitles / representative["level"] / "mp3" / filename
            target = folder / "mp3" / filename
            if target.exists():
                if target.is_symlink() or digest(target) != digest(source):
                    raise ValueError(f"Existing work audio changed: {target}")
            else:
                shutil.copy2(source, target)
            evidence_group = evidence_groups.get((representative["sound_name"], representative["sound_id"]))
            encoded_versions = {(r["sample_rate_hz"], r["payload_sha256"]) for r in group}
            evidence_class = (evidence_group["evidence"] if evidence_group else
                              "identical_adpcm" if len(encoded_versions) == 1 else "needs_manual_review")
            row = {k: v for k, v in representative.items() if k not in ("level", "filename")}
            row.update(file="mp3/" + filename, source_level=representative["level"],
                       source_filename=filename, reuse_evidence=evidence_class,
                       requires_variant_review=kind == "common" and evidence_class == "needs_manual_review",
                       targets=[])
            for item in group:
                original = documents[item["level"]].get(item["filename"])
                row["targets"].append({"level": item["level"], "filename": item["filename"],
                                       "payload_sha256": item["payload_sha256"],
                                       "initial_translation": original.get("translation", "") if isinstance(original, dict) else "",
                                       "initial_needs_review": original.get("needs_review", True) if isinstance(original, dict) else True})
            entries.append(row)
            original = documents[representative["level"]].get(filename)
            if original is not None:
                seed[filename] = deepcopy(original)
        manifest = {"schema_version": "voice_work_1", "collection_id": collection_id, "kind": kind,
                    "label": label, "entries": entries}
        manifest_path = folder / "manifest.json"
        if manifest_path.exists():
            old = read(manifest_path)
            # Preserve the original baseline used for conflict detection on later syncs.
            def routes(document):
                return [(r["sound_name"], r["sound_id"], r["file"],
                         [(t["level"], t["filename"], t["payload_sha256"]) for t in r["targets"]])
                        for r in document["entries"]]
            if routes(old) != routes(manifest):
                raise ValueError(f"Existing work routing changed; preserve edits before rebuilding: {folder}")
        else:
            write(manifest_path, manifest)
        json_path = folder / "whisper_results.json"
        if seed and not json_path.exists():
            write(json_path, seed)
        template = folder / "whisper_results.template.json"
        if not template.exists():
            write(template, {Path(r["file"]).name: "" for r in entries})
        inventory.append({"id": collection_id, "path": relative, "label": label, "kind": kind,
                          "entries": len(entries), "target_copies": sum(len(r["targets"]) for r in entries),
                          "requires_variant_review": sum(r["requires_variant_review"] for r in entries)})
    report = {"schema_version": "voice_work_1", "created_utc": datetime.now(timezone.utc).isoformat(),
              "sources": sources, "collections": inventory,
              "summary": {"common": sum(c["entries"] for c in inventory if c["kind"] == "common"),
                          "common_target_copies": sum(c["target_copies"] for c in inventory if c["kind"] == "common"),
                          "story": sum(c["entries"] for c in inventory if c["kind"] == "story"),
                          "story_levels": sum(c["kind"] == "story" for c in inventory)}}
    write(workspace / "catalog.json", report)
    return report


if __name__ == "__main__":
    result = prepare(evidence=HERE / "research/shared_battle_voice/pcm_comparison.json")
    print(json.dumps({"summary": result["summary"], "collections": result["collections"]}, ensure_ascii=False, indent=2))
