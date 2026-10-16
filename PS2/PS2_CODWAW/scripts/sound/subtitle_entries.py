"""Stable review keys for audio subtitles and explicitly registered DLLN text."""
from pathlib import Path


def unbanked_key(row):
    return f"DLLN:{row['sound_name']}:{row['sound_id']:08X}"


def entry_key(row):
    if row.get('entry_kind') == 'unbanked_dlln':
        key = unbanked_key(row)
        if row.get('entry_key') != key:
            raise ValueError('Supplemental DLLN key differs from its exact name and sound ID')
        return key
    return Path(row['file']).with_suffix('.mp3').name


def review_entries(manifest):
    entries = [*manifest.get('entries', []), *manifest.get('supplemental_entries', [])]
    keys = [entry_key(row) for row in entries]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate subtitle entry key in manifest')
    return entries
