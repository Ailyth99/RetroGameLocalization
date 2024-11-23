import struct
from PIL import Image
import numpy as np

def convert_bmp_to_gs(bmp_path, gs_path):
    # 读取BMP文件
    img = Image.open(bmp_path)
    
    # 确保图像是4bpp模式
    if img.mode != 'P':
        raise ValueError("输入图片必须是索引色模式哦~")
    
    palette = img.getpalette()
    if not palette or len(palette) > 48:  # 16色 * 3(RGB)
        raise ValueError("调色板必须是16色或更少呢~")
    
    width, height = img.size
    
    # 准备GS文件头
    header = struct.pack('<2sHHHH6x',
        b'GS',      # 魔数
        0x14,       # 4bpp模式
        width,      # 宽度
        height,     # 高度
        0          # Mipmap数量
    )
    
    # 准备调色板数据 (16色 RGBA)
    palette_data = bytearray()
    for i in range(0, 48, 3):
        r, g, b = palette[i:i+3]
        # 如果是纯黑色(000000)，设置Alpha为0，否则保持0x80
        alpha = 0x00 if (r == 0 and g == 0 and b == 0) else 0x80
        palette_data.extend([r, g, b, alpha])
    
    # 添加填充，确保数据对齐
    padding_size = 0x50 - (len(header) + len(palette_data))
    padding = bytes([0] * padding_size)
    
    # 获取图像数据
    img_data = np.array(img)
    
    # 将图像数据转换为4bpp格式
    pixel_data = []
    for row in img_data:
        row_data = bytearray()
        for i in range(0, len(row), 2):
            if i + 1 < len(row):
                # 交换两个像素的顺序
                low = (row[i] & 0x0F)
                high = (row[i + 1] & 0x0F)
                byte = (high << 4) | low  # 高位放第二个像素
            else:
                # 处理奇数像素的情况
                byte = (row[i] & 0x0F)  # 低位放最后一个像素
            row_data.append(byte)
        pixel_data.append(row_data)
    
    # 直接使用原始顺序，不进行翻转
    final_data = bytearray()
    for row in pixel_data:
        final_data.extend(row)
    
    # 写入GS文件
    with open(gs_path, 'wb') as f:
        f.write(header)
        f.write(palette_data)
        f.write(padding)
        f.write(final_data)


convert_bmp_to_gs(r"UNPACKER/PRM4BPPZH.bmp", r"UNPACKER/PRM0004.GS")