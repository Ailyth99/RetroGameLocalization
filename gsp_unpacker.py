import os
import json
from pathlib import Path
import struct

def get_gs_dimensions(data, offset):
    """获取GS文件的宽度和高度"""
    # GS文件头部结构：
    # 0x00-0x01: 'GS' 魔数
    # 0x02-0x03: 图像类型
    # 0x04-0x05: 宽度
    # 0x06-0x07: 高度
    width = struct.unpack('<H', data[offset + 4:offset + 6])[0]
    height = struct.unpack('<H', data[offset + 6:offset + 8])[0]
    return width, height

def is_aligned_to_16(width, height):
    """检查宽度和高度是否都是16的倍数"""
    return width % 16 == 0 and height % 16 == 0

def find_next_gs_start(data, start_pos):
    """从给定位置开始寻找下一个GS文件的开始"""
    # 定义所有已知的GS图像类型
    VALID_GS_TYPES = {0x00, 0x13, 0x14, 0x20}
    
    # 先向上对齐到下一个0x10的位置
    pos = ((start_pos + 0xF) // 0x10) * 0x10
    
    while pos < len(data) - 1:
        # 只在16字节对齐的位置检查GS标识
        if pos % 0x10 == 0 and data[pos:pos + 2] == b'GS':
            # 验证一下文件头的合法性
            if pos + 8 <= len(data):  # 确保有足够的空间读取宽高
                img_type = struct.unpack('<H', data[pos + 2:pos + 4])[0]
                width = struct.unpack('<H', data[pos + 4:pos + 6])[0]
                height = struct.unpack('<H', data[pos + 6:pos + 8])[0]
                
                # 检查图像类型和基本的宽高合法性
                if img_type in VALID_GS_TYPES and width > 0 and height > 0:
                    return pos
        pos += 0x10
    return None

def unpack_gsp(gsp_path):
    """解包GSP文件，提取所有的GS图片"""
    
    print(f"\n开始处理文件: {gsp_path}")
    
    # 创建输出目录
    gsp_name = Path(gsp_path).stem
    output_dir = Path(gsp_path).parent / gsp_name
    output_dir.mkdir(exist_ok=True)
    
    # 读取GSP文件
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
                print("这是最后一个GS文件")
            
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
            print(f"文件大小: {end_pos - start_pos} bytes")
            
            # 输出文件头部的十六进制数据，用于验证
            print("文件头部数据:")
            header_data = data[start_pos:start_pos+16]
            print(' '.join(f'{b:02X}' for b in header_data))
            
            # 提取并保存GS文件
            size = end_pos - start_pos
            filename = f"{texture_count:03d}.gs"
            output_path = output_dir / filename
            with open(output_path, 'wb') as f:
                f.write(data[start_pos:end_pos])
            
            # 记录文件信息
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
    
    print(f"\n处理完成，共找到 {texture_count} 个文件")
    
    # 生成JSON信息文件
    info = {
        "tmx_info": {
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

if __name__ == "__main__":
    gsp_path = r"UNPACKER\MPB9\GV_BMP.GSP"
    count = unpack_gsp(gsp_path)
    print(f"\n解包完成啦~ 总共提取了 {count} 个GS文件哦 ♪(^∇^*)")