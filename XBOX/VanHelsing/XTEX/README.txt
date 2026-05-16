需要配合微软的texconv.exe使用，注意修改下代码里面写死的texconv的路径。

生成PNG为游戏的XTEX格式命令示意：
xtex_tool.exe -f DXT3 -p xboxfont.png -o GOELANFONT.DDS

此游戏的DDS非真DDS，实际是改造过文件头的格式。


texconv：
https://github.com/microsoft/DirectXTex/releases/tag/may2026