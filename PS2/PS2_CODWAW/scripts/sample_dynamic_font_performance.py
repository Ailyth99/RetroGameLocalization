"""Read-only diagnostics sampler for the explicitly owned DebugServer instance.

Verify TCP 21512 belongs to the intended PCSX2 process before starting. Tick
totals are wrapping CP0 Count values, not host frame-time or tearing measurements.
"""
import argparse
import json
from pathlib import Path
import struct
import time

from pcsx2_debug_query import q
from inspect_dynamic_font_dump import FIELDS

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--name', default='preload_training_samples.jsonl')
    args = parser.parse_args()
    assert Path(args.name).name == args.name and args.name.endswith('.jsonl')
    state = json.loads((ROOT/'SOUND/research/dynamic_font_cache/installed_build.json').read_text(encoding='utf-8'))
    output = ROOT/'SOUND/research/dynamic_font_cache/performance'/args.name
    previous = None
    started = time.monotonic()
    with output.open('w', encoding='utf-8') as log:
        while time.monotonic() - started < args.seconds:
            raw = q('read_memory', address=state['diagnostics_address'], length=128)
            words = struct.unpack('<32I', bytes.fromhex(raw['hex']))
            assert words[:3] == (0x4643485a, 2, 128)
            counters = dict(zip(FIELDS, words))
            if previous is None or any(counters[k] != previous[k] for k in ('loads', 'opens', 'errors', 'miss_batches')):
                text = bytes.fromhex(q('read_memory',address='0x00480e80',length=256)['hex']).decode('utf-16-le',errors='replace').split('\0',1)[0]
                row = dict(elapsed=time.monotonic()-started,elf_sha256=state['elf_sha256'],
                           subtitle_buffer=text,counters=counters)
                if previous is not None:
                    row['delta'] = {k:(counters[k]-previous[k])&0xffffffff for k in
                                    ('loads','fences','opens','blocks','read_bytes','resident_hits',
                                     'io_ticks','fence_ticks','decode_ticks','write_ticks','batch_ticks')}
                log.write(json.dumps(row,ensure_ascii=False)+'\n');log.flush()
                print(json.dumps({k:v for k,v in row.items() if k not in ('elf_sha256','counters')},ensure_ascii=False),flush=True)
                previous=counters
            time.sleep(.1)


if __name__ == '__main__':
    main()
