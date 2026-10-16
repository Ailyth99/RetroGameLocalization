"""Read-only comparison of the user's original/success and Chinese/black-screen EE dumps.

The allocator is the dlmalloc variant at 0x243118, state 0x4e8748.
Chunk sizes include allocator overhead; these are not texture file sizes.
"""
import bisect
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'SOUND/research/l1_ram_comparison'
STATE = 0x4e8748
HEAP_START = 0x59b008
HEAP_END = 0x1ff8000


def u32(data, address):
    return struct.unpack_from('<I', data, address)[0]


def all_matches(data, needle):
    result = []
    pos = data.find(needle)
    while pos >= 0:
        result.append(pos)
        pos = data.find(needle, pos + 1)
    return result


def heap(data):
    top = u32(data, STATE + 0x30)
    fast = set()
    fast_lists = []
    for off in range(4, 0x30, 4):
        p = u32(data, STATE + off)
        chain = []
        while p:
            assert HEAP_START <= p < top and p not in fast, ('fastbin', hex(p))
            fast.add(p)
            chain.append(p)
            p = u32(data, p + 8)
        if chain:
            fast_lists.append({'state_offset': off, 'chunks': chain})
    result = []
    anomalies = []
    bins = []
    bin_addresses = set()
    for index in range(1, 96):
        head = STATE + 0x30 + index * 8
        p = u32(data, head + 8)
        previous = head
        while p != head:
            assert HEAP_START <= p < top and p not in bin_addresses, ('bin', index, hex(p))
            bin_addresses.add(p)
            size = u32(data, p + 4) & ~3
            assert 16 <= size <= HEAP_END - p
            assert u32(data, p + 12) == previous, ('bin backlink', hex(p))
            assert u32(data, p + size) == size and not (u32(data, p + size + 4) & 1), ('bin footer', hex(p))
            bins.append({'address': p, 'size': size, 'bin': index})
            previous, p = p, u32(data, p + 8)
        assert u32(data, head + 12) == previous, ('bin tail', index)
    p = HEAP_START
    while p < HEAP_END:
        raw = u32(data, p + 4)
        size = raw & ~3
        if size < 16 or p + size > HEAP_END or (p != top and size % 16):
            anomalies.append({'kind': 'invalid_chunk_header', 'address': p, 'raw_size': raw})
            break
        if p == top:
            status = 'top_free'
            assert p + size == HEAP_END
        else:
            assert size % 16 == 0, (hex(p), size)
            status = 'fast_free' if p in fast else ('allocated' if u32(data, p + size + 4) & 1 else 'free')
            if status == 'free':
                if u32(data, p + size) != size:
                    anomalies.append({'kind': 'free_footer_mismatch', 'address': p,
                                      'size': size, 'footer': u32(data, p + size)})
        result.append({'address': p, 'payload': p + 8, 'size': size, 'status': status})
        p += size
    complete = p == HEAP_END
    if complete:
        assert any(c['address'] == top for c in result)
        assert fast <= {c['address'] for c in result}
        assert bin_addresses == {c['address'] for c in result if c['status'] == 'free'}
    counts = Counter(c['status'] for c in result)
    totals = Counter()
    for c in result:
        totals[c['status']] += c['size']
    free = [dict(c, status='free') for c in bins]
    free.extend({'address': c, 'size': u32(data, c + 4) & ~3, 'status': 'fast_free'} for c in fast)
    free.append({'address': top, 'size': u32(data, top + 4) & ~3, 'status': 'top_free'})
    coalesced = []
    for c in sorted(free, key=lambda c: c['address']):
        if coalesced and coalesced[-1]['address'] + coalesced[-1]['size'] == c['address']:
            coalesced[-1]['size'] += c['size']
        else:
            coalesced.append({'address': c['address'], 'size': c['size']})
    summary = {'start': HEAP_START, 'end': HEAP_END, 'extent': HEAP_END - HEAP_START,
               'top': top, 'physical_walk_complete': complete, 'physical_walk_stop': p,
               'counts': dict(counts), 'chunk_bytes': dict(totals),
               'free_total_chunk_bytes': sum(c['size'] for c in bins) + sum(u32(data, c + 4) & ~3 for c in fast) + (u32(data, top + 4) & ~3),
               'largest_free_chunk': max([u32(data, top + 4) & ~3] + [c['size'] for c in bins] + [u32(data, c + 4) & ~3 for c in fast]),
               'largest_free_after_fastbin_coalescing': max(c['size'] for c in coalesced),
               'largest_free_chunks': sorted(free, key=lambda c: -c['size'])[:12],
               'fastbins': fast_lists, 'regular_bins': bins, 'anomalies': anomalies}
    return result, summary


