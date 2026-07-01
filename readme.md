## My Retro Game Localization Tools 

This repository contains a collection of tools that I used as part of a retro game localization project.

一些作为本人旧游戏本地化项目的一部分而开发的工具。

---

EN

| - | NAME | DESC | FEATURE |
|------|--------|----------|----------|
| PS1 | King's Field | T file, TIM/RTIM texture, and dialogue text processing | File splitting, texture conversion, and text generation; also applicable to some other PS1 games by FromSoftware. |
| PS1 | Zutto Issho | OPEN.DAT processing | Extracts OPEN.DAT into multiple TIM files, and supports repacking into a new OPEN.DAT. |
| PS1 | Ace Combat | MISC.DAT processing | Extracts MIS.DAT into multiple LZSS files,Decompress LZSS, and supports repacking into a new MIS.DAT. |
| PS2 | King's Field 4 | Font texture processing | Converts and rebuilds the dual-CLUT font texture .tmr format for KF4. |
| PS2 | Chou Aniki | CMP/PAC archive processing | Decompression and compression (custom LZSS). |
| PS2 | Detective Conan | HED/DAT archive processing, fonts | Unpacking, repacking (in-place injection). Font file export (PNG) and import. |
| PS2 | Dragon Ball Z: Budokai Tenkaichi 3 | Font texture processing | Extraction and rebuilding of (dual-CLUT) font textures. |
| PS2 | G-Saviour | Text, GS/GSP image, and font processing | Text extraction and import (EUC-JP), image conversion, custom fonts. |
| PS2 | Mobile Suit Gundam: Lost War Chronicles | MB archive processing | Unpacking and packing. Also applicable to some other PS2 Gundam games. |
| PS2 | Hunter X Hunter | RH2 texture and CVT file processing | Texture conversion, file processing, and multi-bit-depth support; also applicable to some other PS2 Konami games. |
| PS2 | Ka (Mr. Mosquito) | TIM2 texture processing | Extraction and re-importing. |
| PS2 | Kagero 2 (Trapt) | ARC archive processing | Unpacking. |
| PS2 | SEGA AGES 2500, SVR | SVR textures | Scans for SVR format textures, exports and imports images. Applicable to *Panzer Dragoon* and *Golden Axe*. |
| PS2 | Metal Slug 3D | PAK archive, PKLZ compression, and texture processing | Archive unpacking/packing, compression/decompression, and texture conversion; also applicable to KOF 3D (*KOF: Maximum Impact*). |
| PS2 | Samurai Western / Shinobido | VOLUME.DAT archive processing | Unpacking and packing; also applicable to the PSP game *Patchwork Heroes* (1,000,000 ton no Barabara). |
| PS2 | Red Ninja | QTX texture, RBB archive, and font processing | Texture conversion, archive processing, and font injection; can also unpack the XBOX version. |
| PS2 | DOG OF BAY | Unpacking and image rebuilding | Processes the custom disc image file system, exports hidden files, and supports re-importing. |
| PS2 | Shakugan No Shana | Texture processing, decompression, and fonts | Block-compressed texture conversion and restoration, font import/export, and checksum mechanism bypassing. |
| PS2 | Spartan: Total Warrior | PAK file processing | Unpacking and rebuilding of PAK files. |
| PS2 | Van Helsing | GRP.bin files, TEX textures, etc. | Processing of textures, text, fonts, and LBA tables. |
| PS2 | TAMSOFT TOOL | CMP compression and TI texture processing | Compression/decompression, texture conversion, and GUI viewer. |
| NDS | TENCHU DARK SHADOWS | BD1/FARC unpacking tool | Unpacking/packing of BD1/FARC files. |
| NDS | SD GUNDAM SANGOKUDEN | DAT text files | Export/import of Unicode text within .DAT files. |
| PSP | Airou de Puzzle | PAK/ARC files | Export/import of .PAK/ARC archive files, with automatic decompression/compression. |
| XBOX | Van Helsing | GRP.bin files, TEX textures, etc. | Processing of textures, text, fonts, and LBA tables (some files differ from the PS2 version). |
| XBOX | XBOX XISO TOOL | XISO images | Rebuilding and unpacking of XISO images; supports inserting and importing individual files. |
| DC | Zombie Revenge | Compressed format with PRESSEDPVRFORMAT header | Decompression. |
| General | Multi-CLUT Tile Font Tool | PS2 dual-CLUT tile font processing | 4bpp dual-layer font extraction and repacking. |


CN


