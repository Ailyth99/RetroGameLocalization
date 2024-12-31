import csv
from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass
class TextBlock:
    number: str
    start_offset: int
    end_offset: int
    jp_text: str
    cn_text: str

class TranslationImporter:
    def __init__(self, encoding_file: str):
        self.encoding_map: Dict[str, bytes] = {}
        self.load_encoding_table(encoding_file)
        self.success_count = 0
        self.failed_blocks: List[Tuple[str, str]] = []

    def load_encoding_table(self, file_path: str):
        print("💫 正在加载编码表...")
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    char, code = row[0], row[1]
                    self.encoding_map[char] = bytes.fromhex(code)
        print(f"✨ 成功加载 {len(self.encoding_map)} 个字符编码")

    def read_translation_file(self, trans_file: str) -> List[TextBlock]:
        blocks = []
        current_block = None
        
        print("📖 正在读取译文文件...")
        with open(trans_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('['):
                    if current_block:
                        blocks.append(current_block)
                    
                    # 解析块信息
                    num = line[1:5]
                    offsets = line[7:-1].split(',')
                    start = int(offsets[0], 16)
                    end = int(offsets[1], 16)
                    current_block = TextBlock(num, start, end, "", "")
                elif line.startswith('JP：'):
                    if current_block:
                        current_block.jp_text = line[3:]
                elif line.startswith('CN：'):
                    if current_block:
                        current_block.cn_text = line[3:]
            
            if current_block:
                blocks.append(current_block)
                
        print(f"📝 共读取 {len(blocks)} 个文本块")
        return blocks

    def encode_text(self, text: str) -> Tuple[bool, bytes, str]:
        result = bytearray()
        for char in text:
            if char not in self.encoding_map:
                return False, bytes(), f"未找到字符 '{char}' 的编码"
            result.extend(self.encoding_map[char])
        return True, bytes(result), ""

    def pad_translation(self, orig_bytes: bytes, trans_bytes: bytes) -> Tuple[bool, bytes]:
        if len(trans_bytes) > len(orig_bytes):
            return False, bytes()
        
        # 直接在末尾填充0即可
        padding_count = len(orig_bytes) - len(trans_bytes)
        result = bytearray(trans_bytes)
        result.extend([0x00] * padding_count)
        
        return True, bytes(result)

    def import_translations(self, trans_file: str, target_file: str):
        blocks = self.read_translation_file(trans_file)
        
        print("\n🚀 开始导入译文...")
        with open(target_file, 'rb+') as f:
            for block in blocks:
                if not block.cn_text:  # 跳过未翻译的块
                    continue
                    
                # 读取原文
                f.seek(block.start_offset)
                original = f.read(block.end_offset - block.start_offset)
                
                # 编码译文
                success, encoded_text, error = self.encode_text(block.cn_text)
                if not success:
                    self.failed_blocks.append((block.number, error))
                    print(f"\n⚠️ 块 {block.number} 导入失败: {error}")
                    continue
                
                # 填充处理
                success, padded_text = self.pad_translation(original, encoded_text)
                if not success:
                    self.failed_blocks.append((block.number, "译文长度超过原文"))
                    print(f"\n⚠️ 块 {block.number} 导入失败: 译文过长")
                    continue
                
                # 写入译文
                f.seek(block.start_offset)
                f.write(padded_text)
                self.success_count += 1
                print(f"\r✨ 已成功导入 {self.success_count} 个文本块...", end='')

        print("\n\n📊 导入统计:")
        print(f"✅ 成功导入: {self.success_count} 个文本块")
        print(f"❌ 导入失败: {len(self.failed_blocks)} 个文本块")
        
        if self.failed_blocks:
            print("\n⚠️ 失败详情:")
            for num, reason in self.failed_blocks:
                print(f"  块 {num}: {reason}")

def main():
    print("🌟 文本导入工具启动")
    ENCODE_FILE =   r'TEMP\tbl.csv'    
    TRANSLATION_FILE = r'SCRIPT\ELF_output.txt'
    TARGET_FILE = r'DVD_REBUILD\SLPS_250.09'

    importer = TranslationImporter(ENCODE_FILE)
    importer.import_translations(TRANSLATION_FILE, TARGET_FILE)

if __name__ == "__main__":
    main()