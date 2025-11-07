import os, struct, zlib, argparse, json, time

def repack_rbb_ultimate_v2(input_dir, original_rbb_path, output_rbb_path, compression_level):
    """
    RBB RepackeR:
    - Rebuilds RBB with a dynamic, compact layout (no size limits).
    - Allows user-defined zlib compression level.
    - All previous fixes (alignment, flags, case-sensitivity) are included.
    """
    print(f"RBB REPACKER"); start_time = time.time()
    manifest_path = os.path.join(input_dir, "manifest.json")
    if not os.path.exists(manifest_path): raise FileNotFoundError("未找到 manifest.json。")
    if not os.path.exists(original_rbb_path): raise FileNotFoundError(f"找不到模板 '{original_rbb_path}'。")

    print(f"[*] 正在加载清单文件: '{manifest_path}'")
    with open(manifest_path, 'r', encoding='utf-8') as f: manifest = json.load(f)
    print(f"  -> 清单加载成功，包含 {len(manifest)} 个文件条目。")
    
    print(f"[*] 正在分析 RBB 模板并保留未知块...")
    preserved_chunks, original_chunk_order = [], []
    with open(original_rbb_path, 'rb') as f_tpl:
        f_tpl.seek(8)
        while True:
            chunk_sig_bytes = f_tpl.read(4)
            if not chunk_sig_bytes: break
            chunk_sig = chunk_sig_bytes.decode('ascii', 'ignore')
            chunk_size = struct.unpack('<I', f_tpl.read(4))[0]
            original_chunk_order.append(chunk_sig)
            if chunk_sig not in ['RIDX', 'TYPE', 'EXIX', 'RBB0']:
                preserved_chunks.append({'signature': chunk_sig_bytes, 'size': chunk_size, 'data': f_tpl.read(chunk_size)})
            else: f_tpl.seek(chunk_size, 1)
    
    print(f"[*] 正在准备新的文件数据 (压缩等级: {compression_level})...")
    new_ridx_entries, new_type_entries, new_exix_entries, rbb0_data_blobs = [], [], [], []
    sorted_manifest = sorted(manifest, key=lambda x: x['id'])
    total_files = len(sorted_manifest)
    
    current_new_offset = 0

    for i, entry in enumerate(sorted_manifest):
        progress = (i + 1) / total_files; bar_length = 30; filled_length = int(bar_length * progress)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        print(f'\r  -> 正在处理文件 {i+1}/{total_files} [{bar}] {progress:.1%}', end='', flush=True)

        file_path = os.path.join(input_dir, entry['disk_filename'])
        uncompressed_data = b''
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f: uncompressed_data = f.read()
        
        comp_data = uncompressed_data
        if entry.get('original_ridx_terminator') == 0x80:
            comp_data = zlib.compress(uncompressed_data, level=compression_level)

        ext, flag = entry['extension'], entry['original_type_flag']
        type_entry = ext.encode('ascii').ljust(3, b'\x00') + bytes([flag])
        new_type_entries.append(type_entry)

        rbb0_data_blobs.append(comp_data)
        
        new_ridx_entries.append({'start_addr': current_new_offset, 'comp_size': len(comp_data), 'terminator': entry['original_ridx_terminator']})
        new_exix_entries.append({'uncomp_size': len(uncompressed_data)})
        current_new_offset += len(comp_data)
        
    print("\n  -> 所有文件处理完毕。")

    print("[*] 正在将所有数据块写入新的 RBB 文件...")
    with open(output_rbb_path, 'wb') as f_out:
        f_out.write(b'siff'); f_out.write(b'\x00\x00\x00\x00')
        preserved_idx = 0
        for chunk_sig_str in original_chunk_order:
            if chunk_sig_str == 'RIDX':
                f_out.write(b'RIDX'); f_out.write(struct.pack('<I', len(new_ridx_entries) * 8))
                for ridx_entry in new_ridx_entries:
                    f_out.write(struct.pack('<I', ridx_entry['start_addr'])); f_out.write(ridx_entry['comp_size'].to_bytes(3, 'little')); f_out.write(bytes([ridx_entry['terminator']]))
            elif chunk_sig_str == 'TYPE':
                f_out.write(b'TYPE'); f_out.write(struct.pack('<I', len(new_type_entries) * 4))
                for type_entry in new_type_entries: f_out.write(type_entry)
            elif chunk_sig_str == 'EXIX':
                f_out.write(b'EXIX'); f_out.write(struct.pack('<I', len(new_exix_entries) * 4))
                for entry in new_exix_entries: f_out.write(struct.pack('<I', entry['uncomp_size']))
            elif chunk_sig_str == 'RBB0':
                rbb0_total_size = sum(len(b) for b in rbb0_data_blobs)
                f_out.write(b'RBB0'); f_out.write(struct.pack('<I', rbb0_total_size))
                for blob in rbb0_data_blobs: f_out.write(blob)
            else:
                if preserved_idx < len(preserved_chunks) and preserved_chunks[preserved_idx]['signature'].decode('ascii', 'ignore') == chunk_sig_str:
                    chunk = preserved_chunks[preserved_idx]; f_out.write(chunk['signature']); f_out.write(struct.pack('<I', chunk['size'])); f_out.write(chunk['data'])
                    preserved_idx += 1
        
        total_container_size = f_out.tell()
        f_out.seek(4); f_out.write(struct.pack('<I', total_container_size))
    print(f"封包成功！总耗时: {time.time() - start_time:.2f} 秒。")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Ultimate RBB Repacker v2 (Adjustable Compression).")
    parser.add_argument("input_dir", help="Input directory.")
    parser.add_argument("original_rbb", help="Original .rbb template.")
    parser.add_argument("-o", "--output", dest="output_file", help="Output .rbb file path.")
    parser.add_argument("-l", "--level", dest="compression_level", type=int, default=6, choices=range(0, 10),
                        help="Zlib compression level (0-9). Default is 6.")
    
    args = parser.parse_args();
    output_file = args.output_file or os.path.basename(os.path.normpath(args.input_dir)) + "_repacked.rbb"
    
    try:
        repack_rbb_ultimate_v2(args.input_dir, args.original_rbb, output_file, args.compression_level)
    except (ValueError, FileNotFoundError) as e:
        print(f"\n错误: {e}")