| - | NAME | DESC | FEATURE |
|------|--------|----------|----------|
| PS1 | King's Field<br>国王密令 | T文件、TIM/RTIM贴图、对话文本处理 | 文件拆分、贴图转换、文本生成，也适用于一些FS其他的PS1游戏 |
| PS1 | Zutto Issho<br>一直在一起 | OPEN.DAT处理 | 解压OPEN.DAT为多个TIM，并支持重新压缩为新OPEN.DAT |
| PS1 | Ace Combat<br>皇牌空战 | MIS.DAT处理 | 解包MIS.DAT里面的LZSS压缩文件，并进行解压，重新打包为DAT |
| PS2 | King's Field 4 <br>国王密令4 | 字体贴图处理 | 转换、重建KF4的双CLUT字体贴图.tmr格式 |
| PS2 | Chou Aniki<br>超兄貴 | CMP/PAC档案处理 | 解压缩、压缩（自定义LZSS） |
| PS2 | Detective Conan<br>名探偵コナン 大英帝国の遺産 | HED/DAT档案处理，字体 | 解包、重打包（原地注入）。字体文件导出(PNG)，导入 |
| PS2 | Dragon Ball Z: Budokai Tenkaichi 3<br>龙珠Z电光火石3 | 字体贴图处理 | 提取、重建（双CLUT）字体贴图 |
| PS2 | G-Saviour<br>G救世主 | 文本、GS/GSP图像、字体处理 | 文本提取导入（EUC-JP）、图像转换、自定义字体 |
| PS2 | Mobile Suit Gundam: Lost War Chronicles<br>高达战记 | MB档案处理 | 解包、打包。也适用于其他一些PS2高达游戏 |
| PS2 | Hunter X Hunter<br>全职猎人 | RH2贴图、CVT文件处理 | 贴图转换、文件处理、多位深支持，也适用于其他一些KONAMI的PS2游戏 |
| PS2 | Ka (Mr. Mosquito)<br>蚊 | TIM2贴图处理 | 提取、重导入 |
| PS2 | Kagero 2 (Trapt)<br>影牢2 | ARC档案处理 | 解包 |
| PS2 | SEGA AGES 2500,SVR | SVR贴图 | 扫描SVR格式贴图，导出，导入图像。适用于铁甲飞龙，战斧 |
| PS2 | Metal Slug 3D<br>合金弹头3D | PAK档案、PKLZ压缩、贴图处理 | 档案解包打包、压缩解压、贴图转换，也适用于KOF3D |
| PS2 | Samurai Western / Shinobido<br>西部侍道 / 忍道 | VOLUME.DAT档案处理 | 解包、打包，也适用于PSP《百万吨barabra》 |
| PS2 | Red Ninja<br>红忍 | QTX贴图、RBB档案、字体处理 | 贴图转换、档案处理、字体注入，也可以拆包XBOX版本 |
| PS2 | DOG OF BAY<br>港湾之犬 | 拆包，重建镜像 | 处理自定义的镜像文件系统，导出隐藏文件，支持导回 |
| PS2 | Shakugan No Shana <br>灼眼的夏娜 | 贴图处理、解压缩、字库 | 分块压缩贴图转换转回、字库导入导出，校验机制破除 |
| PS2 | Spartan: Total Warrior <br>全面战士 斯巴达 | PAK文件处理 | PAK文件的解包，以及重建 |
| PS2 | Van Helsing<br>范海辛 | GRP.bin文件，TEX贴图等 | 贴图，文本，字库，LBA表处理 |
| PS2 | TAMSOFT TOOL <br>TAMSOFT 工具 | CMP压缩、TI贴图处理 | 压缩解压、贴图转换、GUI查看器 |
| NDS | TENCHU DARK SHADOWS<br>天诛 暗影 | BD1/FARC解包工具 | 解包/打包BD1/FARC文件 |
| NDS | SD GUNDAM SANGOKUDEN<br>SD高达三国传 | dat文本文件 | 导出/导入.DAT里面的unicode文本 |
| PSP | Airou de Puazzle<br>艾露猫方块 | PAK/ARC文件 | 导出/导入.PAK/ARC封包文件，并自动解压/压缩 |
| XBOX | Van Helsing<br>范海辛 | GRP.bin文件，TEX贴图等 | 贴图，文本，字库，LBA表处理（部分文件和PS2版不同） |
| XBOX | XBOX XISO TOOL | XISO镜像 | 重建，解包XISO镜像，比支持插入，导入单个文件 |
| DC | Zombie Revenge<br>僵尸复仇 | PRESSEDPVRFORMAT头的压缩格式 | 解压缩 |
| 通用 | Multi-CLUT Tile Font Tool<br>多CLUT tile字体工具 | PS2双clut tile字体处理 | 4bpp双层字体提取、重打包 |

---

##  Build

**Go tool：**
```bash
go build <tool_name>.go
```



---

##  Doc / 文档

Each game folder contains README files / 每个游戏文件夹包含了README文件


## License / 许可证

See LICENSE file for details / 详见LICENSE文件

