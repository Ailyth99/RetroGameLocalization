#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VAGRipper - Extract VAG audio files from Asura engine packages (.am / .ps2)

Usage:
    python VAGRipper.py <file_or_dir> [output_dir]

    File:      extract VAGs from that single file
    Directory: scan for all .am / .ps2 inside, extract each into its own subfolder
    Default output: project SOUND/extracted

VAG format: 4-bit ADPCM, mono, used in PS2 game audio.
Container:  Asura engine (Rebellion Developments)
"""

import struct
import sys
import os
import glob

# --- Constants ---
VAG_MAGIC = b'VAGp'
HEADER_SIZE = 48       # Asura VAGp header is 48 bytes (not standard 64)
STD_HEADER_SIZE = 64   # Standard Sony VAGp header for output
EXPECTED_VERSION = 0x20
EXPECTED_SAMPLE_RATE = 22050

# Standard VAG flag values
VAG_FLAG_LOOP_BODY = 0x00
VAG_FLAG_LOOP_START = 0x04
VAG_FLAG_LOOP_END = 0x01
VAG_FLAG_END = 0x03


def find_vag_entries(data):
    """Scan binary data for all valid VAGp entries."""
    entries = []
    pos = 0
    while True:
        idx = data.find(VAG_MAGIC, pos)
        if idx == -1:
            break
        # Validate: need at least 48 bytes for header
        if idx + HEADER_SIZE > len(data):
            break
        version = struct.unpack('>I', data[idx+4:idx+8])[0]
        data_size = struct.unpack('>I', data[idx+12:idx+16])[0]
        sample_rate = struct.unpack('>I', data[idx+16:idx+20])[0]

        # Validate header fields
        if (version == EXPECTED_VERSION
                and data_size > 0
                and data_size < len(data)
                and sample_rate > 0
                and sample_rate <= 96000):
            entries.append({
                'offset': idx,
                'data_size': data_size,
                'sample_rate': sample_rate,
            })
        pos = idx + 4

    return entries


def build_std_vag_header(data_size, sample_rate):
    """Build a standard 64-byte Sony VAGp header."""
    header = bytearray(STD_HEADER_SIZE)
    header[0:4] = VAG_MAGIC                           # magic
    struct.pack_into('>I', header, 4, 0x00000020)      # version 32
    struct.pack_into('>I', header, 8, 0)               # reserved
    struct.pack_into('>I', header, 12, data_size)      # data size
    struct.pack_into('>I', header, 16, sample_rate)    # sample rate
    struct.pack_into('>I', header, 20, 0)              # channels (mono=0)
    # bytes 24-63: zero padding (name, etc.)
    return bytes(header)


def extract_vag(data, entry):
    """Extract a single VAG file with standard header."""
    offset = entry['offset']
    data_size = entry['data_size']
    sample_rate = entry['sample_rate']

    # ADPCM data starts right after the 48-byte header
    adpcm_start = offset + HEADER_SIZE
    adpcm_end = adpcm_start + data_size
    adpcm_data = data[adpcm_start:adpcm_end]

    # Verify the last frame has an end flag
    if len(adpcm_data) >= 16:
        last_frame = adpcm_data[-16:]
        flags = last_frame[1]
        if flags not in (VAG_FLAG_END, VAG_FLAG_LOOP_END, 0x07):
            # Not a clean end - might be a false positive or truncated
            pass  # still extract, tools can handle it

    header = build_std_vag_header(data_size, sample_rate)
    return header + adpcm_data


def process_file(input_path, output_dir):
    """Process a single .am or .ps2 file."""
    filename = os.path.basename(input_path)
    # Use full filename (without extension) as stem to avoid collisions
    # e.g., L1_Gcan.am -> L1_Gcan_am, L1_Gcan.ps2 -> L1_Gcan_ps2
    stem = filename.replace('.', '_')

    print(f"\n{'='*60}")
    print(f"Processing: {filename}")
    print(f"{'='*60}")

    with open(input_path, 'rb') as f:
        data = f.read()

    print(f"  File size: {len(data):,} bytes")

    entries = find_vag_entries(data)
    print(f"  VAG entries found: {len(entries)}")

    if not entries:
        print("  No VAG entries found!")
        return 0

    # Print first few entries
    print(f"\n  {'#':>4} {'Offset':>12} {'Size':>10} {'Rate':>6} {'Duration':>10}")
    print(f"  {'----':>4} {'--------':>12} {'----':>10} {'----':>6} {'--------':>10}")

    total_size = 0
    for i, entry in enumerate(entries):
        duration_s = entry['data_size'] / 28.0 / entry['sample_rate'] if entry['sample_rate'] > 0 else 0
        total_size += entry['data_size'] + STD_HEADER_SIZE
        if i < 10 or i == len(entries) - 1:
            print(f"  {i:4d} 0x{entry['offset']:08X} {entry['data_size']:10,} {entry['sample_rate']:6d} {duration_s:9.2f}s")
        elif i == 10:
            print(f"  {'...':>4}")

    print(f"\n  Total VAG data: {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")

    # Extract files into a subfolder named after the container
    extract_dir = os.path.join(output_dir, stem)
    os.makedirs(extract_dir, exist_ok=True)
    extracted = 0
    for i, entry in enumerate(entries):
        vag_data = extract_vag(data, entry)
        out_name = f"{stem}_{i:04d}.vag"
        out_path = os.path.join(extract_dir, out_name)
        with open(out_path, 'wb') as f:
            f.write(vag_data)
        extracted += 1

    print(f"  Extracted: {extracted} files -> {extract_dir}/")
    return extracted


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arg = sys.argv[1]
    script_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "SOUND"))
    default_output = os.path.abspath(os.path.join(script_dir, 'extracted'))

    if os.path.isdir(arg):
        # Directory mode: scan for all .am/.ps2
        output_dir = sys.argv[2] if len(sys.argv) > 2 else default_output
        files = sorted(glob.glob(os.path.join(arg, '*.am')) +
                       glob.glob(os.path.join(arg, '*.ps2')))
        if not files:
            print(f"No .am or .ps2 files found in {arg}")
            sys.exit(1)
        print(f"Found {len(files)} container file(s) in {arg}")
        total = 0
        for f in files:
            total += process_file(f, output_dir)
        print(f"\n{'='*60}")
        print(f"TOTAL: {total} VAG files extracted")
    elif os.path.isfile(arg):
        # Single file mode
        output_dir = sys.argv[2] if len(sys.argv) > 2 else default_output
        process_file(arg, output_dir)
    else:
        print(f"Error: Not a file or directory: {arg}")
        sys.exit(1)


if __name__ == '__main__':
    main()
