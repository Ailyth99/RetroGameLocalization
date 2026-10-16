"""Install remaining large-font translations, extending both 20px font atlases."""
import json
import math
import re
import struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
import build_start_menu_zh as s
import build_options_menu_zh as options
from build_large_menu_font import fonts, rsfl_entries
from game_text_resources import chunks

ROOT = s.ROOT
BACKUP = ROOT / 'SOURCE/backups/large_texts_zh'
OUT = ROOT / 'TEMP/builds/large_texts_zh'
SPEC = ROOT / 'TEXT/translations/large_font_additions_zh.json'


def extend_font(data, name, translations):
    definitions = fonts(data)
    info = definitions[name]
    s.require((info['width'], info['height']) == (512, 512), 'Unexpected source geometry')
    references = rsfl_entries(data, definitions)
    codes = {r[3] for r in info['records']}
    added = sorted({ord(c) for e in translations for c in e['zh'] if c not in '\r\n\t'} - codes)
    texture_name = name.removesuffix('.asr').lower().encode() + b'_0.tm2'
    tag, rp, rs = next(c for c in chunks(data) if c[0] == b'RSCF' and texture_name in data[c[1]:c[1]+128].lower())
    resource = bytearray(data[rp:rp+rs])
    tim2 = resource.index(b'TIM2')
    pic = tim2 + 128
    total, clut_size, image_size = struct.unpack_from('<III', resource, pic)
    image_offset = pic + struct.unpack_from('<H', resource, pic+12)[0]
    s.require(image_size == 131072 and struct.unpack_from('<HH', resource, pic+20) == (512,512), 'Unexpected TIM2')
    s.require(struct.unpack_from('<Q', resource, pic+24)[0] == 0, 'Unexpected precomputed TEX0')
    packed = resource[image_offset:image_offset+image_size]
    clut = resource[image_offset+image_size:image_offset+image_size+clut_size]
    pixels = bytearray(512*512)
    pixels[0::2] = bytes(v & 15 for v in packed)
    pixels[1::2] = bytes(v >> 4 for v in packed)
    page = Image.new('P', (512,1024), 0)
    page.paste(Image.frombytes('P',(512,512),bytes(pixels)), (0,0))
    page.putpalette([v for i in range(16) for v in clut[i*4:i*4+3]] + [0]*(768-48))
    alpha = [min(255,clut[i*4+3]*2) for i in range(16)]
    page.info['transparency'] = bytes(alpha)
    quantize = [min(range(16), key=lambda i: abs(alpha[i]-v)) for v in range(256)]
    heading = name.startswith('Times')
    face = options.HEADING_FONT if heading else s.TTF
    with TTFont(face) as font:
        s.require(all(code in font.getBestCmap() for code in added), 'Source font lacks glyph')
    font = ImageFont.truetype(str(face), 24*4)
    sample_height = int(info['sample_height'])
    width, step = (28,30) if heading else (26,28)
    columns = (512-8)//step
    records = [(u,v/2,w,code,extra) for u,v,w,code,extra in info['records']]
    for i,code in enumerate(added):
        x,y = 4+(i%columns)*step, 514+(i//columns)*33
        s.require(y+sample_height < 1024, 'Extended atlas full')
        tile = Image.new('L',(width*4,sample_height*4))
        if heading:
            left,top,right,bottom = font.getbbox(chr(code),anchor='ls')
            ink = Image.new('L',(max(1,right-left),max(1,bottom-top)))
            ImageDraw.Draw(ink).text((-left,-top),chr(code),font=font,anchor='ls',fill=255)
            size = (min(ink.width,(width-2)*4),min(ink.height,29*4))
            if ink.size != size: ink=ink.resize(size,Image.Resampling.LANCZOS)
            top_y=max(4,min(26*4+top,tile.height-4-ink.height))
            tile.paste(ink,((tile.width-ink.width)//2,top_y))
        else:
            ImageDraw.Draw(tile).text((4,27*4),chr(code),font=font,anchor='ls',fill=255)
        tile=tile.resize((width,sample_height),Image.Resampling.LANCZOS).point(quantize)
        s.require(tile.getbbox() is not None, 'Blank new glyph')
        page.paste(tile,(x,y))
        records.append(((x+.5)/512,(y+.5)/1024,float(width),code,0))
    records.sort(key=lambda r:r[3])
    raw = page.tobytes()
    s.require(raw[:len(pixels)] == bytes(pixels), 'Existing glyph pixels changed')
    body=bytes(a|(b<<4) for a,b in zip(raw[0::2],raw[1::2]))
    delta=len(body)-image_size
    resource[image_offset:image_offset+image_size]=body
    struct.pack_into('<I',resource,4,len(resource))
    struct.pack_into('<I',resource,24,struct.unpack_from('<I',resource,24)[0]+delta)
    struct.pack_into('<I',resource,pic,total+delta)
    struct.pack_into('<I',resource,pic+8,len(body))
    struct.pack_into('<H',resource,pic+22,1024)
    fp,fs=info['offset'],info['size']
    block=bytearray(data[fp:fp+0xF8])
    for record in records: block.extend(struct.pack('<fffHh',*record))
    struct.pack_into('<I',block,4,len(block))
    struct.pack_into('<HHIII',block,0xE8,records[0][3],records[-1][3],512,1024,len(records))
    result=bytearray(data[:8])
    for tag,p,size in chunks(data):
        result.extend(resource if p==rp else block if p==fp else data[p:p+size])
    result.extend(data[-4:])
    updated=fonts(result)
    for ref,cursor,base in references:
        target=updated[next(n for n in updated if n.lower()==ref.lower())]
        struct.pack_into('<II',result,cursor,target['offset']-base,target['size'])
    rsfl_entries(result,updated)
    s.require({ord(c) for e in translations for c in e['zh'] if c not in '\r\n\t'} <= {r[3] for r in records}, 'Glyph coverage gap')
    # Compare every other resource chunk after relocations.
    old_chunks,new_chunks=list(chunks(data)),list(chunks(result))
    s.require(len(old_chunks)==len(new_chunks), 'Chunk count changed')
    for (tag,p,size),(tag2,q,size2) in zip(old_chunks,new_chunks):
        s.require(tag==tag2,'Chunk order changed')
        if p not in (rp,fp) and tag!=b'RSFL':
            s.require(data[p:p+size]==result[q:q+size2],'Unrelated font resource changed')
    page.save(OUT/(('heading' if heading else 'small')+'_atlas.png'))
    return bytes(result), {'font':name,'added':len(added),'total':len(records),'dimensions':[512,1024],
                           'existing_pixels_preserved':True,'sample_height':sample_height}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    spec=json.loads(SPEC.read_text(encoding='utf-8'))
    source_menu=s.read_original(s.MENU_PATH)
    originals,_=s.parse_menu(source_menu)
    paths=(s.MENU_PATH,s.FONT_PATH)
    previous={p:(s.TARGET/p).read_bytes() for p in paths}
    baseline={p:(BACKUP/p).read_bytes() if (BACKUP/p).exists() else previous[p] for p in paths}
    current,_=s.parse_menu(baseline[s.MENU_PATH])
    listing=(ROOT/'TEXT/大字字库文本清单.txt').read_text(encoding='utf-8-sig')
    listed={int(n) for n in re.findall(r'\[HTXT:(\d+)\]',listing)}
    additions=[]
    for index,text in spec['translations'].items():
        index=int(index);old=originals[index]
        s.require(index in listed and current[index]['text']==old['text'],'Unexpected translation target')
        additions.append({'index':index,'id':f"{old['id']:08X}",'en':old['text'],'zh':text})
    merged={e['index']:{'index':e['index'],'id':f"{e['id']:08X}",'en':originals[e['index']]['text'],'zh':e['text']}
            for e in current if e['text']!=originals[e['index']]['text']}
    merged.update({e['index']:e for e in additions})
    planned=list(merged.values())
    menu,menu_report=s.patch_menu(source_menu,planned)
    font,heading_report=extend_font(baseline[s.FONT_PATH],'Times New Roman_20_Bold.asr',planned)
    font,small_report=extend_font(font,'Verdana_20.asr',planned)
    outputs={s.MENU_PATH:menu,s.FONT_PATH:font}
    for p in paths:
        s.require(previous[p] in (baseline[p],outputs[p]),'Target has subsequent edits')
        dest=BACKUP/p;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():dest.write_bytes(baseline[p])
        s.require(dest.read_bytes()==baseline[p],'Backup mismatch')
    for p,data in outputs.items():
        s.require((s.TARGET/p).read_bytes()==previous[p],'Target changed during build')
    try:
        for p,data in outputs.items():
            (s.TARGET/p).write_bytes(data)
            s.require((s.TARGET/p).read_bytes()==data,'Install readback mismatch')
    except Exception:
        for p,data in previous.items():(s.TARGET/p).write_bytes(data)
        raise
    final,_=s.parse_menu(menu)
    s.require(all(final[i]['text']!=originals[i]['text'] for i in listed),'Untranslated listed entry')
    spec['entries']=additions
    spec['description']=f'大字清单新增翻译{len(additions)}条；清单{len(listed)}条均已汉化。'
    SPEC.write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report={'new_translations':len(additions),'listed_total':len(listed),'menu':menu_report,
            'fonts':[heading_report,small_report], 'runtime_validation':'pending_user_test',
            'files':{p.as_posix():{'before':s.sha256(baseline[p]),'after':s.sha256(d)} for p,d in outputs.items()}}
    (OUT/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Update only current text lines, retaining all source locations in the user's list.
    def update(match):
        index=int(match.group(1))
        return match.group(0).rsplit('当前文本：',1)[0]+'当前文本：'+final[index]['text']
    listing=re.sub(r'\[HTXT:(\d+)\][^\n]*\n英文：[^\n]*\n当前文本：[^\n]*',update,listing)
    (ROOT/'TEXT/大字字库文本清单.txt').write_text(listing,encoding='utf-8-sig')
    (ROOT/'TEXT/大字翻译待确认.txt').write_text('\n'.join(f"HTXT:{k} {v}" for k,v in spec['review_notes'].items())+'\n',encoding='utf-8-sig')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
