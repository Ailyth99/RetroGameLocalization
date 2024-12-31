def extract_text_blocks(data, start_offset, end_offset):
    print(f"\n🔍 开始处理文本区块：0x{start_offset:X} - 0x{end_offset:X}")
    blocks = []
    current_pos = start_offset
    block_number = 1
    
    while current_pos < end_offset:
        block_start = current_pos
        text_bytes = bytearray()
        
        while current_pos < end_offset:
            # 检查文本块结束
            if data[current_pos] == 0:
                zero_count = 0
                temp_pos = current_pos
                while temp_pos < end_offset and data[temp_pos] == 0:
                    zero_count += 1
                    temp_pos += 1
                if zero_count >= 2:
                    break
            
            # 收集字节
            text_bytes.append(data[current_pos])
            current_pos += 1
        
        # 尝试用 EUC-JP 解码
        try:
            text = text_bytes.decode('euc-jp').strip()
            if text:
                print(f"\n✅ 找到文本块 {block_number}：{text}")
                blocks.append({
                    'number': f'{block_number:04d}',
                    'start': f'0x{block_start:08X}',
                    'end': f'0x{current_pos:08X}',
                    'text': text
                })
                block_number += 1
        except UnicodeDecodeError as e:
            print(f"\n⚠️ 解码错误 at 0x{current_pos:X}: {e}")
        
        # 跳过结束标记
        while current_pos < end_offset and data[current_pos] == 0:
            current_pos += 1
            
    print(f"\n📊 该区块共找到 {len(blocks)} 个文本块")
    return blocks

def export_text_blocks(blocks, output_file):
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for block in blocks:
                f.write(f"[{block['number']}][{block['start']},{block['end']}]\n")
                f.write(f"JP：{block['text']}\n")
                f.write("CN：\n\n")
        print(f"\n💾 文本已成功导出到：{output_file}")
    except Exception as e:
        print(f"❌ 导出文本时出错：{e}")

def main():
    print("🌟 开始处理文本导出...")
    
    try:
        # 读取原始文件
        print("\n📂 正在读取原始文件...")
        with open('SLPS_250.09', 'rb') as f:
            data = f.read()
        print(f"✨ 成功读取文件，大小：{len(data)} 字节")
        
        # 处理两个文本区域
        blocks1 = extract_text_blocks(data, 0xEC430, 0xEE5FB)
        blocks2 = extract_text_blocks(data, 0xEEA50, 0xEEF8D)
        
        # 合并并导出所有文本块
        total_blocks = blocks1 + blocks2
        print(f"\n🎉 总共找到 {len(total_blocks)} 个文本块")
        export_text_blocks(total_blocks, 'output.txt')
        
    except Exception as e:
        print(f"\n❌ 程序执行出错：{e}")

if __name__ == "__main__":
    main()