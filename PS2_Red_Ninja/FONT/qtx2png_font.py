import os
import struct
import argparse
from PIL import Image


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
PSMT4_PAGE_WIDTH, PSMT4_PAGE_HEIGHT, PSMT4_BLOCK_HEIGHT = 128, 128, 16
PSMCT32_PAGE_WIDTH, PSMCT32_PAGE_HEIGHT, PSMCT32_BLOCK_HEIGHT = 64, 32, 8
def _unswizzle4_convert_block(input_block_data: bytes) -> bytes:
    unswizzle_lut_table = (
        0, 8, 16, 24, 32, 40, 48, 56, 2, 10, 18, 26, 34, 42, 50, 58, 4, 12, 20, 28, 36, 44, 52, 60, 6, 14, 22, 30, 38, 46, 54, 62, 64, 72, 80, 88, 96, 104, 112, 120, 66, 74, 82, 90, 98, 106, 114, 122, 68, 76, 84, 92, 100, 108, 116, 124, 70, 78, 86, 94, 102, 110, 118, 126, 33, 41, 49, 57, 1, 9, 17, 25, 35, 43, 51, 59, 3, 11, 19, 27, 37, 45, 53, 61, 5, 13, 21, 29, 39, 47, 55, 63, 7, 15, 23, 31, 97, 105, 113, 121, 65, 73, 81, 89, 99, 107, 115, 123, 67, 75, 83, 91, 101, 109, 117, 125, 69, 77, 85, 93, 103, 111, 119, 127, 71, 79, 87, 95, 32, 40, 48, 56, 0, 8, 16, 24, 34, 42, 50, 58, 2, 10, 18, 26, 36, 44, 52, 60, 4, 12, 20, 28, 38, 46, 54, 62, 6, 14, 22, 30, 96, 104, 112, 120, 64, 72, 80, 88, 98, 106, 114, 122, 66, 74, 82, 90, 100, 108, 116, 124, 68, 76, 84, 92, 102, 110, 118, 126, 70, 78, 86, 94, 1, 9, 17, 25, 33, 41, 49, 57, 3, 11, 19, 27, 35, 43, 51, 59, 5, 13, 21, 29, 37, 45, 53, 61, 7, 15, 23, 31, 39, 47, 55, 63, 65, 73, 81, 89, 97, 105, 113, 121, 67, 75, 83, 91, 99, 107, 115, 123, 69, 77, 85, 93, 101, 109, 117, 125, 71, 79, 87, 95, 103, 111, 119, 127
    )
    output_block_data = bytearray(256); index1, p_in = 0, 0
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
                start, end = po1_offset + k * input_page_line_size, po1_offset + k * input_page_line_size + 32
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

def convert_qtx_to_png_font_final(qtx_path, png_path):
    print(f"--- FONT模式: 正在处理 '{os.path.basename(qtx_path)}' ---")
    try:
        with open(qtx_path, 'rb') as f:
            if f.read(4) != b'MFZQ': return
            f.seek(0x30)
            header_width, header_height = struct.unpack('<II', f.read(8))
            f.seek(0x40)
            bpp_flag, = struct.unpack('<B', f.read(1))
            if bpp_flag != 0x14: return
            bpp, num_colors = 4, 16
            
            pixel_data_offset = 0x200
            pixel_data_size = (header_width * header_height * bpp) // 8
            palette_offset = pixel_data_offset + pixel_data_size + 128
            f.seek(palette_offset)
            raw_palette = f.read(num_colors * 4);
            if len(raw_palette) < num_colors * 4: return
            
            unswizzled_palette_data = _convert_ps2_palette(raw_palette)
            processed_palette = bytearray()
            for i in range(num_colors):
                r, g, b, x = unswizzled_palette_data[i*4 : i*4+4]; a = min(x * 2, 255)
                processed_palette.extend([r, g, b, a])
            
            f.seek(pixel_data_offset)
            raw_pixel_data = f.read(pixel_data_size)
            
            intermediate_width = 128
            total_pixels = header_width * header_height
            intermediate_height = total_pixels // intermediate_width
            intermediate_image = Image.new('P', (intermediate_width, intermediate_height))
            intermediate_image.putpalette(processed_palette, 'RGBA')
            
            unswizzled_data = _ps2_unswizzle4(raw_pixel_data, intermediate_width, intermediate_height)
            pixel_indices = []
            for byte in unswizzled_data: pixel_indices.extend([byte & 0x0F, (byte >> 4) & 0x0F])
            intermediate_image.putdata(pixel_indices)

            print(f"  -> 使用 FONT 专用线性重排 (图块尺寸: 128x128)...")
            
            TILE_WIDTH = 128
            TILE_HEIGHT = 128
            
            GRID_COLS = header_width // TILE_WIDTH
            num_tiles = (header_width // TILE_WIDTH) * (header_height // TILE_HEIGHT)
            
            final_image = Image.new('P', (header_width, header_height))
            final_image.putpalette(processed_palette, 'RGBA')

            for i in range(num_tiles):
                src_y = i * TILE_HEIGHT
                tile = intermediate_image.crop((0, src_y, TILE_WIDTH, src_y + TILE_HEIGHT))
                
                dest_x = (i % GRID_COLS) * TILE_WIDTH
                dest_y = (i // GRID_COLS) * TILE_HEIGHT
                final_image.paste(tile, (dest_x, dest_y))
            
            final_image.save(png_path)
            print(f"成功！已将 FONT 图像保存为: '{os.path.basename(png_path)}'")

    except Exception as e:
        print(f"处理 FONT 文件时发生错误: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Final Font-specific QTX to PNG converter.")
    parser.add_argument("qtx_file", help="Path to the font.qtx file.")
    parser.add_argument("-o", "--output", dest="output_file", help="Path for the output PNG file.")
    args = parser.parse_args()
    
    output_file = args.output_file or os.path.splitext(os.path.basename(args.qtx_file))[0] + ".png"
    convert_qtx_to_png_font_final(args.qtx_file, output_file)