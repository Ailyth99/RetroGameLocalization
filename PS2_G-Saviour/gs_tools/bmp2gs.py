import struct
from PIL import Image
import numpy as np

def convert_bmp_to_gs(bmp_path, gs_path):
    
    img = Image.open(bmp_path)

    if img.mode != 'P':
        raise ValueError("图片必须是索引色模式 must be indexed color mode")
    
    palette = img.getpalette()
    width, height = img.size
    
    # 判断调色板
    colors = len(palette) // 3
    if colors <= 16:
        img_type = 0x14  # 4bpp
        palette_size = 16
        if len(palette) > 48:  # 16色 * 3(RGB)
            raise ValueError("调色板数量错误，应为16或更少")
    else:
        img_type = 0x13  # 8bpp
        palette_size = 256
        if len(palette) > 768:  # 256色 * 3(RGB)
            raise ValueError("调色板数量错误，应为256或更少")
    
    # 准备GS文件头
    header = struct.pack('<2sHHHH6x',
        b'GS',      # magic id
        img_type,   # bpp
        width,       
        height,      
        0           
    )
    
    # 调色板数据
    palette_data = bytearray()
    for i in range(0, palette_size * 3, 3):
        if i < len(palette):
            r, g, b = palette[i:i+3]
        else:
            r, g, b = 0, 0, 0  
            
        ##000000全部透明
        if img_type == 0x14:  # 4bpp
            alpha = 0x00 if (r == 0 and g == 0 and b == 0) else 0x80
        else:  # 8bpp
            alpha = 0x00  
            
        palette_data.extend([r, g, b, alpha])
    
    # 添加填充 
    padding_size = 0x50 - (len(header) + len(palette_data))
    padding = bytes([0] * padding_size)
    
     
    img_data = np.array(img)
    
    
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
    
    
    final_data = bytearray()
    for row in pixel_data:
        final_data.extend(row)
    
   
    with open(gs_path, 'wb') as f:
        f.write(header)
        f.write(palette_data)
        f.write(padding)
        f.write(final_data)


convert_bmp_to_gs(r"\MC_BMP\001.bmp", r"\MC_BMP\001.gs")