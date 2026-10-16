"""Read original game resources and locate length-delimited English text."""

import io
import struct
from pathlib import Path

import pycdlib


ROOT = Path(__file__).resolve().parents[1]


def iso_path():
    candidates = list((ROOT / "SOURCE").glob("*.iso")) + list(ROOT.glob("*.iso"))
    exact = [p for p in candidates if p.name ==
             "Call of Duty - World at War - Final Fronts (USA, Canada) (En,Fr).iso"]
    if len(exact) != 1:
        raise ValueError("Expected one original Call of Duty ISO in the root or SOURCE directory")
    return exact[0]


class OriginalResources:
    def __enter__(self):
        self.iso = pycdlib.PyCdlib()
        self.iso.open(str(iso_path()))
        return self

    def read(self, relative):
        stream = io.BytesIO()
        path = "/" + str(relative).replace("\\", "/").upper() + ";1"
        self.iso.get_file_from_iso_fp(stream, iso_path=path)
        return stream.getvalue()

    def __exit__(self, *args):
        self.iso.close()


def chunks(data):
    if data[:8] != b"Asura   ":
        raise ValueError("Not an uncompressed Asura resource")
    pos = 8
    while pos + 8 <= len(data):
        tag = data[pos:pos + 4]
        if tag == b"\0" * 4:
            break
        size = struct.unpack_from("<I", data, pos + 4)[0]
        if size < 8 or pos + size > len(data):
            raise ValueError(f"Invalid chunk {tag!r} at {pos:#x}")
        yield tag, pos, size
        pos += size
    if any(data[pos:]):
        raise ValueError(f"Unparsed ASR tail at {pos:#x}")


def text_record(data, length_offset, block_end, key, **meta):
    words = struct.unpack_from("<I", data, length_offset)[0]
    start = length_offset + 4
    end = start + words * 2
    if words == 0 and meta.get("kind") == "DLLN" and start == block_end:
        return {"key": key, "offset": start, "capacity": 0, "text": "", **meta}, end
    if words < 1 or end > block_end:
        raise ValueError(f"Invalid text allocation {key}")
    raw = data[start:end]
    stop = next((i for i in range(0, len(raw), 2) if raw[i:i + 2] == b"\0\0"), None)
    if stop is None:
        raise ValueError(f"Unterminated text {key}")
    return {"key": key, "offset": start, "capacity": words * 2,
            "text": raw[:stop].decode("utf-16-le"), **meta}, end


def locate_text(data):
    records = []
    for tag, pos, size in chunks(data):
        end = pos + size
        if tag == b'HTXT':
            count = struct.unpack_from('<I', data, pos + 16)[0]
            cursor = pos + 28
            for index in range(count):
                text_id = struct.unpack_from('<I', data, cursor)[0]
                item, cursor = text_record(data, cursor + 4, end, f"HTXT:{index}",
                                           kind="HTXT", index=index, text_id=f"{text_id:08X}")
                records.append(item)
        elif tag == b'LTXT':
            count = struct.unpack_from('<I', data, pos + 16)[0]
            cursor = pos + 20
            for index in range(count):
                item, cursor = text_record(data, cursor, end, f"LTXT:{index}",
                                           kind="LTXT", index=index)
                records.append(item)
            if cursor != end:
                raise ValueError("Unparsed LTXT data")
        elif tag == b'DLLN':
            name_end = data.index(b'\0', pos + 16, end)
            name = data[pos + 16:name_end].decode('ascii')
            fields = pos + ((name_end - pos + 4) & ~3)
            item, cursor = text_record(data, fields + 20, end, f"DLLN:{name}",
                                       kind="DLLN", name=name)
            if cursor != end:
                raise ValueError(f"Unparsed DLLN data: {name}")
            records.append(item)
        elif tag == b'PTXT':
            count, language = struct.unpack_from('<II', data, pos + 20)
            name_end = data.index(b'\0', pos + 28, end)
            name = data[pos + 28:name_end].decode('ascii')
            cursor = pos + ((name_end - pos + 4) & ~3)
            for index in range(count):
                item, cursor = text_record(data, cursor, end,
                                           f"PTXT:{language}:{name}:{index}",
                                           kind="PTXT", index=index, name=name, language=language)
                if language in (0, 6):
                    records.append(item)
            if cursor != end:
                raise ValueError(f"Unparsed PTXT data: {name}")
    return records
