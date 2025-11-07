import os, struct, zlib, argparse, re, json

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', '_', filename)

def unpack_rbb_definitive(rbb_path, output_dir):
    if not os.path.exists(rbb_path): raise FileNotFoundError(f"文件 '{rbb_path}' 不存在。")
    os.makedirs(output_dir, exist_ok=True)
    
    ridx_entries, type_entries, exix_entries = [], [], []
    rbb0_data_offset = 0

    with open(rbb_path, 'rb') as f:
        f.seek(8)
        current_offset = f.tell()
        while True:
            f.seek(current_offset); chunk_sig = f.read(4)
            if not chunk_sig: break
            chunk_size = struct.unpack('<I', f.read(4))[0]
            
            if chunk_sig == b'RIDX':
                for _ in range(chunk_size // 8):
                    ridx_entries.append({'start_addr': struct.unpack('<I', f.read(4))[0], 'comp_size': int.from_bytes(f.read(3), 'little'), 'terminator': f.read(1)[0]})
            elif chunk_sig == b'TYPE':
                for _ in range(chunk_size // 4):
                    b = f.read(4)
                    type_entries.append({'ext': b[:3].decode('ascii', 'ignore').strip('\x00'), 'flag': b[3]})
            elif chunk_sig == b'EXIX':
                for _ in range(chunk_size // 4): exix_entries.append({'uncomp_size': struct.unpack('<I', f.read(4))[0]})
            elif chunk_sig == b'RBB0': rbb0_data_offset = f.tell()
            current_offset += 8 + chunk_size
        
        manifest_data = []
        for i in range(len(ridx_entries)):
            ext_info = type_entries[i] if i < len(type_entries) else {'ext': 'bin', 'flag': 0}
            manifest_entry = {
                "id": i,
                "original_start_addr": ridx_entries[i]['start_addr'],
                "extension": ext_info['ext'],
                "original_type_flag": ext_info['flag'],
                "uncompressed_size": exix_entries[i]['uncomp_size'] if i < len(exix_entries) else 0,
                "original_compressed_size": ridx_entries[i]['comp_size'],
                "original_ridx_terminator": ridx_entries[i]['terminator']
            }
            manifest_entry["was_compressed"] = (manifest_entry['original_ridx_terminator'] == 0x80)
            
            if manifest_entry['extension'] == 'NON' or manifest_entry['original_compressed_size'] == 0:
                manifest_entry['disk_filename'] = f"{i:05d}.none"
                manifest_data.append(manifest_entry); continue
            
            f.seek(rbb0_data_offset + manifest_entry['original_start_addr'])
            original_data = f.read(manifest_entry['original_compressed_size'])
            output_data = original_data
            try:
                if manifest_entry["was_compressed"]: output_data = zlib.decompress(original_data)
            except zlib.error: manifest_entry["was_compressed"] = False
            
            base_filename_without_ext = f"{i:05d}"
            ext_lower = manifest_entry['extension'].lower()
            final_filename = f"{base_filename_without_ext}.{ext_lower}"

            if ext_lower == 'qtx' and len(output_data) > 0x60:
                try:
                    name_data = output_data[0x60:]; null_pos = name_data.find(b'\x00')
                    if null_pos != -1:
                        internal_name = sanitize_filename(name_data[:null_pos].decode('ascii', 'ignore'))
                        if internal_name:
                            final_filename_with_internal = f"{base_filename_without_ext}_{internal_name}"
                            if not internal_name.lower().endswith(f'.{ext_lower}'):
                                final_filename = f"{final_filename_with_internal}.{ext_lower}"
                            else:
                                final_filename = final_filename_with_internal
                except: pass
            
            manifest_entry["disk_filename"] = final_filename
            with open(os.path.join(output_dir, final_filename), 'wb') as f_out: f_out.write(output_data)
            print(f"[{i+1:04d}/{len(ridx_entries)}] 提取 -> {final_filename} (Flag: {hex(ext_info['flag'])})")
            manifest_data.append(manifest_entry)

    with open(os.path.join(output_dir, "manifest.json"), 'w', encoding='utf-8') as f:
        json.dump(sorted(manifest_data, key=lambda x: x['id']), f, indent=4, ensure_ascii=False)
    print(f"\n清单json已生成")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Definitive RBB Unpacker.")
    parser.add_argument("rbb_file", help="Path to the .rbb file."); parser.add_argument("-o", "--output", dest="output_dir", help="Output directory.")
    args = parser.parse_args(); output_dir = args.output_dir or os.path.splitext(os.path.basename(args.rbb_file))[0] + "_unpacked"
    unpack_rbb_definitive(args.rbb_file, output_dir)