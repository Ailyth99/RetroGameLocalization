@echo off
chcp 65001 > nul
echo 删除先前的镜像，并复制一份原始镜像
del  TESTXISO.iso
copy /Y "ORIGINAL.iso" "TESTXISO.iso"

echo 处理镜像，注入新数据，并添加dummy文件到末尾，生成新的INDEX.BIN索引表
XBOX_ISO_TOOL.exe -rename \data\INTERFACE.GRP.bin -newname INTERFACE.GRP.000 -iso TESTXISO.iso
XBOX_ISO_TOOL.exe -append WORK\INTERFACE.GRP.bin -dir  \data -iso TESTXISO.iso
XBOX_ISO_TOOL.exe -tbl TESTXISO.iso
xbox_index_patcher.exe -p -b work\index.bin  -i TESTXISO.csv -o INDEX_PATCHED.BIN 

echo 提取原始INTERFACE.GRP.bin
XBOX_ISO_TOOL -iso ORIGINAL.iso -get DATA\INTERFACE.GRP.bin
echo 解包原始INTERFACE.GRP.bin
xbox_grp_bin.exe -u INTERFACE.GRP.bin
ren "INTERFACE.GRP.bin_extracted" "INTERFACE_BUILD"

echo ====生成字库======
echo [1]生成字库贴图和坐标表
van_font_gen.exe -t work/font.ttf -s 25 -f 25 -c work\XBCHARS.TXT -w 1024 -h 1024 -o xboxfont 
echo [2] 移动FNT文件...
move /y xboxfont.FNT INTERFACE_BUILD\GOELANFONT.FNT
echo [3] 转换PNG2XTEX
xtex_tool.exe -f DXT3 -p xboxfont.png -o INTERFACE_BUILD\GOELANFONT.DDS
 
echo 重新打包 GRP.bin
xbox_grp_bin.exe -r INTERFACE_BUILD -t work/INTERFACE.GRPoriginal.bin -o INTERFACE_BUILD.GRP.bin

echo 注入文件
XBOX_ISO_TOOL.exe -inject \data\INTERFACE.GRP.bin   -file INTERFACE_BUILD.GRP.bin -iso TESTXISO.iso
XBOX_ISO_TOOL.exe -inject \data\englishStrings.bin  -file work\englishStrings.bin -iso TESTXISO.iso
XBOX_ISO_TOOL.exe -inject \data\index.bin  -file INDEX_PATCHED.BIN -iso TESTXISO.iso

echo 完成，请检查是否成功
