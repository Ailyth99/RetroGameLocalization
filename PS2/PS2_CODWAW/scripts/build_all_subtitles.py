"""Merge saved voice-work translations, rebuild all AM banks and render fonts once."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys

from game_text_resources import ROOT, OriginalResources
import build_start_menu_zh as s
from build_l1_subtitles import rebuild

sys.path.insert(0, str(ROOT / 'scripts/sound'))
from review_server import ReviewStore
from voice_sync import make_plan, apply_plan

OUT = ROOT / 'SOUND/subtitles/build_all'
STATE = OUT / 'installed_build.json'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--reviewed-only', action='store_true',
                        help='Only reuse reviewed workspace translations; default includes all saved translations')
    parser.add_argument('--plan', action='store_true', help='Show merge counts without writing or building')
    args = parser.parse_args()
    store = ReviewStore(ROOT / 'SOUND/subtitles')
    plan = make_plan(store, reviewed_only=args.reviewed_only)
    preview = plan['preview']
    print(json.dumps({'stage': 'subtitle_merge', 'mode': 'reviewed_only' if args.reviewed_only else 'all_saved',
                      'updates': preview['updates'], 'levels': preview['levels'],
                      'independent_edits_preserved': preview['conflict_count'],
                      'variants_awaiting_review': preview['variant_blocked']}, ensure_ascii=False), flush=True)
    if args.plan:
        return
    if args.install:
        apply_plan(store, preview['revision'], reviewed_only=args.reviewed_only)
    # Staging uses the same planned translations without changing editable JSON.
    installed = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    previous, outputs, reports, snapshots = {}, {}, {}, {}
    for filename in plan['snapshots']:
        path = Path(filename)
        if path.is_relative_to(store.workspace):
            snapshots[path] = path.read_bytes() if path.exists() else None
    elf_path = ROOT / 'ISO_UNPACK/slus_217.46'
    elf_before = elf_path.read_bytes()
    s.require(struct.unpack_from('<I', elf_before, 0x3D19C4 - 0x100000 + 0x80)[0] == 0x24020001,
              'Native subtitle renderer is not enabled')
    with OriginalResources() as original:
        for level, directory in store.directories().items():
            if directory.resolve().parent != store.root:
                continue
            manifest_path = directory / 'manifest.json'
            manifest_raw = manifest_path.read_bytes()
            manifest = json.loads(manifest_raw.decode('utf-8-sig'))
            filename = level[:-3] + '.am'
            relative = 'Envs/sp/' + filename
            source = original.read(relative)
            s.require(s.sha256(source) == manifest['source_sha256'], f'Original AM differs from manifest: {level}')
            spec, raw, document = store.load_document(directory)
            if not args.install and level in plan['updates']:
                document = plan['updates'][level]['output']
            translations = {name: {'translation': value.get('translation', '') if isinstance(value, dict) else ''}
                            for name, value in document.items()}
            am, entries, delta = rebuild(source, translations, allow_unbanked_dlln=True)
            target = ROOT / 'ISO_UNPACK' / relative
            before = target.read_bytes()
            allowed = {s.sha256(source), s.sha256(am)}
            last = installed.get('levels', {}).get(level, {})
            if installed.get('installed'):
                allowed.add(last.get('am_sha256'))
            legacy_report = directory / 'build/build_report.json'
            if legacy_report.exists():
                legacy = json.loads(legacy_report.read_text(encoding='utf-8'))
                if legacy.get('installed'):
                    allowed.add(legacy.get('am_sha256'))
            s.require(s.sha256(before) in allowed, f'AM contains unrecognized newer changes: {level}')
            staged = OUT / 'rebuilt' / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(am)
            previous[relative], outputs[relative] = before, am
            snapshots[spec] = raw
            snapshots[manifest_path] = manifest_raw
            reports[level] = {
                'translation_source': str(spec.relative_to(ROOT)), 'translation_sha256': s.sha256(raw or b''),
                'entries': entries, 'translated': sum(bool(e['translation']) for e in entries),
                'blank': sum(not e['translation'] for e in entries),
                'original_bytes': len(source), 'rebuilt_bytes': len(am),
                'streamed_audio_offset_delta': delta, 'all_vag_bytes_preserved': True,
                'unbanked_dlln_preserved': not any(e.get('modified') for e in entries if e.get('entry_kind') == 'unbanked_dlln'),
                'supplemental_entries': sum(e.get('entry_kind') == 'unbanked_dlln' for e in entries),
                'supplemental_translated': sum(bool(e.get('modified')) for e in entries if e.get('entry_kind') == 'unbanked_dlln'),
                'am_sha256': s.sha256(am),
                'target': relative, 'installed': False,
            }
            print(f"{filename}: {reports[level]['translated']} translated / {len(entries)} subtitle entries", flush=True)
    s.require(outputs, 'No subtitle levels found')
    command = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'scripts/build_menu_hints_zh.py')]
    for relative in outputs:
        command += ['--subtitle-am', str(OUT / 'rebuilt' / relative)]
    if args.install:
        command.append('--install')
    subprocess.run(command, check=True)
    for path, expected in snapshots.items():
        s.require((path.read_bytes() if path.exists() else None) == expected,
                  f'Subtitle input changed during build: {path}')
    s.require(elf_path.read_bytes() == elf_before, 'ELF changed during subtitle build')
    for relative, before in previous.items():
        s.require((ROOT / 'ISO_UNPACK' / relative).read_bytes() == before, f'AM changed during build: {relative}')
    if args.install:
        try:
            for relative, am in outputs.items():
                target = ROOT / 'ISO_UNPACK' / relative
                target.write_bytes(am)
                s.require(target.read_bytes() == am, f'AM install readback mismatch: {relative}')
        except Exception:
            for relative, before in previous.items():
                (ROOT / 'ISO_UNPACK' / relative).write_bytes(before)
            raise
        for level, report in reports.items():
            report['installed'] = True
            write_json(store.level(level) / 'build/build_report.json', report)
    result = {'installed': args.install, 'mode': 'reviewed_only' if args.reviewed_only else 'all_saved',
              'merge': preview, 'levels': reports, 'runtime_validation': 'pending_user_test'}
    write_json(OUT / 'build_report.json', result)
    if args.install:
        write_json(STATE, result)
    print(json.dumps({'stage': 'subtitles_complete', 'levels': len(reports),
                      'translated': sum(r['translated'] for r in reports.values()),
                      'installed': args.install}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
