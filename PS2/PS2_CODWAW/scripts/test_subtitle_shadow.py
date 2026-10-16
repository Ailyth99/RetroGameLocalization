"""Check native shadow submissions with emitted MIPS, without simulating the GS."""
import struct

import unicorn as U
import unicorn.mips_const as M


def check_subtitle_shadow(elf, report):
    enabled = report['subtitle_style']['shadow']['enabled']
    instruction = struct.unpack_from('<I', elf, 0x3D1A8C - 0x100000 + 0x80)[0]
    assert instruction == (0x24062184 if enabled else 0x24060184), 'Subtitle shadow flag mismatch'
    segment = struct.unpack_from('<8I', elf, 52)
    body = elf[segment[1]:segment[1] + segment[4]]
    worker = int(report['symbols']['zh_ensure_draw'], 16)
    color = int(report['subtitle_style']['color_after'], 16)
    results = []

    def float_bits(value):
        return struct.unpack('<I', struct.pack('<f', value))[0]

    for flags in (0x184, 0x2184):
        u = U.Uc(U.UC_ARCH_MIPS, U.UC_MODE_MIPS64 | U.UC_MODE_LITTLE_ENDIAN)
        u.ctl_set_cpu_model(M.UC_CPU_MIPS64_MIPS64R2_GENERIC)
        u.mem_map(0x100000, 0x1f00000)
        u.mem_write(segment[2], body)
        glyph, page, clip = 0xd00000, 0xd00100, 0xd00200
        u.mem_write(glyph, struct.pack('<fffHh', 0.125, 0.25, 24, 0x4e00, 0))
        u.mem_write(page + 0x64, struct.pack('<I', 123))
        u.mem_write(page + 0x70, struct.pack('<II', 512, 512))
        u.mem_write(clip, struct.pack('<4f', 0, 0, 640, 448))
        u.mem_write(0x480dc0, struct.pack('<III', color, color, flags))
        # No live viewport is present in this CPU-only test.
        u.mem_write(0x4d8ceb, b'\0')
        for register, value in (
            (M.UC_MIPS_REG_GP, 0x4e06f0), (M.UC_MIPS_REG_SP, 0x1e00000),
            (M.UC_MIPS_REG_RA, 0xff0000), (M.UC_MIPS_REG_A0, clip),
            (M.UC_MIPS_REG_A1, color), (M.UC_MIPS_REG_A2, glyph), (M.UC_MIPS_REG_A3, page),
            (M.UC_MIPS_REG_F12, float_bits(100)), (M.UC_MIPS_REG_F13, float_bits(200)),
            (M.UC_MIPS_REG_F14, float_bits(1)),
        ):
            u.reg_write(register, value)
        primitives, ensured = [], []

        def intercept(uc, address, size, data):
            if address == worker:
                assert uc.reg_read(M.UC_MIPS_REG_A0) == glyph
                assert uc.reg_read(M.UC_MIPS_REG_A1) == page
                ensured.append(address)
            elif address == 0x208740:
                uc.reg_write(M.UC_MIPS_REG_F0, float_bits(32))
            elif address == 0x252450:
                uc.reg_write(M.UC_MIPS_REG_F0, float_bits(1))
            elif address == 0x24f9f8:
                uc.mem_write(uc.reg_read(M.UC_MIPS_REG_A0), struct.pack('<4f', 0, 0, 640, 448))
            elif address == 0x20a380:
                raw = bytes(uc.mem_read(uc.reg_read(M.UC_MIPS_REG_A0), 96))
                primitives.append({
                    'xy': list(struct.unpack_from('<8f', raw)),
                    'uv': list(struct.unpack_from('<8f', raw, 32)),
                    'rgba': struct.unpack_from('<I', raw, 64)[0],
                    'texture': struct.unpack_from('<I', raw, 80)[0],
                })
            else:
                return
            uc.reg_write(M.UC_MIPS_REG_PC, uc.reg_read(M.UC_MIPS_REG_RA))

        u.hook_add(U.UC_HOOK_CODE, intercept)
        # Enter the installed cache hook, then execute the actual native draw body.
        u.emu_start(0x2064f8, 0xff0000, timeout=3000000, count=3000)
        assert u.reg_read(M.UC_MIPS_REG_PC) == 0xff0000
        assert len(ensured) == 1, 'Shadow must not re-enter the glyph cache hook'
        assert len(primitives) == (2 if flags & 0x2000 else 1)
        foreground = primitives[-1]
        assert foreground['rgba'] == color
        assert foreground['xy'] == [100, 124, 124, 100, 200, 200, 232, 232]
        if flags & 0x2000:
            shadow = primitives[0]
            assert shadow['rgba'] == 0xa0000000
            assert shadow['uv'] == foreground['uv'] and shadow['texture'] == foreground['texture']
            assert all(a - b == 1.5 for a, b in zip(shadow['xy'], foreground['xy']))
        results.append({'flags': hex(flags), 'glyph_cache_checks': len(ensured),
                        'submissions': len(primitives), 'foreground_preserved': True})
    return {'native_subtitle_shadow': {'enabled_in_build': enabled,
            'instruction': hex(instruction), 'cpu_checks': results,
            'shared_texture_and_uv': True, 'shadow_offset_draw_units': [1.5, 1.5],
            'gs_or_hardware_test': False}}