def containing(chunks, address):
    index = bisect.bisect_right([c['address'] for c in chunks], address) - 1
    if index >= 0 and address < chunks[index]['address'] + chunks[index]['size']:
        return chunks[index]
    return None


def cstring(data, address, limit=200):
    return data[address:address + limit].split(b'\0', 1)[0].decode('ascii', errors='replace')


def original_font():
    """Read ISO9660 extents directly, without changing or extracting the source ISO."""
    from game_text_resources import iso_path
    with iso_path().open('rb') as src:
        src.seek(16 * 2048)
        pvd = src.read(2048)
        assert pvd[:7] == b'\x01CD001\x01'
        record = pvd[156:190]
        for component in ('FONTS', 'NTSC_FON.ASR;1'):
            assert record[25] & 2
            src.seek(u32(record, 2) * 2048)
            directory = src.read(u32(record, 10))
            cursor = 0
            found = None
            while cursor < len(directory):
                length = directory[cursor]
                if not length:
                    cursor = (cursor // 2048 + 1) * 2048
                    continue
                entry = directory[cursor:cursor + length]
                if entry[33:33 + entry[32]].decode('ascii').upper() == component:
                    found = entry
                    break
                cursor += length
            assert found is not None, component
            record = found
        src.seek(u32(record, 2) * 2048)
        return src.read(u32(record, 10))


def executable_check(data, path):
    elf = path.read_bytes()
    assert elf[:6] == b'\x7fELF\x01\x01'
    shoff = u32(elf, 32)
    shsize, shcount = struct.unpack_from('<HH', elf, 46)
    checked = 0
    differences = []
    for i in range(shcount):
        _, section_type, flags, address, offset, size = struct.unpack_from('<6I', elf, shoff + i * shsize)
        if flags & 6 != 6 or section_type == 8 or not 0x100000 <= address < len(data):
            continue
        assert address + size <= len(data) and offset + size <= len(elf)
        checked += size
        for j in range(0, size, 4):
            a, b = elf[offset + j:offset + j + 4], data[address + j:address + j + 4]
            if a != b:
                differences.append({'address': address + j, 'elf': a.hex(), 'ram': b.hex()})
    return {'elf': str(path.relative_to(ROOT)), 'elf_sha256': hashlib.sha256(elf).hexdigest(),
            'checked_executable_bytes': checked, 'word_differences': differences}


def font_details(data, chunks, disk):
    from unified_fonts import parse_pages
    from game_text_resources import chunks as resource_chunks
    definitions = parse_pages(disk)
    resources = {}
    for tag, p, size in resource_chunks(disk):
        if tag == b'RSCF':
            name = cstring(disk, p + 28).replace('\\', '/').split('/')[-1].lower()
            resources[name] = disk[p:p + size]
    fonts = []
    owned = {}

    def account(address, kind):
        c = containing(chunks, address)
        assert c and c['status'] == 'allocated', ('font allocation', hex(address), c)
        if c['address'] in owned:
            assert owned[c['address']]['kind'] == kind
        owned[c['address']] = dict(c, kind=kind)
        return c

    for f in struct.unpack_from('<4I', data, 0x5841e0):
        if not f:
            continue
        name = cstring(data, f + 12).split('\\')[-1] + '.asr'
        pages = u32(data, f + 8)
        base = u32(data, f + 4)
        account(f, 'font_objects')
        account(base, 'page_tables')
        assert pages == len(definitions[name]['pages'])
        font = {'name': name, 'address': f, 'pages': []}
        for i in range(pages):
            g = base + i * 124
            tid = u32(data, g + 100)
            glyph = u32(data, g + 104)
            w, h, n = struct.unpack_from('<III', data, g + 112)
            account(glyph, 'glyph_records')
            expected = definitions[name]['pages'][i]
            records = [struct.unpack_from('<fffHh', data, glyph + j * 16) for j in range(n)]
            assert (w, h) == (expected['width'], expected['height']) and records == expected['records']
            t = u32(data, 0x4e8c60 + tid * 4)
            account(t, 'texture_objects')
            tim, pic = struct.unpack_from('<II', data, t)
            allocation = account(tim, 'texture_tim2_buffers')
            assert containing(chunks, pic) == allocation
            image_bytes = u32(data, pic + 8)
            image_start = pic + struct.unpack_from('<H', data, pic + 12)[0]
            assert image_bytes == w * h // 2
            image_type = data[pic + 19]
            clut_colors = struct.unpack_from('<H', data, pic + 14)[0]
            clut_bytes = u32(data, pic + 4)
            # The game's original IDTEX4 files store a 32-entry/128-byte CLUT.
            # Pixel indices still use four bits; CLUT storage is not pixel depth.
            assert image_type == 4 and clut_colors == 32 and clut_bytes == 128
            assert image_start + image_bytes <= allocation['address'] + allocation['size']
            texture = cstring(data, g)
            res = resources[texture.split('\\')[-1].lower().replace('.tga', '.tm2')]
            disk_pic = res.index(b'TIM2') + 128
            assert res[disk_pic + 19] == image_type
            assert struct.unpack_from('<H', res, disk_pic + 14)[0] == clut_colors
            disk_start = disk_pic + struct.unpack_from('<H', res, disk_pic + 12)[0]
            matches = data[image_start:image_start + image_bytes] == res[disk_start:disk_start + image_bytes]
            packets = []
            for p in struct.unpack_from('<12I', data, t + 8):
                if p:
                    packets.append(account(p, 'texture_dma_packets'))
            font['pages'].append({'texture': texture, 'texture_id': tid, 'texture_object': t,
                                  'tim2': tim, 'image_address': image_start, 'image_bytes': image_bytes,
                                  'width': w, 'height': h, 'bits_per_pixel': image_bytes * 8 // (w * h),
                                  'tim2_image_type': image_type, 'clut_colors': clut_colors,
                                  'clut_bytes': clut_bytes,
                                  'image_matches_disk': matches, 'glyphs': n, 'glyph_records': glyph,
                                  'glyph_records_match_disk': True, 'dma_packets': packets})
        fonts.append(font)
    totals = Counter()
    for c in owned.values():
        totals[c['kind']] += c['size']
    return {'fonts': fonts, 'owned_allocations': list(owned.values()), 'allocation_bytes': dict(totals),
            'total_traced_chunk_bytes': sum(totals.values()),
            'image_bytes': sum(p['image_bytes'] for f in fonts for p in f['pages'])}


def texture_registry(data, chunks):
    tree = u32(data, 0x583a88)
    todo = [u32(data, tree)]
    seen = set()
    rows = []
    while todo:
        p = todo.pop()
        if not p:
            continue
        assert p not in seen
        seen.add(p)
        key, tid, _, name = struct.unpack_from('<4I', data, p)
        assert tid < 250
        obj = u32(data, 0x4e8c60 + 4 * tid)
        tim = u32(data, obj) if obj else 0
        rows.append({'node': p, 'id': tid, 'key': key, 'name': cstring(data, name),
                     'object': obj, 'tim2': tim, 'group': u32(data, 0x5835a0 + tid * 4),
                     'tim2_allocation': containing(chunks, tim) if tim else None})
        todo.extend(struct.unpack_from('<2I', data, p + 24))
    assert len(rows) == u32(data, tree + 4) == u32(data, 0x583a84)
    return sorted(rows, key=lambda r: r['id'])


def spatial_tree(data):
    base, leaves, count, depth = struct.unpack_from('<4I', data, 0x4df130)
    assert count == 2 * leaves - 1
    invalid = []
    leaf_count = 0
    for i in range(count):
        child, obj = struct.unpack_from('<II', data, base + i * 32 + 24)
        if obj:
            leaf_count += 1
        elif child + 1 >= count:
            invalid.append({'node': i, 'first_child': child, 'second_child': child + 1,
                            'first_child_address': base + child * 32,
                            'second_child_address': base + (child + 1) * 32})
    return {'global': 0x4df130, 'nodes': base, 'object_count': leaves, 'node_capacity': count,
            'recorded_depth': depth, 'expected_node_data_bytes': count * 32,
            'allocation_header': base - 8, 'allocation_size': u32(data, base - 4) & ~3,
            'non_null_leaf_nodes': leaf_count, 'invalid_children': invalid,
            'builder_node_request': count * 32, 'builder_temporary_request': count * 40,
            'builder_index_request': leaves * 4}


def character_scope():
    from build_menu_hints_zh import CATALOG, is_overhead_name
    entries = json.loads(CATALOG.read_text(encoding='utf-8'))['entries']
    shared = {'Misc/Menu/Menu_Am.asr', 'Text/american.asr', 'Envs/sp/L1_Gcan.ps2'}
    small = [e['zh'] for e in entries if any(not is_overhead_name(r) for r in e['references'])]
    partial = [e['zh'] for e in entries if any(r['file'] in shared and not is_overhead_name(r) for r in e['references'])]
    spec = ROOT / 'SOUND/subtitles/L1_Gcan_am/whisper_results.json'
    subtitles = [v['translation'] for v in json.loads(spec.read_text(encoding='utf-8')).values()]

    def codes(texts):
        return {ord(c) for text in texts for c in text if c not in '\n\r\t' and not 0xe000 <= ord(c) <= 0xf8ff}

    return {'catalog_sha256': hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
            'subtitle_spec_sha256': hashlib.sha256(spec.read_bytes()).hexdigest(),
            'small_all': len(codes(small)), 'small_l1_plus_shared': len(codes(partial)),
            'subtitle': len(codes(subtitles)), 'combined_all': len(codes(small + subtitles)),
            'combined_l1_plus_shared': len(codes(partial + subtitles))}


def inspect(label, path):
    data = path.read_bytes()
    assert len(data) == 0x2000000
    chunks, summary = heap(data)
    report = {'label': label, 'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(data).hexdigest(),
              'heap': summary, 'globals': {hex(a): hex(u32(data, a)) for a in
                  (0x4813f4, 0x4e4518, 0x4e4530, 0x480e78, 0x575710, 0x583a84, 0x583a88, 0x583a8c)},
              'font_strings': {}}
    for needle in (b'Times New Roman_20_Bold', b'Verdana_10', b'Verdana_20', b'ntsc_fon', b'L1_Gcan'):
        report['font_strings'][needle.decode()] = [
            {'address': a, 'chunk': containing(chunks, a)} for a in all_matches(data, needle)]
    report['large_allocations'] = sorted((c for c in chunks if c['status'] == 'allocated'), key=lambda c: -c['size'])[:30]
    disk = original_font() if label == 'original_success' else (ROOT / 'ISO_UNPACK/Fonts/ntsc_fon.asr').read_bytes()
    report['font_file_sha256'] = hashlib.sha256(disk).hexdigest()
    report['fonts'] = font_details(data, chunks, disk)
    report['textures'] = texture_registry(data, chunks)
    report['spatial_tree'] = spatial_tree(data)
    report['code_against_original'] = executable_check(data, ROOT / 'slus_217.46')
    expected_elf = ROOT / ('slus_217.46' if label == 'original_success' else 'ISO_UNPACK/slus_217.46')
    report['code_against_matching_elf'] = executable_check(data, expected_elf)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (label + '_chunks.json')).write_text(json.dumps(chunks, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    reports = [inspect('original_success', ROOT / 'scratch/成功载入.bin'),
               inspect('chinese_black', ROOT / 'scratch/黑屏.bin')]
    (OUT / 'comparison.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (OUT / 'character_scope.json').write_text(json.dumps(character_scope(), indent=2) + '\n', encoding='utf-8')
    log = ROOT / 'SOUND/research/subtitle_test_20261004/ghidra_reads.jsonl'
    if log.exists():
        wanted = {'0x00243118', '0x00242d18', '0x002420c8', '0x002420e8', '0x00242168',
                  '0x00243758', '0x00243610', '0x004434c8', '0x002321d0', '0x0012dea8',
                  '0x00208230', '0x00208568', '0x002064f8', '0x00254070', '0x00253f18',
                  '0x002531b8', '0x00254160', '0x00449df8', '0x00449db0', '0x0044af48',
                  '0x0044ac18', '0x0016a150', '0x0016a210'}
        latest = {}
        for line in log.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row['endpoint'] == 'decompile_function' and row['params']['address'] in wanted:
                latest[row['params']['address']] = row
        (OUT / 'ghidra_evidence.json').write_text(json.dumps(latest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for r in reports:
        print(r['label'], json.dumps({k: v for k, v in r['heap'].items() if k not in ('fastbins', 'regular_bins', 'largest_free_chunks')}, ensure_ascii=False))
        print('globals', r['globals'])
        print('font allocations', r['fonts']['allocation_bytes'], 'total', r['fonts']['total_traced_chunk_bytes'])
        print('font pixels match disk', [p['image_matches_disk'] for f in r['fonts']['fonts'] for p in f['pages']])
        print('executable word differences', len(r['code_against_matching_elf']['word_differences']))


if __name__ == '__main__':
    main()
