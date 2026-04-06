PS2 Detective Conan Daiei Teikoku no Isan(名探偵コナン 大英帝国の遺産) HED/DAT Tool
A simple tool to unpack and repack .hed and .dat archives.
Usage:
Unpack: hedtool unpack <file.hed> <file.dat> <output_dir>
Repack: hedtool repack <original.dat> <input_dir>
Note: Repacking uses in-place injection. Modified files cannot exceed the original file size. Smaller files are automatically padded.


FONT TOOL
Usage:
  [kanji.dat,Tile Mode 20x20]
    Extract: conan_font -tile <kanji.dat>
    Repack : conan_font -tile -r <l1.png> <l2.png> <out.dat>
  [driknj1.dat & driknj2.dat,Texture Mode 640x768]
    Extract: conan_font -tex <driknj.dat>
    Repack : conan_font -tex -r <l1.png> <l2.png> <out.dat>