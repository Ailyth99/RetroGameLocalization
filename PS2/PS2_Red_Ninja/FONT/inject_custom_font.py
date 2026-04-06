import os
import shutil

#这个工具是把修改好的font qtx注入会00003.RBB里面
TARGET_RBB = "00003.rbb"
FILE_TO_INJECT = "custom_font.qtx"#默认叫这个，可以改别的

INJECTION_START_OFFSET = 0x5bc0
INJECTION_END_OFFSET = 0x45edf

EXPECTED_SIZE = INJECTION_END_OFFSET - INJECTION_START_OFFSET + 1

def inject_specific_file():


    if not os.path.exists(TARGET_RBB):
        print(f"错误: 目标文件 '{TARGET_RBB}' 不在当前目录。")
        return

    if not os.path.exists(FILE_TO_INJECT):
        print(f"错误: 待注入文件 '{FILE_TO_INJECT}' 不在当前目录。")
        return

    print(f"目标RBB: '{TARGET_RBB}'")
    print(f"待注入文件: '{FILE_TO_INJECT}'")
    print(f"注入范围: {hex(INJECTION_START_OFFSET)} -> {hex(INJECTION_END_OFFSET)}")
    print(f"要求的精确大小: {EXPECTED_SIZE} 字节")

    try:
        actual_size = os.path.getsize(FILE_TO_INJECT)
    except Exception as e:
        print(f"错误: 无法获取 '{FILE_TO_INJECT}' 的文件大小: {e}")
        return

    print(f"'{FILE_TO_INJECT}' 的实际大小: {actual_size} 字节")

    if actual_size != EXPECTED_SIZE:
        print("\n!!! 致命错误: 文件大小不匹配 !!!")
        print(f"'{FILE_TO_INJECT}' 的大小是 {actual_size} 字节，但注入范围要求的大小是 {EXPECTED_SIZE} 字节。")
        return
    
    print("  -> 大小验证通过，准备注入。")

    backup_path = TARGET_RBB + ".bak"
    try:
        shutil.copy2(TARGET_RBB, backup_path)
        print(f"  -> 已创建备份文件: '{backup_path}'")
    except Exception as e:
        print(f"错误: 创建备份失败: {e}")
        return

    try:
        with open(FILE_TO_INJECT, 'rb') as f_inject:
            data_to_inject = f_inject.read()
        
        with open(TARGET_RBB, 'r+b') as f_rbb:
            f_rbb.seek(INJECTION_START_OFFSET)
            f_rbb.write(data_to_inject)

        print("\n注入成功！")
        print(f"'{FILE_TO_INJECT}' 的内容已成功写入 '{TARGET_RBB}' 的指定范围。")

    except Exception as e:
        print(f"\n注入过程中发生错误: {e}")
        print("正在从备份恢复原始文件...")
        os.replace(backup_path, TARGET_RBB)
        print("原始文件已恢复。")

if __name__ == '__main__':
    inject_specific_file()