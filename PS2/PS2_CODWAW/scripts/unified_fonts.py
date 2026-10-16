"""Native FONT v3 multipage builder, matching FUN_0012dea8 / FUN_00208568."""
import math
import json
import struct
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from game_text_resources import chunks
import build_start_menu_zh as s
from build_large_menu_font import fonts, rsfl_entries
from build_settings import SETTINGS_PATH, normalize, resolve_font


RENDER_SETTINGS=SETTINGS_PATH
SUPERSAMPLE=4


def render_glyph(font, code, width, sample, baseline, bold_px=0):
    """Expand the outline before antialiasing; retain the existing glyph cell."""
    stroke=round(bold_px*SUPERSAMPLE)
    tile=Image.new('L',(width*SUPERSAMPLE,sample*SUPERSAMPLE))
    left,top,right,bottom=font.getbbox(chr(code),anchor='ls',stroke_width=stroke)
    ink=Image.new('L',(max(1,right-left),max(1,bottom-top)))
    ImageDraw.Draw(ink).text((-left,-top),chr(code),font=font,anchor='ls',fill=255,
                            stroke_width=stroke,stroke_fill=255)
    target=(min(ink.width,max(1,width-2)*SUPERSAMPLE),min(ink.height,(sample-2)*SUPERSAMPLE))
    if ink.size!=target:ink=ink.resize(target,Image.Resampling.LANCZOS)
    top_y=max(SUPERSAMPLE,min(baseline*SUPERSAMPLE+top,tile.height-SUPERSAMPLE-ink.height))
    tile.paste(ink,((tile.width-ink.width)//2,top_y))
    return tile.resize((width,sample),Image.Resampling.LANCZOS)


def parse_pages(data):
    result={}
    for tag,pos,size in chunks(data):
        if tag!=b'FONT': continue
        name=data[pos+16:data.index(b'\0',pos+16)].decode('ascii')
        count=struct.unpack_from('<I',data,pos+0x78)[0]
        cur=pos+0x7c; pages=[]
        for _ in range(count):
            texture=data[cur:data.index(b'\0',cur)].decode('ascii')
            lo,hi,w,h,n=struct.unpack_from('<HHIII',data,cur+0x6c)
            rec=[struct.unpack_from('<fffHh',data,cur+0x7c+i*16) for i in range(n)]
            codes=[r[3] for r in rec]
            s.require(codes==sorted(set(codes)) and (lo,hi)==(codes[0],codes[-1]),'Invalid page codes')
            pages.append({'texture':texture,'width':w,'height':h,'records':rec})
            cur+=0x7c+n*16
        s.require(cur==pos+size,'FONT page extent mismatch')
        result[name]={'offset':pos,'size':size,'pages':pages}
    return result


def build(source, texts, heading_texts=None, subtitle_texts=()):
    settings_bytes=RENDER_SETTINGS.read_bytes()
    settings=normalize(json.loads(settings_bytes))
    weights=settings['synthetic_bold_px']
    s.require(set(weights)<= {'Verdana_10.asr','Verdana_20.asr'},'Synthetic bold only applies to Verdana')
    for name,value in weights.items():
        s.require(type(value) in (int,float) and math.isfinite(value) and 0<=value<=1
                  and value*SUPERSAMPLE==round(value*SUPERSAMPLE),
                  f'{name}: synthetic_bold_px must be 0..1 in 0.25-pixel steps')
    definitions=fonts(source)  # Baseline has one page per font.
    refs=rsfl_entries(source,definitions)
    required={ord(c) for text in texts for c in text if c not in '\n\r\t' and not 0xE000<=ord(c)<=0xF8FF}
    s.require(all(0<c<=0xFFFF for c in required),'Only BMP glyphs supported')
    blocks={}; texture_blocks={}; added_resources=[]; reports=[]
    for name,info in definitions.items():
        fp=info['offset']; original=source[fp:fp+info['size']]
        existing={r[3] for r in info['records']}
        heading=name.startswith('Times'); tiny=name.startswith('Verdana_10')
        bold_px=weights.get(name,0)
        font_required=required
        if name=='Verdana_20.asr':
            font_required=required | {ord(c) for text in subtitle_texts for c in text
                                     if c not in '\n\r\t' and not 0xE000<=ord(c)<=0xF8FF}
        if heading and heading_texts is not None:
            font_required={ord(c) for text in heading_texts for c in text
                           if c not in '\n\r\t' and not 0xE000<=ord(c)<=0xF8FF}
        missing=sorted(font_required-existing)
        face=resolve_font(settings['fonts'][name])
        fallback_face=resolve_font(settings['fallback_font'])
        with TTFont(face) as ff: cmap=ff.getBestCmap()
        with TTFont(fallback_face) as ff: fallback_cmap=ff.getBestCmap()
        unavailable=[c for c in missing if c not in cmap and c not in fallback_cmap]
        s.require(not unavailable,f'Missing source font glyphs in {name}: '+
                  ', '.join(f'U+{c:04X}' for c in unavailable))
        s.require(all(0<c<=0xFFFF for c in font_required),'Only BMP glyphs supported')
        sample=int(info['sample_height']); px=12 if tiny else 24
        width=14 if tiny else 28 if heading else 26
        baseline=14 if tiny else 26 if heading else 27
        step_x=width+2;step_y=sample+2
        columns=(512-4)//step_x;rows=(512-4)//step_y;capacity=columns*rows
        texture_marker=name.removesuffix('.asr').lower().encode()+b'_0.tm2'
        _,rp,rs=next(c for c in chunks(source) if c[0]==b'RSCF' and texture_marker in source[c[1]:c[1]+128].lower())
        resource=source[rp:rp+rs];tm=resource.index(b'TIM2');pic=tm+128
        old_size,clut_size,image_size=struct.unpack_from('<III',resource,pic)
        header_size=struct.unpack_from('<H',resource,pic+12)[0]
        image_start=pic+header_size
        clut=resource[image_start+image_size:image_start+image_size+clut_size]
        alpha=[min(255,clut[i*4+3]*2) for i in range(16)]
        quant=[min(range(16),key=lambda i:abs(alpha[i]-v)) for v in range(256)]
        font=ImageFont.truetype(str(face),px*4); fallback=ImageFont.truetype(str(fallback_face),px*4)
        # Re-render existing glyphs as well: file names are not font identities.
        # Keep UVs/advances so replacing the source face does not grow allocations.
        old_packed=resource[image_start:image_start+image_size]
        old_pixels=bytearray(info['width']*info['height'])
        old_pixels[0::2]=bytes(v&15 for v in old_packed)
        old_pixels[1::2]=bytes(v>>4 for v in old_packed)
        old_page=Image.frombytes('P',(info['width'],info['height']),bytes(old_pixels))
        first_page=Image.new('P',old_page.size,0)
        preserved_special=[]; rerendered=0
        for u,v,advance,code,extra in info['records']:
            x,y=round(u*info['width']-.5),round(v*info['height']-.5)
            tile_width=math.ceil(advance)
            s.require(tile_width>0 and x>=0 and y>=0 and
                      x+tile_width<=info['width'] and y+sample<=info['height'],
                      f'Invalid existing glyph bounds {name} U+{code:04X}')
            if code not in cmap and code not in fallback_cmap:
                # Font-specific symbols cannot be invented; report every fallback.
                tile=old_page.crop((x,y,x+tile_width,y+sample))
                preserved_special.append(code)
            else:
                f=font if code in cmap else fallback
                tile=render_glyph(f,code,tile_width,sample,baseline,bold_px).point(quant)
                s.require(chr(code).isspace() or tile.getbbox() is not None,
                          f'Blank rebuilt glyph {name} U+{code:04X}')
                rerendered+=1
            first_page.paste(tile,(x,y))
        pixels=first_page.tobytes()
        rebuilt_resource=bytearray(resource)
        rebuilt_resource[image_start:image_start+image_size]=bytes(
            a|(b<<4) for a,b in zip(pixels[0::2],pixels[1::2]))
        texture_blocks[rp]=bytes(rebuilt_resource)
        block=bytearray(original);pages=1;fallbacks=[]
        old_texture=original[0x7c:original.index(b'\0',0x7c)].decode('ascii')
        old_rname=resource[28:resource.index(b'\0',28)].decode('ascii')
        for begin in range(0,len(missing),capacity):
            batch=missing[begin:begin+capacity]
            used_height=4+math.ceil(len(batch)/columns)*step_y
            page_height=max(32,1<<(used_height-1).bit_length())
            s.require(page_height<=512,'Page exceeds supported size')
            page=Image.new('P',(512,page_height),0);records=[]
            for index,code in enumerate(batch):
                x,y=2+(index%columns)*step_x,2+(index//columns)*step_y
                f=font if code in cmap else fallback
                if code not in cmap:fallbacks.append(code)
                tile=render_glyph(f,code,width,sample,baseline,bold_px).point(quant)
                s.require(tile.getbbox() is not None,f'Blank glyph {code:04x}')
                page.paste(tile,(x,y))
                records.append(((x+.5)/512,(y+.5)/page_height,float(width),code,0))
            texture=old_texture.replace('_0.tga',f'_{pages}.tga')
            rname=old_rname.replace('_0.tm2',f'_{pages}.tm2')
            page_header=bytearray(original[0x7c:0xf8])
            page_header[:100]=texture.encode().ljust(100,b'\0')
            struct.pack_into('<HHIII',page_header,0x6c,batch[0],batch[-1],512,page_height,len(batch))
            block.extend(page_header)
            for r in records:block.extend(struct.pack('<fffHh',*r))
            pixels=page.tobytes();body=bytes(a|(b<<4) for a,b in zip(pixels[0::2],pixels[1::2]))
            image=bytearray(resource[tm:image_start])
            struct.pack_into('<III',image,128,header_size+len(body)+clut_size,clut_size,len(body))
            struct.pack_into('<HH',image,148,512,page_height)
            image.extend(body);image.extend(clut)
            new=bytearray(resource[:28]);new.extend(rname.encode()+b'\0')
            new.extend(b'\0'*(-len(new)%4));new.extend(image)
            struct.pack_into('<I',new,4,len(new));struct.pack_into('<I',new,24,len(image))
            added_resources.append(bytes(new));pages+=1
        struct.pack_into('<I',block,0x78,pages);struct.pack_into('<I',block,4,len(block))
        blocks[fp]=bytes(block)
        reports.append({'font':name,'pages':pages,'total_glyphs':len(existing)+len(missing),
                        'new_glyphs':len(missing),'fallback_codes':fallbacks,
                        'rebuild_mode':'all_glyphs_from_current_font_files',
                        'synthetic_bold_px':bold_px,
                        'supersample':SUPERSAMPLE,
                        'render_settings':str(RENDER_SETTINGS.relative_to(s.ROOT)),
                        'render_settings_sha256':s.sha256(settings_bytes),
                        'existing_glyphs_rerendered':rerendered,
                        'unavailable_special_codes_preserved':preserved_special,
                        'source_font':str(face.relative_to(s.ROOT)),
                        'source_font_sha256':s.sha256(face.read_bytes()),
                        'fallback_font':str(fallback_face.relative_to(s.ROOT)),
                        'fallback_font_sha256':s.sha256(fallback_face.read_bytes()),
                        'required_codes':sorted(font_required)})
    result=bytearray(source[:8]);inserted=False
    for tag,p,size in chunks(source):
        if tag==b'FONT' and not inserted:
            for resource in added_resources:result.extend(resource)
            inserted=True
        result.extend(blocks.get(p,texture_blocks.get(p,source[p:p+size])))
    result.extend(source[-4:])
    parsed=parse_pages(result)
    for name,cursor,base in refs:
        info=next(v for k,v in parsed.items() if k.lower()==name.lower())
        struct.pack_into('<II',result,cursor,info['offset']-base,info['size'])
    for name,info in parsed.items():
        codes=[r[3] for page in info['pages'] for r in page['records']]
        expected=next(r['required_codes'] for r in reports if r['font']==name)
        s.require(len(codes)==len(set(codes)) and set(expected)<=set(codes),'Page coverage/duplicates')
    for report in reports:
        report['required_glyphs']=len(report.pop('required_codes'))
    # Remove the large blank areas inherited from the historical single-page fonts.
    # This runs only after every glyph was redrawn from the current source faces.
    from compact_font_pages import compact
    result,packing=compact(bytes(result),parse_pages)
    for report,packed in zip(reports,packing):
        s.require(report['font']==packed['font'],'Packing report order mismatch')
        report.update(packed)
    return result,reports
