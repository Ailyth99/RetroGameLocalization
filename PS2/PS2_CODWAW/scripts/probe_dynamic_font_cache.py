"""Offline cache reference model and capacity audit; does not patch/build game files.

Existing pixels are read only as analysis inputs. This is not a font rebuild,
PS2 renderer, optical-disc performance test, or proof of GPU synchronization.
"""
from collections import Counter, OrderedDict, defaultdict
import hashlib
import json
from pathlib import Path
import random
import struct

from game_text_resources import chunks
from unified_fonts import parse_pages

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'SOUND/research/dynamic_font_cache'
BIG = 'Times New Roman_20_Bold.asr'
SMALL = 'Verdana_10.asr'
SUB = 'Verdana_20.asr'
LAYOUTS = {
    'large': dict(width=512, height=512, cell_width=32, cell_height=34,
                  columns=16, slots=240, transparent=0),
    'small': dict(width=128, height=128, cell_width=16, cell_height=18,
                  columns=8, slots=48, transparent=15),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def lane(key):
    return 'small' if key[0] == SMALL else 'large'


def pixel(raw, width, x, y):
    p = y * width + x
    return (raw[p // 2] >> (4 * (p & 1))) & 15


def put(raw, width, x, y, value):
    p = y * width + x
    shift = 4 * (p & 1)
    raw[p // 2] = (raw[p // 2] & ~(15 << shift)) | (value << shift)


class ExistingGlyphs:
    def __init__(self, data):
        resources = {}
        for tag, pos, size in chunks(data):
            if tag == b'RSCF':
                res = data[pos:pos + size]
                name = res[28:res.index(b'\0', 28)].decode('ascii')
                resources[name.replace('\\', '/').split('/')[-1].lower()] = res
        self.records = {}
        self.palettes = {}
        self.fonts = []
        for name, font in parse_pages(data).items():
            sample = round(struct.unpack_from('<f', data, font['offset'] + 0x74)[0])
            glyph_count = 0
            for page in font['pages']:
                key = page['texture'].replace('\\', '/').split('/')[-1].lower().replace('.tga', '.tm2')
                res = resources[key]
                pic = res.index(b'TIM2') + 128
                _, clut_size, image_size, header_size = struct.unpack_from('<IIIH', res, pic)
                width, height = page['width'], page['height']
                assert res[pic + 19] == 4 and image_size == width * height // 2
                start = pic + header_size
                raw = res[start:start + image_size]
                palette = res[start + image_size:start + image_size + clut_size]
                assert self.palettes.setdefault(name, palette) == palette
                for u, v, advance, code, extra in page['records']:
                    # Current data has integer advances; reject assumptions if it changes.
                    assert advance == int(advance)
                    x, y = round(u * width - .5), round(v * height - .5)
                    w = int(advance)
                    assert 0 < w and 0 <= x <= width - w and 0 <= y <= height - sample
                    key = (name, code)
                    assert key not in self.records
                    self.records[key] = (raw, width, x, y, w, sample, advance, extra)
                    glyph_count += 1
            self.fonts.append(dict(font=name, glyphs=glyph_count, sample_height=sample,
                                   palette_sha256=sha(self.palettes[name])))
        assert self.palettes[BIG] == self.palettes[SUB]
        assert self.palettes[SMALL] != self.palettes[SUB]
        for key, record in self.records.items():
            layout = LAYOUTS[lane(key)]
            assert record[4] + 2 <= layout['cell_width']
            assert record[5] + 2 <= layout['cell_height']
            palette = self.palettes[key[0]]
            assert palette[layout['transparent'] * 4 + 3] == 0

    def tile(self, key):
        raw, width, x, y, w, h, _, _ = self.records[key]
        return bytes(pixel(raw, width, x + xx, y + yy) for yy in range(h) for xx in range(w))


class CacheModel:
    """Fixed packed 4bpp atlases; caller must retire every submitted batch first.

    The pending guard is deliberately page-wide: native DMA references a whole
    atlas, so even a presently unused slot cannot be edited during its upload.
    retire() models an external fence; it does NOT implement that fence on PS2.
    """
    def __init__(self, glyphs):
        self.glyphs = glyphs
        self.atlases = {n: bytearray([v['transparent'] * 17]) * (v['width'] * v['height'] // 2)
                        for n, v in LAYOUTS.items()}
        self.resident = {n: OrderedDict() for n in LAYOUTS}
        self.pending = None
        self.stats = Counter()

    def coords(self, group, slot):
        cfg = LAYOUTS[group]
        return slot % cfg['columns'] * cfg['cell_width'], slot // cfg['columns'] * cfg['cell_height']

    def prepare(self, keys):
        if self.pending is not None:
            raise BufferError('CPU batch / DMA still pending; atlas replacement forbidden')
        keys = set(keys)
        # Validate all requests before mutating anything, including capacity failures.
        for key in keys:
            if key not in self.glyphs.records:
                raise KeyError(key)
        counts = Counter(lane(key) for key in keys)
        if any(counts[g] > LAYOUTS[g]['slots'] for g in LAYOUTS):
            raise BufferError('Working set exceeds lane capacity; split/retire/prefetch is required')
        for key in sorted(keys):
            group = lane(key)
            residents = self.resident[group]
            if key in residents:
                residents.move_to_end(key)
                self.stats['hits'] += 1
                continue
            cfg = LAYOUTS[group]
            if len(residents) == cfg['slots']:
                victim = next(k for k in residents if k not in keys)
                slot = residents.pop(victim)
                self.stats['evictions'] += 1
            else:
                slot = min(set(range(cfg['slots'])) - set(residents.values()))
            residents[key] = slot
            atlas = self.atlases[group]
            x, y = self.coords(group, slot)
            assert x + cfg['cell_width'] <= cfg['width'] and y + cfg['cell_height'] <= cfg['height']
            for yy in range(cfg['cell_height']):
                for xx in range(cfg['cell_width']):
                    put(atlas, cfg['width'], x + xx, y + yy, cfg['transparent'])
            w, h = self.glyphs.records[key][4:6]
            tile = self.glyphs.tile(key)
            for yy in range(h):
                for xx in range(w):
                    put(atlas, cfg['width'], x + 1 + xx, y + 1 + yy, tile[yy * w + xx])
            self.stats['loads'] += 1
        return keys

    def submit(self, keys):
        assert self.pending is None
        self.pending = [(k, self.resident[lane(k)][k], self.glyphs.tile(k)) for k in keys]
        self.stats['batches'] += 1

    def retire(self):
        assert self.pending is not None
        for key, slot, expected in self.pending:
            group = lane(key)
            cfg = LAYOUTS[group]
            x, y = self.coords(group, slot)
            w, h = self.glyphs.records[key][4:6]
            actual = bytes(pixel(self.atlases[group], cfg['width'], x + 1 + xx, y + 1 + yy)
                           for yy in range(h) for xx in range(w))
            assert actual == expected, ('pending glyph changed', key)
            self.stats['glyph_pixel_comparisons'] += 1
        self.pending = None

    def run(self, keys):
        self.submit(self.prepare(keys))
        self.retire()


def text_keys(font, text):
    # Whitespace still needs width metadata; it needs no visible pixel slot.
    return {(font, ord(c)) for c in text if not c.isspace() and not 0xE000 <= ord(c) <= 0xF8FF}


def existing_io_buffers():
    from analyze_l1_ram import containing, u32
    folder = ROOT / 'SOUND/research/l1_ram_comparison'
    comparisons = json.loads((folder / 'comparison.json').read_text(encoding='utf-8'))
    result = []
    for snapshot in comparisons:
        data = (ROOT / snapshot['path']).read_bytes()
        assert sha(data) == snapshot['sha256'], 'Re-run RAM comparison after replacing dumps'
        blocks = json.loads((folder / (snapshot['label'] + '_chunks.json')).read_text(encoding='utf-8'))
        handles = []
        for h in range(2):
            base = 0x4e9188 + h * 0x44
            buffers = []
            for b in range(2):
                pointer = u32(data, base + 0x18 + b * 4)
                block = containing(blocks, pointer)
                assert block is not None and block['status'] == 'allocated'
                assert pointer + 0xc000 <= block['address'] + block['size']
                buffers.append(dict(address=hex(pointer), capacity=0xc000,
                                    containing_chunk=block))
            handles.append(dict(handle=h, open_flag=data[base], buffers=buffers))
        result.append(dict(snapshot=snapshot['label'], sha256=snapshot['sha256'], handles=handles))
    return result


def main():
    source = ROOT / 'ISO_UNPACK/Fonts/ntsc_fon.asr'
    data = source.read_bytes()
    glyphs = ExistingGlyphs(data)
    cache = CacheModel(glyphs)
    all_keys = sorted(glyphs.records)
    for seed in range(3):
        ordered = all_keys.copy()
        random.Random(seed).shuffle(ordered)
        for i in range(0, len(ordered), 32):
            cache.run(ordered[i:i + 32])

    cache.submit(cache.prepare(all_keys[:1]))
    before = {n: sha(v) for n, v in cache.atlases.items()}
    try:
        cache.prepare(all_keys[-1:])
    except BufferError:
        pending_guard = True
    else:
        raise AssertionError('Pending atlas was allowed to change')
    assert before == {n: sha(v) for n, v in cache.atlases.items()}
    cache.retire()
    before_residents = {n: list(v.items()) for n, v in cache.resident.items()}
    too_many = [k for k in all_keys if lane(k) == 'large'][:241]
    try:
        cache.prepare(too_many)
    except BufferError:
        overflow_guard = True
    else:
        raise AssertionError('Overflow was not reported')
    assert before == {n: sha(v) for n, v in cache.atlases.items()}
    assert before_residents == {n: list(v.items()) for n, v in cache.resident.items()}

    subtitle_path = ROOT / 'SOUND/subtitles/L1_Gcan_am/whisper_results.json'
    subs = json.loads(subtitle_path.read_text(encoding='utf-8'))
    subtitle_counts = []
    for filename, row in subs.items():
        keys = text_keys(SUB, row['translation'])
        cache.run(keys)
        subtitle_counts.append(dict(file=filename, unique_visible_glyphs=len(keys)))

    catalog_path = ROOT / 'TEXT/菜单与提示译文.json'
    entries = json.loads(catalog_path.read_text(encoding='utf-8'))['entries']
    bykey = {r['key']:e['zh'] for e in entries for r in e['references']
             if r['file'] == 'Misc/Menu/Menu_Am.asr'}
    binding_path = ROOT / 'TEMP/analysis/large_font/menu_font_bindings.json'
    bindings = json.loads(binding_path.read_text(encoding='utf-8'))
    for name, digest in bindings['gui_sha256'].items():
        assert sha((ROOT / 'ISO_UNPACK/GUIMenu' / name).read_bytes()) == digest, 'Stale GUI bindings'
    screens = defaultdict(set)
    unresolved = []
    for row in bindings['bindings']:
        text = bykey.get('HTXT:' + str(row['menu_index']), row.get('en'))
        if text is None:
            unresolved.append(row)
        else:
            screens[(row['gui'], row['screen'])].update(text_keys(row['font'] + '.asr', text))
    screen_counts = []
    for (gui, screen), keys in screens.items():
        missing = sorted(keys - glyphs.records.keys())
        counts = Counter(lane(k) for k in keys)
        fits = all(counts[n] <= v['slots'] for n, v in LAYOUTS.items())
        if fits and not missing:
            cache.run(keys)
        screen_counts.append(dict(gui=gui, screen=screen, unique_visible_glyphs=len(keys),
                                  per_lane=dict(counts), fits_model=fits, missing=missing))

    report = dict(
        kind='offline_reference_model_only', runtime_patch_installed=False,
        inputs={str(p.relative_to(ROOT)): sha(p.read_bytes())
                for p in (source, subtitle_path, catalog_path, binding_path)},
        source_pixels='Existing ASR read only for analysis; no font rebuild or generated font bank',
        fonts=glyphs.fonts, layouts=LAYOUTS,
        total_slots=sum(v['slots'] for v in LAYOUTS.values()),
        packed_atlas_bytes=sum(len(v) for v in cache.atlases.values()),
        current_native_glyph_record_bytes=len(all_keys) * 16,
        metadata_note='Full native tables would still grow with characters; bank index and metrics need a separate bounded design',
        existing_native_io_buffers=existing_io_buffers(),
        guards=dict(pending_page_mutation_rejected=pending_guard, overflow_rejected_atomically=overflow_guard),
        statistics=dict(cache.stats),
        subtitle_scan_order='JSON order, not gameplay order or optical-disc timing',
        subtitles=sorted(subtitle_counts, key=lambda r:-r['unique_visible_glyphs']),
        screens=sorted(screen_counts, key=lambda r:-r['unique_visible_glyphs']),
        unresolved_gui_bindings=unresolved,
        limitations=[
            'No PS2 code, DMA fence, texture invalidation, file-bank reader or optical-disc timing implemented',
            'Sharing the large-font palette/atlas is validated for offline pixels, not in-game rendering',
            'GUI screen unions are static resource groups, not a measured simultaneous display set',
            'Dynamic HUD, overhead labels, user strings and combined overlays are not bounded by this audit',
            '48 tiny-font slots are a trial split, not a proven runtime capacity',
            'Pixel buffers exclude bank index, metrics, I/O staging, DMA packets, font objects and patch code',
        ],
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Keep selected raw static evidence alongside the reproducible offline report.
    addresses = {
        '00208568', '002064f8', '00255558', '00255e68', '00251c40', '003d19c0',
        '00258138', '00257ef0', '00259618', '00253060', '002542b0', '00254bb0',
        '00254a50', '00254a70', '00253670', '002536e0', '00253998', '00436ef8',
        '00437028', '00243d98', '001a3a68', '0026a030', '00269b00', '002681d8',
        '00437000', '00269d18', '00244970', '0026a090', '0026a188', '00257ca8',
    }
    evidence = {}
    log = ROOT / 'SOUND/research/subtitle_test_20261004/ghidra_reads.jsonl'
    for line in log.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        address = row['params'].get('address', '').lower().removeprefix('0x')
        if address in addresses:
            evidence[(row['endpoint'], address)] = row
    (OUT / 'ghidra_evidence.json').write_text(
        json.dumps(list(evidence.values()), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('kind', 'total_slots', 'packed_atlas_bytes', 'guards', 'statistics')},
                     ensure_ascii=False, indent=2))
    print('Largest subtitle:', report['subtitles'][0])
    print('Largest static screen:', report['screens'][0])
    print('Unresolved GUI bindings:', len(unresolved))


if __name__ == '__main__':
    main()
