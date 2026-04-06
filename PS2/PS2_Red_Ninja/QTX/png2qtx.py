import os
import struct
import argparse
from PIL import Image

try:
    import numpy as np
    from swizzle_ps2_4bit import _ps2_swizzle4
except ImportError:
    print("缺少依赖")
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

def _convert_ps2_8bit(image_data: bytes, img_width: int, img_height: int, swizzle_flag: bool) -> bytes:
    converted_data: bytearray = bytearray(img_width * img_height)
    for y in range(img_height):
        for x in range(img_width):
            block_location = (y & (~0xF)) * img_width + (x & (~0xF)) * 2
            swap_selector = (((y + 2) >> 2) & 0x1) * 4
            pos_y = (((y & (~3)) >> 1) + (y & 1)) & 0x7
            column_location = pos_y * img_width * 2 + ((x + swap_selector) & 0x7) * 4
            byte_num = ((y >> 1) & 1) + ((x >> 2) & 2)
            swizzle_id = block_location + column_location + byte_num
            if swizzle_flag and swizzle_id < len(converted_data):
                converted_data[swizzle_id] = image_data[y * img_width + x]
    return converted_data

def convert_png_to_qtx(png_path, template_qtx_path, output_qtx_path):
 
    try: img = Image.open(png_path)
    except Exception as e: raise ValueError(f"无法打开PNG文件: {e}")
    if img.mode != 'P': raise ValueError("输入PNG必须是索引色 ('P') 模式。")
    with open(template_qtx_path, 'rb') as f: template_data = bytearray(f.read())
    header_width, header_height = struct.unpack('<II', template_data[0x30:0x38])
    if img.size != (header_width, header_height): raise ValueError(f"PNG尺寸与QTX模板尺寸不匹配。")
    bpp_flag = template_data[0x40]
    bpp, num_colors_qtx = (4, 16) if bpp_flag == 0x14 else (8, 256) if bpp_flag == 0x13 else (0, 0)
    if bpp == 0: raise ValueError(f"未知的QTX BPP标志: {hex(bpp_flag)}")

    print("  -> 正在处理调色板...")
    rgb_palette = img.getpalette()
    transparency_info = img.info.get('transparency')
    
    alpha_values = []
    
    if isinstance(transparency_info, bytes):
        #1: transparency是一个字节串 (多级透明度)
        alpha_values = list(transparency_info)
    elif isinstance(transparency_info, int):
        #2: transparency是一个整数 (单一透明色索引)
        print(f"     - 检测到单一透明色索引: {transparency_info}")
        alpha_values = [255] * num_colors_qtx 
        if transparency_info < len(alpha_values):
            alpha_values[transparency_info] = 0 
            
    palette_rgbx = bytearray()
    for i in range(num_colors_qtx):
        r, g, b, a = 0, 0, 0, 255
        if i * 3 + 2 < len(rgb_palette):
            r, g, b = rgb_palette[i*3 : i*3+3]
        if i < len(alpha_values):
            a = alpha_values[i]
        
        palette_rgbx.extend([r, g, b, a // 2])
    
    swizzled_palette = _convert_ps2_palette(bytes(palette_rgbx))
    
    first_pass_image = img
    if bpp == 4 and header_width >= 512:
        MACRO_WIDTH, MACRO_HEIGHT = 256, 128
        first_pass_image = Image.new('P', img.size)
        first_pass_image.putpalette(img.getpalette())
        cols, rows = header_width // MACRO_WIDTH, header_height // MACRO_HEIGHT
        for r in range(rows):
            for c in range(cols):
                src_x, src_y = c * MACRO_WIDTH, r * MACRO_HEIGHT
                dest_col_in_pair = r % 2; pair_index = r // 2
                dest_x_new, dest_y_new = dest_col_in_pair * MACRO_WIDTH, pair_index * (MACRO_HEIGHT * cols) + c * MACRO_HEIGHT
                macro_block = img.crop((src_x, src_y, src_x + MACRO_WIDTH, src_y + MACRO_HEIGHT))
                first_pass_image.paste(macro_block, (dest_x_new, dest_y_new))

    intermediate_width, total_pixels = 128, header_width * header_height
    intermediate_height = total_pixels // intermediate_width
    intermediate_image = Image.new('P', (intermediate_width, intermediate_height))
    
    TILE_WIDTH, TILE_HEIGHT = 128, 64
    GRID_COLS, num_tiles = header_width // TILE_WIDTH, (header_width // TILE_WIDTH) * (header_height // TILE_HEIGHT)
    block_table4 = (0, 2, 8, 10, 1, 3, 9, 11, 4, 6, 12, 14, 5, 7, 13, 15, 16, 18, 24, 26, 17, 19, 25, 27, 20, 22, 28, 30, 21, 23, 29, 31)
    
    for i in range(num_tiles):
        src_x = (i % GRID_COLS) * TILE_WIDTH
        src_y = (i // GRID_COLS) * TILE_HEIGHT
        tile = first_pass_image.crop((src_x, src_y, src_x + TILE_WIDTH, src_y + TILE_HEIGHT))
        
        dest_tile_index_on_strip = i
        if bpp == 4:
            dest_tile_index_on_strip = block_table4[i % len(block_table4)]
        
        dest_y_on_strip = dest_tile_index_on_strip * TILE_HEIGHT
        intermediate_image.paste(tile, (0, dest_y_on_strip))

    pixel_indices = list(intermediate_image.getdata())
    
    if bpp == 8:
        swizzled_pixel_data = _convert_ps2_8bit(bytes(pixel_indices), intermediate_width, intermediate_height, True)
    else: # 4bpp
        pixel_data_to_swizzle = bytearray((p2 << 4) | p1 for p1, p2 in zip(pixel_indices[0::2], pixel_indices[1::2]))
        swizzled_pixel_data = _ps2_swizzle4(bytes(pixel_data_to_swizzle), intermediate_width, intermediate_height)

    pixel_data_offset, pixel_data_size = 0x200, len(swizzled_pixel_data)
    palette_offset = pixel_data_offset + pixel_data_size + 128
    template_data[pixel_data_offset : pixel_data_offset + pixel_data_size] = swizzled_pixel_data
    template_data[palette_offset : palette_offset + len(swizzled_palette)] = swizzled_palette
    with open(output_qtx_path, 'wb') as f: f.write(template_data)
    print(f"\n成功！已将新的 QTX 文件保存到: '{output_qtx_path}'")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Converts an indexed PNG back to a QTX file (v6, transparency bug fixed).")
    parser.add_argument("png_file", help="Path to the modified, indexed PNG file.")
    parser.add_argument("template_qtx", help="Path to the original QTX file to use as a template.")
    parser.add_argument("-o", "--output", dest="output_file", help="Path for the new output QTX file.")
    args = parser.parse_args()
    output_file = args.output_file or os.path.splitext(os.path.basename(args.png_file))[0] + ".qtx"
    try: convert_png_to_qtx(args.png_file, args.template_qtx, output_file)
    except (ValueError, IndexError) as e: print(f"\n错误: {e}")