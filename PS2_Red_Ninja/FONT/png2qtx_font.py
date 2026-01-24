import os
import struct
import argparse
from PIL import Image

try:
    import numpy as np
    from swizzle_ps2_4bit import _ps2_swizzle4
except ImportError:
    print("错误: 缺少必要的模块。请检查 numpy 是否安装，以及 swizzle_ps2_4bit.py 是否在同一目录。")
    exit()

def _convert_ps2_palette(palette_data: bytes) -> bytes:
    converted_palette_data: bytes = b""
    bytes_per_palette_pixel: int = 4
    if len(palette_data) % 32 != 0: return palette_data
    parts: int = len(palette_data) // 32
    for part in range(parts):
        for block in range(2):
            for stripe in range(2):
                for color in range(8):
                    palette_index = (part * 32) + (block * 8) + (stripe * 16) + color
                    palette_offset = palette_index * bytes_per_palette_pixel
                    palette_entry = palette_data[palette_offset : palette_offset + bytes_per_palette_pixel]
                    converted_palette_data += palette_entry
    return converted_palette_data

def convert_png_to_qtx_font(png_path, template_qtx_path, output_qtx_path):
    print(f"--- FONT 模式 v2: 正在将 '{os.path.basename(png_path)}' 转换为 QTX ---")
    
    try: img = Image.open(png_path)
    except Exception as e: raise ValueError(f"无法打开PNG文件: {e}")
    if img.mode != 'P': raise ValueError("输入PNG必须是索引色 ('P') 模式。")
    with open(template_qtx_path, 'rb') as f: template_data = bytearray(f.read())
    header_width, header_height = struct.unpack('<II', template_data[0x30:0x38])
    if img.size != (header_width, header_height): raise ValueError(f"PNG尺寸与FONT模板尺寸不匹配。")
    bpp_flag = template_data[0x40]
    if bpp_flag != 0x14: raise ValueError("模板文件不是 4bpp 格式。")
    bpp, num_colors_qtx = 4, 16
    print(f"  -> PNG 与 QTX 模板验证通过。")

    print("  -> 正在处理调色板...")
    rgb_palette = img.getpalette()
    transparency_info = img.info.get('transparency')
    
    alpha_values = []
    
    if isinstance(transparency_info, bytes):
        alpha_values = list(transparency_info)
    elif isinstance(transparency_info, int):
        print(f"     - 检测到单一透明色索引: {transparency_info}")
        alpha_values = [255] * num_colors_qtx 
        if transparency_info < len(alpha_values):
            alpha_values[transparency_info] = 0 #将指定索引的颜色设为全透明
    
    palette_rgbx = bytearray()
    for i in range(num_colors_qtx):
        r, g, b, a = 0, 0, 0, 255
        if i * 3 + 2 < len(rgb_palette):
            r, g, b = rgb_palette[i*3 : i*3+3]
        if i < len(alpha_values):
            a = alpha_values[i]
        
        palette_rgbx.extend([r, g, b, a // 2])
    
    swizzled_palette = _convert_ps2_palette(bytes(palette_rgbx))
    
    print("  -> 正在应用 FONT 专用线性逆向重组...")
    intermediate_width = 128
    intermediate_height = (header_width * header_height) // intermediate_width
    intermediate_image = Image.new('P', (intermediate_width, intermediate_height))
    
    TILE_WIDTH, TILE_HEIGHT = 128, 128
    GRID_COLS = header_width // TILE_WIDTH
    num_tiles = (header_width // TILE_WIDTH) * (header_height // TILE_HEIGHT)
    
    for i in range(num_tiles):
        src_x, src_y = (i % GRID_COLS) * TILE_WIDTH, (i // GRID_COLS) * TILE_HEIGHT
        tile = img.crop((src_x, src_y, src_x + TILE_WIDTH, src_y + TILE_HEIGHT))
        dest_y_on_strip = i * TILE_HEIGHT
        intermediate_image.paste(tile, (0, dest_y_on_strip))

    print("  -> 正在应用 4bpp 像素 Swizzle...")
    pixel_indices = list(intermediate_image.getdata())
    pixel_data_to_swizzle = bytearray((p2 << 4) | p1 for p1, p2 in zip(pixel_indices[0::2], pixel_indices[1::2]))
    swizzled_pixel_data = _ps2_swizzle4(bytes(pixel_data_to_swizzle), intermediate_width, intermediate_height)

    pixel_data_offset, pixel_data_size = 0x200, len(swizzled_pixel_data)
    palette_offset = pixel_data_offset + pixel_data_size + 128
    
    template_data[pixel_data_offset : pixel_data_offset + pixel_data_size] = swizzled_pixel_data
    template_data[palette_offset : palette_offset + len(swizzled_palette)] = swizzled_palette
    
    with open(output_qtx_path, 'wb') as f: f.write(template_data)
    print(f"\n成功！已将新的 FONT QTX 文件保存到: '{output_qtx_path}'")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Converts an indexed PNG back to a FONT QTX file (v2, robust transparency handling).")
    parser.add_argument("png_file", help="Path to the modified, indexed 1024x512 PNG file.")
    parser.add_argument("template_qtx", help="Path to the original font.qtx file to use as a template.")
    parser.add_argument("-o", "--output", dest="output_file", help="Path for the new output font.qtx file.")
    args = parser.parse_args()
    
    output_file = args.output_file or os.path.splitext(os.path.basename(args.png_file))[0] + ".qtx"
    
    try:
        convert_png_to_qtx_font(args.png_file, args.template_qtx, output_file)
    except (ValueError, IndexError) as e:
        print(f"\n错误: {e}")