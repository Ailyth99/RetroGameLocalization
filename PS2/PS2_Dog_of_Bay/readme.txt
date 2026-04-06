PS2 <DOG OF BAY> 镜像拆包工具
PS2 <DOG OF BAY> Disc Image Unpacking Tool

这个游戏没有使用标准的光盘文件系统，而是把整个DATA目录隐藏了起来，因此需要把整个镜像看成一个封包文件，再对其解包。
This game does not use a standard disc file system; instead, the entire DATA directory is hidden. Therefore, the entire disc image must be treated as a single archive file for unpacking.

游戏的ELF文件（SLPS_200.57）储存了相关的自定义目录表，可以根据这个解包。
The game's ELF file (SLPS_200.57) stores the relevant custom directory table, which is used as the basis for extraction.

同时支持插入修改后的文件，但是不能超过原来文件大小。
It also supports re-inserting modified files, provided they do not exceed the original file size.

首先需要把镜像格式用bin+cue转换成ISO格式（扇区大小2048）。
First, you need to convert the image from BIN+CUE format to ISO format (sector size 2048 bytes).

然后使用 dog_tool：
Then use dog_tool:
Usage (用法):
Export (导出): dog_tool -export <game.elf> <game.iso>
Import (导入): dog_tool -import <game.elf> <game.iso> <new_file_path>