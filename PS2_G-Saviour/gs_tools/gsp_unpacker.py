import os
import json
from pathlib import Path
import struct

def get_gs_dimensions(data, offset):
    # GS头：
    # 0x00-0x01: GS
    # 0x02-0x03: bpp的类型
    # 0x04-0x05: 宽
    # 0x06-0x07: 高
    #其余不知道
    
    width = struct.unpack('<H', data[offset + 4:offset + 6])[0]
    height = struct.unpack('<H', data[offset + 6:offset + 8])[0]
    return width, height

def is_aligned_to_16(width, height):
    return width % 16 == 0 and height % 16 == 0

def find_next_gs_start(data, start_pos):
    
    # 定义所有已知的GS图像类型
    VALID_GS_TYPES = {0x00, 0x13, 0x14, 0x20}
    
    # 先gs的id只在0x10的倍数那里找，其他位置忽略
    pos = ((start_pos + 0xF) // 0x10) * 0x10
    
    while pos < len(data) - 1:
        if pos % 0x10 == 0 and data[pos:pos + 2] == b'GS':
           
            if pos + 8 <= len(data):  
                img_type = struct.unpack('<H', data[pos + 2:pos + 4])[0]
                width = struct.unpack('<H', data[pos + 4:pos + 6])[0]
                height = struct.unpack('<H', data[pos + 6:pos + 8])[0]
                
               
                if img_type in VALID_GS_TYPES and width > 0 and height > 0:
                    return pos
        pos += 0x10
    return None

def unpack_gsp(gsp_path):
    
    print(f"\n输入的文件: {gsp_path}")
    
    gsp_name = Path(gsp_path).stem
    output_dir = Path(gsp_path).parent / gsp_name
    output_dir.mkdir(exist_ok=True)
    
    with open(gsp_path, 'rb') as f:
        data = f.read()
    
    print(f"文件总大小: {len(data)} bytes")
    
    textures = []
    current_pos = 0
    texture_count = 0
    
    while current_pos < len(data):
        if current_pos % 0x10 == 0 and data[current_pos:current_pos + 2] == b'GS':
            start_pos = current_pos
            
            # 获取当前GS文件的宽高
            width, height = get_gs_dimensions(data, start_pos)
            print(f"\n找到第 {texture_count} 个GS文件:")
            print(f"位置: 0x{start_pos:X}")
            print(f"尺寸: {width}x{height}")
            
            # 查找下一个GS文件的开始位置
            next_gs_pos = find_next_gs_start(data, start_pos + 1)
            if next_gs_pos is not None:
                print(f"下一个GS文件位置: 0x{next_gs_pos:X}")
            else:
                print("最后一个GS文件")
            
            if next_gs_pos is None:
                # 如果是最后一个文件，查找最后的FF填充
                scan_pos = start_pos
                while scan_pos < len(data):
                    if data[scan_pos] == 0xFF:
                        end_pos = scan_pos
                        break
                    scan_pos += 1
            else:
                # 向前查找FF填充的开始位置
                end_pos = next_gs_pos
                while end_pos > start_pos and data[end_pos - 1] == 0xFF:
                    end_pos -= 1
            
            print(f"文件结束位置: 0x{end_pos:X}")
            print(f"文件size: {end_pos - start_pos} bytes")
            
            
            header_data = data[start_pos:start_pos+16]
            print(' '.join(f'{b:02X}' for b in header_data))
            
            # 保存GS文件
            size = end_pos - start_pos
            filename = f"{texture_count:03d}.gs"
            output_path = output_dir / filename
            with open(output_path, 'wb') as f:
                f.write(data[start_pos:end_pos])
            
           
            textures.append({
                "index": texture_count,
                "filename": filename,
                "offset_start": start_pos,
                "offset_end": next_gs_pos if next_gs_pos is not None else end_pos,
                "size": end_pos - start_pos
            })
            
            texture_count += 1
            current_pos = next_gs_pos if next_gs_pos is not None else len(data)
            
            # 验证下一个位置
            if next_gs_pos is not None:
                print(f"下一个位置的数据:")
                next_data = data[next_gs_pos:next_gs_pos+16]
                print(' '.join(f'{b:02X}' for b in next_data))
        else:
            current_pos += 0x10
    
    print(f"\n共找到 {texture_count} 个文件")
    
    # 生成JSON索引
    info = {
        "gsp_info": {
            "file_name": os.path.basename(gsp_path),
            "total_length": len(data),
            "texture_count": texture_count
        },
        "textures": textures
    }
    
    json_path = output_dir / f"{gsp_name}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    
    return texture_count


gsp_path = r"UNPACKER\MPB9\GV_BMP.GSP"
count = unpack_gsp(gsp_path)
print(f"\n完成，提取了 {count} 个GS文件")