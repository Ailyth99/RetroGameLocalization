"""Rebuild L1 DLLN text and relocate streamed audio; preserve ELF and VAG bytes."""
import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

from game_text_resources import ROOT, chunks
import build_start_menu_zh as s

sys.path.insert(0, str(ROOT/'scripts/sound'))
from extract_am_vag import parse_container, read_name
from subtitle_entries import unbanked_key

BASE=ROOT/'SOUND/subtitles/L1_Gcan_am'
OUT=BASE/'build'
REPORT=OUT/'build_report.json'
TARGET=ROOT/'ISO_UNPACK/Envs/sp/L1_Gcan.am'
SOURCE=ROOT/'SOUND/L1_Gcan.am'
SPEC=BASE/'whisper_results.json'


def rebuild(source, translations, *, allow_unbanked_dlln=False):
    rows, layout=parse_container(source, allow_unbanked_dlln=allow_unbanked_dlln)
    by_offset={r['dlln_offset']:r for r in rows}
    expected={Path(r['file']).with_suffix('.mp3').name:r for r in rows}
    unbanked = {unbanked_key(r): r for r in layout.get('unbanked_dlln_entries', [])}
    s.require(set(translations)<=set(expected)|set(unbanked),'Unknown subtitle key / sound ID')
    desired={}
    for key,row in {**expected, **unbanked}.items():
        value=translations.get(key,{'translation':''})
        s.require(isinstance(value,dict) and isinstance(value.get('translation'),str),
                  f'Invalid translation object: {key}')
        text=value['translation']
        s.require(not any(c in text for c in '\0\n\r\t'),
                  f'Control character / timed newline in {key}; use a single subtitle segment')
        s.require(all(ord(c)<=0xFFFF for c in text),'Non-BMP subtitle character')
        if key in unbanked:
            # Missing/blank supplemental translations retain the original DLLN.
            if text.strip():
                desired[row['sound_id']] = text
                by_offset[row['dlln_offset']] = row
        else:
            desired[row['sound_id']]=text
    result=bytearray(source[:8]); relocation=None
    for tag,pos,size in chunks(source):
        block=bytearray(source[pos:pos+size])
        if tag==b'DLLN' and pos in by_offset:
            row=by_offset[pos]
            _,fields=read_name(source,pos+16,pos+size,pos)
            text=desired[row['sound_id']]
            raw=text.encode('utf-16-le')+b'\0\0' if text else b''
            # Keep the next chunk aligned; padding is included in UTF-16 units.
            raw+=b'\0'*(-len(raw)%4)
            block=block[:fields+24-pos]
            struct.pack_into('<I',block,fields+20-pos,len(raw)//2)
            block.extend(raw)
            struct.pack_into('<I',block,4,len(block))
        elif tag==b'RSCF':
            s.require(pos==layout['rscf_offset'],'Unexpected sound resource')
            relocation=len(result)-pos
            for row in rows:
                struct.pack_into('<I',block,row['table_entry_offset']-pos+16,
                                 row['vag_offset']+relocation)
        result.extend(block)
    result.extend(bytes.fromhex(layout['container_trailer_hex']))
    after,new_layout=parse_container(result, allow_unbanked_dlln=allow_unbanked_dlln)
    s.require(layout['chunk_counts']==new_layout['chunk_counts'],'Chunk counts changed')
    s.require(len(after)==len(rows),'Audio count changed')
    before_unbanked=layout.get('unbanked_dlln_entries', [])
    after_unbanked=new_layout.get('unbanked_dlln_entries', [])
    for old,new in zip(before_unbanked,after_unbanked):
        if old['sound_id'] not in desired:
            s.require(source[old['dlln_offset']:old['dlln_offset']+old['dlln_size']]==
                      result[new['dlln_offset']:new['dlln_offset']+new['dlln_size']],
                      'Untranslated supplemental DLLN changed')
        else:
            s.require(new['embedded_english'] == desired[old['sound_id']], 'Supplemental subtitle readback mismatch')
            headers = []
            for data, row in ((source, old), (result, new)):
                pos = row['dlln_offset']
                _, fields = read_name(data, pos+16, pos+row['dlln_size'], pos)
                header = bytearray(data[pos:fields+20])
                header[4:8] = b'\0'*4  # Chunk size changes; all other DLLN metadata must match.
                headers.append(header)
            s.require(headers[0] == headers[1], 'Supplemental DLLN metadata changed')
    s.require(len(before_unbanked)==len(after_unbanked),'Unbanked DLLN count changed')
    for before,current in zip(rows,after):
        for key in ('index','sound_id','sound_name','vag_sha256','payload_sha256',
                    'vag_size','sample_rate_hz','table_unknown_1','table_unknown_2',
                    'dlln_float_at_fields_plus_16'):
            s.require(before[key]==current[key],f'Audio/metadata changed: {key}')
        s.require(current['embedded_english']==desired[before['sound_id']],
                  f'Subtitle readback mismatch: {before["index"]}')
    reports=[{
        'index':r['index'],'sound_id':r['sound_id_hex'],'sound_name':r['sound_name'],
        'filename':Path(r['file']).with_suffix('.mp3').name,
        'translation':desired[r['sound_id']],
        'vag_sha256':r['vag_sha256'],
    } for r in after]
    reports.extend({
        'sound_id': r['sound_id_hex'], 'sound_name': r['sound_name'],
        'filename': unbanked_key(r), 'translation': translations[unbanked_key(r)]['translation'],
        'entry_kind': 'unbanked_dlln', 'embedded_text_after': r['embedded_english'],
        'modified': r['sound_id'] in desired,
    } for r in after_unbanked if unbanked_key(r) in translations)
    return bytes(result),reports,relocation


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install',action='store_true')
    args=parser.parse_args()
    source=SOURCE.read_bytes()
    s.require(s.sha256(source)=='462c976164bd112e30f237adbbc7d3497fb80e50afeaab242a999f1f1b9ce9fe',
              'Unexpected original L1 AM')
    raw=SPEC.read_bytes(); translations=json.loads(raw.decode('utf-8-sig'))
    am,entries,delta=rebuild(source,translations)
    previous=TARGET.read_bytes()
    # Recognize the original, the three-line prototype, and the last installed build.
    allowed={s.sha256(source),s.sha256(am)}
    prototype_spec=json.loads((BASE/'subtitle_test_zh.json').read_text(encoding='utf-8'))
    original_rows,_=parse_container(source)
    prototype_bytes=bytearray(source)
    for item in prototype_spec['entries']:
        row=original_rows[item['index']]
        s.require(row['sound_id_hex']==item['sound_id'],'Prototype sound ID mismatch')
        encoded=item['zh'].replace('\n','').encode('utf-16-le')+b'\0\0'
        size=row['embedded_text_utf16_units']*2; pos=row['embedded_text_offset']
        s.require(len(encoded)<=size,'Invalid prototype allocation')
        prototype_bytes[pos:pos+size]=encoded.ljust(size,b'\0')
    allowed.add(s.sha256(prototype_bytes))
    prototype=ROOT/'SOUND/subtitles/training_zh_test_20261004/rebuilt/Envs/sp/L1_Gcan.am'
    if prototype.exists(): allowed.add(s.sha256(prototype.read_bytes()))
    if REPORT.exists():
        last=json.loads(REPORT.read_text(encoding='utf-8'))
        if last.get('installed'): allowed.add(last['am_sha256'])
    s.require(s.sha256(previous) in allowed,'AM contains unrecognized newer changes')
    elf=ROOT/'ISO_UNPACK/slus_217.46'; elf_before=elf.read_bytes()
    s.require(struct.unpack_from('<I',elf_before,0x3D19C4-0x100000+0x80)[0]==0x24020001,
              'Native subtitle renderer is not enabled')
    OUT.mkdir(parents=True,exist_ok=True)
    staged=OUT/'L1_Gcan.am'; staged.write_bytes(am)
    command=[sys.executable,'-X','utf8',str(ROOT/'scripts/build_menu_hints_zh.py'),
             '--subtitle-am',str(staged)]
    if args.install: command.append('--install')
    subprocess.run(command,check=True)
    font_report=json.loads((ROOT/'TEMP/builds/menu_hints_zh/build_report.json').read_text(encoding='utf-8'))
    s.require(SPEC.read_bytes()==raw,'Translations changed during build')
    s.require(TARGET.read_bytes()==previous,'AM changed during build')
    s.require(elf.read_bytes()==elf_before,'ELF changed during build')
    if args.install:
        TARGET.write_bytes(am)
        s.require(TARGET.read_bytes()==am,'AM install readback mismatch')
    report={
        'translation_source':str(SPEC.relative_to(ROOT)),
        'translation_sha256':s.sha256(raw),'entries':entries,
        'translated':sum(bool(e['translation']) for e in entries),
        'blank':sum(not e['translation'] for e in entries),
        'original_bytes':len(source),'rebuilt_bytes':len(am),
        'streamed_audio_offset_delta':delta,'all_508_vag_bytes_preserved':True,
        'am_sha256':s.sha256(am),'elf_sha256_unchanged':s.sha256(elf_before),
        'fonts':font_report['fonts'],'installed':args.install,
        'runtime_validation':'pending_user_test',
    }
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('translated','blank','rebuilt_bytes',
                     'streamed_audio_offset_delta','installed')},ensure_ascii=False))


if __name__=='__main__': main()
