也适用于XBOX版的文件，但没有严格测试。

\## 1. Convert QTX to PNG  / 转换QTX到PNG



\#### For regular textures/普通贴图:



```bash

python qtx2png.py texture\\\_name.qtx

```

\#### For the FONT file/字库贴图(00003.RBB):



```bash

python qtx2png\\\_font.py font.qtx

```



\## 2. Convert PNG to QTX/转换PNG到QTX



\*\*Note: Your input PNG must be an indexed-color (paletted) image (16 or 256 colors)./PNG必须为16色或256色索引类型



\#### For regular textures/普通贴图:

```bash

python png2qtx.py edited\\\_texture.png original\\\_texture.qtx

```



\#### For the FONT file/字库贴图:

```bash

python png2qtx\\\_font.py edited\\\_font.png original\\\_font.qtx

```



\## 3. RBB Tool/RBB解包封包



\### 1. To Unpack an RBB file/解包RBB:



```bash

python unrbb.py res.rbb

```



\*(Creates a folder `res\\\_unpacked` with all files and manifest json./会得到一个res\_unpacked文件夹装拆分的文件，以及一个清单json)\*



\### 2. To Repack into a new RBB file/重打包RBB:



```bash

python repack\\\_rbb.py res\\\_unpacked original\\\_res.rbb -o new\\\_res.rbb -l 9

```

-l <level>: (Optional) The zlib compression level to use (from 1 to 9). Default is 6.



-l <压缩等级>：可选项，rbb内部某些文件使用了ZLIB压缩，游戏默认是等级6，可以使用1~9之间的等级，都能读取。



另外inject\_custom\_font.py可以把自定义字库qtx重新插入00003.RBB，范围是0x5bc0~0x45edf



