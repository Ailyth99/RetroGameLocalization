
Zutto Issho OPEN.DAT Tool
A command-line utility to unpack and repack the OPEN.DAT archive for the PS1 game Zutto Issho. It supports the custom RLE decompression and compression required to handle the game's subtitle assets.

Usage
Unpack and decompress: 

zutto_open_tool -u <file.dat>

Extracts and decompresses all frames into the OPEN_EXTRACT directory as indexed .tim files.

Compress and repack:

zutto_open_tool -r <dir_path> [-o <name>]

Compresses .tim files from the specified directory and rebuilds the OPEN.DAT