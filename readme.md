## My Retro Game Localization Tools 

This repository contains a collection of tools that I used as part of a retro game localization project.

一些作为本人旧游戏本地化项目的一部分而开发的工具。

---

| - | NAME | DESC | FEATURE |
|------|--------|----------|----------|
| PS1 | King's Field<br>国王密令 | T文件、TIM/RTIM贴图、对话文本处理 | 文件拆分、贴图转换、文本生成，也适用于一些FS其他的PS1游戏 |
| PS2 | King's Field 4 <br>国王密令4 | 字体贴图处理 | 转换、重建KF4的双CLUT字体贴图.tmr格式 |
| PS2 | Chou Aniki<br>超兄貴 | CMP/PAC档案处理 | 解压缩、压缩（自定义LZSS） |
| PS2 | Detective Conan<br>名探偵コナン 大英帝国の遺産 | HED/DAT档案处理，字体 | 解包、重打包（原地注入）。字体文件导出(PNG)，导入 |
| PS2 | Dragon Ball Z: Budokai Tenkaichi 3<br>龙珠Z电光火石3 | 字体贴图处理 | 提取、重建（双CLUT）字体贴图 |
| PS2 | G-Saviour<br>G救世主 | 文本、GS/GSP图像、字体处理 | 文本提取导入（EUC-JP）、图像转换、自定义字体 |
| PS2 | Mobile Suit Gundam: Lost War Chronicles<br>高达战记 | MB档案处理 | 解包、打包。也适用于其他一些PS2高达游戏 |
| PS2 | Hunter X Hunter<br>全职猎人 | RH2贴图、CVT文件处理 | 贴图转换、文件处理、多位深支持，也适用于其他一些KONAMI的PS2游戏 |
| PS2 | Ka (Mr. Mosquito)<br>蚊 | TIM2贴图处理 | 提取、重导入 |
| PS2 | Kagero 2 (Trapt)<br>影牢2 | ARC档案处理 | 解包 |
| PS2 | Metal Slug 3D<br>合金弹头3D | PAK档案、PKLZ压缩、贴图处理 | 档案解包打包、压缩解压、贴图转换，也适用于KOF3D |
| PS2 | Samurai Western / Shinobido<br>西部侍道 / 忍道 | VOLUME.DAT档案处理 | 解包、打包 |
| PS2 | Red Ninja<br>红忍 | QTX贴图、RBB档案、字体处理 | 贴图转换、档案处理、字体注入，也可以拆包XBOX版本 |
| PS2 | DOG OF BAY<br>港湾之犬 | 拆包，重建镜像 | 处理自定义的镜像文件系统，导出隐藏文件，支持导回 |
| PS2 | Shakugan No Shana <br>灼眼的夏娜 | 贴图处理、解压缩、字库 | 分块压缩贴图转换转回、字库导入导出，校验机制破除 |
| PS2 | Spartan: Total Warrior <br>全面战士 斯巴达 | PAK文件处理 | PAK文件的解包，以及重建 |
| PS2 | TAMSOFT TOOL <br>TAMSOFT 工具 | CMP压缩、TI贴图处理 | 压缩解压、贴图转换、GUI查看器 |
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

