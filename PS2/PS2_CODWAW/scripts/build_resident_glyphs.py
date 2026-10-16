"""Choose a bounded set of lossless compressed glyphs to preload with the ELF.

Pixels still use the fixed atlas. Unselected records retain the disk path.
This module only consumes freshly rendered records from the full build chain.
"""
from collections import Counter
import json
import struct

# Includes dynamic ASCII HUD and the GUI overlays used during each level.
# Eight-byte offset units keep a compact uint16 index beyond 256 KiB.
# Default Verdana synthetic bold needs at most 307216 bytes; reserve headroom
# for saved translation edits while still rejecting an oversized required set.
BUDGET = 320 * 1024
OFFSET_UNIT = 8
PROFILE_VERSION = 2


def record_size(bank, offset):
    return (4 + struct.unpack_from('<H', bank, offset + 2)[0] + OFFSET_UNIT - 1) & -OFFSET_UNIT


def gui_texts(root):
    """Resolve actual GUI font/text bindings through the sole translation catalog."""
    catalog = json.loads((root / 'TEXT/菜单与提示译文.json').read_text(encoding='utf-8'))
    bindings = json.loads((root / 'TEMP/analysis/large_font/menu_font_bindings.json').read_text(encoding='utf-8'))
    by_key = {r['key']:entry['zh'] for entry in catalog['entries'] for r in entry['references']
              if r['file'] == 'Misc/Menu/Menu_Am.asr'}
    result = []
    for binding in bindings['bindings']:
        value = by_key.get('HTXT:' + str(binding['menu_index']), binding['en']) or ''
        result.append((binding['gui'].split('/')[-1], binding['screen'], binding['font'], value))
    return result


def main_menu_texts(root):
    return [(screen,font,text) for gui,screen,font,text in gui_texts(root)
            if gui=='MainMenu.gui' and 'Credits' not in screen]


def level_gui_texts(root, level):
    result=[]
    for gui,screen,font,text in gui_texts(root):
        if gui in ('In_Game.gui','TRC_IG.gui') or (
            gui=='Intro.gui' and screen.lower()==level.lower()) or (
            gui=='Gameover.gui' and screen.lower() in ('go_continue_quit',level.lower()+'_go')) or (
            gui=='L1.gui' and level.lower()=='l1_gcan' and screen=='L1_Inter'):
            result.append((screen,font,text))
    return result


