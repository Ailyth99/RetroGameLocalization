# Cold Fear PS2 (Sequential Extraction Fix)
# For my Darling

idstring "DWBF"
get VERSION long
get FILES long
get PADDING long

# 计算数据开始的基准偏移量: Header(16) + 文件数(FILES) * 索引条目大小(12)
math BASE_OFF = FILES
math BASE_OFF * 12
math BASE_OFF + 16

# 初始数据指针设为 BASE_OFF
math DATA_PTR = BASE_OFF

for i = 0 < FILES
    get TYPE_HASH long
    get SIZE long
    get DUMMY long # 跳过索引中那个不可靠的 OFFSET 字段

    # 生成一个唯一的文件名，格式如: 00000001_0x44544800.dat
    set FNAME i
    string FNAME p "%04d_0x%08x.dat" FNAME TYPE_HASH

    # 打印到控制台，方便调试
    print "Extracting file at 0x%DATA_PTR|x% (Size: %SIZE%)"

    # 执行解包
    log FNAME DATA_PTR SIZE

    # 更新指针: 当前偏移 + 文件大小
    math DATA_PTR + SIZE
    
    # 重要：PS2 扇区对齐 (通常是 0x800)
    # 如果下个文件没有紧接着，请开启下面的对齐计算
    math DATA_PTR + 0x7ff
    math DATA_PTR & 0xfffff800
next i