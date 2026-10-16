"""Local subtitle and system-text review UI; no game import/build.

Run: python -X utf8 scripts/sound/review_server.py [--port 8765] [--no-browser]
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socket
import tempfile
import threading
from urllib.parse import unquote, urlsplit
import webbrowser
from subtitle_entries import entry_key, review_entries

APP_DIR = Path(__file__).resolve().parent
HERE = Path(__file__).resolve().parents[2] / "SOUND"
LEVEL_NAME = re.compile(r"L(\d+)_[A-Za-z0-9_-]+(?:_am)?$", re.I)


class ReviewError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else "missing"


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError) as error:
        raise ReviewError(f"JSON 无法读取：{path.name}（{error}）") from error


def language_of(name, original, record):
    parts = name.upper().split("_")
    marker = parts[0]
    # BC is battle chatter, not a language: bc_jap is Japanese, bc_uk1/2 English.
    if marker == "BC" and len(parts) > 1:
        speaker = parts[1]
        if speaker in ("JA", "JS", "JP", "JAP"):
            return "ja", "BC / " + speaker
        if re.fullmatch(r"(?:UK|US)\d*", speaker):
            return "en", "BC / " + speaker
        if speaker in ("GE", "DE", "GER"):
            return "de", "BC / " + speaker
    known = {"US": "en", "JA": "ja", "JS": "ja", "JP": "ja", "JAP": "ja",
             "GE": "de", "DE": "de"}
    if marker in known:
        return known[marker], marker
    if isinstance(record, dict) and record.get("language") in ("en", "ja", "de"):
        return record["language"], "ASR"
    if re.search(r"[\u3040-\u30ff]", original):
        return "ja", "原文"
    if re.search(r"[A-Za-z]", original) and not re.search(r"[\u3400-\u9fff]", original):
        return "en", "原文"
    return "other", marker or "未定"


def fields(record):
    if isinstance(record, str):
        return {"asr_text": record, "translation": "", "needs_review": True, "note": ""}
    if isinstance(record, dict):
        for key in ("asr_text", "translation", "note"):
            if key in record and not isinstance(record[key], str):
                raise ReviewError(f"字幕字段 {key} 必须是字符串")
        for key in ("needs_review", "reuse_approved"):
            if key in record and not isinstance(record[key], bool):
                raise ReviewError(f"{key} 必须是布尔值")
        return {"asr_text": record.get("asr_text", ""), "translation": record.get("translation", ""),
                "needs_review": record.get("needs_review", True), "note": record.get("note", "")}
    if record is None:
        return {"asr_text": "", "translation": "", "needs_review": True, "note": ""}
    raise ReviewError("识别 JSON 的值必须为原文字符串或字幕对象")


def asr_status(text):
    if text.strip() == "_SKIPPED_TOO_LONG_":
        return "skipped_too_long"
    return "ready" if text.strip() else "missing"


class ReviewStore:
    error = ReviewError

    def __init__(self, root, workspace=None):
        self.root = Path(root).resolve()
        self.workspace = Path(workspace).resolve() if workspace is not None else self.root.parent / "voice_work"
        self.lock = threading.RLock()
        from system_text_review import SystemTextReview, CATALOG_NAME
        self.system_text = SystemTextReview(self.root.parent.parent / 'TEXT' / CATALOG_NAME, self)

    def work_collections(self):
        catalog = self.workspace / "catalog.json"
        if not catalog.is_file():
            return {}
        result = {}
        for item in read_json(catalog).get("collections", []):
            if (not re.fullmatch(r"(?:common_[A-Z]+|story_L\d+_[A-Za-z0-9_-]+)", item["id"])
                    or item.get("kind") not in ("common", "story")):
                raise ReviewError("语音工作目录索引格式错误")
            path = (self.workspace / item["path"]).resolve()
            if not path.is_relative_to(self.workspace.resolve()) or path == self.workspace.resolve():
                raise ReviewError("语音工作目录超出 SOUND/voice_work")
            result[item["id"]] = dict(item, directory=path)
        return result

    def directories(self):
        if not self.root.is_dir():
            raise ReviewError(f"找不到字幕目录：{self.root}", 404)
        result = {}
        for path in self.root.iterdir():
            if (path.is_dir() and not path.is_symlink() and LEVEL_NAME.fullmatch(path.name)
                    and path.resolve().parent == self.root and (path / "mp3").is_dir()):
                result[path.name] = path
        levels = dict(sorted(result.items(), key=lambda item: (int(LEVEL_NAME.fullmatch(item[0])[1]), item[0])))
        return {**{key: item["directory"] for key, item in self.work_collections().items()}, **levels}

    def level(self, name):
        path = self.directories().get(name)
        if path is None:
            raise ReviewError("找不到该关卡", 404)
        return path

    def load_document(self, path):
        target = path / "whisper_results.json"
        if target.is_symlink():
            raise ReviewError("字幕 JSON 必须是关卡目录内的普通文件")
        raw = target.read_bytes() if target.exists() else None
        try:
            data = json.loads(raw.decode("utf-8-sig")) if raw is not None else {}
        except (ValueError, UnicodeError) as error:
            raise ReviewError(f"whisper_results.json 格式错误：{error}") from error
        if not isinstance(data, dict):
            raise ReviewError("whisper_results.json 顶层必须是“完整音频文件名 → 识别结果”的对象")
        for name, record in data.items():
            try:
                fields(record)
            except ReviewError as error:
                raise ReviewError(f"{name}：{error}") from error
        return target, raw, data

    def audio_files(self, path):
        audio = (path / "mp3").resolve()
        if audio.parent != path.resolve():
            raise ReviewError("MP3 目录不能指向关卡目录之外")
        with os.scandir(audio) as entries:
            return dict(sorted((entry.name, Path(entry.path)) for entry in entries
                               if entry.name.lower().endswith(".mp3")
                               and entry.is_file(follow_symlinks=False) and not entry.is_symlink()))

    def audio_file(self, path, filename):
        if any(char in filename for char in "/\\:\0") or not filename.lower().endswith(".mp3"):
            raise ReviewError("音频文件不存在", 404)
        audio = (path / "mp3").resolve()
        candidate = audio / filename
        if (audio.parent != path.resolve() or candidate.is_symlink() or
                candidate.resolve().parent != audio or not candidate.is_file()):
            raise ReviewError("音频文件不存在", 404)
        return candidate

    def load(self, name):
        if name == 'system_text':
            return self.system_text.load()
        path = self.level(name)
        _, raw, data = self.load_document(path)
        audio = self.audio_files(path)
        manifest_path = path / "manifest.json"
        manifest = read_json(manifest_path) if manifest_path.is_file() else {}
        metadata = {entry_key(row): row for row in review_entries(manifest)}
        rows = []
        for position, filename in enumerate(sorted(set(audio) | set(metadata))):
            row = metadata.get(filename, {})
            text_only = row.get('entry_kind') == 'unbanked_dlln'
            match = re.fullmatch(r"(\d+)__(.+)__([0-9a-fA-F]{8})\.mp3", filename)
            sound_name = row.get("sound_name", match[2] if match else Path(filename).stem)
            value = fields(data.get(filename))
            embedded = row.get("embedded_english", "")
            if row.get("text_status") == "placeholder" or embedded.strip().lower() == "subtitle_missing":
                embedded = ""
            language, marker = language_of(sound_name, value["asr_text"] or embedded, data.get(filename))
            targets = row.get("targets", [])
            variants = []
            seen = set()
            for target in targets:
                if text_only:
                    continue
                if target["payload_sha256"] not in seen:
                    seen.add(target["payload_sha256"])
                    variants.append({"level": target["level"], "filename": target["filename"]})
            rows.append({"filename": filename, "index": row.get("index", int(match[1]) if match else position),
                         "sound_name": sound_name, "sound_id": row.get("sound_id_hex", "0x" + match[3] if match else ""),
                         "language": language, "language_marker": marker,
                         "embedded_english": embedded, "audio_available": filename in audio,
                         "text_only": text_only,
                         "has_asr": asr_status(value["asr_text"]) == "ready",
                         "asr_status": 'embedded_only' if text_only else asr_status(value["asr_text"]), "has_record": filename in data,
                         "duration": row.get("frame_based_duration_seconds"),
                         "reuse_targets": targets, "audio_variants": variants,
                         "requires_variant_review": row.get("requires_variant_review", False),
                         "reuse_approved": bool(data.get(filename, {}).get("reuse_approved", False)) if isinstance(data.get(filename), dict) else False,
                         "reuse_evidence": row.get("reuse_evidence"), **value})
        rows.sort(key=lambda row: (row["index"], row["filename"]))
        counts = {"total": len(rows), "audio": len(audio),
                  "text_only": sum(row['text_only'] for row in rows),
                  "asr": sum(row["has_asr"] for row in rows),
                  "translated": sum(bool(row["translation"].strip()) for row in rows),
                  "reviewed": sum(not row["needs_review"] for row in rows)}
        kind = manifest.get("kind", "level")
        label = manifest.get("label", name[:-3] + ".am" if name.endswith("_am") else name)
        return {"id": name, "label": label, "kind": kind,
                "directory_hint": ("SOUND/voice_work/" + path.relative_to(self.workspace).as_posix() if kind != "level" else "SOUND/subtitles/" + name),
                "revision": digest(raw), "json_exists": raw is not None, "counts": counts,
                "unmatched_json_keys": sorted(set(data) - {r["filename"] for r in rows}), "entries": rows}

    def list_levels(self):
        result = []
        names = (['system_text'] if self.system_text.path.is_file() else []) + list(self.directories())
        for name in names:
            try:
                data = self.load(name)
                result.append({key: value for key, value in data.items() if key not in ("entries", "revision")})
            except (ReviewError, OSError) as error:
                result.append({"id": name, "label": name, "error": str(error),
                               "counts": {"total": 0, "audio": 0, "asr": 0, "translated": 0, "reviewed": 0}})
        return result

    def save(self, name, revision, edits):
        if name == 'system_text':
            return self.system_text.save(revision, edits)
        if not isinstance(revision, str) or not isinstance(edits, dict) or not edits:
            raise ReviewError("没有可保存的修改")
        with self.lock:
            path = self.level(name)
            current = self.load(name)
            target, raw, data = self.load_document(path)
            if digest(raw) != revision:
                raise ReviewError("磁盘上的 JSON 已被其他程序修改。当前编辑仍保留，请先导出草稿，再重新读取。", 409)
            allowed = {row["filename"] for row in current["entries"]}
            if not set(edits) <= allowed:
                raise ReviewError("修改包含未匹配的音频文件名")
            output = deepcopy(data)
            for filename, change in edits.items():
                if not isinstance(change, dict) or not set(change) <= {"translation", "needs_review", "note", "reuse_approved"}:
                    raise ReviewError("只能修改译文、校对状态、复用确认及备注")
                for key, value in change.items():
                    if key in ("needs_review", "reuse_approved"):
                        if not isinstance(value, bool):
                            raise ReviewError("校对状态必须是布尔值")
                    elif not isinstance(value, str):
                        raise ReviewError(f"{key} 必须是字符串")
                translation = change.get("translation", "")
                if any(c in translation for c in "\0\r\n\t") or any(ord(c) > 0xFFFF for c in translation):
                    raise ReviewError(f"{filename}：译文需为单段文字，不含换行、Tab、空字符或四字节字符")
                old = output.get(filename)
                record = deepcopy(old) if isinstance(old, dict) else fields(old)
                record.update(change)
                output[filename] = record
            if output == data:
                return {"revision": revision, "saved": 0, "backup": None, "counts": current["counts"]}
            written = self.write_document(target, output, revision)
            updated = self.load(name)
            return {**written, "saved": len(edits), "counts": updated["counts"]}

    def import_json(self, name, revision, incoming):
        """Merge ASR/translation into the selected collection without replacing edits."""
        if not isinstance(revision, str) or not isinstance(incoming, dict) or not incoming:
            raise ReviewError("请选择非空的 JSON：完整 MP3 文件名 → ASR 字符串或含 translation 的对象")
        with self.lock:
            path = self.level(name)
            current = self.load(name)
            target, raw, data = self.load_document(path)
            if digest(raw) != revision:
                raise ReviewError("磁盘 JSON 已发生变化，请重新读取后再导入。", 409)
            allowed = {row["filename"] for row in current["entries"]}
            unknown = sorted(set(incoming) - allowed)
            if unknown:
                raise ReviewError(f"有 {len(unknown)} 个文件名不属于当前目录 {current['label']}，未写入任何内容。请先选择对应军队或关卡。\n" + "\n".join(unknown[:8]))
            output, conflicts, changed = deepcopy(data), [], 0
            for filename, source in incoming.items():
                values = fields(source)
                translation = values["translation"]
                if any(c in translation for c in "\0\r\n\t") or any(ord(c) > 0xFFFF for c in translation):
                    raise ReviewError(f"{filename}：译文需为单段文字，不含换行、Tab、空字符或四字节字符；本次尚未写入")
                old = data.get(filename)
                record = deepcopy(old) if isinstance(old, dict) else fields(old)
                existing = fields(old)
                for key in ("asr_text", "translation", "note"):
                    value, prior = values[key], existing[key]
                    if not value.strip() or value == prior:
                        continue
                    if key == "asr_text":
                        # A skipped result must never displace a real transcript.
                        if asr_status(value) != "ready" and prior.strip():
                            continue
                        can_fill = asr_status(prior) != "ready"
                    else:
                        # An intentionally blank, reviewed translation is also protected.
                        can_fill = not prior.strip() and (key != "translation" or existing["needs_review"])
                    if can_fill:
                        record[key] = value
                        if key == "asr_text":
                            record["asr_status"] = asr_status(value)
                        if key == "translation":
                            record["needs_review"] = True
                            record["reuse_approved"] = False
                    else:
                        conflicts.append({"filename": filename, "field": key,
                                          "existing": prior, "incoming": value})
                if filename not in data or record != (old if isinstance(old, dict) else fields(old)):
                    output[filename] = record
                    changed += 1
            written = self.write_document(target, output, revision) if changed else {"revision": revision, "backup": None}
            return {**written, "saved": changed, "matched": len(incoming), "conflicts": conflicts,
                    "counts": self.load(name)["counts"] if changed else current["counts"]}

    def write_document(self, target, output, revision, *, backup_subdir='asr/review_backups'):
        path = target.parent
        if target.is_symlink():
            raise ReviewError("字幕 JSON 必须是普通文件")
        raw = target.read_bytes() if target.exists() else None
        if digest(raw) != revision:
            raise ReviewError("磁盘上的 JSON 已被其他程序修改，已取消覆盖。", 409)
        encoded = (json.dumps(output, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        backup = None
        if raw is not None:
            backup_dir = path / backup_subdir
            if not backup_dir.resolve().is_relative_to(path.resolve()):
                raise ReviewError("备份目录不能指向关卡目录之外")
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = backup_dir / f"{target.stem}.{stamp}.{digest(raw)[:12]}.json"
            with backup.open("xb") as stream:
                stream.write(raw)
        handle, temporary = tempfile.mkstemp(prefix=".review_save_", suffix=".tmp", dir=path)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            latest = target.read_bytes() if target.exists() else None
            if digest(latest) != revision:
                raise ReviewError("保存期间 JSON 被外部修改，已取消覆盖；当前编辑仍保留。", 409)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return {"revision": digest(encoded), "backup": str(backup.relative_to(path)) if backup else None}

    def sync_preview(self):
        from voice_sync import make_plan
        with self.lock:
            return make_plan(self)["preview"]

    def sync(self, revision):
        from voice_sync import apply_plan
        with self.lock:
            return apply_plan(self, revision)


class ReviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        # HTTPServer enables SO_REUSEADDR by default. On Windows this can bind
        # over another live checker, while requests still reach the old process.
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, address, store):
        super().__init__(address, ReviewHandler)
        self.store = store
        self.token = secrets.token_urlsafe(32)


class ReviewHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        if not args or str(args[1] if len(args) > 1 else "") not in ("200", "206"):
            super().log_message(format, *args)

    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def same_origin(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            raise ReviewError("仅允许从本机校对页面访问", 403)
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in hosts}:
            raise ReviewError("不允许其他网页写入字幕", 403)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self.same_origin()
            parts = [unquote(p) for p in urlsplit(self.path).path.split("/") if p]
            if not parts or parts == ["review_checker.html"]:
                body = (APP_DIR / "review_checker.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
            elif parts == ["review_checker.js"]:
                body = (APP_DIR / "review_checker.js").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
            elif parts == ["api", "levels"]:
                self.send_json({"levels": self.server.store.list_levels(), "token": self.server.token})
            elif parts == ["api", "sync-preview"]:
                self.send_json(self.server.store.sync_preview())
            elif parts == ["favicon.ico"]:
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif len(parts) == 3 and parts[:2] == ["api", "level"]:
                self.send_json(self.server.store.load(parts[2]))
            elif len(parts) == 3 and parts[0] == "audio":
                path = self.server.store.level(parts[1])
                audio = self.server.store.audio_file(path, parts[2])
                self.send_audio(audio)
            else:
                raise ReviewError("未找到该地址", 404)
        except ReviewError as error:
            self.send_json({"error": str(error)}, error.status)
        except ConnectionError:
            pass
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.send_json({"error": f"读取失败：{error}"}, 500)

    def do_POST(self):
        try:
            self.same_origin()
            if self.headers.get("X-Review-Token") != self.server.token:
                raise ReviewError("页面会话已失效，请重新打开校对页面", 403)
            endpoint = urlsplit(self.path).path
            if endpoint not in ("/api/save", "/api/sync", "/api/import"):
                raise ReviewError("未找到该地址", 404)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4 * 1024 * 1024:
                raise ReviewError("保存请求大小不正确", 413)
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                raise ReviewError("保存请求格式不正确")
            if endpoint == "/api/sync":
                result = self.server.store.sync(body.get("revision"))
            elif endpoint == "/api/import":
                result = self.server.store.import_json(body.get("level"), body.get("revision"), body.get("document"))
            else:
                result = self.server.store.save(body.get("level"), body.get("revision"), body.get("edits"))
            self.send_json(result)
        except ReviewError as error:
            self.send_json({"error": str(error)}, error.status)
        except ConnectionError:
            pass
        except (ValueError, UnicodeError, OSError, TypeError) as error:
            self.send_json({"error": f"保存失败：{error}"}, 400)

    def send_audio(self, path):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        requested = self.headers.get("Range")
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
            if match and (match[1] or match[2]):
                if match[1]:
                    start = int(match[1])
                    end = min(int(match[2]), size - 1) if match[2] else size - 1
                else:
                    start = max(0, size - int(match[2]))
                status = 206
            if not match or not (match[1] or match[2]) or not 0 <= start <= end < size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        self.send_response(status)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with path.open("rb") as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining:
                    block = stream.read(min(64 * 1024, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
        except ConnectionError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--root", type=Path, default=HERE / "subtitles")
    args = parser.parse_args()
    try:
        server = ReviewHTTPServer(("127.0.0.1", args.port), ReviewStore(args.root))
    except OSError:
        server = ReviewHTTPServer(("127.0.0.1", 0), ReviewStore(args.root))
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"字幕校对工具：{address}\n页面目录：{APP_DIR}\n数据目录：{args.root.resolve()}\n请使用本窗口显示的网址；关闭窗口或按 Ctrl+C 停止服务。", flush=True)
    if not args.no_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
