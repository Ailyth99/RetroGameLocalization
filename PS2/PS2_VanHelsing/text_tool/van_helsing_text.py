import struct
import os
import re
import argparse

def format_char(val):
    if val >> 8 == 0xFF:
        # Special character: High byte is FF.
        return f"[{val & 0xFF:02X}{val >> 8:02X}]"
    elif val == 0x0A:
        return "\n"
    elif val == 0x0D:
        return "\r"
    elif 0x20 <= val <= 0x7E:
        return chr(val)
    else:
        # Generic hex for any other non-printable character
        # Using [LowHigh] format
        return f"[{val & 0xFF:02X}{val >> 8:02X}]"

def parse_text(text):
    words = []
    i = 0
    while i < len(text):
        if text[i] == '[':
            match = re.match(r'\[([0-9A-Fa-f]{4})\]', text[i:])
            if match:
                hex_str = match.group(1)
                # [LowHigh] -> val = High << 8 | Low
                low = int(hex_str[0:2], 16)
                high = int(hex_str[2:4], 16)
                words.append((high << 8) | low)
                i += 6
                continue
        
        char = text[i]
        if char == '\n':
            words.append(0x0A)
        elif char == '\r':
            words.append(0x0D)
        else:
            words.append(ord(char))
        i += 1
    return words

def export_bin(bin_path, txt_path):
    if not os.path.exists(bin_path):
        print(f"Error: {bin_path} not found.")
        return
        
    with open(bin_path, 'rb') as f:
        data = f.read()
    
    count = struct.unpack_from('<I', data, 0)[0]
    entries = []
    for i in range(count):
        entry_offset = 4 + i * 8
        id_val = struct.unpack_from('<I', data, entry_offset)[0]
        str_offset = struct.unpack_from('<I', data, entry_offset + 4)[0]
        
        # Read string
        chars = []
        pos = str_offset
        while pos + 1 < len(data):
            val = struct.unpack_from('<H', data, pos)[0]
            if val == 0:
                break
            chars.append(val)
            pos += 2
        
        text = "".join(format_char(c) for c in chars)
        entries.append((id_val, text))
    
    with open(txt_path, 'w', encoding='utf-8') as f:
        for id_val, text in entries:
            f.write(f"[{id_val:04d}]\n")
            f.write(f"EN:{text}\n")
            f.write(f"CN:\n\n")
    print(f"Exported {count} entries to {txt_path}")

def import_txt(txt_path, out_bin_path):
    if not os.path.exists(txt_path):
        print(f"Error: {txt_path} not found.")
        return

    with open(txt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
 
    pattern = re.compile(r'\[(\d+)\]\r?\nEN:(.*?)\r?\nCN:(.*?)(?=\r?\n\[\d+\]\r?\nEN:|$)', re.DOTALL)
    matches = pattern.findall(content)
    
    entries = []
    for id_str, en_text, cn_text in matches:
        id_val = int(id_str)
        # Do not strip to preserve original newlines/spaces at the end
        
        final_text = cn_text if cn_text.strip() else en_text
        words = parse_text(final_text)
        entries.append((id_val, words))
    
    # Build binary
    count = len(entries)
    header_size = 4 + count * 8
    
    string_data = bytearray()
    offsets = []
    
    for id_val, words in entries:
        offsets.append(header_size + len(string_data))
        for word in words:
            string_data.extend(struct.pack('<H', word))
        string_data.extend(b'\x00\x00') # Terminator
        
    bin_data = bytearray()
    bin_data.extend(struct.pack('<I', count))
    for i in range(count):
        id_val, _ = entries[i]
        offset = offsets[i]
        bin_data.extend(struct.pack('<II', id_val, offset))
    
    bin_data.extend(string_data)
    
    # Align to 4 bytes
    while len(bin_data) % 4 != 0:
        bin_data.append(0)
    
    with open(out_bin_path, 'wb') as f:
        f.write(bin_data)
    print(f"Imported {count} entries to {out_bin_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Van Helsing (PS2/XBOX) Text Tool')
    parser.add_argument('-e', nargs=2, metavar=('bin', 'txt'), help='Export bin to txt')
    parser.add_argument('-i', nargs=2, metavar=('txt', 'bin'), help='Import txt to bin')
    
    args = parser.parse_args()
    
    if args.e:
        export_bin(args.e[0], args.e[1])
    elif args.i:
        import_txt(args.i[0], args.i[1])
    else:
        parser.print_help()
