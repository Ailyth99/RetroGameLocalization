import struct
from PIL import Image
import numpy as np

def convert_bmp_to_gs(bmp_path, gs_path):
    # 读取BMP文件
    img = Image.open(bmp_path)
    
    # 确保图像是索引色模式
    if img.mode != 'P':
        raise ValueError("输入图片必须是索引色模式哦~")
    
    palette = img.getpalette()
    width, height = img.size
    
    # 判断调色板大小，确定图像类型
    colors = len(palette) // 3
    if colors <= 16:
        img_type = 0x14  # 4bpp
        palette_size = 16
        if len(palette) > 48:  # 16色 * 3(RGB)
            raise ValueError("4bpp模式调色板必须是16色或更少呢~")
    else:
        img_type = 0x13  # 8bpp
        palette_size = 256
        if len(palette) > 768:  # 256色 * 3(RGB)
            raise ValueError("8bpp模式调色板必须是256色或更少呢~")
    
    # 准备GS文件头
    header = struct.pack('<2sHHHH6x',
        b'GS',      # 魔数
        img_type,   # 图像类型
        width,      # 宽度
        height,     # 高度
        0          # Mipmap数量
    )
    
    # 准备调色板数据
    palette_data = bytearray()
    for i in range(0, palette_size * 3, 3):
        if i < len(palette):
            r, g, b = palette[i:i+3]
        else:
            r, g, b = 0, 0, 0  # 填充剩余调色板为黑色
            
        # 4bpp模式下纯黑色设置Alpha为0，8bpp模式下统一使用0x80
        if img_type == 0x14:  # 4bpp
            alpha = 0x00 if (r == 0 and g == 0 and b == 0) else 0x80
        else:  # 8bpp
            alpha = 0x80  # 统一使用0x80
            
        palette_data.extend([r, g, b, alpha])
    
    # 添加填充，确保数据对齐
    padding_size = 0x50 - (len(header) + len(palette_data))
    padding = bytes([0] * padding_size)
    
    # 获取图像数据
    img_data = np.array(img)
    
    # 根据不同的位深度处理像素数据
    if img_type == 0x14:  # 4bpp
        pixel_data = []
        for row in img_data:
            row_data = bytearray()
            for i in range(0, len(row), 2):
                if i + 1 < len(row):
                    low = (row[i] & 0x0F)
                    high = (row[i + 1] & 0x0F)
                    byte = (high << 4) | low
                else:
                    byte = (row[i] & 0x0F)
                row_data.append(byte)
            pixel_data.append(row_data)
    else:  # 8bpp
        pixel_data = []
        for row in img_data:
            pixel_data.append(bytearray(row))
    
    # 合并所有行数据
    final_data = bytearray()
    for row in pixel_data:
        final_data.extend(row)
    
    # 写入GS文件
    with open(gs_path, 'wb') as f:
        f.write(header)
        f.write(palette_data)
        f.write(padding)
        f.write(final_data)


convert_bmp_to_gs(r"UNPACKER/TELOP1.bmp", r"UNPACKER/TELOP1.GS")