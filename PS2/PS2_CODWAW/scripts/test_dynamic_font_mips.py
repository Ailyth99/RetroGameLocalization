"""Execute emitted MIPS hooks/guards in Unicorn, with game callees intercepted.

This validates CPU ABI/control flow only, not the EE/GS or game runtime.
"""
import json
import struct
import unicorn as U
import unicorn.mips_const as M
from build_dynamic_fonts import ROOT, OUT

MASK = (1 << 64) - 1


def main():
    report=json.loads((OUT/'build_report.json').read_text(encoding='utf-8'))
    symbols={k:int(v,16) for k,v in report['symbols'].items()}
    elf=(OUT/'rebuilt/slus_217.46').read_bytes()
    segment=struct.unpack_from('<8I',elf,52)
    body=elf[segment[1]:segment[1]+segment[4]]
    checks=[]
    from test_text_wrapping import check_text_wrapping
    checks.append(check_text_wrapping(elf))
    from test_subtitle_shadow import check_subtitle_shadow
    checks.append(check_subtitle_shadow(elf, report))
    # EE kernel interrupt/context code uses SQ/LQ on its caller's stack.
    # Generic MIPS EABI's 8-byte default silently breaks those context saves.
    text_begin=symbols['__patch_start']
    text_end=min(symbols[name] for name in ('bank_offsets','resident_data','resident_profiles') if name in symbols)
    adjustments=[]
    for pc in range(text_begin,text_end,4):
        word=struct.unpack_from('<I',body,pc-segment[2])[0]
        if word>>16==0x27bd:  # addiu sp,sp,imm16
            delta=struct.unpack('<h',struct.pack('<H',word&65535))[0]
            assert delta%16==0, ('EE stack misalignment',hex(pc),delta)
            adjustments.append({'pc':hex(pc),'delta':delta})
    assert adjustments
    checks.append(dict(all_stack_adjustments_16byte_aligned=True,count=len(adjustments)))
    gpr=[M.UC_MIPS_REG_A0,M.UC_MIPS_REG_A1,M.UC_MIPS_REG_A2,M.UC_MIPS_REG_A3,
         M.UC_MIPS_REG_T0,M.UC_MIPS_REG_T1,M.UC_MIPS_REG_T2,M.UC_MIPS_REG_T3]
    fpr=[M.UC_MIPS_REG_F12,M.UC_MIPS_REG_F13,M.UC_MIPS_REG_F14,M.UC_MIPS_REG_F15]
    def machine():
        u=U.Uc(U.UC_ARCH_MIPS,U.UC_MODE_MIPS64|U.UC_MODE_LITTLE_ENDIAN)
        # R4000 (Unicorn's default) rejects MOVN used by the native allocator.
        u.ctl_set_cpu_model(M.UC_CPU_MIPS64_MIPS64R2_GENERIC)
        u.mem_map(0x100000,0x1f00000);u.mem_write(0x100000,body)
        u.reg_write(M.UC_MIPS_REG_SP,0x1e00000)
        return u

    # Exercise the game's real, independent heap provider. The former tests
    # mocked allocation and missed dlmalloc overwriting the appended patch.
    u=machine();stop=0xff0000
    u.reg_write(M.UC_MIPS_REG_GP,0x4e06f0)
    u.reg_write(M.UC_MIPS_REG_RA,stop)
    u.emu_start(0x2420c8,stop,timeout=3000000,count=1000)
    heap_start=u.reg_read(M.UC_MIPS_REG_V0)
    expected_start=(symbols['__patch_end']+4095)&~4095
    assert heap_start==expected_start and heap_start>=symbols['__patch_end'], (hex(heap_start),hex(expected_start))
    patch_before=bytes(u.mem_read(symbols['__patch_start'],symbols['__patch_end']-symbols['__patch_start']))
    allocations=[]
    for size in (104,1024,40,152,24,152,56,24,104,168,8192,49152,139264):
        u.reg_write(M.UC_MIPS_REG_A0,size)
        u.reg_write(M.UC_MIPS_REG_RA,stop)
        u.emu_start(0x243118,stop,timeout=3000000,count=100000)
        assert u.reg_read(M.UC_MIPS_REG_PC)==stop
        allocated=u.reg_read(M.UC_MIPS_REG_V0)
        assert heap_start<=allocated<0x1ff8000-size, (size,hex(allocated))
        u.mem_write(allocated,b'\xa5'*size)
        allocations.append({'bytes':size,'address':hex(allocated)})
    assert bytes(u.mem_read(symbols['__patch_start'],len(patch_before)))==patch_before
    checks.append(dict(native_heap_start=hex(heap_start),real_dlmalloc_allocations=allocations,
                       patch_code_and_data_preserved=True))

    for hook,worker,resume,frame in [
        ('zh_draw_hook','zh_ensure_draw',0x206500,0x70),
        ('zh_text_hook','zh_prepare_text',0x207478,0x100),
        ('zh_register_hook','zh_reset_fonts',0x208238,0),
        ('zh_open_hook','zh_before_open',0x1a3a70,0x20),
    ]:
        u=machine();initial=[0x1234567800100000+i*0x100 for i in range(8)]
        floats=[0x3f800000+i*0x100000 for i in range(4)]
        for reg,value in zip(gpr,initial):u.reg_write(reg,value)
        for reg,value in zip(fpr,floats):u.reg_write(reg,value)
        original_ra=0x8765432100123400;original_s0=0x1020304050607080
        u.reg_write(M.UC_MIPS_REG_RA,original_ra);u.reg_write(M.UC_MIPS_REG_S0,original_s0)
        original_gp=0x4e06f0;u.reg_write(M.UC_MIPS_REG_GP,original_gp)
        visited=[]
        def intercept(uc,address,size,data):
            if address==symbols[worker]:
                visited.append(address)
                args=[uc.reg_read(r) for r in gpr[:3]]
                if hook=='zh_draw_hook':assert args[:2]==initial[2:4],args
                if hook=='zh_text_hook':assert args==[initial[0],initial[3],initial[4]],args
                ret=uc.reg_read(M.UC_MIPS_REG_RA)
                for r in gpr:uc.reg_write(r,0xdeadbeefcafef00d)
                for r in fpr:uc.reg_write(r,0x41200000)
                uc.reg_write(M.UC_MIPS_REG_GP,0)
                uc.reg_write(M.UC_MIPS_REG_PC,ret)
        u.hook_add(U.UC_HOOK_CODE,intercept)
        u.emu_start(symbols[hook],resume,timeout=3000000,count=1000)
        assert visited and u.reg_read(M.UC_MIPS_REG_PC)==resume,hook
        expected=initial.copy()
        if hook=='zh_register_hook':expected[4]=initial[0]
        assert [u.reg_read(r) for r in gpr]==expected,hook
        assert [u.reg_read(r) for r in fpr]==floats,hook
        assert u.reg_read(M.UC_MIPS_REG_RA)==original_ra
        assert u.reg_read(M.UC_MIPS_REG_GP)==original_gp
        assert u.reg_read(M.UC_MIPS_REG_SP)==0x1e00000-frame
        if frame==0x70:assert struct.unpack('<Q',u.mem_read(0x1e00000-frame+16,8))[0]==original_s0
        checks.append(dict(hook=hook,full_64bit_arguments_restored=True,float_arguments_restored=True,
                           displaced_prologue_verified=True))

    # Execute the real emitted routing wrappers. Native preparation and drawing
    # are intercepted to observe draw order and count timer updates per frame.
    for name_hash in (0, 0x12345678, 0x71602625, 0x71602626):
        u=machine();stop=0xff0000;line=0x950000;sp=0x1e00000
        logo=name_hash in (0x71602625,0x71602626)
        u.mem_write(line+4,struct.pack('<I',name_hash))
        u.mem_write(0x480e80,'字幕'.encode('utf-16-le')+b'\0\0')
        u.reg_write(M.UC_MIPS_REG_A0,line if name_hash else 0)
        u.reg_write(M.UC_MIPS_REG_A1,999)
        u.reg_write(M.UC_MIPS_REG_F12,0x403a5e81)
        calls=[]
        def subtitle_native(uc,address,size,data):
            if address==0x211b08:
                assert uc.reg_read(M.UC_MIPS_REG_A0)==(line if name_hash else 0)
                assert uc.reg_read(M.UC_MIPS_REG_A1)==999
                assert uc.reg_read(M.UC_MIPS_REG_F12)==0x403a5e81
                calls.append('prepare')
            elif address==0x211c30:
                calls.append('subtitle_update_and_draw')
            elif address==0x3c94c8:
                calls.append('gui')
                for r in gpr:uc.reg_write(r,0xdeadbeef)
                uc.reg_write(M.UC_MIPS_REG_V0,0x12345678)
                uc.reg_write(M.UC_MIPS_REG_V1,0x98765432)
            else:return
            uc.reg_write(M.UC_MIPS_REG_PC,uc.reg_read(M.UC_MIPS_REG_RA))
        u.hook_add(U.UC_HOOK_CODE,subtitle_native)
        def route(hook):
            u.reg_write(M.UC_MIPS_REG_RA,stop)
            u.emu_start(symbols[hook],stop,timeout=3000000,count=1000)
            assert u.reg_read(M.UC_MIPS_REG_PC)==stop
            assert u.reg_read(M.UC_MIPS_REG_SP)==sp
        route('zh_logo_subtitle_prepare')
        assert calls==['prepare']
        assert struct.unpack('<I',u.mem_read(symbols['zh_logo_subtitle_active'],4))[0]==int(logo)
        calls.clear()
        route('zh_subtitle_before_gui');route('zh_logo_subtitle_after_gui')
        expected=['gui','subtitle_update_and_draw'] if logo else ['subtitle_update_and_draw','gui']
        assert calls==expected, (name_hash,calls)
        # Audio cleanup may clear the line pointer while the caption lingers.
        u.mem_write(0x480e78,b'\0'*4)
        calls.clear()
        route('zh_subtitle_before_gui');route('zh_logo_subtitle_after_gui')
        assert calls==expected
        if logo:
            calls.clear();route('zh_logo_subtitle_after_gui')
            assert calls==['gui','subtitle_update_and_draw']  # GUI-only path
            u.mem_write(0x480e80,b'\0\0')
            calls.clear();route('zh_logo_subtitle_after_gui')
            assert calls==['gui']
            assert bytes(u.mem_read(symbols['zh_logo_subtitle_active'],4))==b'\0'*4
        checks.append(dict(subtitle_name_hash=hex(name_hash),logo_caption=logo,
            draw_order=expected,one_native_timer_update_per_frame=True,
            original_preparation_arguments_preserved=True))

    for stage,resume in enumerate((0x44a0e8,0x44a0fc,0x44a570),1):
        for fail in (False,True):
            u=machine();sp=0x1e00000;tree=0x950000;node=0 if stage==1 else 0x960000
            temporary=0x970000 if stage==3 else 0
            u.mem_write(tree,struct.pack('<4I',node,112,223,0))
            u.reg_write(M.UC_MIPS_REG_S7,tree);u.reg_write(M.UC_MIPS_REG_S6,temporary)
            u.reg_write(M.UC_MIPS_REG_A0,7136);u.reg_write(M.UC_MIPS_REG_RA,resume)
            saved=[]
            for i in range(9):
                value=0x4567000000000000+i;saved.append(value)
                u.mem_write(sp+0x230+i*8,struct.pack('<Q',value))
            stop=0xff0000
            u.mem_write(sp+0x278,struct.pack('<Q',stop))
            u.mem_write(sp+0x280,struct.pack('<I',0x3fc00000))
            freed=[];allocated=[]
            def native(uc,address,size,data):
                if address==0x422f48:
                    allocated.append(uc.reg_read(M.UC_MIPS_REG_A0))
                    uc.reg_write(M.UC_MIPS_REG_V0,0 if fail else 0x980000)
                elif address==0x422f28:freed.append(uc.reg_read(M.UC_MIPS_REG_A0))
                elif address==0x449db0:
                    p=uc.reg_read(M.UC_MIPS_REG_A0)
                    old=struct.unpack('<I',uc.mem_read(p,4))[0]
                    if old:freed.append(old)
                    uc.mem_write(p,b'\0'*16)
                else:return
                uc.reg_write(M.UC_MIPS_REG_PC,uc.reg_read(M.UC_MIPS_REG_RA))
            u.hook_add(U.UC_HOOK_CODE,native)
            end=stop if fail else resume
            u.emu_start(symbols['zh_tree_alloc_guard'],end,timeout=3000000,count=1000)
            assert allocated==[7136] and u.reg_read(M.UC_MIPS_REG_PC)==end
            if fail:
                assert freed==([temporary] if temporary else [])+([node] if node else []),(stage,freed)
                assert bytes(u.mem_read(tree,16))==b'\0'*16
                assert u.reg_read(M.UC_MIPS_REG_SP)==sp+0x290
                assert u.reg_read(M.UC_MIPS_REG_S0)==saved[0] and u.reg_read(M.UC_MIPS_REG_S8)==saved[8]
                assert struct.unpack('<I',u.mem_read(symbols['zh_diagnostics']+60,4))[0]==1
            else:
                assert not freed and u.reg_read(M.UC_MIPS_REG_SP)==sp and u.reg_read(M.UC_MIPS_REG_V0)==0x980000
            checks.append(dict(tree_allocation_stage=stage,forced_failure=fail,passed=True))

    frame=report.get('hardware_frame',{'enabled':False})
    for va,original,hook in ((0x259650,0x424fd8,'zh_frame_vsync_guard'),
                             (0x259658,0x2596f0,'zh_frame_blend_guard')):
        target=symbols[hook] if frame['enabled'] else original
        assert struct.unpack_from('<I',body,va-segment[2])[0]==0x0c000000|(target>>2)
    if frame['enabled']:
        for prepared in (0,1):
            u=machine();state=symbols['zh_hardware_frame'];calls=[]
            u.mem_write(state+12,struct.pack('<I',prepared))
            def frame_native(uc,address,size,data):
                if address not in (0x424fd8,0x2596f0):return
                if address==0x2596f0:assert uc.reg_read(M.UC_MIPS_REG_A0)==0
                calls.append(address);uc.reg_write(M.UC_MIPS_REG_V0,1)
                uc.reg_write(M.UC_MIPS_REG_PC,uc.reg_read(M.UC_MIPS_REG_RA))
            u.hook_add(U.UC_HOOK_CODE,frame_native)
            for va in (0x259650,0x259658):
                u.emu_start(va,va+8,timeout=3000000,count=1000)
                assert u.reg_read(M.UC_MIPS_REG_PC)==va+8
                assert u.reg_read(M.UC_MIPS_REG_SP)==0x1e00000
            assert calls==([] if prepared else [0x424fd8,0x2596f0]),calls
            words=struct.unpack('<7I',u.mem_read(state,28))
            assert words[3]==0 and words[5]==prepared,words
            checks.append(dict(native_frame_call_sites_executed=True,early_prepared=bool(prepared),
                               original_calls_once_or_consumed=True,stack_preserved=True))

    result={'engine':'Unicorn MIPS64, little endian','checks':checks,
            'native_game_callees':'intercepted test stubs','ps2_runtime_tested':False}
    (OUT/'mips_test_report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Emitted MIPS hooks/guards:',len(checks),'cases passed')


if __name__=='__main__':main()
