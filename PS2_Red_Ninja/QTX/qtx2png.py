import os
import struct
import argparse
from PIL import Image

#通用调色板 Unswizzle
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

#8BPP像素Unswzl
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
            if not swizzle_flag and swizzle_id < len(image_data):
                converted_data[y * img_width + x] = image_data[swizzle_id]
            elif swizzle_flag:
                converted_data[swizzle_id] = image_data[y * img_width + x]
    return converted_data

#4BPPType1像素Unswizzle
PSMT4_PAGE_WIDTH, PSMT4_PAGE_HEIGHT, PSMT4_BLOCK_HEIGHT = 128, 128, 16
PSMCT32_PAGE_WIDTH, PSMCT32_PAGE_HEIGHT, PSMCT32_BLOCK_HEIGHT = 64, 32, 8


#https://github.com/bartlomiejduda/ReverseBox/blob/main/reversebox/image/swizzling/swizzle_ps2_4bit.py
def _unswizzle4_convert_block(input_block_data: bytes) -> bytes:
    unswizzle_lut_table = (
        0, 8, 16, 24, 32, 40, 48, 56, 2, 10, 18, 26, 34, 42, 50, 58, 4, 12, 20, 28, 36, 44, 52, 60, 6, 14, 22, 30, 38, 46, 54, 62, 64, 72, 80, 88, 96, 104, 112, 120, 66, 74, 82, 90, 98, 106, 114, 122, 68, 76, 84, 92, 100, 108, 116, 124, 70, 78, 86, 94, 102, 110, 118, 126, 33, 41, 49, 57, 1, 9, 17, 25, 35, 43, 51, 59, 3, 11, 19, 27, 37, 45, 53, 61, 5, 13, 21, 29, 39, 47, 55, 63, 7, 15, 23, 31, 97, 105, 113, 121, 65, 73, 81, 89, 99, 107, 115, 123, 67, 75, 83, 91, 101, 109, 117, 125, 69, 77, 85, 93, 103, 111, 119, 127, 71, 79, 87, 95, 32, 40, 48, 56, 0, 8, 16, 24, 34, 42, 50, 58, 2, 10, 18, 26, 36, 44, 52, 60, 4, 12, 20, 28, 38, 46, 54, 62, 6, 14, 22, 30, 96, 104, 112, 120, 64, 72, 80, 88, 98, 106, 114, 122, 66, 74, 82, 90, 100, 108, 116, 124, 68, 76, 84, 92, 102, 110, 118, 126, 70, 78, 86, 94, 1, 9, 17, 25, 33, 41, 49, 57, 3, 11, 19, 27, 35, 43, 51, 59, 5, 13, 21, 29, 37, 45, 53, 61, 7, 15, 23, 31, 39, 47, 55, 63, 65, 73, 81, 89, 97, 105, 113, 121, 67, 75, 83, 91, 99, 107, 115, 123, 69, 77, 85, 93, 101, 109, 117, 125, 71, 79, 87, 95, 103, 111, 119, 127
    )
    output_block_data = bytearray(256)
    index1, p_in = 0, 0
    for k in range(4):
        index0 = (k % 2) * 128
        for i in range(16):
            for j in range(4):
                c_out = 0x00
                i0 = unswizzle_lut_table[index0]; index0 += 1; i1, i2 = i0 // 2, (i0 & 0x1) * 4
                c_out |= (input_block_data[p_in + i1] & (0x0F << i2)) >> i2
                i0 = unswizzle_lut_table[index0]; index0 += 1; i1, i2 = i0 // 2, (i0 & 0x1) * 4
                c_out |= ((input_block_data[p_in + i1] & (0x0F << i2)) >> i2) << 4
                output_block_data[index1] = c_out; index1 += 1
        p_in += 64
    return bytes(output_block_data)

