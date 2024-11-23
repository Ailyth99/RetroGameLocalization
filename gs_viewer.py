import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import struct
import io
import os

class GSViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("GS Image Viewer")
        
        # 设置窗口大小并禁止调整
        self.root.geometry("940x480")
        self.root.resizable(False, False)
        
        # 创建主框架
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(fill='both', expand=True)
        
        # 创建左侧图像区域（带滚动条）
        self.image_frame = tk.Frame(self.main_frame, width=640, height=480)
        self.image_frame.pack(side='left', fill='both', expand=True)
        
        # 添加滚动条
        self.h_scrollbar = tk.Scrollbar(self.image_frame, orient='horizontal')
        self.v_scrollbar = tk.Scrollbar(self.image_frame, orient='vertical')
        self.canvas = tk.Canvas(self.image_frame, 
                              width=640, height=480,
                              xscrollcommand=self.h_scrollbar.set,
                              yscrollcommand=self.v_scrollbar.set)
        
        self.h_scrollbar.config(command=self.canvas.xview)
        self.v_scrollbar.config(command=self.canvas.yview)
        
        self.h_scrollbar.pack(side='bottom', fill='x')
        self.v_scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        
        # 创建右侧信息区域，调整宽度
        self.info_frame = tk.Frame(self.main_frame, width=300, height=480)
        self.info_frame.pack(side='right', fill='both', padx=5)  # 添加边距
        self.info_frame.pack_propagate(False)  # 防止frame被内容压缩
        
        # 创建信息表格
        self.create_info_table()
        
        # 创建菜单栏
        menubar = tk.Menu(root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Open", command=self.open_file)
        menubar.add_cascade(label="File", menu=filemenu)
        root.config(menu=menubar)
        
    def create_info_table(self):
        # 创建表格标题，调整列宽
        headers = ['属性', '值']
        widths = [15, 25]  # 调整两列的宽度比例
        
        for i, header in enumerate(headers):
            tk.Label(self.info_frame, 
                    text=header, 
                    relief='ridge', 
                    width=widths[i]).grid(row=0, 
                                        column=i, 
                                        sticky='nsew')
        
        # 预设信息行
        self.info_labels = {}
        info_items = ['文件名', '图像类型', '宽度', '高度', '调色板大小', '文件大小']
        
        for i, item in enumerate(info_items):
            tk.Label(self.info_frame, 
                    text=item, 
                    relief='ridge',
                    width=widths[0]).grid(row=i+1, 
                                        column=0, 
                                        sticky='nsew')
            
            self.info_labels[item] = tk.Label(self.info_frame, 
                                            text='', 
                                            relief='ridge',
                                            width=widths[1],
                                            anchor='w')  # 左对齐
            self.info_labels[item].grid(row=i+1, 
                                      column=1, 
                                      sticky='nsew')
        
        # 配置列权重，使其能够正确扩展
        self.info_frame.grid_columnconfigure(0, weight=1)
        self.info_frame.grid_columnconfigure(1, weight=2)

    def update_info(self, filepath, img_type, width, height, palette_size, file_size):
        self.info_labels['文件名'].config(text=os.path.basename(filepath))
        self.info_labels['图像类型'].config(text=f"{'8bpp 256色' if img_type == 0x13 else '4bpp 16色'} (0x{img_type:02X})")
        self.info_labels['宽度'].config(text=str(width))
        self.info_labels['高度'].config(text=str(height))
        self.info_labels['调色板大小'].config(text=str(palette_size))
        self.info_labels['文件大小'].config(text=f"{file_size} 字节")

    def open_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("GS files", "*.gs")])
        if filepath:
            try:
                self.display_gs_image(filepath)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open file: {str(e)}")
    
    def display_gs_image(self, filepath):
        with open(filepath, 'rb') as f:
            # 读取头部信息
            magic = f.read(2)
            if magic != b'GS':
                raise ValueError("Invalid GS file format")
            
            img_type = struct.unpack('<H', f.read(2))[0]
            width = struct.unpack('<H', f.read(2))[0]
            height = struct.unpack('<H', f.read(2))[0]
            f.seek(0x10)  # 跳到调色板位置
            
            # 读取调色板
            if img_type == 0x13:  # 256色
                palette_size = 256
                palette_data = f.read(palette_size * 4)
            elif img_type == 0x14:  # 16色
                palette_size = 16
                palette_data = f.read(palette_size * 4)
            else:
                raise ValueError("Unsupported image type")
                
            # 转换调色板格式为RGBA
            palette = []
            alpha_values = []  # 新增：存储Alpha值
            for i in range(palette_size):
                r, g, b, a = struct.unpack('BBBB', palette_data[i*4:(i+1)*4])
                palette.extend((r, g, b))
                alpha_values.append(a)  # 新增：记录Alpha值
            
            # 读取图像数据
            f.seek(0x50)
            if img_type == 0x13:  # 8bpp
                raw_data = f.read(width * height)
                pixel_data = bytearray(width * height)
                
                if width <= 64:  # 小图处理模式
                    pixel_data = raw_data
                    
                else:  # 大图处理
                    half_width = width // 2
                    
                    for y in range(height):
                        for x in range(half_width):
                            # 左半边数据
                            src_pos = (y + 1) % height * width + x
                            dst_pos = y * width + (x + half_width)
                            pixel_data[dst_pos] = raw_data[src_pos]
                            
                            # 右半边数据
                            src_pos = y * width + (x + half_width)
                            dst_pos = y * width + x
                            pixel_data[dst_pos] = raw_data[src_pos]
                
                img = Image.frombytes('P', (width, height), bytes(pixel_data))
                img.putpalette(palette)
                    
            else:  # 4bpp
                raw_data = f.read((width * height) // 2)
                pixel_data = bytearray()
                
                # 按行处理4bpp数据
                for y in range(height):
                    row_start = y * (width // 2)
                    for x in range(width // 2):
                        byte = raw_data[row_start + x]
                        # 每个字节的两个像素需要交换位置
                        low = (byte & 0x0F)
                        high = (byte & 0xF0) >> 4
                        pixel_data.extend([low, high])
                
                # 创建4bpp图像
                img = Image.frombytes('P', (width, height), bytes(pixel_data))
                img.putpalette(palette)
            
            # 创建最终的图像显示
            self.photo = ImageTk.PhotoImage(img)
            self.canvas.config(scrollregion=(0, 0, width, height))
            self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
            
            # 更新信息显示
            file_size = os.path.getsize(filepath)
            self.update_info(filepath, img_type, width, height, palette_size, file_size)
            self.info_labels['调色板'].config(text=f"Alpha[0]={alpha_values[0]:02X}")

def main():
    root = tk.Tk()
    app = GSViewer(root)
    root.mainloop()

if __name__ == "__main__":
    main()