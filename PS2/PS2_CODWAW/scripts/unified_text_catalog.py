"""One-time migration of menus, HUD hints and objectives to one editable JSON."""
import json
from pathlib import Path
from game_text_resources import ROOT, locate_text

CATALOG = ROOT / 'TEXT/菜单与提示译文.json'


def in_scope(path):
    return path in ('Misc/Menu/Menu_Am.asr', 'Text/american.asr') or path.lower().endswith('.ps2')


def main():
    if CATALOG.exists():
        raise ValueError('Unified catalog already exists; edit it directly, do not migrate again')
    old = json.loads((ROOT/'TEXT/full_game/catalog.json').read_text(encoding='utf-8'))
    # Read ONLY objective translations from the interrupted work, not dialogue.
    objective_ids = {r['id'] for r in old if any(x['key'].startswith('PTXT:') for x in r['references'])}
    completed = {}
    for line in (ROOT/'SOUND/research/deferred_unimported/completion_zh.tsv').read_text(encoding='utf-8').splitlines():
        key, text = line.split('\t', 1)
        if key in objective_ids:
            completed[key] = text
    completed.update({
        'T1721':'清除风车周围的防御', 'T1722':'摧毁德军前哨',
        'T1723':'拾取狙击步枪，消灭敌方巡逻队', 'T1724':'与马多克会合',
        'T1725':'沿主街前进', 'T1726':'击退被惊动的德军巡逻队',
        'T1727':'潜入集结地', 'T1728':'射击炸药', 'T1729':'摧毁轴心军集结地',
        'T1730':'潜入巴斯托涅', 'T1731':'摧毁3辆坦克',
        'T1732':'击退被惊动的德军巡逻队', 'T1733':'潜入巴斯托涅',
        'T1818':'在布尔教堂与上尉会合', 'T1819':'击退教堂北面的进攻',
        'T1820':'击退教堂东面的进攻', 'T1821':'坚守教堂，等待车辆抵达',
        'T1822':'登车撤离', 'T1823':'包抄并摧毁半履带车',
        'T1824':'击退教堂南面的敌人', 'T1825':'坚持到空中支援抵达',
    })
    current = {}
    records = []
    for record in old:
        refs = [x for x in record['references'] if in_scope(x['file'])]
        if not refs: continue
        changes = set()
        for ref in refs:
            path = ref['file']
            if path not in current:
                current[path] = {x['key']: x for x in locate_text((ROOT/'ISO_UNPACK'/path).read_bytes())}
            text = current[path][ref['key']]['text']
            if text != record['en']: changes.add(text)
        if len(changes)>1: raise ValueError(f"Conflicting installed translations: {record['id']}")
        zh = next(iter(changes)) if changes else record['zh'] or completed.get(record['id'], '')
        if not zh: raise ValueError(f"Untranslated: {record['id']}")
        records.append({'id':record['id'], 'en':record['en'], 'zh':zh,
                        'category':refs[0]['key'].split(':')[0], 'references':refs,
                        'notes':'人名或键盘字符按原样保留' if zh==record['en'] else ''})
    CATALOG.write_text(json.dumps({'schema_version':1,
        '说明':'唯一编辑入口。只修改zh；菜单、HUD提示、任务目标。AM对白及旧CSText对白不在本文件范围。',
        'entries':records},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(records)} entries -> {CATALOG}')


if __name__=='__main__': main()