def _unswizzle4_convert_page(width: int, height: int, input_page_data: bytes) -> bytes:
    block_table4 = (0, 2, 8, 10, 1, 3, 9, 11, 4, 6, 12, 14, 5, 7, 13, 15, 16, 18, 24, 26, 17, 19, 25, 27, 20, 22, 28, 30, 21, 23, 29, 31)
    block_table32 = (0, 1, 4, 5, 16, 17, 20, 21, 2, 3, 6, 7, 18, 19, 22, 23, 8, 9, 12, 13, 24, 25, 28, 29, 10, 11, 14, 15, 26, 27, 30, 31)
    output_page_data = bytearray(PSMCT32_PAGE_WIDTH * 4 * PSMCT32_PAGE_HEIGHT)
    index32_h_arr, index32_v_arr = [0] * 32, [0] * 32
    index0 = 0
    for i in range(4):
        for j in range(8):
            index1 = block_table32[index0]; index32_h_arr[index1], index32_v_arr[index1] = j, i; index0 += 1
    n_width, n_height = width // 32, height // 16
    input_page_line_size, output_page_line_size = 256, 64
    for i in range(n_height):
        for j in range(n_width):
            in_block_nb = block_table4[i * n_width + j]
            po0 = bytearray(256)
            po1_offset = 8 * index32_v_arr[in_block_nb] * input_page_line_size + index32_h_arr[in_block_nb] * 32
            for k in range(PSMCT32_BLOCK_HEIGHT):
                start = po1_offset + k * input_page_line_size
                end = start + 32
                po0[k*32:(k+1)*32] = input_page_data[start:end]
            output_block = _unswizzle4_convert_block(bytes(po0))
            for k in range(PSMT4_BLOCK_HEIGHT):
                start = (16 * i * output_page_line_size) + j * 16 + k * output_page_line_size
                output_page_data[start:start + 16] = output_block[k*16 : k*16 + 16]
    return bytes(output_page_data)

def _ps2_unswizzle4(input_data: bytes, img_width: int, img_height: int) -> bytes:
    output_data = bytearray(len(input_data))
    n_page_w = (img_width + PSMT4_PAGE_WIDTH - 1) // PSMT4_PAGE_WIDTH
    n_page_h = (img_height + PSMT4_PAGE_HEIGHT - 1) // PSMT4_PAGE_HEIGHT
    n_page4_width_byte, n_page32_width_byte = 64, 256
    n_input_width_byte = n_page32_width_byte if n_page_h > 1 else img_height * 2
    n_output_height = PSMT4_PAGE_HEIGHT if n_page_h > 1 else img_height
    n_input_height = PSMCT32_PAGE_HEIGHT if n_page_w > 1 else img_width // 4
    n_output_width_byte = n_page4_width_byte if n_page_w > 1 else img_width // 2
    for i in range(n_page_h):
        for j in range(n_page_w):
            po0_offset = (n_input_width_byte * n_input_height) * n_page_w * i + n_input_width_byte * j
            input_page = bytearray(64 * PSMT4_PAGE_HEIGHT)
            for k in range(n_input_height):
                src_offset = po0_offset + k * n_input_width_byte * n_page_w
                dst_offset = k * n_page32_width_byte
                input_page[dst_offset:dst_offset + n_input_width_byte] = input_data[src_offset:src_offset + n_input_width_byte]
            output_page = _unswizzle4_convert_page(PSMT4_PAGE_WIDTH, PSMT4_PAGE_HEIGHT, bytes(input_page))
            pi0_offset = (n_output_width_byte * n_output_height) * n_page_w * i + n_output_width_byte * j
            for k in range(n_output_height):
                src_offset = k * n_page4_width_byte
                dst_offset = pi0_offset + k * n_output_width_byte * n_page_w
                output_data[dst_offset:dst_offset + n_output_width_byte] = output_page[src_offset:src_offset + n_output_width_byte]
    return bytes(output_data)

