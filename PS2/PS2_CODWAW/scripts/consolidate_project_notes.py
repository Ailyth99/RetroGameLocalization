"""One-time consolidation of research notes, preserving old paths as navigation links."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
target=ROOT/'破解笔记.md'
if target.exists():raise SystemExit('Combined notes already exist; append new findings there.')
paths=sorted((ROOT/'docs').rglob('*.md'))+[ROOT/'PCSX2-MCP使用指南.md']
report=json.loads((ROOT/'SOUND/subtitles/L1_Gcan_am/build/build_report.json').read_text(encoding='utf-8'))
before=sum(f['texture_bytes_before'] for f in report['fonts'])
after=sum(f['texture_bytes_after'] for f in report['fonts'])
head=f'''# PS2 COD5 破解笔记（唯一维护入口）

从 2026-10-05 起，破解研究、修改过程、调试结论及交付状态只追加到本文件，不再按问题新建笔记。历史文件内容已完整收入文末，原路径仅保留导航，旧结论以本页最新记录为准。结构化构建报告、原始内存及日志是证据数据，仍放在各自工作目录，不作为第二套笔记维护。

## 当前工作入口

- 菜单、HUD、目标及头顶人名：`TEXT/菜单与提示译文.json` 的 zh。
- 第一关字幕：`SOUND/subtitles/L1_Gcan_am/whisper_results.json` 的 translation。
- 一体构建：`scripts/build_chinese_test.ps1`，自动导入第一关字幕、菜单及字体，覆盖根目录 `COD5_TEST.iso`。
- 第一关 AM 构建：`scripts/build_l1_subtitles.py`；字体：`scripts/unified_fonts.py` 与 `scripts/compact_font_pages.py`。
- 全部字形每次从 FONT/source 当前文件重绘，保留实际字体 SHA256；U+007F 源字体缺字，明确报告并保留其特殊像素。
- AM 对应 508 条声音，502 条译文，6 条空白；所有 VAG 原样保留。
- 字幕颜色 #CCFFFF，比例112.5%；头顶姓名仍用大字字体。ELF 样式补丁不回退。

## 2026-10-05：“别说了，他来了！”处卡死

### 用户现象与实证

用户测试首版全量字幕 ISO：能进入游戏并显示几句中文字幕，到上述台词画面卡死、音效继续。

日志在 96.1544 秒起显示 PC=0x002320B8 连续向 0x0、0x4…0x1C 写入，以及 PC=0x00232128 向0x1C写入。Ghidra 查到调用链：

`FUN_00233538 -> FUN_002321D0 -> FUN_004434C8 -> FUN_00422EB8 / FUN_00422F48`

这是场景绘制队列节点分配。扩展内存池失败后，调用者未判空，继续执行节点初始化 `FUN_002320B8` 和挂接 `FUN_00232128`。池参数为32×128字节，即4096字节节点区，另有池管理对象。

实际调用了新版 PCSX2-MCP Python 工具：找到 pcsx2-qt.exe PID16628，但 connect 返回 WinError10061；GDB端口没有监听，用户配置 EnablePINE=false。不能将此描述成MCP寄存器/断点调试成功。

为保留用户卡死现场，没有重启模拟器。使用只读 OpenProcess/ReadProcessMemory，并以游戏指令签名搜索EE映射，读取32MiB EE RAM。工具 `scripts/capture_pcsx2_ee.py`，现场在 `SOUND/research/l1_freeze/ee_ram.bin`；本次宿主基址0x21F00000000，仅对本进程有效，不硬编码。

动态内存发现：

- 0x00480E80 字幕缓冲确为“别说了，他来了！”，0x00480E78 当前对白对象已清零。
- 0x004E4518绘制队列结构的池指针为空，节点区参数0x20、0x80。
- 主堆顶指针（0x004E8778）为0x01FF7FC8，块大小标记0x39，即可用尾块长度0x38=56字节，堆顶已到0x01FF8000。
- 56字节仅为堆顶尾块，不是所有空闲链总量；结合分配失败链和错误日志，证据指向运行内存不足。没有把台词字面内容当成原因。

### 已实施修复

旧FONT基线的大字与Verdana_20仍各保留512×1024底页，其中大量空白；原来只在其后增页，导致常驻纹理持续增长。

现在先全量重绘，再把全部既有及新增字形矩形紧凑重排到原生多页纹理。保留字符集合、每字像素、字宽、采样高度、调色板及未知字形字段，仅更新纹理坐标、页信息、纹理资源和RSFL偏移。构建内逐字回读比较像素与字宽，确认一致。不是压缩音频、缩字、删字幕或修改空指针处让程序跳过错误。

Ghidra `FUN_00208568` 确认按页查找失败后会继续后续页，支持页间代码范围重叠；`FUN_002064F8` 使用所属页宽高进行采样，所以新坐标和页尺寸由原生绘制支持。

纹理占用：{before:,} -> {after:,}字节，减少{before-after:,}字节（{(before-after)//1024}KiB）。比此前用户确认正常的头顶人名版本1,015,808字节再低98,304字节。

本次读取的是用户当前 JSON：AM {report['rebuilt_bytes']:,}字节；字形数为大字516、小号896、字幕1094。与上次1095的差异来自当前字幕输入需求，不能恢复旧JSON来强行匹配旧数量。

### 限制与后续方向

此修复直接降低常驻内存，但不是无限扩字方案。后续全关卡字幕仍需字库内存预算；必要时做每关独立字体及生命周期管理，当前尚未实现按需装卸。构建校验通过不等于用户运行验证通过。

固定测试ISO的最终生成结果在本页下方追加；用户负责运行效果确认。本轮没有重启用户的卡死现场。

## 历史笔记全文

以下保留原始历史内容及原路径；含过时构建器、ISO名称和中间假设，只作研究沿革。执行时以本页“当前工作入口”与最新记录为准。

'''
parts=[head]
for path in paths:
    rel=path.relative_to(ROOT).as_posix()
    parts.append(f'\n\n---\n\n## 历史来源：{rel}\n\n'+path.read_text(encoding='utf-8-sig'))
target.write_text(''.join(parts),encoding='utf-8')
# Verify the full historical text before converting old paths to links.
combined=target.read_text(encoding='utf-8')
for path in paths:
    assert path.read_text(encoding='utf-8-sig') in combined
for path in paths:
    depth=len(path.relative_to(ROOT).parts)-1
    link='../'*depth+'破解笔记.md'
    path.write_text(f'# 已合并到总笔记\n\n本文原始内容已完整合并到 [破解笔记]({link})。后续只维护总笔记，本路径保留用于兼容旧链接。\n',encoding='utf-8')
print(f'Consolidated {len(paths)} documents into {target.name}')
