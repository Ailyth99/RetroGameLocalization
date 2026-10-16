"""Apply configured subtitle style as part of the complete dynamic-font build."""
import argparse
import hashlib
import json
import struct
import subprocess

from build_settings import ROOT, ensure_build_idle, load_settings, normalize, save_settings

REPORT = ROOT / 'SOUND/subtitles/subtitle_style.json'


def apply_style(elf, settings):
    """Patch a freshly generated ELF, preserving the immutable dynamic base."""
    style = normalize(settings)['subtitles']
    multiplier = style['scale_percent'] / 100
    bits = struct.unpack('<I', struct.pack('<f', multiplier / 1280))[0]
    color = 0xFF000000 | int(style['color'][1:], 16)
    data = bytearray(elf)
    # Expected values are from the hash-checked dynamic base, not the installed ELF.
    patches = [
        (0x003D1A14, 0x3C013A66, 0x3C010000 | (bits >> 16)),
        (0x003D1A18, 0x34216666, 0x34210000 | (bits & 0xFFFF)),
        (0x003D1A74, 0x3C05FFCC, 0x3C050000 | (color >> 16)),
        (0x003D1A90, 0x34A5FFFF, 0x34A50000 | (color & 0xFFFF)),
        (0x003D1A8C, 0x24060184, 0x24062184 if style['shadow'] else 0x24060184),
    ]
    for va, before, after in patches:
        offset = va - 0x100000 + 0x80
        actual = struct.unpack_from("<I", data, offset)[0]
        if actual != before:
            raise ValueError(f"Unexpected instruction at {va:#x}: {actual:#x}")
        struct.pack_into("<I", data, offset, after)
    if struct.unpack_from("<I", data, 0x3D19C4 - 0x100000 + 0x80)[0] != 0x24020001:
        raise ValueError('Native subtitle enable patch missing')
    report = {
        'color_before': '0xFFCCFFFF', 'color_after': f'0x{color:08X}',
        'color': style['color'], 'rgb': [(color >> shift) & 255 for shift in (16, 8, 0)],
        'scale_percent': style['scale_percent'], 'scale_multiplier': multiplier,
        'scale_constant': multiplier / 1280,
        'shadow': {'enabled': style['shadow'], 'mode': 'native_deep' if style['shadow'] else 'off',
                   'flag': '0x2000' if style['shadow'] else '0x0',
                   'color': '#000000', 'alpha_at_full_opacity': 160,
                   'offset_draw_units': [1.5, 1.5], 'shared_glyph_texture': True},
        'patches': [dict(address=hex(v), before=hex(b), after=hex(a),
                         purpose='configured subtitle shadow' if v == 0x003D1A8C else
                                 'configured subtitle color/scale') for v, b, a in patches],
        'elf_sha256': hashlib.sha256(data).hexdigest(),
        'runtime_validation': 'pending_user_test', 'iso': 'COD5_TEST.iso',
    }
    return bytes(data), report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--color', help='RGB hex color, e.g. #CCFFFF')
    parser.add_argument('--scale-percent', type=float)
    shadow = parser.add_mutually_exclusive_group()
    shadow.add_argument('--shadow', action='store_true', default=None)
    shadow.add_argument('--no-shadow', action='store_false', dest='shadow')
    parser.add_argument('--save-only', action='store_true')
    args = parser.parse_args()
    ensure_build_idle()
    settings = load_settings()
    if args.color is not None: settings['subtitles']['color'] = args.color
    if args.scale_percent is not None: settings['subtitles']['scale_percent'] = args.scale_percent
    if args.shadow is not None: settings['subtitles']['shadow'] = args.shadow
    settings = save_settings(settings)
    print(json.dumps(settings['subtitles']), flush=True)
    if not args.save_only:
        subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                        '-File', str(ROOT / 'scripts/build_chinese_test.ps1')], check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