# 大tile重组
def reassemble_final_macro_blocks(first_pass_image, final_width, final_height):
    print("  -> TILE REBUILD...")
    
    MACRO_WIDTH = 256
    MACRO_HEIGHT = 128
    
    final_image = Image.new('P', (final_width, final_height))
    final_image.putpalette(first_pass_image.getpalette())

    cols = final_width // MACRO_WIDTH
    rows = final_height // MACRO_HEIGHT
    
    for r in range(rows):
        for c in range(cols):
            
            dest_x = c * MACRO_WIDTH
            dest_y = r * MACRO_HEIGHT
            
           
            src_x = (r % 2) * MACRO_WIDTH # 偶数行取第0列, 奇数行取第1列
            src_y = (r // 2) * (MACRO_HEIGHT * cols) + c * MACRO_HEIGHT
            
            crop_box = (src_x, src_y, src_x + MACRO_WIDTH, src_y + MACRO_HEIGHT)
            macro_block = first_pass_image.crop(crop_box)
            
            final_image.paste(macro_block, (dest_x, dest_y))
            
    return final_image

#主转换逻辑
def convert_qtx_to_png(qtx_path, png_path):
    print(f"--- Processing '{os.path.basename(qtx_path)}' ---")
    try:
        with open(qtx_path, 'rb') as f:
            
            if f.read(4) != b'MFZQ': return
            f.seek(0x30)
            header_width, header_height = struct.unpack('<II', f.read(8))
            f.seek(0x40)
            bpp_flag, = struct.unpack('<B', f.read(1))
            if bpp_flag == 0x14: bpp, num_colors = 4, 16
            elif bpp_flag == 0x13: bpp, num_colors = 8, 256
            else: return
            
            print(f"  -> Header SIZE: {header_width}x{header_height}, BPP: {bpp}")

            pixel_data_offset = 0x200
            pixel_data_size = (header_width * header_height * bpp) // 8
            palette_offset = pixel_data_offset + pixel_data_size + 128
            f.seek(palette_offset)
            raw_palette = f.read(num_colors * 4)
            if len(raw_palette) < num_colors * 4: return
            unswizzled_palette_data = _convert_ps2_palette(raw_palette)
            processed_palette = bytearray()
            for i in range(num_colors):
                r, g, b, x = unswizzled_palette_data[i*4 : i*4+4]; a = min(x * 2, 255)
                processed_palette.extend([r, g, b, a])
            f.seek(pixel_data_offset)
            raw_pixel_data = f.read(pixel_data_size)
            
            #第一步: 生成128PX的中间长条图 (PS2 TYPE 1 unswizzle)
            intermediate_width = 128
            total_pixels = header_width * header_height
            if total_pixels == 0: return
            intermediate_height = total_pixels // intermediate_width
            intermediate_image = Image.new('P', (intermediate_width, intermediate_height))
            intermediate_image.putpalette(processed_palette, 'RGBA')
            
            pixel_indices = []
            if bpp == 8:
                unswizzled_data = _convert_ps2_8bit(raw_pixel_data, intermediate_width, intermediate_height, False)
                pixel_indices = list(unswizzled_data)
            elif bpp == 4:
                unswizzled_data = _ps2_unswizzle4(raw_pixel_data, intermediate_width, intermediate_height)
                for byte in unswizzled_data: pixel_indices.extend([byte & 0x0F, (byte >> 4) & 0x0F])
            intermediate_image.putdata(pixel_indices)

            # 步骤2: 第一次重组 (图块级unswzl)
            block_table4 = (0, 2, 8, 10, 1, 3, 9, 11, 4, 6, 12, 14, 5, 7, 13, 15, 16, 18, 24, 26, 17, 19, 25, 27, 20, 22, 28, 30, 21, 23, 29, 31)
            TILE_WIDTH, TILE_HEIGHT = 128, 64
            GRID_COLS = header_width // TILE_WIDTH
            num_tiles = (header_width // TILE_WIDTH) * (header_height // TILE_HEIGHT)
            first_pass_image = Image.new('P', (header_width, header_height))
            first_pass_image.putpalette(processed_palette, 'RGBA')

            for i in range(num_tiles):
                src_tile_index = i if bpp == 8 else block_table4[i % len(block_table4)]
                src_y = src_tile_index * TILE_HEIGHT
                if src_y + TILE_HEIGHT > intermediate_image.height: continue
                tile = intermediate_image.crop((0, src_y, TILE_WIDTH, src_y + TILE_HEIGHT))
                dest_x, dest_y = (i % GRID_COLS) * TILE_WIDTH, (i // GRID_COLS) * TILE_HEIGHT
                first_pass_image.paste(tile, (dest_x, dest_y))
            
            #步骤3: 最终重组
            truly_final_image = first_pass_image
            if bpp == 4 and header_width > 256: #只对需要重组的大图操作
                truly_final_image = reassemble_final_macro_blocks(first_pass_image, header_width, header_height)
            
            truly_final_image.save(png_path)
            print(f"success！: '{os.path.basename(png_path)}'")

    except Exception as e:
        print(f"ERROR: {e}")

def batch_convert(input_path):
    if os.path.isfile(input_path): files_to_convert = [input_path]
    elif os.path.isdir(input_path):
        files_to_convert = [os.path.join(input_path, f) for f in os.listdir(input_path) if f.lower().endswith('.qtx')]
    else: return
    for qtx_file in files_to_convert:
        output_dir = os.path.dirname(qtx_file)
        png_name = os.path.splitext(os.path.basename(qtx_file))[0] + ".png"
        png_path = os.path.join(output_dir, png_name)
        convert_qtx_to_png(qtx_file, png_path)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="QTX to PNG Grand Finale Converter.")
    parser.add_argument("input_path", help="要转换的.qtx文件或包含.qtx文件的目录。")
    args = parser.parse_args()
    batch_convert(args.input_path)