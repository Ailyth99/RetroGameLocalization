"""Freshly rebuild authorized text/fonts, then build the native dynamic-font test.

Default stages the result; --install installs it. The caller builds COD5_TEST.iso.
No cached source-font pixels are used: the standard full renderer runs every time.
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

import lz4.block
from game_text_resources import chunks, locate_text
from unified_fonts import parse_pages
from build_large_menu_font import rsfl_entries
from probe_dynamic_font_cache import ExistingGlyphs, BIG, SMALL, SUB, LAYOUTS, put
from build_settings import SETTINGS_PATH, load_settings
from set_subtitle_style import apply_style, REPORT as STYLE_REPORT

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'TEMP/builds/dynamic_font_cache'
STATE = ROOT / 'SOUND/research/dynamic_font_cache/installed_build.json'
BACKUP = ROOT / 'SOURCE/backups/dynamic_font_cache'
RUNTIME = ROOT / 'scripts/dynamic_font'
COMPILER = Path('C:/pspdev/bin/psp-gcc.exe')
OBJCOPY = COMPILER.with_name('psp-objcopy.exe')
NM = COMPILER.with_name('psp-nm.exe')
OBJDUMP = COMPILER.with_name('psp-objdump.exe')
BASE = 0x59b000
NAMES = (BIG, SMALL, SUB)
BASE_ELF_SHA = '8b90285e9fa6dbc0d0a52c63fef16300c8b5ec8950a3a436762a9f3ed144d2c9'
ORIGINAL_ELF_SHA = 'e191d4275760546a7a0f3a6ee3d7b8bc2c5205ec30a9e6bdb61436237e83b4c3'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(n, boundary):
    return (n + boundary - 1) // boundary * boundary


def resource(template, name, width, height, pixels, palette):
    tm = template.index(b'TIM2'); pic = tm + 128
    header_size = struct.unpack_from('<H', template, pic + 12)[0]
    tim = bytearray(template[tm:pic + header_size])
    struct.pack_into('<III', tim, 128, header_size + len(pixels) + len(palette), len(palette), len(pixels))
    struct.pack_into('<HH', tim, 148, width, height)
    tim.extend(pixels); tim.extend(palette)
    result = bytearray(template[:28]) + name.encode('ascii') + b'\0'
    result.extend(b'\0' * (-len(result) % 4)); result.extend(tim)
    struct.pack_into('<I', result, 4, len(result))
    struct.pack_into('<I', result, 24, len(tim))
    return bytes(result)


def build_resources(fresh, subtitle_texts=(), subtitle_by_level=None):
    glyphs = ExistingGlyphs(fresh)
    definitions = parse_pages(fresh)
    refs = rsfl_entries(fresh, definitions)
    assert sum(len(p['records']) for f in definitions.values() for p in f['pages']) <= 4096, \
        'Native glyph metadata exceeds the explicit 64 KiB test-build budget'
    resources = {}
    for tag, pos, size in chunks(fresh):
        if tag == b'RSCF':
            res = fresh[pos:pos + size]
            name = res[28:res.index(b'\0', 28)].decode('ascii').replace('\\', '/').split('/')[-1].lower()
            resources[name] = (pos, res)
    remove = set(); templates = {}
    for name, font in definitions.items():
        for page in font['pages']:
            key = page['texture'].replace('\\', '/').split('/')[-1].lower().replace('.tga', '.tm2')
            pos, res = resources[key]; remove.add(pos)
            templates.setdefault(name, res)

    atlases = {g: bytearray([v['transparent'] * 17]) * (v['width'] * v['height'] // 2)
               for g, v in LAYOUTS.items()}
    offsets, specs, encoded_tiles, expected_tiles = [], [], [], []
    bank = bytearray(2048)
    font_blocks = {}
    for font_id, name in enumerate(NAMES):
        info = definitions[name]
        records = sorted((r for p in info['pages'] for r in p['records']), key=lambda r:r[3])
        small = name == SMALL
        dim, stride, sample = (128, 16, 16) if small else (512, 32, 31 if name == BIG else 32)
        tile_bytes = 128 if small else 512
        fallback_index = next(i for i,r in enumerate(records) if r[3] == 63)
        specs.append((len(offsets), len(records), tile_bytes, fallback_index))
        default_slot = 0 if font_id == 0 else 240 if small else 1
        local_slot = default_slot - 240 if small else default_slot
        x = local_slot % (8 if small else 16) * stride + 1
        y = local_slot // (8 if small else 16) * (18 if small else 34) + 1
        fallback_uv = ((x + .5) / dim, (y + .5) / dim)
        block = bytearray(fresh[info['offset']:info['offset'] + 0x7c])
        struct.pack_into('<I', block, 0x78, 1)
        ph = bytearray(fresh[info['offset'] + 0x7c:info['offset'] + 0xf8])
        texture = '\\fonts\\' + ('zhcache_small.tga' if small else 'zhcache_big.tga')
        ph[:100] = texture.encode().ljust(100, b'\0')
        struct.pack_into('<HHIII', ph, 0x6c, records[0][3], records[-1][3], dim, dim, len(records))
        block.extend(ph)
        for index, (_, _, advance, code, extra) in enumerate(records):
            assert advance == int(advance) and 0 < advance <= stride - 2
            tile = bytearray([255 if small else 0]) * tile_bytes
            unpacked = glyphs.tile((name, code))
            for yy in range(sample):
                for xx in range(int(advance)):
                    put(tile, stride, xx, yy, unpacked[yy * int(advance) + xx])
            if code == 63:
                atlas = atlases['small' if small else 'large']
                for yy in range(sample):
                    for xx in range(int(advance)):
                        put(atlas, dim, x + xx, y + yy, unpacked[yy * int(advance) + xx])
            packed = lz4.block.compress(bytes(tile), mode='high_compression', compression=12, store_size=False)
            mode = int(len(packed) < len(tile))
            if not mode: packed = bytes(tile)
            record_bytes = struct.pack('<HH', mode, len(packed)) + packed
            # One glyph record never crosses an existing native 48 KiB read buffer.
            if len(bank) // 0xc000 != (len(bank) + len(record_bytes) - 1) // 0xc000:
                bank.extend(b'\0' * (align(len(bank), 0xc000) - len(bank)))
            offsets.append(len(bank)); bank.extend(record_bytes); bank.extend(b'\0' * (-len(bank) % 4))
            restored = lz4.block.decompress(packed, uncompressed_size=tile_bytes) if mode else packed
            assert restored == tile
            encoded_tiles.append((mode, packed)); expected_tiles.append(bytes(tile))
            block.extend(struct.pack('<fffHh', *fallback_uv, advance, code, extra))
        struct.pack_into('<I', block, 4, len(block))
        font_blocks[info['offset']] = bytes(block)

    identity = b'ZHFCBANK' + struct.pack('<II', 1, len(offsets)) + hashlib.sha256(fresh).digest()[:16]
    bank[:32] = identity
    bank.extend(b'\0' * (-len(bank) % 2048))
    big_res = resource(templates[BIG], '\\graphics\\fonts\\zhcache_big.tm2', 512, 512, atlases['large'], glyphs.palettes[BIG])
    tiny_res = resource(templates[SMALL], '\\graphics\\fonts\\zhcache_small.tm2', 128, 128, atlases['small'], glyphs.palettes[SMALL])
    result = bytearray(fresh[:8]); inserted = False
    for tag, pos, size in chunks(fresh):
        if pos in remove: continue
        if tag == b'FONT' and not inserted:
            result.extend(big_res); result.extend(tiny_res); inserted = True
        result.extend(font_blocks.get(pos, fresh[pos:pos + size]))
    result.extend(fresh[-4:])
    parsed = parse_pages(result)
    for name, cursor, base in refs:
        info = next(v for k,v in parsed.items() if k.lower() == name.lower())
        struct.pack_into('<II', result, cursor, info['offset'] - base, info['size'])
    rsfl_entries(result, parsed)
    for name in NAMES:
        old = sorted((r[2:] for p in definitions[name]['pages'] for r in p['records']), key=lambda r:r[1])
        new = [r[2:] for r in parsed[name]['pages'][0]['records']]
        assert old == new, ('Metrics/code/kerning index changed', name)
        assert fresh[definitions[name]['offset'] + 0x74:definitions[name]['offset'] + 0x78] == \
               result[parsed[name]['offset'] + 0x74:parsed[name]['offset'] + 0x78]
    from build_resident_glyphs import build as build_resident
    runtime_offsets, resident_header, resident_report, resident_manifest, profiles = build_resident(
        ROOT, parsed, NAMES, bank, offsets, subtitle_texts, subtitle_by_level)
    (OUT/'resident_manifest.json').write_text(json.dumps(resident_manifest,indent=2)+'\n',encoding='utf-8')
    header = '/* Generated from freshly rendered sources; do not hand edit. */\n'
    header += 'static const FontConfig font_config[3] = {' + ','.join('{' + ','.join(map(str,s)) + '}' for s in specs) + '};\n'
    header += 'static const u8 bank_identity[32] = {' + ','.join(map(str,identity)) + '};\n'
    header += 'static const u32 bank_offsets[] = {\n' + ',\n'.join(','.join(map(str,runtime_offsets[i:i+16])) for i in range(0,len(offsets),16)) + '\n};\n'
    header += resident_header
    return bytes(result), bytes(bank), header, dict(
        glyphs=len(offsets), fonts=[dict(font=n, count=s[1], fallback_index=s[3]) for n,s in zip(NAMES,specs)],
        atlas_bytes=139264, slots=288, reserved_slots=5,
        native_glyph_record_bytes=len(offsets)*16, bank_index_bytes=len(offsets)*4,
        bank_bytes=len(bank), all_bank_glyphs_roundtrip=True, all_metrics_preserved=True,
        bank_identity=identity.hex(), metadata_glyph_limit=4096, resident=resident_report,
    ), encoded_tiles, expected_tiles, profiles


def compile_runtime(header):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'bank_config.h').write_text(header, encoding='ascii')
    link = '''SECTIONS {
 . = 0x59b000; __patch_start = .;
 .text : { *(.text .text.*) }
 .rodata : { *(.rodata .rodata.*) }
 .data : { *(.data .data.*) }
 . = ALIGN(16); .bss : { *(.bss .bss.* COMMON) }
 . = ALIGN(128); __patch_end = .;
 /DISCARD/ : { *(.reginfo .MIPS.abiflags .pdr .comment .gnu.attributes .eh_frame .mdebug.*) }
}
'''
    (OUT/'patch.ld').write_text(link, encoding='ascii')
    common = ['-march=r5900','-mfix-r5900','-mabi=eabi','-mgp64','-mlong32',
              '-mpreferred-stack-boundary=4','-G0','-mno-abicalls','-fno-pic',
              '-fno-builtin','-ffreestanding','-fno-stack-protector','-fno-strict-aliasing','-O2',
              '-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-I',str(OUT)]
    subprocess.run([str(COMPILER),*common,'-msoft-float','-c',str(RUNTIME/'runtime.c'),'-o',str(OUT/'runtime.o')],check=True)
    subprocess.run([str(COMPILER),*common,'-mhard-float','-c',str(RUNTIME/'hooks.S'),'-o',str(OUT/'hooks.o')],check=True)
    subprocess.run([str(COMPILER),'-march=r5900','-mabi=eabi','-mgp64','-mlong32','-nostdlib',
                    '-Wl,--no-warn-mismatch','-Wl,-T,'+str(OUT/'patch.ld'),'-Wl,-Map,'+str(OUT/'patch.map'),
                    str(OUT/'hooks.o'),str(OUT/'runtime.o'),'-o',str(OUT/'patch.elf')],check=True)
    subprocess.run([str(OBJCOPY),'-O','binary',str(OUT/'patch.elf'),str(OUT/'patch.bin')],check=True)
    syms = subprocess.check_output([str(NM),'-n',str(OUT/'patch.elf')],text=True)
    (OUT/'symbols.txt').write_text(syms,encoding='ascii')
    symbols = {line.split()[2]:int(line.split()[0],16) for line in syms.splitlines() if len(line.split()) == 3}
    disasm = subprocess.check_output([str(OBJDUMP),'-d',str(OUT/'patch.elf')],text=True)
    (OUT/'disassembly.txt').write_text(disasm,encoding='ascii')
    assert not subprocess.check_output([str(NM),'-u',str(OUT/'patch.elf')],text=True).strip(), 'Unresolved runtime symbol'
    end = symbols['__patch_end']
    blob = bytearray((OUT/'patch.bin').read_bytes())
    assert len(blob) <= end - BASE
    blob.extend(b'\0' * (end - BASE - len(blob)))
    struct.pack_into('<I',blob,symbols['zh_diagnostics'] - BASE + 80,end - 0x59af4c)
    (OUT/'patch.bin').write_bytes(blob)
    return bytes(blob), symbols


def patch_elf(base, blob, symbols, frame_safe=False):
    assert sha(base) == BASE_ELF_SHA, 'Unrecognized base ELF; preserve/review newer modifications'
    ph = struct.unpack_from('<8I',base,52)
    assert ph[:4] == (1,128,0x100000,0x100000) and ph[4:6] == (4037784,4829004)
    data = bytearray(base[:128 + ph[4]])
    data.extend(b'\0' * (128 + BASE - 0x100000 - len(data))); data.extend(blob)
    changes = []
    def write(va, expected, replacement, purpose):
        off = va - 0x100000 + 128
        assert struct.unpack_from('<I',data,off)[0] == expected, (hex(va), purpose)
        struct.pack_into('<I',data,off,replacement)
        changes.append(dict(address=hex(va),before=hex(expected),after=hex(replacement),purpose=purpose))
    for va, name, first, second in (
        (0x2064f8,'zh_draw_hook',0x27bdff90,0xffb00010),
        (0x207470,'zh_text_hook',0x27bdff00,0x3c020048),
        (0x208230,'zh_register_hook',0x3c020058,0x0080402d),
        (0x1a3a68,'zh_open_hook',0x27bdffe0,0x3c020058),
    ):
        write(va,first,0x08000000 | (symbols[name] >> 2),name)
        write(va+4,second,0,'hook delay slot; displaced instruction is in trampoline')
    for va in (0x44a0e0,0x44a0f4,0x44a568):
        write(va,0x0c108bd2,0x0c000000 | (symbols['zh_tree_alloc_guard'] >> 2),'spatial tree allocation failure cleanup')
    if frame_safe:
        for va, original, hook in (
            (0x259650, 0x424fd8, 'zh_frame_vsync_guard'),
            (0x259658, 0x2596f0, 'zh_frame_blend_guard'),
        ):
            write(va,0x0c000000 | (original >> 2),0x0c000000 | (symbols[hook] >> 2),
                  'consume early display preparation once at native frame end: '+hook)
    for va, original, hook in (
        (0x210a4c, 0x0c0846c2, 'zh_logo_subtitle_prepare'),
        (0x22b940, 0x0c08470c, 'zh_subtitle_before_gui'),
        (0x30cbc0, 0x0c0f2532, 'zh_logo_subtitle_after_gui'),
        (0x30cff0, 0x0c0f2532, 'zh_logo_subtitle_after_gui'),
    ):
        write(va, original, 0x0c000000 | (symbols[hook] >> 2), hook)
    # Ghidra FUN_00206e08 supplies BOTH line measurement and draw break flags.
    # Keep its 00206F60 delay slot (li v0,0x3002) and all explicit '-' glyphs.
    write(0x206f5c,0x12e0005e,0x08000000 | (symbols['zh_wrap_boundary_hook'] >> 2),
          'CJK boundaries use native character wrapping; Latin keeps word wrapping')
    write(0x2070c8,0x4600adc6,0x460015c6,
          'CJK candidate width includes the last fitting glyph (f23=f2)')
    write(0x2070cc,0x24140003,0x24140002,
          'CJK break kind does not append or reserve a synthetic hyphen')
    write(0x48a1c4,0x59af4c,symbols['__patch_end'],'reserve patch code/state before initial sbrk')
    end = symbols['__patch_end']
    write(0x1001d0,0x3c04005a,0x3c040000 | ((end + 0x8000) >> 16),'SetupHeap start after patch')
    write(0x1001d8,0x2484af4c,0x24840000 | (end & 65535),'SetupHeap start after patch')
    # The game allocator does NOT use libc sbrk/SetupHeap as its source.
    # 002420C8 rounds this independently linked end address up to a 4 KiB page.
    # Leaving it unchanged makes dlmalloc allocate over the appended code.
    write(0x2420c8,0x3c02005a,0x3c020000 | ((end + 0x8000) >> 16),
          'native game heap source after patch (high)')
    write(0x2420d0,0x2442af4c,0x24420000 | (end & 65535),
          'native game heap source after patch (low)')
    # Keep startup BSS clearing at its ORIGINAL end; extending it would erase code.
    assert struct.unpack_from('<I',data,0x128+128)[0] == 0x2463af4c
    size = symbols['__patch_end'] - 0x100000
    struct.pack_into('<II',data,52+16,size,size)
    # Original debug section table lies beyond the old LOAD segment; strip it.
    struct.pack_into('<I',data,32,0)
    struct.pack_into('<HHH',data,46,0,0,0)
    assert len(data) == 128 + size
    return bytes(data), changes


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install',action='store_true')
    hardware = parser.add_mutually_exclusive_group()
    hardware.add_argument('--hardware-freeze-glyphs', action='store_true',
                        help='DIAGNOSTIC ONLY: freeze all glyph-cache misses in levels; uncached text uses question marks')
    hardware.add_argument('--hardware-native-sync', action='store_true',
                        help='HARDWARE TEST: keep full text and native DMA waits, omit the extra private GS FINISH handshake')
    hardware.add_argument('--hardware-selective-textures', action='store_true',
                        help='HARDWARE TEST: retain original DMA/GS sync; invalidate only modified font textures')
    hardware.add_argument('--hardware-frame-safe', action='store_true', default=None,
                        help='Enable the hardware flicker fix (default: shared build settings)')
    hardware.add_argument('--no-hardware-frame-safe', action='store_false', dest='hardware_frame_safe',
                        help='Disable the hardware flicker fix for this build')
    reuse = parser.add_mutually_exclusive_group()
    reuse.add_argument('--reviewed-only', action='store_true', default=None)
    reuse.add_argument('--all-saved', action='store_false', dest='reviewed_only')
    return parser.parse_args(argv)


def resolve_hardware_frame_safe(args, settings):
    if args.hardware_frame_safe is not None:
        return args.hardware_frame_safe
    # Explicit historical experiments remain isolated from the default fix.
    if args.hardware_freeze_glyphs or args.hardware_native_sync or args.hardware_selective_textures:
        return False
    return settings['build']['hardware_frame_safe']


def resolve_elf_base(previous_elf):
    """Recognize pristine extraction, canonical base, or the exact installed build."""
    digest = sha(previous_elf)
    if digest == ORIGINAL_ELF_SHA:
        base = bytearray(previous_elf)
        # Same verified initialization as the release workspace's init command.
        for va, before, after in (
            (0x3D19C4, 0x93829271, 0x24020001),
            (0x3D1A14, 0x3C013A4C, 0x3C013A66),
            (0x3D1A18, 0x3421CCCD, 0x34216666),
            (0x3D1A74, 0x3C05FFFF, 0x3C05FFCC),
            (0x3D1A90, 0x34A5C080, 0x34A5FFFF),
        ):
            offset = va - 0x100000 + 0x80
            if struct.unpack_from('<I', base, offset)[0] != before:
                raise ValueError(f'原版字幕基础指令不符：{va:#x}')
            struct.pack_into('<I', base, offset, after)
        if sha(base) != BASE_ELF_SHA:
            raise ValueError('原版字幕基础初始化校验失败。')
        return bytes(base), 'verified_original'
    if digest == BASE_ELF_SHA:
        return previous_elf, 'verified_subtitle_base'
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    if not state.get('installed') or digest != state.get('elf_sha256'):
        raise ValueError('无法识别当前 ELF：既非已验证原版/字幕基础，也不匹配上次安装报告；'
                         f'为保留未知修改，已停止构建。当前 SHA256={digest}')
    base = (BACKUP/'slus_217.46').read_bytes()
    if sha(base) != BASE_ELF_SHA:
        raise ValueError('动态字幕基础备份校验失败，已停止构建。')
    return base, 'verified_installed_build'


def main():
    args = parse_args()
    settings_hash = sha(SETTINGS_PATH.read_bytes())
    settings = load_settings()
    reviewed_only = settings['build']['reviewed_only'] if args.reviewed_only is None else args.reviewed_only
    args.hardware_frame_safe = resolve_hardware_frame_safe(args, settings)
    print('HARDWARE FLICKER FIX: ' + ('enabled' if args.hardware_frame_safe else 'disabled'), flush=True)
    print('SUBTITLE SHADOW: ' + ('native deep' if settings['subtitles']['shadow'] else 'disabled'), flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    elf_path = ROOT/'ISO_UNPACK/slus_217.46'
    previous_elf = elf_path.read_bytes()
    input_elf_sha = sha(previous_elf)
    base, input_elf_kind = resolve_elf_base(previous_elf)
    if input_elf_kind == 'verified_original':
        if not args.install:
            raise ValueError('首次从原版初始化请使用 GUI 或一键构建ISO.bat（完整 --install 流程）。')
        # Initialize only an exact original inside the complete install workflow.
        # Never replace an unknown/installed ELF or modify the protected backup.
        assert elf_path.read_bytes() == previous_elf, 'ELF changed before initialization'
        elf_path.write_bytes(base)
        assert elf_path.read_bytes() == base, 'Subtitle base initialization readback failed'
        previous_elf = base
        print('VERIFIED ORIGINAL ELF: initialized the canonical subtitle base for the complete build.', flush=True)
    # This executes the real full renderer on FONT/source on EVERY invocation.
    has_l1 = (ROOT/'SOUND/subtitles/L1_Gcan_am/whisper_results.json').exists() and \
             struct.unpack_from('<I',previous_elf,0x3d19c4-0x100000+128)[0] == 0x24020001
    has_workspace = (ROOT/'SOUND/voice_work/catalog.json').exists()
    builder = 'build_all_subtitles.py' if has_l1 and has_workspace else 'build_l1_subtitles.py' if has_l1 else 'build_menu_hints_zh.py'
    command = [sys.executable,'-X','utf8',str(ROOT/'scripts'/builder)]
    if args.install: command.append('--install')
    if reviewed_only and builder == 'build_all_subtitles.py': command.append('--reviewed-only')
    subprocess.run(command,check=True)
    regular = json.loads((ROOT/'TEMP/builds/menu_hints_zh/build_report.json').read_text(encoding='utf-8'))
    fresh_path = ROOT/'TEMP/builds/menu_hints_zh/rebuilt/Fonts/ntsc_fon.asr'
    fresh = fresh_path.read_bytes()
    assert sha(fresh) == regular['files']['Fonts/ntsc_fon.asr']['after']
    assert sha(SETTINGS_PATH.read_bytes()) == settings_hash, 'Build settings changed during the build'
    for font in regular['fonts']:
        assert font['rebuild_mode'] == 'all_glyphs_from_current_font_files'
        assert sha((ROOT/font['source_font']).read_bytes()) == font['source_font_sha256']
        assert sha((ROOT/font['fallback_font']).read_bytes()) == font['fallback_font_sha256']
        assert sha((ROOT/font['render_settings']).read_bytes()) == font['render_settings_sha256'], \
            'Font render settings changed during the build'
    subtitle_sources = regular.get('subtitle_glyph_sources', [regular['subtitle_glyph_source']])
    subtitle_texts = [r['text'] for path in subtitle_sources
                      for r in locate_text(Path(path).read_bytes()) if r['kind'] == 'DLLN']
    subtitle_by_level = {Path(path).stem: [r['text'] for r in locate_text(Path(path).read_bytes())
                                          if r['kind'] == 'DLLN'] for path in subtitle_sources}
    font, bank, header, details, _, _, profiles = build_resources(fresh, subtitle_texts, subtitle_by_level)
    header += f'\n#define ZH_HARDWARE_FREEZE_GLYPHS {int(args.hardware_freeze_glyphs)}\n'
    header += f'#define ZH_HARDWARE_NATIVE_SYNC {int(args.hardware_native_sync)}\n'
    header += f'#define ZH_HARDWARE_SELECTIVE_TEXTURES {int(args.hardware_selective_textures)}\n'
    header += f'#define ZH_HARDWARE_FRAME_SAFE {int(args.hardware_frame_safe)}\n'
    blob, symbols = compile_runtime(header)
    elf, patches = patch_elf(base,blob,symbols,frame_safe=args.hardware_frame_safe)
    elf, subtitle_style = apply_style(elf, settings)
    patches.extend(subtitle_style['patches'])
    outputs = {'Fonts/ntsc_fon.asr':font,'Fonts/ZHGLYPH.BIN':bank,'slus_217.46':elf}
    outputs.update(profiles)
    for name, content in outputs.items():
        p = OUT/'rebuilt'/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(content)
    report = dict(details, installed=False, runtime_validation='pending_user_test',
                  build_settings=settings, build_settings_sha256=settings_hash,
                  subtitle_style=subtitle_style, translation_sync_mode='reviewed_only' if reviewed_only else 'all_saved',
                  source_font_reports=regular['fonts'], freshly_rendered_asr_sha256=sha(fresh),
                  font_sha256=sha(font), bank_sha256=sha(bank), elf_sha256=sha(elf),
                  base_elf_sha256=sha(base), patch_bytes=len(blob),
                  input_elf={'kind': input_elf_kind, 'sha256': input_elf_sha,
                             'initialized_subtitle_base': input_elf_kind == 'verified_original'},
                  patch_start=hex(BASE), patch_end=hex(symbols['__patch_end']),
                  native_heap_start=hex(align(symbols['__patch_end'], 4096)),
                  diagnostics_address=hex(symbols['zh_diagnostics']), symbols={k:hex(v) for k,v in symbols.items()},
                  hardware_diagnostic={
                      'mode': 'freeze_glyphs_in_levels' if args.hardware_freeze_glyphs else 'normal',
                      'enabled': args.hardware_freeze_glyphs,
                      'state_address': hex(symbols['zh_hardware_diagnostic']),
                      'state_words': ['magic', 'version', 'enabled', 'in_level', 'suppressed_batches', 'profile_trigger'],
                      'activation': 'level_open_trigger_independent_of_preload_success',
                      'uncached_glyphs': 'question_mark_slot' if args.hardware_freeze_glyphs else 'normal_load',
                      'subtitle_timing_and_layout_preserved': True,
                      'main_menu_cache_updates_enabled': True,
                  },
                  hardware_sync={
                      'mode': 'native_dma_only' if args.hardware_native_sync else 'native_dma_plus_private_gs_finish',
                      'enabled': args.hardware_native_sync,
                      'state_address': hex(symbols['zh_hardware_sync']),
                      'state_words': ['magic', 'version', 'enabled', 'native_sync_batches'],
                      'native_batch_flush_and_chain_submit': True,
                      'native_dma_waits_per_batch': 2,
                      'private_finish_packet_and_csr_handshake': not args.hardware_native_sync,
                      'full_glyph_loading': not args.hardware_freeze_glyphs,
                      'runtime_validation': 'pending_user_hardware_test',
                  },
                  profile_diagnostics_address=hex(symbols['zh_profile_diagnostics']),
                  hardware_texture={
                      'mode': 'modified_font_textures_only' if args.hardware_selective_textures else 'all_four_residency_slots',
                      'enabled': args.hardware_selective_textures,
                      'state_address': hex(symbols['zh_hardware_texture']),
                      'state_words': ['magic', 'version', 'enabled', 'dirty_batches', 'invalidated_slots'],
                      'residency_table_address': '0x481918',
                      'residency_slots': 4,
                      'preserves_unmodified_texture_residency': args.hardware_selective_textures,
                      'runtime_validation': 'pending_user_hardware_test',
                  },
                  hardware_frame={
                      'mode': 'prepare_scanout_before_glyph_submit' if args.hardware_frame_safe else 'native_frame_end_only',
                      'enabled': args.hardware_frame_safe,
                      'state_address': hex(symbols['zh_hardware_frame']),
                      'state_words': ['magic', 'version', 'enabled', 'prepared', 'early_preparations', 'consumed_preparations', 'original_buffer_index'],
                      'native_frame_end_hooks_installed': args.hardware_frame_safe,
                      'vsync_call_site': '0x259650', 'blend_call_site': '0x259658',
                      'additional_pixel_buffers': 0,
                      'runtime_validation': 'pending_user_hardware_test',
                      'prior_user_hardware_feedback': {
                          'date': '2026-10-08',
                          'setup': 'PS2 / OPL + USB',
                          'result': 'no_flicker_in_user_tested_scene',
                          'tested_iso_sha256': 'c03b597f35a636bffd0308af5a4a24a962b3ab685f98ae09d93647740b0aef74',
                          'full_playthrough_retested': False,
                      } if args.hardware_frame_safe else None,
                  },
                  l1_logo_subtitles={'names': ['L1_Intro_2', 'L1_Intro_3'],
                      'draw_after_gui': True, 'native_timing_once_per_frame': True,
                      'state_address': hex(symbols['zh_logo_subtitle_active'])},
                  profile_sha256={name:sha(content) for name,content in profiles.items()},
                  patches=patches, native_io_buffers_reused=True, retained_file_handle=False,
                  source_text_report=regular['files'], test_iso='COD5_TEST.iso',
                  subtitle_am_sha256={f'Envs/sp/{Path(path).name}':sha(Path(path).read_bytes())
                                      for path in subtitle_sources})
    (OUT/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Runtime CPU tests run before installation; they use the compiled C core.
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/test_dynamic_font_runtime.py')],check=True)
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/test_dynamic_font_mips.py')],check=True)
    if args.install:
        assert sha(SETTINGS_PATH.read_bytes()) == settings_hash, 'Build settings changed before installation'
        assert (ROOT/'ISO_UNPACK/slus_217.46').read_bytes() == previous_elf
        assert (ROOT/'ISO_UNPACK/Fonts/ntsc_fon.asr').read_bytes() == fresh
        BACKUP.mkdir(parents=True,exist_ok=True)
        if not (BACKUP/'slus_217.46').exists(): (BACKUP/'slus_217.46').write_bytes(base)
        if not (BACKUP/'ntsc_fon.asr').exists(): (BACKUP/'ntsc_fon.asr').write_bytes(fresh)
        previous = {name:(ROOT/'ISO_UNPACK'/name).read_bytes() if (ROOT/'ISO_UNPACK'/name).exists() else None for name in outputs}
        try:
            for name, content in outputs.items():
                target = ROOT/'ISO_UNPACK'/name; target.write_bytes(content)
                assert target.read_bytes() == content
        except Exception:
            for name, old in previous.items():
                target = ROOT/'ISO_UNPACK'/name
                if old is not None: target.write_bytes(old)
                elif target.exists(): target.unlink()
            raise
        report['installed'] = True
        STATE.parent.mkdir(parents=True,exist_ok=True)
        STATE.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        STYLE_REPORT.parent.mkdir(parents=True, exist_ok=True)
        STYLE_REPORT.write_text(json.dumps(subtitle_style,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (OUT/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('glyphs','atlas_bytes','bank_bytes','patch_bytes','diagnostics_address','installed')},ensure_ascii=False))


if __name__ == '__main__': main()
