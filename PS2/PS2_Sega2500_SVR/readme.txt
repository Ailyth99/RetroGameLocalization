This tool allows you to convert SVR texture files from certain SEGA AGES 2500 games on the PS2 into PNG format. It includes a GUI tool that can scan files for SVR textures, export them to PNG, or inject new images.

CLI Tool Usage
SVR (GBIX) Advanced Ripper
Usage: svr_ripper [flags] <file_or_folder>
-extract int
Extract GBIX at the given offset to PNG (the input file must be specified) (default -1)
-inject int
Inject a PNG into the GBIX at the given offset (default -1)
-outdir string
Output directory for extraction mode (default is the same as the input)
-png string
Input PNG file for injection
-scan
Scan the file for GBIX and output a JSON array


Games Known to Use the SVR Format:
Sega Ages 2500 Series Vol. 5 - Golden Axe
Sega Ages 2500 Series Vol. 27 - Panzer Dragoon

