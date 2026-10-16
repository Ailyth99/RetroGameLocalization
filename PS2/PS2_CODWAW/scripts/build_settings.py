"""Shared, versioned settings for the GUI and the existing complete build."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
SETTINGS_PATH=ROOT/'FONT/render_settings.json'
FONT_ROOT=ROOT/'FONT/source'
FONT_NAMES=('Times New Roman_20_Bold.asr','Verdana_10.asr','Verdana_20.asr')
DEFAULTS={
    'version':1,
    'fonts':{
        FONT_NAMES[0]:'FONT/source/USMCCyuanjiantecu.otf',
        FONT_NAMES[1]:'FONT/source/IBMPlexSansSC-Regular.ttf',
        FONT_NAMES[2]:'FONT/source/IBMPlexSansSC-Regular.ttf',
    },
    'fallback_font':'FONT/source/IBMPlexSansSC-Regular.ttf',
    'synthetic_bold_px':{FONT_NAMES[1]:0.25,FONT_NAMES[2]:0.5},
    'subtitles':{'color':'#CCFFFF','scale_percent':112.5,'shadow':True},
    'build':{'reviewed_only':False,'hardware_frame_safe':True},
}


def normalize(value):
    if not isinstance(value,dict) or value.get('version')!=1:
        raise ValueError('配置文件版本无效，需要 version=1。')
    result=copy.deepcopy(DEFAULTS)
    for key,item in value.items():
        if key not in DEFAULTS:raise ValueError(f'未知配置项：{key}')
        if isinstance(DEFAULTS[key],dict):
            if not isinstance(item,dict) or set(item)-set(DEFAULTS[key]):
                raise ValueError(f'配置项格式无效：{key}')
            result[key].update(item)
        else:result[key]=item
    for name,amount in result['synthetic_bold_px'].items():
        if type(amount) not in (int,float) or not math.isfinite(amount) or not 0<=amount<=1 or amount*4!=round(amount*4):
            raise ValueError(f'{name} 仿粗体应为 0–1，步进 0.25。')
    color=result['subtitles']['color']
    if not isinstance(color,str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',color):
        raise ValueError('字幕颜色应为 #RRGGBB，例如 #CCFFFF。')
    result['subtitles']['color']=color.upper()
    scale=result['subtitles']['scale_percent']
    if type(scale) not in (int,float) or not math.isfinite(scale) or not 50<=scale<=200:
        raise ValueError('字幕大小应在原生比例的 50%–200% 之间。')
    if type(result['subtitles']['shadow']) is not bool:
        raise ValueError('subtitles.shadow 必须为 true 或 false。')
    for name, enabled in result['build'].items():
        if type(enabled) is not bool:
            raise ValueError(f'{name} 必须为 true 或 false。')
    for name,path in [*result['fonts'].items(),('fallback_font',result['fallback_font'])]:
        if not isinstance(path,str) or not path.strip():raise ValueError(f'字体路径为空：{name}')
        resolve_font(path,require_exists=False)
    return result


def load_settings(path=SETTINGS_PATH):
    return normalize(json.loads(Path(path).read_text(encoding='utf-8-sig')))


def resolve_font(value,require_exists=True):
    path=Path(value)
    path=(ROOT/path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(FONT_ROOT.resolve()):
        raise ValueError('构建字体必须保存在 FONT/source；请通过 GUI 导入外部字体。')
    if path.suffix.lower() not in ('.ttf','.otf'):
        raise ValueError(f'需要 TTF 或 OTF 字体：{path.name}')
    if require_exists and not path.is_file():raise ValueError(f'字体文件不存在：{path}')
    return path


def import_font(value):
    """Keep project fonts in place; import external fonts without overwriting any."""
    from fontTools.ttLib import TTFont
    path=Path(value).expanduser()
    if not path.is_absolute():path=ROOT/path
    path=path.resolve()
    if not path.is_file() or path.suffix.lower() not in ('.ttf','.otf'):
        raise ValueError(f'请选择有效的 TTF/OTF 文件：{path}')
    with TTFont(path,lazy=True) as font:
        if not font.getBestCmap():raise ValueError(f'字体没有可用的字符映射：{path.name}')
    if path.is_relative_to(FONT_ROOT.resolve()):return path.relative_to(ROOT).as_posix()
    data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
    target=FONT_ROOT/'imported'/f'{path.stem}-{digest[:16]}{path.suffix.lower()}'
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if target.read_bytes()!=data:raise ValueError('导入字体文件冲突，请检查 FONT/source/imported。')
    else:
        with target.open('xb') as stream:stream.write(data)
    return target.relative_to(ROOT).as_posix()


def ensure_build_idle():
    lock=ROOT/'TEMP/builds/one_click_build/build.lock'
    if lock.exists():
        try:
            with lock.open('a+b'):pass
        except OSError as error:
            raise ValueError('另一项构建正在运行，请完成后再保存配置或构建。') from error


def save_settings(value,path=SETTINGS_PATH):
    value=normalize(value)
    for font in [*value['fonts'].values(),value['fallback_font']]:resolve_font(font)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+f'.{os.getpid()}.tmp')
    try:
        temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()
    return value