def build(root, definitions, names, bank, disk_offsets, subtitle_texts, subtitle_by_level=None):
    from build_menu_hints_zh import is_overhead_name, is_weapon_name
    catalog = json.loads((root / 'TEXT/菜单与提示译文.json').read_text(encoding='utf-8'))
    bindings = json.loads((root / 'TEMP/analysis/large_font/menu_font_bindings.json').read_text(encoding='utf-8'))
    headings = {'HTXT:' + str(b['menu_index']) for b in bindings['bindings']
                if b['font'] == 'Times New Roman_20_Bold'}
    subtitle_frequency = Counter(''.join(subtitle_texts))
    frequency = [Counter(), Counter(), Counter()]
    overhead = Counter()
    weapons = Counter()
    menu = {(font, ord(c)) for _,font,text in main_menu_texts(root) for c in text}
    for entry in catalog['entries']:
        refs = entry['references']
        if any(is_overhead_name(r) for r in refs):
            overhead.update(entry['zh'])
        if any(is_weapon_name(r) for r in refs):
            weapons.update(entry['zh'])
        if any(is_overhead_name(r) or is_weapon_name(r) or
               (r['file'] == 'Misc/Menu/Menu_Am.asr' and r['key'] in headings) for r in refs):
            frequency[0].update(entry['zh'])
        if any(not is_overhead_name(r) for r in refs):
            frequency[1].update(entry['zh'])
            frequency[2].update(entry['zh'])
    keys = [(i, r[3]) for i, name in enumerate(names)
            for r in definitions[name]['pages'][0]['records']]
    overhead_required = {i for i,(f,c) in enumerate(keys) if f == 0 and chr(c) in overhead}
    weapon_required = {i for i,(f,c) in enumerate(keys) if f == 0 and chr(c) in weapons}
    menu_required = {i for i,(f,c) in enumerate(keys) if (names[f].removesuffix('.asr'),c) in menu}
    ascii_required = {i for i,(f,c) in enumerate(keys) if 32<=c<=126}
    boot_gui={(font,ord(c)) for gui,screen,font,text in gui_texts(root)
              if gui in ('TRC.gui','pre_game.gui') for c in text}
    boot_gui_required={i for i,(f,c) in enumerate(keys) if (names[f].removesuffix('.asr'),c) in boot_gui}
    # Boot/menu profile can hold the entire small font. In a level, require
    # every common gameplay hint plus that level's objectives instead of an
    # arbitrary frequency-based 12 KiB subset.
    hud = {index for index,(font,code) in enumerate(keys) if font == 1}
    hud_bytes = sum(record_size(bank,disk_offsets[i]) for i in hud)
    fixed = overhead_required | weapon_required | menu_required | hud | ascii_required | boot_gui_required
    candidates = []
    required = set()
    for index, (font, code) in enumerate(keys):
        if font == 2 and chr(code) in subtitle_frequency:
            required.add(index)
        if (names[font].removesuffix('.asr'), code) in menu:
            priority, weight = 0, frequency[font][chr(code)]
        elif font == 0 and (overhead[chr(code)] or weapons[chr(code)]):
            priority, weight = 1, overhead[chr(code)] + weapons[chr(code)]
        elif index in hud:
            priority, weight = 2, frequency[font][chr(code)]
        elif font == 2 and chr(code) in subtitle_frequency:
            priority, weight = 5, subtitle_frequency[chr(code)]
        elif font == 2 and 32 <= code <= 126:
            priority, weight = 4, 1
        elif 32 <= code <= 126:
            priority, weight = 3, 1
        elif frequency[font][chr(code)]:
            priority, weight = 6, frequency[font][chr(code)]
        else:
            continue
        candidates.append((priority, -weight, font, code, index))
    resident = bytearray()
    offsets = list(disk_offsets)
    selected = []
    for _, _, font, code, index in sorted(candidates,key=lambda row:(row[4] not in fixed,*row)):
        disk = disk_offsets[index]
        length = 4 + struct.unpack_from('<H', bank, disk + 2)[0]
        aligned = record_size(bank,disk)
        if len(resident) + aligned > BUDGET:
            continue
        offset = len(resident)
        resident.extend(bank[disk:disk + length])
        resident.extend(b'\0' * (aligned - length))
        offsets[index] = 0x80000000 | offset
        selected.append(dict(index=index, font=font, code=code, disk_offset=disk,
                             resident_offset=offset, record_bytes=length))
    selected_indices = {r['index'] for r in selected}
    uncovered = [keys[i][1] for i in sorted(required - selected_indices)]
    report = dict(budget_bytes=BUDGET, payload_bytes=len(resident), glyphs=len(selected),
                  glyphs_per_font=[sum(r['font'] == i for r in selected) for i in range(3)],
                  subtitle_required_glyphs=len(required),
                  subtitle_resident_glyphs=len(required & selected_indices),
                  subtitle_disk_codes=uncovered, all_current_subtitles_resident=not uncovered,
                  overhead_required_glyphs=len(overhead_required),
                  overhead_resident_glyphs=len(overhead_required & selected_indices),
                  overhead_disk_codes=[keys[i][1] for i in sorted(overhead_required-selected_indices)],
                  weapon_required_glyphs=len(weapon_required),
                  weapon_resident_glyphs=len(weapon_required & selected_indices),
                  weapon_disk_codes=[keys[i][1] for i in sorted(weapon_required-selected_indices)],
                  main_menu_required_glyphs=len(menu_required),
                  main_menu_resident_glyphs=len(menu_required & selected_indices),
                  main_menu_disk_keys=[list(keys[i]) for i in sorted(menu_required-selected_indices)],
                  small_hud_budget_bytes=hud_bytes, small_hud_payload_bytes=hud_bytes,
                  small_hud_required_glyphs=len(hud), small_hud_resident_glyphs=len(hud & selected_indices),
                  offset_unit_bytes=OFFSET_UNIT, profile_version=PROFILE_VERSION,
                  policy='boot: main menus, save/legal screens, overhead/weapon names, entire small font; levels: subtitles, dual-font gameplay HUD, overhead/weapon names, main menus and actual level GUI overlays; all profiles require ASCII in all fonts; required sets must fit',
                  storage='fixed writable ELF buffer, replaced only at resource transitions; same 4bpp LZ4 records')
    assert resident and len(resident) <= BUDGET
    # A uint16 stores offset/8 + 1. The original disk index stays immutable, so
    # a failed/partial profile load can safely fall back without using stale data.
    def index_for(rows):
        result = [0] * len(keys)
        for r in rows:
            value = r['resident_offset'] // OFFSET_UNIT + 1
            assert 1 <= value <= 0xffff, 'Resident offset exceeds uint16 index'
            result[r['index']] = value
        return result

    def fnv(data):
        h = 2166136261
        for b in data:
            h = ((h ^ b) * 16777619) & 0xffffffff
        return h

    index_bytes = (len(keys) * 2 + 15) & ~15
    profiles, profile_reports = {}, []
    definitions_out = []

    def profile(number, trigger, data, rows, required_indices):
        required_bytes = sum(record_size(bank,disk_offsets[i]) for i in required_indices)
        index = struct.pack('<' + 'H' * len(keys), *index_for(rows)).ljust(index_bytes, b'\0')
        payload = index + data
        head = bytes(bank[:32]) + struct.pack('<8I', 0x5250485a, PROFILE_VERSION, number, len(keys), index_bytes,
                                              len(data), len(payload), fnv(payload))
        path = f'Fonts/ZHPR{number:02d}.BIN'
        profiles[path] = head + payload
        definitions_out.append((trigger, path.replace('/', '\\\\')))
        selected_set = {r['index'] for r in rows}
        missing = sorted(required_indices - selected_set)
        assert not missing, ('Profile budget insufficient; do not silently reintroduce glyph I/O', trigger,
                             required_bytes, BUDGET, [keys[i] for i in missing])
        profile_reports.append(dict(id=number, trigger=trigger, file=path, payload_bytes=len(data),
                                    glyphs=len(rows), glyphs_per_font=[sum(r['font'] == f for r in rows) for f in range(3)],
                                    required_glyphs=len(required_indices), required_bytes=required_bytes,
                                    weapon_required_glyphs=len(weapon_required), missing_required=[],
                                    sha256=__import__('hashlib').sha256(profiles[path]).hexdigest()))

    profile(0, 'MainMenu.gui', resident, selected, fixed)
    for number, (level, texts) in enumerate((subtitle_by_level or {}).items(), 1):
        level_frequency = Counter(''.join(texts))
        hud_codes = {c for entry in catalog['entries'] if any(
            (ref['file'] == 'Text/american.asr' and not is_overhead_name(ref)) or
            ref['file'].lower() == ('Envs/sp/' + level + '.ps2').lower() for ref in entry['references'])
            for c in entry['zh']}
        level_hud = {i for i,(f,c) in enumerate(keys) if f == 1 and (chr(c) in hud_codes or 32 <= c <= 126)}
        # FUN_003D1ED8 and FUN_003D2628 switch to Verdana_20 for objectives
        # and scrolling gameplay hints; live L5 captured these disk misses.
        level_hud_large = {i for i,(f,c) in enumerate(keys) if f == 2 and (chr(c) in hud_codes or 32 <= c <= 126)}
        gui_keys={(font,ord(c)) for _,font,text in level_gui_texts(root,level) for c in text}
        level_gui={i for i,(f,c) in enumerate(keys) if (names[f].removesuffix('.asr'),c) in gui_keys}
        level_required = overhead_required | weapon_required | menu_required | ascii_required | level_gui | level_hud | level_hud_large | {
            i for i, (f, c) in enumerate(keys) if f == 2 and chr(c) in level_frequency}
        level_data = bytearray()
        level_rows = []
        for _, _, font, code, index in sorted(candidates, key=lambda row:(row[4] not in level_required, *row)):
            disk = disk_offsets[index]
            length = 4 + struct.unpack_from('<H', bank, disk + 2)[0]
            aligned = record_size(bank,disk)
            if len(level_data) + aligned > BUDGET:
                continue
            offset = len(level_data)
            level_data.extend(bank[disk:disk + length]); level_data.extend(b'\0' * (aligned-length))
            level_rows.append(dict(index=index, font=font, code=code, disk_offset=disk,
                                   resident_offset=offset, record_bytes=length))
        profile(number, level, level_data, level_rows, level_required)
        profile_reports[-1]['hud_required_glyphs'] = len(level_hud)
        profile_reports[-1]['hud_large_required_glyphs'] = len(level_hud_large)
        profile_reports[-1]['level_gui_required_glyphs'] = len(level_gui)
        profile_reports[-1]['ascii_required_glyphs'] = len(ascii_required)

    # Keep exactly one bounded compressed buffer shared by all profiles.
    resident.extend(b'\0' * (BUDGET - len(resident)))
    header = 'static u8 resident_data[] = {\n' + ',\n'.join(
        ','.join(map(str, resident[i:i + 32])) for i in range(0, len(resident), 32)) + '\n};\n'
    header += 'static u16 resident_index[] = {' + ','.join(map(str, index_for(selected))) + '};\n'
    header += '#define PROFILE_INDEX_BYTES ' + str(index_bytes) + '\n'
    header += '#define RESIDENT_OFFSET_UNIT ' + str(OFFSET_UNIT) + '\n'
    header += '#define PROFILE_VERSION ' + str(PROFILE_VERSION) + '\n'
    header += 'static const struct { const char *trigger, *path; } resident_profiles[] = {\n'
    header += ',\n'.join('{"' + trigger + '","' + path + '"}' for trigger,path in definitions_out) + '\n};\n'
    report['profiles'] = profile_reports
    report['per_level_required_all_resident'] = True
    return disk_offsets, header, report, dict(disk_offsets=disk_offsets, selected=selected), profiles
