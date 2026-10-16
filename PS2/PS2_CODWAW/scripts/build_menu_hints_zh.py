"""Build/install unified menu and hint translations. Never changes AM or ELF.

python -X utf8 scripts/build_menu_hints_zh.py --install
"""
import argparse
import json
from pathlib import Path
from collections import defaultdict
from game_text_resources import ROOT, OriginalResources, locate_text
from unified_text_catalog import CATALOG, in_scope
from unified_fonts import build as build_fonts
from sound.system_text_rules import is_staffroll_reference, preserved_english_reason
import build_start_menu_zh as s

OUT=ROOT/'TEMP/builds/menu_hints_zh'
BACKUP=ROOT/'SOURCE/backups/menu_hints_zh'
REPORT=OUT/'build_report.json'


def is_overhead_name(ref):
    return (ref['file']=='Text/american.asr' and ref['key'].startswith('LTXT:')
            and 75<=int(ref['key'].split(':')[1])<=207)


def is_weapon_name(ref):
    if ref['file']!='Text/american.asr' or not ref['key'].startswith('LTXT:'):
        return False
    index=int(ref['key'].split(':')[1])
    return 8<=index<=43 or 63<=index<=67 or index==208


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--subtitle-am',type=Path,action='append',
                        help='Subtitle AM for glyph collection; repeat for multiple levels')
    args=parser.parse_args()
    catalog=json.loads(CATALOG.read_text(encoding='utf-8'))
    byfile=defaultdict(dict); seen=set()
    for entry in catalog['entries']:
        s.require(entry['id'] not in seen,'Duplicate catalog ID');seen.add(entry['id'])
        if any(is_staffroll_reference(ref) for ref in entry['references']):
            s.require(entry['zh'] == entry['en'], f"{entry['id']}：{preserved_english_reason(entry)}")
        s.require(isinstance(entry['zh'],str) and entry['zh'] and '\0' not in entry['zh'],f"Invalid translation {entry['id']}")
        for ref in entry['references']:
            s.require(in_scope(ref['file']),'Out-of-scope resource')
            s.require(ref['key'] not in byfile[ref['file']],'Duplicate target reference')
            byfile[ref['file']][ref['key']]=entry
    OUT.mkdir(parents=True,exist_ok=True)
    outputs={};previous={};counts={}
    old_report=json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else None
    with OriginalResources() as original:
        original_font_sha = s.sha256(original.read(s.FONT_PATH.as_posix()))
        for path,entries in byfile.items():
            source=original.read(path); data=bytearray(source); records=locate_text(source)
            found=set()
            for record in records:
                if record['key'] not in entries: continue
                item=entries[record['key']];found.add(record['key'])
                s.require(item['en']==record['text'],f"Original mismatch {item['id']}")
                raw=item['zh'].encode('utf-16-le')+b'\0\0'
                s.require(len(raw)<=record['capacity'],
                          f"{item['id']} exceeds {record['capacity']//2-1} UTF16 units in {path}; shorten zh")
                data[record['offset']:record['offset']+record['capacity']]=raw.ljust(record['capacity'],b'\0')
            s.require(found==set(entries),'Missing target record')
            for before,after in zip(records,locate_text(data)):
                expected=entries[before['key']]['zh'] if before['key'] in entries else before['text']
                s.require(after['text']==expected and all(before[k]==after[k] for k in before if k!='text'),'Resource readback mismatch')
            current=(ROOT/'ISO_UNPACK'/path).read_bytes();previous[path]=current
            # First migration preserves current edits only when they equal original or planned text.
            if not (BACKUP/path).exists():
                current_records=locate_text(current)
                s.require(len(current)==len(source) and len(current_records)==len(records),'Unexpected installed layout')
                for old,now,new in zip(records,current_records,locate_text(data)):
                    s.require(now['text'] in (old['text'],new['text']),f'Unmerged installed text in {path}')
                check=bytearray(current)
                for record in records:
                    start=record['offset'];end=start+record['capacity'];check[start:end]=source[start:end]
                s.require(check==source,'Unrelated binary edits in text resource')
            else:
                allowed=[s.sha256(source),s.sha256((BACKUP/path).read_bytes()),s.sha256(data)]
                if old_report:allowed.append(old_report['files'].get(path,{}).get('after'))
                s.require(s.sha256(current) in allowed,'Target contains newer external changes')
            outputs[path]=bytes(data);counts[path]=len(entries)
    font_path=s.FONT_PATH.as_posix()
    current=(s.TARGET/s.FONT_PATH).read_bytes();previous[font_path]=current
    baseline=(BACKUP/font_path).read_bytes() if (BACKUP/font_path).exists() else current
    # Dynamic overhead/weapon labels are not listed in the GUI bindings.
    bindings=json.loads((ROOT/'TEMP/analysis/large_font/menu_font_bindings.json').read_text(encoding='utf-8'))
    for path,digest in bindings['gui_sha256'].items():
        s.require(s.sha256((s.TARGET/'GUIMenu'/path).read_bytes())==digest,'GUI changed; regenerate font bindings')
    heading_keys={'HTXT:'+str(b['menu_index']) for b in bindings['bindings']
                  if b['font']=='Times New Roman_20_Bold'}
    name_entries=[e for e in catalog['entries'] if any(is_overhead_name(r) for r in e['references'])]
    weapon_entries=[e for e in catalog['entries'] if any(is_weapon_name(r) for r in e['references'])]
    heading_texts=[e['zh'] for e in catalog['entries'] if any(
        is_overhead_name(r) or is_weapon_name(r) or
        (r['file']=='Misc/Menu/Menu_Am.asr' and r['key'] in heading_keys)
        for r in e['references'])]
    small_texts=[e['zh'] for e in catalog['entries'] if any(
        not is_overhead_name(r) for r in e['references'])]
    # Include the installed subtitles, or a staged replacement supplied by the AM builder.
    # Subtitle-only glyphs belong solely to Verdana_20, not the HUD or heading font.
    subtitle_paths=args.subtitle_am or [ROOT/'ISO_UNPACK/Envs/sp/L1_Gcan.am']
    subtitle_texts=[]; subtitle_hashes={}
    for subtitle_path in subtitle_paths:
        subtitle_data=subtitle_path.read_bytes()
        subtitle_hashes[str(subtitle_path)]=s.sha256(subtitle_data)
        subtitle_texts.extend(r['text'] for r in locate_text(subtitle_data) if r['kind']=='DLLN')
    font,font_report=build_fonts(baseline,small_texts,heading_texts,subtitle_texts)
    if (BACKUP/font_path).exists():
        allowed=[original_font_sha,s.sha256(baseline),s.sha256(font)]
        if old_report:allowed.append(old_report['files'][font_path]['after'])
        # A dynamic build replaces the freshly rendered atlas with fixed caches.
        # Recognize only the exact last installed dynamic resource before redraw.
        dynamic_state=ROOT/'SOUND/research/dynamic_font_cache/installed_build.json'
        if dynamic_state.exists():
            state=json.loads(dynamic_state.read_text(encoding='utf-8'))
            if state.get('installed'):allowed.append(state['font_sha256'])
        s.require(s.sha256(current) in allowed,'Unexpected current font changes')
    outputs[font_path]=font
    report={'catalog':str(CATALOG.relative_to(ROOT)), 'entries':len(catalog['entries']),
            'staffroll_english_entries': [e['id'] for e in catalog['entries']
                if any(is_staffroll_reference(r) for r in e['references'])],
            'weapon_names':{'unique_entries':len(weapon_entries),
                'font':'Times New Roman_20_Bold', 'also_kept_in_small_fonts':True,
                'characters':''.join(sorted(set(''.join(e['zh'] for e in weapon_entries))))},
            'overhead_names':{'unique_entries':len(name_entries),
                'references':sum(sum(is_overhead_name(r) for r in e['references']) for e in name_entries),
                'font':'Times New Roman_20_Bold',
                'name_only_characters_excluded_from_small_fonts':''.join(sorted(
                    set(''.join(e['zh'] for e in name_entries))-set(''.join(small_texts))))},
            'references':sum(counts.values()),'resources':counts,'fonts':font_report,
            'subtitle_glyph_source':str(subtitle_paths[0]),
            'subtitle_am_sha256':subtitle_hashes[str(subtitle_paths[0])],
            'subtitle_glyph_sources':[str(p) for p in subtitle_paths],
            'subtitle_am_sha256s':subtitle_hashes,
            'am_modified':False,'elf_modified':False,'runtime_validation':'pending_user_test',
            'files':{p:{'before':s.sha256(previous[p]),'after':s.sha256(d)} for p,d in outputs.items()},
            'installed':False}
    for p,d in outputs.items():
        target=OUT/'rebuilt'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(d)
    if args.install:
        for p in outputs:
            s.require((s.TARGET/p).read_bytes()==previous[p],'Target changed during build')
            backup=BACKUP/p;backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists():backup.write_bytes(previous[p])
        try:
            for p,d in outputs.items():
                (s.TARGET/p).write_bytes(d)
                s.require((s.TARGET/p).read_bytes()==d,'Install readback mismatch')
        except Exception:
            for p,d in previous.items():(s.TARGET/p).write_bytes(d)
            raise
        report['installed']=True
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    name_lines=['头顶军衔及姓名位置（生成报告，请在菜单与提示译文.json修改zh）',
                '字体：Times New Roman_20_Bold；Text/american.asr LTXT:75–207', '']
    for entry in name_entries:
        refs=', '.join(r['key'] for r in entry['references'] if is_overhead_name(r))
        name_lines.append(f"{entry['id']} | {refs} | {entry['en']} | {entry['zh']}")
    (ROOT/'TEXT/头顶人名位置清单.txt').write_text('\n'.join(name_lines)+'\n',encoding='utf-8-sig')
    print(json.dumps({k:report[k] for k in ('entries','references','resources','fonts','installed')},ensure_ascii=False))


if __name__=='__main__': main()
