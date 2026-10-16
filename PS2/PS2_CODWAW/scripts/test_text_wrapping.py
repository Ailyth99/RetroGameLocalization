"""Run the real line-break MIPS routine; mock only locale, glyph widths and kerning."""
import struct
import unicorn as U
import unicorn.mips_const as M


def check_text_wrapping(elf):
    ph = struct.unpack_from('<8I', elf, 52)
    body = elf[ph[1]:ph[1] + ph[4]]
    original_words = {0x206f5c: 0x12e0005e, 0x2070c8: 0x4600adc6, 0x2070cc: 0x24140003}
    original = bytearray(body)
    for address, word in original_words.items():
        struct.pack_into('<I', original, address - ph[2], word)

    def bits(value):
        return struct.unpack('<I', struct.pack('<f', value))[0]

    def wrap(text, width, code=body):
        u = U.Uc(U.UC_ARCH_MIPS, U.UC_MODE_MIPS64 | U.UC_MODE_LITTLE_ENDIAN)
        u.ctl_set_cpu_model(M.UC_CPU_MIPS64_MIPS64R2_GENERIC)
        u.mem_map(0x100000, 0x1f00000)
        u.mem_write(ph[2], bytes(code))
        start, output, stop = 0x900000, 0x910000, 0xff0000
        u.mem_write(start, text.encode('utf-16-le') + b'\0\0')
        u.reg_write(M.UC_MIPS_REG_SP, 0x1e00000)
        # The native routine adds +/-0.5 before conversion to an integer.
        u.reg_write(M.UC_MIPS_REG_FCSR, 1)  # truncate toward zero

        def external(uc, address, size, data):
            if address == 0x141b30:
                uc.reg_write(M.UC_MIPS_REG_V0, 0)  # English game locale
            elif address == 0x206328:
                char = uc.reg_read(M.UC_MIPS_REG_A0) & 65535
                advance = 20 if char >= 0x2e80 else 6 if char in (32, 45) else 10
                uc.reg_write(M.UC_MIPS_REG_F0, bits(advance))
            elif address == 0x208100:
                uc.reg_write(M.UC_MIPS_REG_F0, bits(0))
            else:
                return
            uc.reg_write(M.UC_MIPS_REG_PC, uc.reg_read(M.UC_MIPS_REG_RA))

        u.hook_add(U.UC_HOOK_CODE, external)
        lines, cursor = [], 0
        while cursor < len(text):
            u.mem_write(output, b'\xff' * 12)
            for reg, value in ((M.UC_MIPS_REG_A0, start + cursor * 2),
                               (M.UC_MIPS_REG_A1, output), (M.UC_MIPS_REG_A2, output + 4),
                               (M.UC_MIPS_REG_A3, output + 8), (M.UC_MIPS_REG_RA, stop),
                               (M.UC_MIPS_REG_F12, bits(width)), (M.UC_MIPS_REG_F13, bits(1))):
                u.reg_write(reg, value)
            u.emu_start(0x206e08, stop, timeout=2000000, count=20000)
            assert u.reg_read(M.UC_MIPS_REG_PC) == stop, 'Line breaker did not return'
            end = (u.reg_read(M.UC_MIPS_REG_V0) - start) // 2
            assert cursor < end <= len(text), ('Line breaker lost progress', cursor, end)
            measured, spaces = struct.unpack('<fI', u.mem_read(output, 8))
            hyphen = bytes(u.mem_read(output + 8, 1))[0]
            assert hyphen in (0, 1)
            lines.append(dict(text=text[cursor:end].rstrip(' \n'), width=measured,
                              hyphen=hyphen, spacing_units=spaces))
            cursor = end
        return lines

    cases = []
    for text, width, expected in (
        ('你好世界', 40, ['你好', '世界']),
        ('中文abc世界', 70, ['中文abc', '世界']),
        ('你好-世界', 46, ['你好-', '世界']),
        ('你好。世界', 60, ['你好。', '世界']),
        ('你好', 10, ['你', '好']),
        ('你好\n世界', 100, ['你好', '世界']),
    ):
        lines = wrap(text, width)
        assert [row['text'] for row in lines] == expected, (text, lines)
        assert all(not row['hyphen'] for row in lines), (text, lines)
        cases.append(dict(input=text, limit=width, lines=lines))
    assert cases[0]['lines'][0]['width'] == 40, 'CJK line width excludes final glyph'
    for text, width in (('hello world', 64), ('abcdefghijklmnop', 46), ('he-llo world', 46)):
        current = wrap(text, width)
        baseline = wrap(text, width, original)
        assert current == baseline, ('Latin wrapping changed', text, current, baseline)
        cases.append(dict(input=text, limit=width, latin_matches_original=True, lines=current))
    return dict(native_line_wrap_cases=cases, chinese_no_synthetic_hyphen=True,
                literal_hyphens_preserved=True, latin_word_wrapping_preserved=True,
                runtime_validation='pending_user_test')
