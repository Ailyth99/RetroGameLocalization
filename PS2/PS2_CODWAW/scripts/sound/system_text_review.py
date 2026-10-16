"""Adapt the single system-text catalog to the existing review UI."""
from copy import deepcopy
from hashlib import sha256
import json
import re
from system_text_rules import is_staffroll_reference, preserved_english_reason

COLLECTION_ID = 'system_text'
CATALOG_NAME = '菜单与提示译文.json'
GROUPS = {'menu': '菜单 / 存档提示', 'weapons': '武器 / 弹药名称',
          'names': '军衔 / 人名', 'general': '通用提示', 'staffroll': 'STAFFROLL · 保留英文'}


def groups_for(entry):
    groups = set()
    for ref in entry['references']:
        file, key = ref['file'], ref['key']
        if file == 'Misc/Menu/Menu_Am.asr':
            groups.add('staffroll' if is_staffroll_reference(ref) else 'menu')
        elif file == 'Text/american.asr':
            index = int(key.split(':')[1]) if key.startswith('LTXT:') else -1
            if 8 <= index <= 43 or 63 <= index <= 67 or index == 208:
                groups.add('weapons')
            elif 75 <= index <= 207:
                groups.add('names')
            else:
                groups.add('general')
        else:
            match = re.fullmatch(r'Envs/sp/(L\d+_[A-Za-z0-9]+)\.ps2', file)
            groups.add(match[1] if match else 'general')
    return sorted(groups)


class SystemTextReview:
    def __init__(self, path, store):
        self.path, self.store = path, store

    def document(self):
        if self.path.is_symlink():
            raise self.store.error('系统译文 JSON 必须是普通文件')
        raw = self.path.read_bytes()
        try:
            document = json.loads(raw.decode('utf-8-sig'))
        except (ValueError, UnicodeError) as error:
            raise self.store.error(f'系统译文 JSON 无法读取：{error}') from error
        if not isinstance(document, dict) or not isinstance(document.get('entries'), list):
            raise self.store.error('系统译文缺少 entries 列表')
        seen = set()
        for item in document['entries']:
            if (not isinstance(item, dict) or not isinstance(item.get('id'), str)
                    or item['id'] in seen or not isinstance(item.get('en'), str)
                    or not isinstance(item.get('zh'), str) or not item.get('references')):
                raise self.store.error('系统译文条目格式错误或 ID 重复')
            seen.add(item['id'])
            if any(not isinstance(r.get('capacity'), int) or r['capacity'] < 2
                   for r in item['references']):
                raise self.store.error(f"{item['id']} 的文本容量无效")
        return raw, document

    def load(self):
        raw, document = self.document()
        entries, groups = [], dict(GROUPS)
        for index, item in enumerate(document['entries']):
            memberships = groups_for(item)
            for name in memberships:
                if name not in groups:
                    groups[name] = f"第{int(re.match(r'L(\d+)', name)[1])}关 · {name}"
            readonly_reason = preserved_english_reason(item)
            entries.append({
                'filename': item['id'], 'sound_id': item['id'], 'index': index, 'kind': 'system',
                'sound_name': ' / '.join(groups[name] for name in memberships),
                'asr_text': item['en'], 'translation': item['zh'], 'note': item.get('notes', ''),
                'needs_review': True, 'language': 'en', 'language_marker': '游戏原文',
                'embedded_english': '', 'audio_available': False, 'has_asr': False,
                'asr_status': 'not_applicable', 'has_record': True, 'duration': None,
                'reuse_targets': [], 'audio_variants': [], 'requires_variant_review': False,
                'reuse_approved': False, 'groups': memberships, 'references': item['references'],
                'max_units': min(ref['capacity'] // 2 - 1 for ref in item['references']),
                'readonly': bool(readonly_reason), 'readonly_reason': readonly_reason,
            })
        counts = {'total': len(entries), 'audio': 0, 'asr': 0, 'reviewed': 0,
                  'translated': sum(bool(row['translation'].strip()) for row in entries)}
        group_order = sorted(groups, key=lambda k: (0, list(GROUPS).index(k)) if k in GROUPS
                             else (1, int(re.match(r'L(\d+)', k)[1])))
        return {'id': COLLECTION_ID, 'label': '系统文本 · 菜单 / 提示 / 目标', 'kind': 'system',
                'directory_hint': 'TEXT', 'save_path': 'TEXT/' + CATALOG_NAME,
                'revision': sha256(raw).hexdigest(), 'json_exists': True, 'counts': counts,
                'unmatched_json_keys': [], 'entries': entries,
                'groups': [{'id': key, 'label': groups[key]} for key in group_order]}

    def save(self, revision, edits):
        if not isinstance(revision, str) or not isinstance(edits, dict) or not edits:
            raise self.store.error('没有可保存的系统文本修改')
        with self.store.lock:
            raw, document = self.document()
            if sha256(raw).hexdigest() != revision:
                raise self.store.error('系统译文 JSON 已被其他程序修改，请保留草稿后重新读取。', 409)
            output = deepcopy(document)
            by_id = {row['id']: row for row in output['entries']}
            normalized, changed = {}, 0
            for identifier, change in edits.items():
                if identifier not in by_id:
                    raise self.store.error(f'不存在的系统文本 ID：{identifier}')
                if (not isinstance(change, dict) or set(change) != {'translation'}
                        or not isinstance(change['translation'], str)):
                    raise self.store.error('系统文本只允许修改译文 zh')
                item = by_id[identifier]
                text = change['translation'].replace('\r\n', '\n').replace('\r', '\n')
                if not text.strip() or '\0' in text or '\t' in text:
                    raise self.store.error(f'{identifier}：译文不能为空或包含空字符、Tab；允许回车换行')
                if any(ord(c) > 0xFFFF or 0xD800 <= ord(c) <= 0xDFFF for c in text):
                    raise self.store.error(f'{identifier}：不支持表情等四字节字符或无效字符')
                readonly_reason = preserved_english_reason(item)
                if readonly_reason and text != item['en']:
                    raise self.store.error(readonly_reason)
                capacity = min(ref['capacity'] for ref in item['references'])
                if len(text.encode('utf-16-le')) + 2 > capacity:
                    raise self.store.error(f'{identifier}：译文超过 {capacity // 2 - 1} 字上限，请缩短后保存')
                if item['zh'] != text:
                    item['zh'] = text
                    changed += 1
                normalized[identifier] = {'translation': text}
            written = self.store.write_document(self.path, output, revision, backup_subdir='review_backups') if changed else {
                'revision': revision, 'backup': None}
            return {**written, 'saved': changed, 'edits': normalized, 'counts': self.load()['counts']}
