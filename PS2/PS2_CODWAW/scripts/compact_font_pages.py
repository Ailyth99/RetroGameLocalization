"""Pack freshly rendered FONT glyph tiles densely without changing their pixels or metrics."""
import math
import struct
from PIL import Image
from game_text_resources import chunks
from build_large_menu_font import rsfl_entries
import build_start_menu_zh as s


def compact(source, parse_pages):
    definitions=parse_pages(source)
    refs=rsfl_entries(source,definitions)
    resources={}
    for tag,pos,size in chunks(source):
        if tag==b'RSCF':
            name=source[pos+28:source.index(b'\0',pos+28)].decode('ascii')
            resources[name.replace('\\','/').split('/')[-1].lower()]=(pos,source[pos:pos+size])
    replacements={}; removed=set(); new_resources=[]; report=[]; expected={}
    for name,info in definitions.items():
        fp=info['offset']; sample=round(struct.unpack_from('<f',source,fp+0x74)[0])
        glyphs=[]; before_bytes=0; template=None; palette=None
        for page in info['pages']:
            key=page['texture'].replace('\\','/').split('/')[-1].lower().replace('.tga','.tm2')
            rp,res=resources[key]; removed.add(rp)
            tm=res.index(b'TIM2'); pic=tm+128
            _,clut_size,image_size=struct.unpack_from('<III',res,pic)
            header_size=struct.unpack_from('<H',res,pic+12)[0]; start=pic+header_size
            clut=res[start+image_size:start+image_size+clut_size]
            if palette is None: palette=clut; template=res
            s.require(palette==clut,'Font pages have different palettes')
            w,h=page['width'],page['height']
            s.require(image_size==w*h//2,'Unexpected font texture layout')
            raw=res[start:start+image_size]; pixels=bytearray(w*h)
            pixels[::2]=bytes(v&15 for v in raw);pixels[1::2]=bytes(v>>4 for v in raw)
            image=Image.frombytes('P',(w,h),bytes(pixels));before_bytes+=image_size
            for u,v,advance,code,extra in page['records']:
                x,y=round(u*w-.5),round(v*h-.5);width=math.ceil(advance)
                s.require(x>=0 and y>=0 and x+width<=w and y+sample<=h,'Invalid glyph bounds')
                tile=image.crop((x,y,x+width,y+sample))
                glyphs.append((code,advance,extra,tile))
        # Fixed-height shelf packing with one clear pixel between glyph rectangles.
        # Small widths fill rows first-fit, reducing wasted space on Latin glyphs.
        pages=[]; rows_per_page=(512-2)//(sample+1)
        for code,advance,extra,tile in sorted(glyphs,key=lambda g:(-g[3].width,g[0])):
            width=tile.width; placed=False
            for page in pages:
                for row,x in enumerate(page['next_x']):
                    if x+width<=511:
                        page['items'].append((x,1+row*(sample+1),code,advance,extra,tile))
                        page['next_x'][row]=x+width+1;placed=True;break
                if placed:break
            if not placed:
                page={'next_x':[1]*rows_per_page,'items':[]};pages.append(page)
                page['items'].append((1,1,code,advance,extra,tile));page['next_x'][0]=width+2
        original=source[fp:fp+info['size']]
        header=bytearray(original[:0x7c]); after_bytes=0
        old_texture=info['pages'][0]['texture']
        old_rname=template[28:template.index(b'\0',28)].decode('ascii')
        tm=template.index(b'TIM2');pic=tm+128
        header_size=struct.unpack_from('<H',template,pic+12)[0]
        for index,page in enumerate(pages):
            used_height=max(y+sample+1 for x,y,*_ in page['items'])
            height=max(32,1<<(used_height-1).bit_length())
            atlas=Image.new('P',(512,height)); records=[]
            for x,y,code,advance,extra,tile in page['items']:
                atlas.paste(tile,(x,y));records.append(((x+.5)/512,(y+.5)/height,advance,code,extra))
                expected[(name,code)]=(advance,extra,tile.tobytes(),tile.width,sample)
            records.sort(key=lambda r:r[3])
            texture=old_texture.replace('_0.tga',f'_{index}.tga')
            rname=old_rname.replace('_0.tm2',f'_{index}.tm2')
            ph=bytearray(original[0x7c:0xf8]);ph[:100]=texture.encode().ljust(100,b'\0')
            struct.pack_into('<HHIII',ph,0x6c,records[0][3],records[-1][3],512,height,len(records))
            header.extend(ph)
            for record in records:header.extend(struct.pack('<fffHh',*record))
            pixels=atlas.tobytes();raw=bytes(a|(b<<4) for a,b in zip(pixels[::2],pixels[1::2]))
            tim=bytearray(template[tm:pic+header_size])
            struct.pack_into('<III',tim,128,header_size+len(raw)+len(palette),len(palette),len(raw))
            struct.pack_into('<HH',tim,148,512,height)
            tim.extend(raw);tim.extend(palette)
            res=bytearray(template[:28]);res.extend(rname.encode()+b'\0');res.extend(b'\0'*(-len(res)%4));res.extend(tim)
            struct.pack_into('<I',res,4,len(res));struct.pack_into('<I',res,24,len(tim))
            new_resources.append(bytes(res));after_bytes+=len(raw)
        struct.pack_into('<I',header,4,len(header));struct.pack_into('<I',header,0x78,len(pages))
        replacements[fp]=bytes(header)
        report.append({'font':name,'pages':len(pages),'texture_bytes_before':before_bytes,
                       'texture_bytes_after':after_bytes,'all_glyph_pixels_and_advances_preserved':True})
    result=bytearray(source[:8]);inserted=False
    for tag,pos,size in chunks(source):
        if pos in removed:continue
        if tag==b'FONT' and not inserted:
            result.extend(b''.join(new_resources));inserted=True
        result.extend(replacements.get(pos,source[pos:pos+size]))
    result.extend(source[-4:])
    after=parse_pages(result)
    # RSFL precedes texture/font resources in this container; its cursor/base stay fixed.
    for name,cursor,base in refs:
        info=next(v for k,v in after.items() if k.lower()==name.lower())
        struct.pack_into('<II',result,cursor,info['offset']-base,info['size'])
    rsfl_entries(result,after)
    # Read back every relocated glyph, comparing pixels and metrics exactly.
    resmap={}
    for tag,pos,size in chunks(result):
        if tag==b'RSCF':
            key=result[pos+28:result.index(b'\0',pos+28)].decode('ascii').replace('\\','/').split('/')[-1].lower()
            resmap[key]=result[pos:pos+size]
    found=set()
    for name,info in after.items():
        for page in info['pages']:
            key=page['texture'].replace('\\','/').split('/')[-1].lower().replace('.tga','.tm2')
            res=resmap[key];pic=res.index(b'TIM2')+128
            start=pic+struct.unpack_from('<H',res,pic+12)[0]
            w,h=page['width'],page['height'];raw=res[start:start+w*h//2]
            pixels=bytearray(w*h);pixels[::2]=bytes(v&15 for v in raw);pixels[1::2]=bytes(v>>4 for v in raw)
            image=Image.frombytes('P',(w,h),bytes(pixels))
            for u,v,advance,code,extra in page['records']:
                key=(name,code);s.require(key not in found,'Duplicate glyph after packing');found.add(key)
                a,e,tile,width,sample=expected[key];x,y=round(u*w-.5),round(v*h-.5)
                s.require((advance,extra)==(a,e) and image.crop((x,y,x+width,y+sample)).tobytes()==tile,
                          f'Glyph changed during packing: {name} U+{code:04X}')
    s.require(found==set(expected),'Glyph lost during packing')
    return bytes(result),report
