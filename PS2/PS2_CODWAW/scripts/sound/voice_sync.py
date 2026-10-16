"""Plan and apply reviewed voice-work records to full per-level subtitle JSON."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from subtitle_entries import entry_key, review_entries


def digest(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else "missing"


def normalized(record):
    if isinstance(record, dict):
        return deepcopy(record)
    return {"asr_text": record if isinstance(record, str) else "", "translation": "",
            "needs_review": True, "note": ""}


def make_plan(store, *, reviewed_only=True):
    collections = store.work_collections()
    snapshots, targets, conflicts, blocked = {}, {}, [], []
    eligible, pending = 0, 0
    catalog = store.workspace / "catalog.json"
    snapshots[str(catalog)] = digest(catalog.read_bytes() if catalog.exists() else None)

    def load(path):
        json_path, raw, document = store.load_document(path)
        snapshots[str(json_path)] = digest(raw)
        manifest_path = path / "manifest.json"
        manifest_raw = manifest_path.read_bytes()
        snapshots[str(manifest_path)] = digest(manifest_raw)
        return json_path, raw, document, json.loads(manifest_raw.decode("utf-8-sig"))

    for collection_id, info in collections.items():
        _, _, source_doc, manifest = load(info["directory"])
        for row in review_entries(manifest):
            source_filename = entry_key(row)
            if source_filename not in source_doc:
                pending += 1
                continue
            source = normalized(source_doc.get(source_filename))
            translation = source.get("translation", "")
            # An explicitly reviewed empty translation means intentional silence.
            if source.get("needs_review", True):
                pending += 1
                if reviewed_only:
                    continue
            # A raw ASR string has no saved translation to apply.
            raw_source = source_doc[source_filename]
            if not isinstance(raw_source, dict) or "translation" not in raw_source:
                continue
            if any(c in translation for c in "\0\t\r\n") or any(ord(c) > 0xFFFF for c in translation):
                raise store.error(f"{source_filename}：已校对译文包含游戏不支持的字符")
            if reviewed_only and row.get("requires_variant_review") and not source.get("reuse_approved", False):
                blocked.append({"collection": collection_id, "filename": source_filename,
                                "reason": "请先核对各关录音版本，并勾选允许跨关复用"})
                continue
            eligible += 1
            for target in row.get("targets", []):
                level, filename = target["level"], target["filename"]
                if level not in targets:
                    path = store.level(level)
                    if path.resolve().parent != store.root:
                        raise store.error("同步目标必须是完整关卡目录")
                    json_path, raw, document, target_manifest = load(path)
                    targets[level] = {"path": json_path, "revision": digest(raw), "original": document,
                                      "output": deepcopy(document), "changes": [],
                                      "entries": {entry_key(r): r for r in review_entries(target_manifest)}}
                plan = targets[level]
                actual = plan["entries"].get(filename)
                identity = 'dlln_sha256' if row.get('entry_kind') == 'unbanked_dlln' else 'payload_sha256'
                if (actual is None or actual["sound_name"] != row["sound_name"]
                        or actual["sound_id"] != row["sound_id"]
                        or actual.get('entry_kind') != row.get('entry_kind')
                        or not target.get(identity) or actual.get(identity) != target[identity]
                        or (identity == 'dlln_sha256' and row.get(identity) != target[identity])):
                    raise store.error(f"{level}/{filename}：完整声音名、ID 或来源版本不匹配")
                existing = normalized(plan["output"].get(filename))
                current_translation = existing.get("translation", "")
                provenance = existing.get("voice_work_source", {})
                same_source = (isinstance(provenance, dict)
                               and provenance.get("collection") == collection_id
                               and provenance.get("filename") == source_filename
                               and provenance.get("applied_translation") == current_translation)
                baseline = (not provenance and (not reviewed_only or existing.get("needs_review", True))
                            and current_translation == target.get("initial_translation", ""))
                protected = bool(current_translation) or not existing.get("needs_review", True)
                if protected and current_translation != translation and not (same_source or baseline):
                    conflicts.append({"level": level, "filename": filename, "existing": current_translation,
                                      "incoming": translation, "collection": collection_id,
                                      "reason": "保留关卡中独立修改或已校对的不同译文"})
                    continue
                updated = deepcopy(existing)
                updated.update(translation=translation, needs_review=source.get("needs_review", True))
                if not updated.get("asr_text") and source.get("asr_text"):
                    updated["asr_text"] = source["asr_text"]
                if not updated.get("note") and source.get("note"):
                    updated["note"] = source["note"]
                updated["voice_work_source"] = {"collection": collection_id, "filename": source_filename,
                                                "applied_translation": translation}
                if updated != plan["output"].get(filename):
                    plan["output"][filename] = updated
                    plan["changes"].append(filename)
    revision = digest(json.dumps(snapshots, sort_keys=True).encode("utf-8"))
    updates = {name: plan for name, plan in targets.items() if plan["changes"]}
    preview = {"available": bool(collections), "revision": revision, "eligible_sources": eligible,
               "pending_sources": pending, "variant_blocked": len(blocked), "blocked": blocked,
               "updates": sum(len(plan["changes"]) for plan in updates.values()),
               "levels": {name: len(plan["changes"]) for name, plan in updates.items()},
               "conflict_count": len(conflicts), "conflicts": conflicts}
    return {"preview": preview, "updates": updates, "snapshots": snapshots}


def apply_plan(store, revision, *, reviewed_only=True):
    plan = make_plan(store, reviewed_only=reviewed_only)
    if not isinstance(revision, str) or revision != plan["preview"]["revision"]:
        raise store.error("字幕或工作目录在预览后已改变，请刷新同步预览再执行。", 409)
    preview = plan["preview"]
    if not plan["updates"]:
        return {"saved": 0, "levels": {}, "conflict_count": preview["conflict_count"],
                "variant_blocked": preview["variant_blocked"], "report": None}
    for filename, expected in plan["snapshots"].items():
        path = Path(filename)
        if digest(path.read_bytes() if path.exists() else None) != expected:
            raise store.error("同步前文件发生变化，已取消写入。", 409)
    report_dir = store.workspace / "sync_reports"
    if not report_dir.resolve().is_relative_to(store.workspace.resolve()):
        raise store.error("同步报告目录超出语音工作目录")
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = report_dir / f"sync.{stamp}.json"
    report = {"created_utc": stamp, "status": "running", "preview": preview, "written": []}

    def record_report():
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    record_report()
    try:
        for level, update in plan["updates"].items():
            result = store.write_document(update["path"], update["output"], update["revision"])
            report["written"].append({"level": level, "entries": len(update["changes"]),
                                      "filenames": update["changes"], **result})
            record_report()
        report["status"] = "completed"
        record_report()
    except (OSError, ValueError, store.error) as error:
        report.update(status="partial" if report["written"] else "failed", error=str(error))
        record_report()
        raise store.error(f"同步中止，已写入 {len(report['written'])} 关；已写文件有备份。详情：{report_path}。{error}") from error
    return {"saved": preview["updates"], "levels": preview["levels"],
            "conflict_count": preview["conflict_count"], "variant_blocked": preview["variant_blocked"],
            "report": str(report_path)}
