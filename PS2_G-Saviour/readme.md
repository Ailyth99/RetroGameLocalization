

用于处理G-Saviour游戏的文本和图像资源。<br>
This toolkit is designed for handling text and image resources of PS2's G-Saviour game.

## 文本处理 / Text Processing

游戏包含两种文本：<br>
The game contains two types of text:
- ELF文件中的系统文本 (SLPS_250.09)：包含记忆卡操作提示和任务评价<br>
  System text in ELF file (SLPS_250.09): Including memory card operations and mission evaluations
- EB文件中的剧情文本：主要游戏剧情对话<br>
  Story text in EB files: Main game dialogue

所有文本使用EUC-JP编码。<br>
All texts are encoded in EUC-JP.

### 编译文本导入工具 / Compilation

```bash
go build elf_importer.go -o elf_importer.exe
go build eb_importer.go -o eb_importer.exe
```
或直接运行/or Run:
```bash
go run elf_importer.go -参数/parameters
go run eb_importer.go -参数/parameters
```
示例用法/Example:
```bash
elf_importer.exe -tbl tbl.csv -elf SLPS_250.09 -tr script.txt
eb_importer.exe -tbl tbl.csv -eb EV431.EB -tr script.txt -align center

### 参数说明 / Parameters
| 参数/Param | 说明/Description | 示例/Example |
|------------|-----------------|--------------|
| -tbl       | 字符编码表文件 / Character encoding table | tbl.csv |
| -elf       | ELF目标文件 / Target ELF file | SLPS_250.09 |
| -eb        | EB目标文件 / Target EB file | *.EB |
| -tr        | 译文文件 / Translation file | *.txt |
| -align     | 文本对齐方式(仅EB工具) / Text alignment(EB tool only) | left/center |

### EB文本分类 / EB Text Classification
- BR01~BR07: 任务简报 / Mission briefings
- MSSEL**: MS选择时的对话 / MS selection dialogue
- EV***: 每关卡对话，EV1开头的就是第一关，EV5开头的就是第五关，以此类推 / Dialogue for each level, EV1 is the first level, EV5 is the fifth level, and so on
- 标注为 center 的是居中对齐的，其他都是居左 / The text marked as center is centered, others are left

## 图像处理 / Image Processing
游戏里面的菜单选项都是图片，格式为gs，为一种位图格式。 /game's menu options are images, the format is gs, which is a bitmap format.

### 文件格式 / gs' Formats
- *.gs: 单个图片文件 / Single gs image file
- *.gsp: gs容器，包含多个gs文件 / gs package container, containing multiple gs 

### gs工具说明 / Tools Desc
相关工具为python编写，需要确保有numpy和wxpython<br>
the tools need to ensure that numpy and wxpython are installed.

1. GSP处理 / GSP Processing :
   - gsp_unpacker.py: 解包GSP文件并生成索引JSON<br>
      Unpack GSP and generate index JSON
   - gsp_importer.py: 导入GS文件到GSP（需要索引JSON）<br>
      Import GS files to GSP (requires index JSON)
导入gsp的gs图片需要和原始gs图片的bpp类型一致，否则会报错。<br>
the gs file of gsp must be the same bpp type as the original


2. 图像转换 / Image Conversion :
   - bmp2gs.py: BMP转换为GS格式 / Convert BMP to GS format
   把gs转换成bmp可以请使用这个项目：https://github.com/ScornMandark/G-SaviourExtract

### 图像格式说明 / Image Format 
- 支持的BMP格式 / Supported BMP BPP:
  - 4bpp (16色索引模式 / 16 colors indexed)
  - 8bpp (256色索引模式 / 256 colors indexed)
- 透明色设置 / Transparency:
  - 纯黑色 (#000000) 将显示为透明（即把alpha通道设置为0） / pure pure black (#000000) will be displayed as transparent
- 格式判断，拿16进制编辑器可以查看0x2位置的值 / Format Detection:
  - 0x14 : 4bpp
  - 0x13 : 8bpp


### 已知问题 / Known Issues
目前不支持真彩色(24/32位)GS文件的处理。部分游戏中的GS文件使用真彩色而非索引色模式。<br>
Currently does not support true color (24/32-bit) GS files processing. Some GS files in the game use true color instead of indexed color mode.