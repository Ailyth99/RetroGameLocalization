"""Exercise the actual C cache/decoder with native I/O/render calls mocked on host.

Also checks the emitted MIPS trampolines and allocation guards. This is not a
PCSX2/GS/optical-disc test and never controls a running emulator.
"""
import ctypes as C
import argparse
import json
from pathlib import Path
import random
import re
import struct
import subprocess

from build_dynamic_fonts import ROOT, OUT, RUNTIME, NAMES
from probe_dynamic_font_cache import ExistingGlyphs
from unified_fonts import parse_pages
from game_text_resources import chunks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk-baseline',action='store_true',help='Host-only comparison with all compressed preloads disabled')
    args=parser.parse_args()
    header=(OUT/'bank_config.h').read_text(encoding='ascii')
    manifest=json.loads((OUT/'resident_manifest.json').read_text(encoding='utf-8'))
    offsets=manifest['disk_offsets']
    runtime_offsets=[int(x) for x in re.search(r'bank_offsets\[\] = \{(.*?)\}',header,re.S)[1].replace('\n','').split(',')]
    preload_index = [int(x) for x in re.search(r'resident_index\[\] = \{(.*?)\}',header,re.S)[1].split(',')]
    offset_unit=int(re.search(r'#define RESIDENT_OFFSET_UNIT (\d+)',header)[1])
    runtime_offsets = [0x80000000 | ((idx-1)*offset_unit) if idx else off for idx,off in zip(preload_index,runtime_offsets)]
    include=OUT
    suffix='_disk_baseline' if args.disk_baseline else ''
    if args.disk_baseline:
        include=OUT/'host_disk_baseline';include.mkdir(exist_ok=True)
        runtime_offsets=offsets
        disk_header=re.sub(r'bank_offsets\[\] = \{.*?\}',
                           'bank_offsets[] = {'+','.join(map(str,offsets))+'}',header,flags=re.S)
        disk_header=re.sub(r'resident_index\[\] = \{.*?\}',
                           'resident_index[] = {'+','.join('0' for _ in offsets)+'}',disk_header,flags=re.S)
        (include/'bank_config.h').write_text(disk_header,encoding='ascii')
    subprocess.run(['C:/TDM-GCC-64/bin/gcc.exe','-shared','-O2','-DHOST_TEST',
                    '-Wno-int-to-pointer-cast','-Wno-pointer-to-int-cast','-I',str(include),
                    str(RUNTIME/'runtime.c'),str(RUNTIME/'host_bridge.c'),
                    '-Wl,--export-all-symbols','-o',str(OUT/f'runtime_host{suffix}.dll')],check=True)
    lib = C.CDLL(str(OUT/f'runtime_host{suffix}.dll'))
    lib.zh_decode.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint,C.c_uint]
    lib.zh_decode.restype=C.c_int
    lib.zh_prepare_text.argtypes=[C.c_void_p,C.c_uint,C.c_int]
    lib.zh_ensure_draw.argtypes=[C.c_void_p,C.c_uint]
    lib.zh_before_open.argtypes=[C.c_char_p]
    lib.zh_frame_vsync_guard.restype=C.c_uint
    lib.zh_frame_blend_guard.argtypes=[C.c_uint]
    lib.host_bind.argtypes=[C.c_uint,C.c_void_p]
    lib.host_set_finish.argtypes=[C.c_uint]
    lib.host_finish_status.restype=C.c_uint
    diag=(C.c_uint*32).in_dll(lib,'zh_diagnostics')
    hardware=(C.c_uint*6).in_dll(lib,'zh_hardware_diagnostic')
    configured_hardware_mode=int(re.search(r'#define ZH_HARDWARE_FREEZE_GLYPHS (\d+)',header)[1])
    assert list(hardware)==[0x4857465a,1,configured_hardware_mode,0,0,0]
    hardware_sync=(C.c_uint*4).in_dll(lib,'zh_hardware_sync')
    configured_sync_mode=int(re.search(r'#define ZH_HARDWARE_NATIVE_SYNC (\d+)',header)[1])
    assert list(hardware_sync)==[0x5357465a,1,configured_sync_mode,0]
    hardware_texture=(C.c_uint*5).in_dll(lib,'zh_hardware_texture')
    configured_texture_mode=int(re.search(r'#define ZH_HARDWARE_SELECTIVE_TEXTURES (\d+)',header)[1])
    assert list(hardware_texture)==[0x5457465a,1,configured_texture_mode,0,0]
    hardware_frame=(C.c_uint*7).in_dll(lib,'zh_hardware_frame')
    configured_frame_mode=int(re.search(r'#define ZH_HARDWARE_FRAME_SAFE (\d+)',header)[1])
    assert list(hardware_frame)==[0x4257465a,1,configured_frame_mode,0,0,0,0]
    assert configured_hardware_mode+configured_sync_mode+configured_texture_mode+configured_frame_mode<=1
    finish_sentinel=0xface0000  # FINISH bit clear: private polling would time out.
    if configured_sync_mode:lib.host_set_finish(finish_sentinel)
    # Retain all existing normal-path validation, then exercise the actual
    # configured diagnostic mode below. This modifies only the host DLL state.
    hardware[2]=0
    bank=(OUT/'rebuilt/Fonts/ZHGLYPH.BIN').read_bytes()
    fresh=(ROOT/'TEMP/builds/menu_hints_zh/rebuilt/Fonts/ntsc_fon.asr').read_bytes()
    glyphs=ExistingGlyphs(fresh)
    dynamic=(OUT/'rebuilt/Fonts/ntsc_fon.asr').read_bytes()
    defs=parse_pages(dynamic)
    keys=[(name,r[3]) for name in NAMES for r in defs[name]['pages'][0]['records']]
    assert len(keys)==len(offsets)
    resident=bytes(map(int,re.search(r'resident_data\[\] = \{(.*?)\}',header,re.S)[1].replace('\n','').split(',')))
    for row in manifest['selected']:
        d,r,n=row['disk_offset'],row['resident_offset'],row['record_bytes']
        assert resident[r:r+n]==bank[d:d+n],row
    decode_buffer=C.create_string_buffer(512)
    expected_tiles={}
    for key,offset in zip(keys,offsets):
        mode,length=struct.unpack_from('<HH',bank,offset)
        src=C.create_string_buffer(bank[offset+4:offset+4+length])
        small=key[0]==NAMES[1]; stride=16 if small else 32; size=128 if small else 512
        assert lib.zh_decode(src,length,decode_buffer,size,mode)==1
        tile=decode_buffer.raw[:size]
        w,h=glyphs.records[key][4:6]
        pixels=bytes((tile[(yy*stride+xx)//2]>>(((yy*stride+xx)&1)*4))&15 for yy in range(h) for xx in range(w))
        assert pixels==glyphs.tile(key),key
        expected_tiles[key]=pixels
    # Malformed offsets, truncation and an output overrun must fail cleanly.
    for payload,capacity in [(b'\x00\x00\x00',16),(b'\xf0',512),(b'\x10A\x01\x00',2)]:
        src=C.create_string_buffer(payload)
        assert lib.zh_decode(src,len(payload),decode_buffer,capacity,1)==0

    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.VirtualAlloc.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint];kernel.VirtualAlloc.restype=C.c_void_p
    kernel.VirtualFree.argtypes=[C.c_void_p,C.c_size_t,C.c_uint]
    address=kernel.VirtualAlloc(0x100000,0x1f00000,0x3000,4)
    if address!=0x100000: raise OSError(C.get_last_error(),'Cannot reserve isolated test EE address range')
    def read(p,n): return C.string_at(p,n)
    def write(p,b): C.memmove(p,b,len(b))
    def word(p,v=None):
        if v is None:return C.c_uint.from_address(p).value
        C.c_uint.from_address(p).value=v

    callbacks=[]; failures=[]; pending=[]; events=[]; current={'fd':False,'position':0,'deny_open':False,'waits':0,'packet':0}
    native_records={}; pages={}; fonts={}; images={}; validated_pixels=0
    resources={}
    for tag,pos,size in chunks(dynamic):
        if tag==b'RSCF':
            res=dynamic[pos:pos+size];name=res[28:res.index(b'\0',28)].decode('ascii')
            resources[name.replace('\\','/').split('/')[-1]]=res
    try:
        for group,name,tex,obj,pic in [('large','zhcache_big.tm2',30,0x800000,0x810000),('small','zhcache_small.tm2',31,0x800100,0x840000)]:
            res=resources[name];source_pic=res.index(b'TIM2')+128
            write(pic,res[source_pic:]);word(obj+4,pic);word(0x4e8c60+tex*4,obj)
            hs=struct.unpack_from('<H',res,source_pic+12)[0]
            images[group]=pic+hs
        for i,name in enumerate(NAMES):
            info=defs[name];page=info['pages'][0]
            font_address=0x700000+i*0x200;page_address=0x701000+i*0x100;records=0x720000+i*0x10000
            fonts[i]=font_address;pages[i]=page_address
            write(font_address,dynamic[info['offset']+0x74:info['offset']+0x78])
            word(font_address+4,page_address);word(font_address+8,1)
            write(font_address+12,('\\fonts\\'+name.removesuffix('.asr')).encode()+b'\0')
            word(font_address+112,0x3f800000)
            write(page_address,dynamic[info['offset']+0x7c:info['offset']+0xf8])
            word(page_address+100,31 if i==1 else 30);word(page_address+104,records)
            for j,r in enumerate(page['records']):
                p=records+j*16;write(p,struct.pack('<fffHh',*r));native_records[(i,r[3])]=p
            word(0x5841e0+i*4,font_address)
        C.c_ubyte.from_address(0x4d8f28).value=1

        def bind(addr,restype,argtypes,worker,default=None):
            def guarded(*args):
                try:return worker(*args)
                except BaseException as ex:
                    failures.append(f'{addr:08X}: {ex!r}');return default
            cb=C.CFUNCTYPE(restype,*argtypes)(guarded);callbacks.append(cb)
            lib.host_bind(addr,C.cast(cb,C.c_void_p))

        def pixels_at(key,slot_uv):
            i=NAMES.index(key[0]);small=i==1;dim=128 if small else 512
            u,v=slot_uv;x=round(u*dim-.5);y=round(v*dim-.5);w,h=glyphs.records[key][4:6]
            assert x>=0 and y>=0 and x+w<=dim and y+h<=dim
            raw=read(images['small' if small else 'large'],dim*dim//2)
            return bytes((raw[((y+yy)*dim+x+xx)//2]>>((((y+yy)*dim+x+xx)&1)*4))&15 for yy in range(h) for xx in range(w))
        def flush():
            for key,coords in pending:assert pixels_at(key,coords)==expected_tiles[key],('overwrote pending glyph',key)
            pending.clear();events.append('batch');current['waits']=0;current['packet']=0
            current['written_textures']=set()
        def wait():current['waits']+=1;events.append('wait')
        def packet(n):
            assert not hardware_sync[2], 'Native-sync mode allocated a private GS FINISH packet'
            assert n==4 and current['waits']==1
            current['packet']=0x1000000;return current['packet']
        def submit(mode):
            assert mode==0 and current['waits']==1
            if current.get('check_frame'):
                assert current['display']!=current['render_target'], 'Submitted drawing into the visible buffer'
                assert word(0x481950)==current['render_target'], 'Changed the remaining commands render target'
            if hardware_sync[2]:
                assert not current['packet'], 'Native-sync mode appended a private packet'
                assert lib.host_finish_status()==finish_sentinel, 'Native-sync mode acknowledged GS FINISH'
            else:
                assert current['packet']
                p=struct.unpack('<16I',read(current['packet'],64))
                assert p==(0x10000003,0,0x13000000,0x50000003,0x8002,0x10000000,14,0,0,0,0x3f,0,0,0,0x61,0)
                lib.host_set_finish(2)
            events.append('submit')
        def fopen(name):
            filename = C.string_at(name).decode('ascii').replace('\\','/')
            assert filename == 'Fonts/ZHGLYPH.BIN' or filename.startswith('Fonts/ZHPR'), filename
            assert not current['fd']
            if filename == 'Fonts/ZHGLYPH.BIN': assert current['waits']==2
            if current['deny_open']:return -1
            current['file'] = bank if filename == 'Fonts/ZHGLYPH.BIN' else (OUT/'rebuilt'/filename).read_bytes()
            if filename.startswith('Fonts/ZHPR') and current.get('corrupt_profile'):
                data = bytearray(current['file']); data[-1] ^= 1; current['file'] = bytes(data)
            if filename.startswith('Fonts/ZHPR') and current.get('truncate_profile'):
                current['file'] = current['file'][:50000]
            current['position'] = 0
            current['fd']=True;return 0
        def seek(fd,pos):
            assert fd==0 and current['fd'] and pos%0xc000==0
            current['position']=pos
        def fread(fd,outptr,mode):
            assert fd==0 and current['fd'] and mode==0
            pos=current['position'];chunk=current['file'][pos:pos+0xc000]
            if not chunk:return -1
            write(0x1100000,chunk)
            C.c_void_p.from_address(outptr).value=0x1100000
            current['position']+=len(chunk);return len(chunk)
        def fclose(fd):assert fd==0 and current['fd'];current['fd']=False
        def writeback(start,end):
            assert not current['fd'] and current['waits']==2
            assert (start,end-start+1) in [(images['large'],131072),(images['small'],8192)]
            current['written_textures'].add(31 if start==images['small'] else 30)
            events.append('writeback')
        def invalidate():
            assert not hardware_texture[2], 'Selective mode cleared all texture residency'
            assert events[-1]=='writeback'
            for entry in range(4):word(0x481918+entry*4,0xffffffff)
            events.append('invalidate')
        def invalidate_one(entry):
            assert hardware_texture[2] and entry<4 and current['waits']==2
            assert events[-1] in ('writeback','invalidate_one')
            assert word(0x481918+entry*4) in current['written_textures'], 'Invalidated an unchanged texture'
            word(0x481918+entry*4,0xffffffff);events.append('invalidate_one')
        def frame_vsync():events.append('vsync');return 1
        def frame_blend(mode):
            assert mode==0;events.append('blend')
        def scanout():
            assert current['waits']==1, 'Changed display before previous DMA drained'
            current['display']=word(0x481950);events.append('scanout')
        def lookup(font,code,flags,outptr):
            i=next(i for i,p in fonts.items() if p==font)
            if flags&0x200 and 97<=code<=122:code-=32
            p=native_records.get((i,code),native_records[(i,63)])
            C.c_uint.from_address(outptr).value=pages[i]
            return p
        bind(0x251c40,None,[],flush)
        bind(0x258138,None,[],wait)
        bind(0x257ca8,C.c_void_p,[C.c_uint],packet)
        bind(0x257ef0,None,[C.c_uint],submit)
        bind(0x1a3a68,C.c_int,[C.c_void_p],fopen,-1)
        bind(0x26a188,None,[C.c_int,C.c_uint],seek)
        bind(0x269d18,C.c_int,[C.c_int,C.c_void_p,C.c_uint],fread,-1)
        bind(0x1a3ef8,None,[C.c_int],fclose)
        bind(0x436fa0,None,[C.c_uint,C.c_uint],writeback)
        bind(0x254a70,None,[],invalidate)
        bind(0x254a50,None,[C.c_uint],invalidate_one)
        bind(0x424fd8,C.c_uint,[],frame_vsync)
        bind(0x2596f0,None,[C.c_uint],frame_blend)
        bind(0x258ca0,None,[],scanout)
        bind(0x208568,C.c_void_p,[C.c_uint,C.c_uint,C.c_uint,C.c_void_p],lookup)

        def show(i,codes):
            nonlocal validated_pixels
            word(0x480da8,i)
            write(0x1200000,b''.join(struct.pack('<H',c) for c in codes)+b'\0\0')
            lib.zh_prepare_text(0x1200000,0,-1)
            assert not failures,failures
            for code in codes:
                p=native_records[(i,code)];lib.zh_ensure_draw(p,pages[i])
                assert not failures,failures
                key=(NAMES[i],code);coords=struct.unpack('<ff',read(p,8))
                assert pixels_at(key,coords)==expected_tiles[key],('render pixels',key)
                pending.append((key,coords));validated_pixels+=1
            assert not current['fd']

        # Warm cache must draw without additional disk reads or submissions.
        show(2,[ord(c) for c in '别说了，他来了！'])
        before=list(diag)
        show(2,[ord(c) for c in '别说了，他来了！'])
        assert diag[7:11]==before[7:11], 'Warm cache unexpectedly flushed/read the bank'
        # Every installed L1 line, cold atlas on each line: distinguish compressed
        # preload coverage from a lucky warm atlas; compare the identical disk path.
        from game_text_resources import locate_text
        regular=json.loads((ROOT/'TEMP/builds/menu_hints_zh/build_report.json').read_text(encoding='utf-8'))
        lines=[r['text'] for r in locate_text(Path(regular['subtitle_glyph_source']).read_bytes())
               if r['kind']=='DLLN' and r['text']]
        if not args.disk_baseline:
            lib.zh_before_open(b'Envs\\sp\\L1_Gcan.ps2')
            assert not failures, failures
        before=list(diag)
        for line in lines:
            flush();lib.zh_reset_fonts()
            show(2,[ord(c) for c in line if (2,ord(c)) in native_records and c not in '\n\r\t'])
        subtitle_stats={name:diag[n]-before[n] for name,n in
                        [('loads',5),('fences',7),('opens',8),('blocks',9),('read_bytes',10),('resident_hits',21)]}
        covered=json.loads((OUT/'build_report.json').read_text(encoding='utf-8'))['resident']['per_level_required_all_resident']
        if not args.disk_baseline and covered:
            assert subtitle_stats['opens']==subtitle_stats['blocks']==subtitle_stats['read_bytes']==0,subtitle_stats
        if args.disk_baseline:assert subtitle_stats['opens']>0 and subtitle_stats['resident_hits']==0
        profile_checks=[]
        if not args.disk_baseline:
            # Exercise every emitted transition with actual compiled C, including
            # all subtitle characters and retry after a partial replacement.
            for path in regular['subtitle_glyph_sources']:
                level=Path(path).stem
                flush();lib.zh_before_open(('Envs\\sp\\'+level+'.ps2').encode('ascii'));lib.zh_reset_fonts()
                codes=sorted({ord(c) for row in locate_text(Path(path).read_bytes()) if row['kind']=='DLLN'
                              for c in row['text'] if (2,ord(c)) in native_records and c not in '\r\n\t'})
                before_profile=list(diag)
                for j in range(0,len(codes),32):show(2,codes[j:j+32])
                from build_menu_hints_zh import is_overhead_name, is_weapon_name
                catalog=json.loads((ROOT/'TEXT/菜单与提示译文.json').read_text(encoding='utf-8'))
                weapon_codes=sorted({ord(c) for entry in catalog['entries']
                                     if any(is_weapon_name(ref) for ref in entry['references'])
                                     for c in entry['zh'] if c not in '\r\n\t'})
                assert all((0,c) in native_records for c in weapon_codes),'Weapon label missing from heading font'
                for j in range(0,len(weapon_codes),32):show(0,weapon_codes[j:j+32])
                hud_codes=sorted({ord(c) for entry in catalog['entries'] if any(
                    (ref['file']=='Text/american.asr' and not is_overhead_name(ref)) or
                    ref['file'].lower()==('Envs/sp/'+level+'.ps2').lower() for ref in entry['references'])
                    for c in entry['zh'] if (1,ord(c)) in native_records and c not in '\r\n\t'} |
                    {c for c in range(32,127) if (1,c) in native_records})
                for j in range(0,len(hud_codes),32):show(1,hud_codes[j:j+32])
                large_hud_codes=[c for c in hud_codes if (2,c) in native_records]
                for j in range(0,len(large_hud_codes),32):show(2,large_hud_codes[j:j+32])
                from build_resident_glyphs import level_gui_texts
                for font_id in range(3):
                    show(font_id,[c for c in range(32,127) if (font_id,c) in native_records])
                for screen,font,text in level_gui_texts(ROOT,level):
                    font_id=NAMES.index(font+'.asr')
                    show(font_id,[ord(c) for c in text if (font_id,ord(c)) in native_records and c not in '\n\r\t'])
                assert diag[8:11]==before_profile[8:11], ('level profile caused glyph I/O',level)
                assert not failures,failures
                profile_checks.append({'level':level,'subtitle_glyphs':len(codes),'hud_glyphs':len(hud_codes),
                                       'large_hud_glyphs':len(large_hud_codes),'weapon_glyphs':len(weapon_codes),'glyph_io':0})
            profile_diag=(C.c_uint*8).in_dll(lib,'zh_profile_diagnostics')
            assert profile_diag[3]==0,list(profile_diag)
            for failure in ('corrupt_profile','truncate_profile'):
                flush();lib.zh_before_open(b'GUIMenu\\MainMenu.gui')
                current[failure]=True;old_errors=profile_diag[3]
                lib.zh_before_open(b'Envs\\sp\\L1_Gcan.am')
                assert profile_diag[3]==old_errors+1 and not current['fd'],list(profile_diag)
                current[failure]=False
                # Invalidate cached pixels, then require a real disk fallback
                # while the compressed profile is incomplete.
                lib.zh_reset_fonts();prior=list(diag)
                show(2,[ord(c) for c in '别说了，他来了！'])
                assert diag[8]>prior[8] and diag[21]==prior[21]
                lib.zh_before_open(b'Envs\\sp\\L1_Gcan.ps2')
                assert profile_diag[6]==1 and not current['fd']
                assert not failures,failures
        # Real menu font bindings: cold transitions and a second stationary frame.
        # A warm paragraph alone would miss eviction caused by other visible lines.
        from build_resident_glyphs import main_menu_texts
        if not args.disk_baseline:
            lib.zh_before_open(b'GUIMenu\\MainMenu.gui')
            assert not failures, failures
        menu_screens={}
        for screen,font,text in main_menu_texts(ROOT):
            menu_screens.setdefault(screen,[]).append((NAMES.index(font+'.asr'),text))
        before=list(diag)
        stationary_frames=[]
        for screen,items in menu_screens.items():
            flush();lib.zh_reset_fonts()
            for frame in range(2):
                frame_before=list(diag)
                for i,line in items:
                    show(i,[ord(c) for c in line if (i,ord(c)) in native_records and c not in '\n\r\t'])
                if frame:
                    assert diag[5:11]==frame_before[5:11], ('stationary menu cache churn',screen)
                    stationary_frames.append(screen)
        menu_stats={name:diag[n]-before[n] for name,n in
                    [('loads',5),('fences',7),('opens',8),('blocks',9),('read_bytes',10)]}
        report=json.loads((OUT/'build_report.json').read_text(encoding='utf-8'))
        if not args.disk_baseline and not report['resident']['main_menu_disk_keys']:
            assert menu_stats['opens']==menu_stats['read_bytes']==0,menu_stats
        for seed in range(2):
            for i,name in enumerate(NAMES):
                codes=[r[3] for r in defs[name]['pages'][0]['records']]
                random.Random(seed).shuffle(codes)
                for j in range(0,len(codes),32):show(i,codes[j:j+32])
        # Capacity overflow must flush/reuse safely rather than lose characters.
        show(0,[r[3] for r in defs[NAMES[0]]['pages'][0]['records']][:320])
        show(1,[r[3] for r in defs[NAMES[1]]['pages'][0]['records']][:100])
        flush()
        assert diag[11]==0 and diag[18]==0 and diag[19]==0,list(diag)
        success_stats=list(diag)
        frame_test={'enabled':bool(configured_frame_mode),
                    'mode':'prepare_scanout_before_glyph_submit' if configured_frame_mode else 'native_frame_end_only'}
        if configured_frame_mode:
            C.c_ubyte.from_address(0x4d8f34).value=1  # native display flipping enabled
            C.c_ubyte.from_address(0x4d8f38).value=1  # native vsync enabled
            current['check_frame']=True
            for original in (0,1):
                flush();lib.zh_reset_fonts();word(0x481950,original)
                current['display']=original;current['render_target']=original
                before_events=len(events);prepared=hardware_frame[4];consumed=hardware_frame[5]
                show(2,[ord('别')])
                assert events[before_events:before_events+5]==['batch','wait','vsync','blend','scanout']
                assert hardware_frame[3]==1 and hardware_frame[4]==prepared+1 and hardware_frame[6]==original
                assert current['display']==original^1 and word(0x481950)==original
                assert lib.host_finish_status()==2
                # Another cold batch in this same frame must not repeat the
                # display switch/blend, including after font registration.
                flush();lib.zh_reset_fonts();before_events=len(events)
                show(2,[ord('别')])
                assert not any(e in ('vsync','blend','scanout') for e in events[before_events:])
                before_events=len(events)
                assert lib.zh_frame_vsync_guard()==0
                lib.zh_frame_blend_guard(0)
                assert len(events)==before_events and hardware_frame[3]==0 and hardware_frame[5]==consumed+1
                # The remaining original frame-end code commits this flip.
                word(0x481950,original^1)
                assert word(0x481950)==current['display']
            current['check_frame']=False
            # Native non-alternating 16/32 mode must retain the original path.
            C.c_ubyte.from_address(0x4d8f33).value=1
            write(0x481954,struct.pack('<HH',16,32))
            flush();lib.zh_reset_fonts();before_events=len(events)
            show(2,[ord('别')])
            assert not any(e in ('vsync','blend','scanout') for e in events[before_events:])
            assert hardware_frame[3]==0
            assert lib.zh_frame_vsync_guard()==1
            lib.zh_frame_blend_guard(0)
            assert events[-2:]==['vsync','blend'], 'Ordinary frame-end processing was lost'
            for addr in (0x4d8f33,0x4d8f34,0x4d8f38):C.c_ubyte.from_address(addr).value=0
            write(0x481954,b'\0'*4)
            assert not failures,failures
            frame_test.update(both_display_buffers_checked=True, no_submission_into_visible_buffer=True,
                              software_render_target_preserved=True, dma_and_finish_waits_preserved=True,
                              preparation_once_per_frame=True, font_registration_preserves_preparation=True,
                              frame_end_consumes_preparation_without_repeating_vsync_or_blend=True,
                              non_alternating_mode_uses_original_path=True,
                              ordinary_frame_end_calls_preserved=True,
                              early_preparations=hardware_frame[4], consumed_preparations=hardware_frame[5])
        texture_test={
            'enabled':bool(configured_texture_mode),
            'mode':'modified_font_textures_only' if configured_texture_mode else 'all_four_residency_slots',
            'all_existing_cache_checks_run_with_configured_texture_mode':True,
        }
        if configured_texture_mode:
            assert hardware_texture[3]>0 and hardware_sync[3]==0
            # Explicit residency outcomes, with duplicate copies of the shared
            # large atlas, the small atlas, unrelated textures, and no match.
            cases=[
                (0,[30,31,30,91],[0xffffffff,31,0xffffffff,91]),
                (1,[30,31,91,31],[30,0xffffffff,91,0xffffffff]),
                (2,[31,92,30,30],[31,92,0xffffffff,0xffffffff]),
                (2,[31,92,93,94],[31,92,93,94]),
            ]
            for font_id,resident,expected in cases:
                flush();lib.zh_reset_fonts()
                for entry,texture in enumerate(resident):word(0x481918+entry*4,texture)
                code=next(c for i,c in native_records if i==font_id and 0x4e00<=c<=0x9fff)
                word(0x480da8,font_id);write(0x1200000,struct.pack('<HH',code,0))
                before=list(diag);invalidated=hardware_texture[4]
                lib.zh_prepare_text(0x1200000,0,-1)
                assert not failures,failures
                assert [word(0x481918+entry*4) for entry in range(4)]==expected
                assert hardware_texture[4]-invalidated==sum(a!=b for a,b in zip(resident,expected))
                assert diag[5]>before[5] and diag[7]>before[7] and lib.host_finish_status()==2
                show(font_id,[code]);flush()
            # Keep the ordinary all-slot invalidation branch available too.
            hardware_texture[2]=0;lib.zh_reset_fonts()
            for entry,texture in enumerate((30,31,90,91)):word(0x481918+entry*4,texture)
            show(2,[ord('别')]);flush()
            assert all(word(0x481918+entry*4)==0xffffffff for entry in range(4))
            hardware_texture[2]=configured_texture_mode
            texture_test.update(all_three_fonts_checked=True, duplicate_resident_copies_invalidated=True,
                                unmodified_font_and_scene_residency_preserved=True,
                                absent_font_texture_changes_no_residency=True,
                                original_dma_and_finish_path_preserved=True,
                                original_all_slot_branch_still_works=True,
                                dirty_batches=hardware_texture[3], invalidated_slots=hardware_texture[4])
        sync_test={
            'enabled':bool(configured_sync_mode),
            'mode':'native_dma_only' if configured_sync_mode else 'native_dma_plus_private_gs_finish',
            'all_existing_cache_checks_run_with_configured_sync_mode':True,
            'native_dma_waits_per_batch':2,
        }
        if configured_sync_mode:
            assert hardware_sync[3]==diag[7] and hardware_sync[3]>0
            assert lib.host_finish_status()==finish_sentinel
            sync_test.update(native_sync_batches=hardware_sync[3],
                             private_finish_packet_omitted=True, finish_status_untouched=True)
            # A cold glyph also exercises the retained original FINISH branch
            # without building another ISO or changing the installed mode.
            hardware_sync[2]=0;lib.zh_reset_fonts();before=list(diag)
            show(2,[ord('别')]);flush()
            assert diag[5]>before[5] and diag[7]>before[7] and diag[11]==0
            assert lib.host_finish_status()==2 and not failures,failures
            hardware_sync[2]=configured_sync_mode;lib.host_set_finish(finish_sentinel)
            sync_test['original_finish_branch_still_loads_correct_pixels']=True
        hardware_test={'enabled':bool(configured_hardware_mode), 'mode':'normal'}
        if configured_hardware_mode:
            assert configured_hardware_mode==1
            flush();lib.zh_before_open(b'GUIMenu\\MainMenu.gui')
            hardware[2]=configured_hardware_mode
            assert hardware[3]==0
            lib.zh_reset_fonts()
            warm_code=ord('别')
            show(2,[warm_code]);flush()
            lib.zh_before_open(b'Envs\\sp\\L1_Gcan.ps2')
            assert hardware[3]==1 and hardware[5]==1
            warm_before=list(diag)
            show(2,[warm_code]);flush()
            assert diag[5:11]==warm_before[5:11], 'Frozen warm glyph unexpectedly updated'

            def check_frozen():
                # Real font registration occurs during loading; it must not
                # silently disable the diagnostic after a level-open trigger.
                lib.zh_reset_fonts()
                assert hardware[3]==1
                before=list(diag); before_events=list(events); suppressed=hardware[4]
                atlas={g:read(p,8192 if g=='small' else 131072) for g,p in images.items()}
                for font_id in range(3):
                    code=next(c for i,c in native_records if i==font_id and 0x4e00<=c<=0x9fff)
                    p=native_records[(font_id,code)];metrics=read(p+8,8)
                    word(0x480da8,font_id)
                    write(0x1200000,struct.pack('<HH',code,0))
                    lib.zh_prepare_text(0x1200000,0,-1)
                    lib.zh_ensure_draw(p,pages[font_id])
                    assert read(p,8)==read(native_records[(font_id,63)],8), 'Missing glyph did not use the reserved question-mark slot'
                    assert read(p+8,8)==metrics, 'Diagnostic changed glyph advance/code'
                assert diag[5:11]==before[5:11], 'Frozen mode loaded/evicted/fenced/read glyphs'
                assert diag[11:13]==before[11:13] and diag[21:30]==before[21:30]
                assert events==before_events, 'Frozen mode submitted/waited/wrote back/invalidated'
                assert all(read(images[g],len(raw))==raw for g,raw in atlas.items())
                assert hardware[4]>suppressed and not current['fd'] and not failures, failures

            check_frozen()
            lib.zh_before_open(b'Envs\\sp\\unrelated.bin')
            assert hardware[3]==1
            lib.zh_before_open(b'GUIMenu\\MainMenu.gui')
            assert hardware[3]==0
            # A failed hardware preload must not leave this diagnostic running
            # as an ordinary build, regardless of the still-active menu profile.
            current['deny_open']=True
            lib.zh_before_open(b'Envs\\sp\\L2_Betio.am')
            assert hardware[3]==1 and hardware[5]==2 and not current['fd']
            check_frozen()
            current['deny_open']=False
            lib.zh_before_open(b'GUIMenu\\MainMenu.gui')
            assert hardware[3]==0
            before=list(diag)
            show(2,[warm_code]);flush()
            assert diag[5]>before[5] and diag[7]>before[7], 'Main menu did not resume normal cache updates'
            hardware_test={
                'enabled':True, 'mode':'freeze_glyphs_in_levels',
                'warm_cached_glyphs_preserved':True,
                'all_three_fonts_use_reserved_fallback_for_cold_glyphs':True,
                'frozen_atlas_unchanged':True, 'glyph_metrics_unchanged':True,
                'frozen_glyph_loads_evictions_fences_io_writebacks_invalidations':0,
                'font_registration_preserves_freeze':True,
                'freeze_independent_of_successful_preload':True,
                'main_menu_resumes_cache_updates':True,
                'normal_cache_checks_run_with_diagnostic_mode_disabled':True,
            }
        # Failed open may not overwrite queued pixels or retain a file handle.
        lib.zh_reset_fonts();current['deny_open']=True
        unselected=next((i,c) for (name,c),off in zip(keys,runtime_offsets)
                        if not off&0x80000000 and (i:=NAMES.index(name))==2 and c>0x3000)
        word(0x480da8,2);key=unselected[1]
        p=native_records[(2,key)];before=read(images['large'],131072)
        lib.zh_ensure_draw(p,pages[2])
        assert diag[12]==9 and read(images['large'],131072)==before and not current['fd']
        assert not failures,failures
        result={'test_kind':'compiled C core with mocked native I/O and render submission',
                'decoded_glyphs':len(keys),'render_pixel_checks':validated_pixels,
                'pending_pixels_preserved':True,'warm_cache_zero_io':True,
                'overflow_preserves_glyphs':True,'failed_open_preserves_atlas':True,
                'malformed_blocks_rejected':True,
                'disk_baseline':args.disk_baseline,'cold_l1_lines':len(lines),
                'cold_l1_diagnostics':subtitle_stats,
                'all_level_profile_checks':profile_checks,
                'partial_and_corrupt_profile_fall_back_safely':not args.disk_baseline,
                'main_menu_screens':len(menu_screens),'cold_main_menu_diagnostics':menu_stats,
                'stationary_menu_frames_zero_churn':stationary_frames,
                'hardware_diagnostic':hardware_test,
                'hardware_sync':sync_test,
                'hardware_texture':texture_test,
                'hardware_frame':frame_test,
                'successful_run_diagnostics':success_stats,'ps2_runtime_tested':False}
        (OUT/f'host_test_report{suffix}.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result))
    finally:
        kernel.VirtualFree(address,0,0x8000)


if __name__=='__main__':main()
