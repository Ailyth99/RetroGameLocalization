Commands:

  Extract ISO to folder:
    XBOX_ISO_TOOL -e game.iso
    XBOX_ISO_TOOL -e game.iso -o output_dir

  Repack folder to ISO:
    XBOX_ISO_TOOL -r game_dir
    XBOX_ISO_TOOL -r game_dir -o output.iso

  Export LBA table as CSV:
    XBOX_ISO_TOOL -tbl game.iso
    XBOX_ISO_TOOL -tbl game.iso -o table.csv

  Extract single file from ISO:
    XBOX_ISO_TOOL -iso game.iso -get DATA\INDEX.BIN
    XBOX_ISO_TOOL -iso game.iso -get DATA\INDEX.BIN -o output.bin

  Inject (replace) file in-place (new file <= original size):
    XBOX_ISO_TOOL -iso game.iso -inject \DATA\INDEX.BIN -file new_index.bin

  Rename file in ISO directory table:
    XBOX_ISO_TOOL -iso game.iso -rename \DATA\FONT.BIN -newname 000

  Append file to ISO (adds at end, creates directory entry):
    XBOX_ISO_TOOL -iso game.iso -append new_font.bin -dir DATA -name FONT.BIN
    XBOX_ISO_TOOL -iso game.iso -append new_font.bin -dir /           (root dir)
    XBOX_ISO_TOOL -iso game.iso -append new_font.bin                   (root dir)