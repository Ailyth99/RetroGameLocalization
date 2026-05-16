BUILD
可以一键构建XBOX版汉化镜像（XBOX汉化版有问题，用于演示和排错）

xbox_grp_bin
XBOX版的GRP.bin拆包与封包工具，和PS2版有差异，主要用于拆包和封包INTERFACE.GRP.bin，里面包含了字库贴图和配置文件。

xbox_index_patcher
XBOX版LBA表INDEX.BIN的补丁工具，用于从新镜像的CSV修改INDEX.BIN

XTEX
转换字库贴图工具生成的PNG为XBOX支持的XTEX块压缩格式

==============================
构建XBOX汉化版

下载BUILD.zip解压

把XISO格式的《范海辛》（大概2.25GB）放入BUILD文件夹，并命名为ORIGINAL.iso，
双击批处理xbox汉化版构建.bat自动构建汉化版。
work文件夹里面的font.ttf是使用的字体，可以自行替换
得到的TESTXISO.iso为汉化版镜像。

目前问题：
在进入某些场景时读盘卡死，最早在第二关，进入铁栅栏门之前。
原因未知，但初步排除是字库扩容造成的问题，即使不扩容，按照原始字库贴图大小和FNT重建INTERFACE.GRP.bin，然后把新文件放在光盘尾部依然不行，可能是某种LBA的原因。