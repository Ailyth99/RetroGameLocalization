"""Read back the fixed test ISO and verify installed dynamic-font/text resources.

Uses ISO9660 directory records directly; does not create or consume an LBA table.
"""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'SOUND/research/dynamic_font_cache/installed_build.json'


def sha(data):return hashlib.sha256(data).hexdigest()


class ISO:
    def __init__(self,path):
        self.fp=path.open('rb')
        self.fp.seek(16*2048);pvd=self.fp.read(2048)
        assert pvd[:7]==b'\x01CD001\x01'
        self.root=pvd[156:190]
    def read_record(self,record):
        sector=struct.unpack_from('<I',record,2)[0];length=struct.unpack_from('<I',record,10)[0]
        self.fp.seek(sector*2048);data=self.fp.read(length)
        assert len(data)==length
        return data
    def directory(self,record):
        data=self.read_record(record);p=0;result={}
        while p<len(data):
            length=data[p]
            if not length:p=(p//2048+1)*2048;continue
            row=data[p:p+length];name=row[33:33+row[32]]
            if name not in (b'\0',b'\1'):result[name.decode('ascii')]=row
            p+=length
        return result
    def read(self,path):
        components=path.replace('\\','/').upper().split('/');record=self.root
        for i,name in enumerate(components):
            directory=self.directory(record)
            record=directory[name+(';1' if i==len(components)-1 else '')]
        return self.read_record(record)
    def count(self):
        todo=[self.root];files=0;directories=0
        while todo:
            record=todo.pop();directories+=1
            for item in self.directory(record).values():
                if item[25]&2:todo.append(item)
                else:files+=1
        return files,directories


def main():
    state=json.loads(STATE.read_text(encoding='utf-8'));assert state['installed']
    iso=ISO(ROOT/'COD5_TEST.iso')
    names=set(state['source_text_report'])|{'Fonts/ntsc_fon.asr','Fonts/ZHGLYPH.BIN','slus_217.46','Envs/sp/L1_Gcan.am'}
    names.update(state.get('subtitle_am_sha256', {}))
    names.update(state.get('profile_sha256', {}))
    checked={}
    try:
        for name in sorted(names):
            disk=(ROOT/'ISO_UNPACK'/name).read_bytes();packed=iso.read(name)
            assert packed==disk,('ISO mismatch',name)
            checked[name]=sha(packed)
            if name == 'slus_217.46' and 'subtitle_style' in state:
                for patch in state['subtitle_style']['patches']:
                    va = int(patch['address'], 16)
                    instruction = struct.unpack_from('<I', packed, va - 0x100000 + 0x80)[0]
                    assert instruction == int(patch['after'], 16), ('Subtitle style mismatch', hex(va))
            if name == 'slus_217.46' and 'hardware_diagnostic' in state:
                hardware = state['hardware_diagnostic']
                offset = int(hardware['state_address'], 16) - 0x100000 + 0x80
                words = struct.unpack_from('<6I', packed, offset)
                assert words == (0x4857465a, 1, int(hardware['enabled']), 0, 0, 0), \
                    ('Hardware diagnostic mode differs from the installed build', words)
            if name == 'slus_217.46' and 'hardware_sync' in state:
                sync = state['hardware_sync']
                offset = int(sync['state_address'], 16) - 0x100000 + 0x80
                words = struct.unpack_from('<4I', packed, offset)
                assert words == (0x5357465a, 1, int(sync['enabled']), 0), \
                    ('Hardware sync mode differs from the installed build', words)
            if name == 'slus_217.46' and 'hardware_texture' in state:
                texture = state['hardware_texture']
                offset = int(texture['state_address'], 16) - 0x100000 + 0x80
                words = struct.unpack_from('<5I', packed, offset)
                assert words == (0x5457465a, 1, int(texture['enabled']), 0, 0), \
                    ('Hardware texture mode differs from the installed build', words)
            if name == 'slus_217.46' and 'hardware_frame' in state:
                frame = state['hardware_frame']
                offset = int(frame['state_address'], 16) - 0x100000 + 0x80
                words = struct.unpack_from('<7I', packed, offset)
                assert words == (0x4257465a, 1, int(frame['enabled']), 0, 0, 0, 0), \
                    ('Hardware frame mode differs from the installed build', words)
                for va, original, hook in ((0x259650, 0x424fd8, 'zh_frame_vsync_guard'),
                                           (0x259658, 0x2596f0, 'zh_frame_blend_guard')):
                    target = int(state['symbols'][hook],16) if frame['enabled'] else original
                    instruction = struct.unpack_from('<I',packed,va-0x100000+0x80)[0]
                    assert instruction == 0x0c000000 | (target >> 2), ('Frame hook mismatch',hex(va))
        files,directories=iso.count()
    finally:iso.fp.close()
    assert files==sum(p.is_file() for p in (ROOT/'ISO_UNPACK').rglob('*'))
    assert files<=640 and directories<=256,'Native directory scanner capacity exceeded'
    assert checked['Fonts/ntsc_fon.asr']==state['font_sha256']
    assert checked['Fonts/ZHGLYPH.BIN']==state['bank_sha256']
    assert checked['slus_217.46']==state['elf_sha256']
    for name, expected in state.get('subtitle_am_sha256', {}).items():
        assert checked[name] == expected, ('Subtitle AM differs from build', name)
    for name, expected in state.get('profile_sha256', {}).items():
        assert checked[name] == expected, ('Resident profile differs from build', name)
    digest=hashlib.sha256()
    with (ROOT/'COD5_TEST.iso').open('rb') as fp:
        for data in iter(lambda:fp.read(4*1024*1024),b''):digest.update(data)
    result={'iso':'COD5_TEST.iso','bytes':(ROOT/'COD5_TEST.iso').stat().st_size,
            'sha256':digest.hexdigest(),'files':files,'directories':directories,
            'verified_resources':checked,'runtime_validation':'pending_user_test'}
    result['hardware_diagnostic'] = state.get('hardware_diagnostic', {'mode': 'normal', 'enabled': False})
    result['hardware_sync'] = state.get('hardware_sync', {'mode': 'native_dma_plus_private_gs_finish', 'enabled': False})
    result['hardware_texture'] = state.get('hardware_texture', {'mode': 'all_four_residency_slots', 'enabled': False})
    result['hardware_frame'] = state.get('hardware_frame', {'mode': 'native_frame_end_only', 'enabled': False})
    result['subtitle_style'] = state.get('subtitle_style', {})
    path=ROOT/'SOUND/research/dynamic_font_cache/iso_verification.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('iso','bytes','sha256','files','directories','hardware_diagnostic','hardware_sync','hardware_texture','hardware_frame','subtitle_style')},ensure_ascii=False))


if __name__=='__main__':main()
