# PS2《使命召唤：战火世界 最终前线》汉化源码

这里是当前发布版使用的程序、构建脚本、译文和声音清单，包含13关字幕、菜单/HUD、动态字库、实机闪烁修复和字幕阴影。需要调整人名或其他译文，可以自行修改并重新构建。

## 修改译文

| 内容 | 文件与字段 |
| --- | --- |
| 菜单、任务目标、HUD、武器及头顶人名 | `TEXT/菜单与提示译文.json`，修改 `zh` |
| 四军通用对白 | `SOUND/voice_work/common/{US,JA,GE,UK}/whisper_results.json`，修改 `translation` |
| 各关剧情对白 | `SOUND/voice_work/story/L*_am/whisper_results.json`，修改 `translation` |
| 各关完整字幕及单关修改 | `SOUND/subtitles/L*_am/whisper_results.json`，修改 `translation` |

双击 `SOUND/start_review_checker.bat` 可通过网页搜索、编辑并保存译文。人名可能同时出现在头顶姓名和对白中，可搜索中文名或英文原文，按需要分别修改。声音ID、JSON键、原文和清单引用用于匹配资源，请保留。

完整构建默认同步所有已保存的通用/剧情译文，并保留完整关卡JSON中的独立修改；网页单独的同步按钮只同步已校对内容。

## 环境与构建

当前程序使用 Windows x64、Python 3.12 x64、PowerShell。

```powershell
python -m pip install -r requirements-gui.txt
```

此目录按原项目路径直接摆放。可以将文件合并到已有项目工作目录使用；已有译文需要保留时，先自行决定哪些JSON要采用。

首次准备新的工作目录，需要自行提供：

1. 美加版原始镜像 `Call of Duty - World at War - Final Fronts (USA, Canada) (En,Fr).iso`，放在本目录或 `SOURCE` 中；将镜像完整解包到 `ISO_UNPACK`，使 `ISO_UNPACK/slus_217.46` 直接存在。完整构建会严格识别原版ELF并初始化字幕基础。
2. 字体放入 `FONT/source`。默认文件为 `USMCCyuanjiantecu.otf` 和 `IBMPlexSansSC-Regular.ttf`；也可通过GUI导入其他TTF/OTF。三套字体、备用字体、仿粗体、字幕颜色/大小/阴影及实机修复统一配置在 `FONT/render_settings.json`。
3. 打包工具 `tools/mkps2iso.exe`，须支持 `-q -y -o 输出ISO 输入目录`。
4. 支持 R5900 的MIPS GCC及同目录配套binutils。下载：https://pspdev.github.io/。如源码路径为 `C:/pspdev/bin/psp-gcc.exe`，配套 `psp-objcopy.exe`、`psp-nm.exe`、`psp-objdump.exe`；宿主检查编译器为 `C:/TDM-GCC-64/bin/gcc.exe`。路径不同可修改 `scripts/build_dynamic_fonts.py` 顶部工具路径与 `scripts/test_dynamic_font_runtime.py` 中宿主GCC路径。普通仅支持PSP/Allegrex的编译器不满足本项目R5900参数。

双击 **`构建工具.bat` → 保存并构建 ISO**，或直接双击 **`一键构建ISO.bat`**。完整入口是 `scripts/build_chinese_test.ps1`，成功后输出固定为 **`COD5_TEST.iso`**，再次构建会覆盖同名测试镜像。

流程：同步译文 → 重建字幕和系统文本 → 全量重绘字体 → 生成动态字形银行及按关预载 → 编译并检查补丁 → 打包 → 回读校验。字幕阴影与实机闪烁修复默认开启，可在GUI修改。

已有工作目录应保留 `SOURCE/backups/dynamic_font_cache`、`menu_hints_zh`、`start_menu_zh_20261004` 等构建依赖及安装报告。ELF、FONT、`ZHGLYPH.BIN`、`ZHPR00.BIN`～`ZHPR13.BIN`必须由完整入口一起生成；独立旧实验脚本不是当前完整构建入口。

日志：`TEMP/builds/one_click_build/latest.log`；GUI日志：同目录 `gui.log`。

## 程序位置

- `scripts/build_*.py`、`*.ps1`：构建入口和底层重建器。
- `scripts/build_gui.py`、`build_settings.py`：GUI与共享配置。
- `scripts/unified_fonts.py`、`build_resident_glyphs.py`：全量字体重绘和按关预载。
- `scripts/dynamic_font/`：MIPS汇编与C字形缓存运行时。
- `scripts/sound/`：网页校对、译文同步和音频处理。
- `scripts/test_*.py`、`verify_dynamic_iso.py`：构建检查与ISO回读。

这里只包含程序和小型数据文件。游戏ISO、解包资源、录音、字体、编译器和第三方可执行程序自行准备。没有MP3也可通过网页修改文字；听音播放需要按声音清单补齐对应音频。`requirements-audio.txt`用于可选音频分析，转码工具路径见相应脚本。
