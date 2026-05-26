# SVRist.py
# -*- coding: utf-8 -*-
import wx
import os
import json
import subprocess
import threading
import tempfile
import shutil
import datetime
import sys
from wx.lib.mixins.listctrl import ColumnSorterMixin

APP_VERSION = "v1.0.0"
CHECKERBOARD_DARK = wx.Colour(18, 23, 25)
CHECKERBOARD_LIGHT = wx.Colour(43, 48, 50)
CHECKERBOARD_CELL_SIZE = 16
DEFAULT_PREVIEW_TEXT = "双击文件扫描GBIX"

# Color mappings for different modes (example)
COLOR_4BPP = wx.Colour(94, 155, 137)
COLOR_8BPP = wx.Colour(186, 105, 164)
COLOR_OTHER = wx.Colour(100, 150, 200)

if getattr(sys, 'frozen', False):
    # If running as PyInstaller EXE
    APP_DIR = os.path.dirname(sys.executable)
else:
    # If running as a normal Python script
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

WORK_DIR = os.path.join(APP_DIR, "work_dir")
if not os.path.exists(WORK_DIR):
    os.makedirs(WORK_DIR)

class SVRListCtrl(wx.ListCtrl, ColumnSorterMixin):
    def __init__(self, parent, frame):
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.frame = frame
        self.itemDataMap = {}
        self.InsertColumn(0, "索引", width=50)
        self.InsertColumn(1, "偏移(16进制)", width=100)
        self.InsertColumn(2, "大小", width=80, format=wx.LIST_FORMAT_RIGHT)
        self.InsertColumn(3, "格式/模式", width=160)
        self.InsertColumn(4, "宽x高", width=100)
        self.InsertColumn(5, "Flag18", width=70)
        ColumnSorterMixin.__init__(self, 6)
        
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemSelected)
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)

    def PopulateList(self, svr_images):
        self.DeleteAllItems()
        self.itemDataMap.clear()
        for idx, info in enumerate(svr_images):
            offset_str = f"0x{info['offset']:X}"
            size_str = str(info['size'])
            mode_str = info['mode']
            dim_str = f"{info['width']}x{info['height']}"
            flag18_str = f"0x{info['flag18']:04X}"

            sort_key_tuple = (
                info['index'], info['offset'], info['size'], mode_str,
                info['width'] * info['height'], info['flag18']
            )
            self.itemDataMap[idx] = (sort_key_tuple, info)

            list_idx = self.InsertItem(self.GetItemCount(), str(info['index']))
            
            text_color = COLOR_OTHER
            if "4BPP" in mode_str: text_color = COLOR_4BPP
            elif "8BPP" in mode_str: text_color = COLOR_8BPP
            self.SetItemTextColour(list_idx, text_color)

            self.SetItem(list_idx, 1, offset_str)
            self.SetItem(list_idx, 2, size_str)
            self.SetItem(list_idx, 3, mode_str)
            self.SetItem(list_idx, 4, dim_str)
            self.SetItem(list_idx, 5, flag18_str)
            
            self.SetItemData(list_idx, idx)

        if self.itemDataMap:
            self.SortListItems(0, True)

    def OnItemSelected(self, event):
        list_index = event.GetIndex()
        original_idx = wx.ListCtrl.GetItemData(self, list_index)
        if original_idx in self.itemDataMap:
            _, info = self.itemDataMap[original_idx]
            wx.CallAfter(self.frame.PreviewImage, info)

    def OnRightDown(self, event):
        pos = event.GetPosition()
        list_index, flags = self.HitTest(pos)
        if list_index != wx.NOT_FOUND:
            if not self.IsSelected(list_index):
                self.Select(list_index)
                
            original_idx = wx.ListCtrl.GetItemData(self, list_index)
            if original_idx in self.itemDataMap:
                _, info = self.itemDataMap[original_idx]
                self.frame.ShowContextMenu(info, self, pos)
        event.Skip()

    def GetListCtrl(self):
        return self

    def GetItemData(self, item):
        if item in self.itemDataMap:
            return self.itemDataMap[item][0]
        return ()

class SVRistFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super(SVRistFrame, self).__init__(*args, **kw, title=f"SVRist - {APP_VERSION}", size=(1280, 768))
        self.current_file_path = None
        self.is_scanning = False
        self.current_bitmap = wx.NullBitmap
        self.preview_target_size = (384, 384)
        self.show_default_text = True
        
        self.exe_path = os.path.join(APP_DIR, "svr_converter.exe")

        self._init_ui()
        self.Centre()
        self.Show()

        self.log_message(f"SVRist {APP_VERSION}，GBIX(SVR) 查看及提取工具。")
        self.log_message(f"后端程序: {self.exe_path}")
        self.log_message(f"工作目录: {WORK_DIR}")

    def _init_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Left side: File Explorer
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        left_title = wx.StaticText(panel, label="双击任意文件进行扫描")
        left_sizer.Add(left_title, 0, wx.LEFT | wx.TOP | wx.RIGHT, 5)
        
        self.dir_ctrl = wx.GenericDirCtrl(panel, -1, dir=os.getcwd(), style=wx.DIRCTRL_DEFAULT_STYLE | wx.BORDER_SUNKEN)
        left_sizer.Add(self.dir_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(left_sizer, 4, wx.EXPAND)
        
        # Middle side: List Control and Scan progress
        mid_sizer = wx.BoxSizer(wx.VERTICAL)
        mid_title = wx.StaticText(panel, label="GBIX 图像扫描结果")
        mid_sizer.Add(mid_title, 0, wx.ALL, 5)
        
        self.list_ctrl = SVRListCtrl(panel, self)
        mid_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        
        self.scan_gauge = wx.Gauge(panel, range=100, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        self.scan_gauge.Hide()
        mid_sizer.Add(self.scan_gauge, 0, wx.EXPAND | wx.ALL, 5)
        
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_export_all = wx.Button(panel, label="导出全部PNG")
        self.btn_clear_workdir = wx.Button(panel, label="清理临时目录")
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self.btn_export_all, 0, wx.ALL, 5)
        btn_sizer.Add(self.btn_clear_workdir, 0, wx.ALL, 5)
        btn_sizer.AddStretchSpacer()
        mid_sizer.Add(btn_sizer, 0, wx.EXPAND)
        
        main_sizer.Add(mid_sizer, 6, wx.EXPAND)
        
        # Right side: Preview and Log
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        self.preview_panel = wx.Panel(panel, size=self.preview_target_size, style=wx.BORDER_SUNKEN)
        self.preview_panel.Bind(wx.EVT_PAINT, self.OnPaintPreview)
        right_sizer.Add(self.preview_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        self.log_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        right_sizer.Add(self.log_text, 1, wx.EXPAND | wx.ALL, 5)
        
        main_sizer.Add(right_sizer, 5, wx.EXPAND)
        
        panel.SetSizer(main_sizer)
        panel.Layout()
        
        # Bind events
        self.dir_ctrl.Bind(wx.EVT_DIRCTRL_FILEACTIVATED, self.OnFileActivated)
        self.btn_export_all.Bind(wx.EVT_BUTTON, self.OnExportAll)
        self.btn_clear_workdir.Bind(wx.EVT_BUTTON, self.OnClearWorkDir)

    def log_message(self, message, is_error=False):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}\n"
        wx.CallAfter(self._append_log, entry, is_error)

    def _append_log(self, text, is_error):
        start_pos = self.log_text.GetLastPosition()
        self.log_text.AppendText(text)
        end_pos = self.log_text.GetLastPosition()
        self.log_text.SetStyle(start_pos, end_pos, wx.TextAttr(wx.RED if is_error else wx.BLACK))
        self.log_text.ShowPosition(end_pos)

    def OnPaintPreview(self, event):
        dc = wx.BufferedPaintDC(self.preview_panel)
        width, height = self.preview_panel.GetClientSize()
        
        # Draw checkerboard background
        dc.SetPen(wx.TRANSPARENT_PEN)
        for y in range(0, height, CHECKERBOARD_CELL_SIZE):
            for x in range(0, width, CHECKERBOARD_CELL_SIZE):
                if (x // CHECKERBOARD_CELL_SIZE % 2) == (y // CHECKERBOARD_CELL_SIZE % 2):
                    dc.SetBrush(wx.Brush(CHECKERBOARD_LIGHT))
                else:
                    dc.SetBrush(wx.Brush(CHECKERBOARD_DARK))
                dc.DrawRectangle(x, y, CHECKERBOARD_CELL_SIZE, CHECKERBOARD_CELL_SIZE)
                
        if self.current_bitmap and self.current_bitmap.IsOk():
            bmp_w, bmp_h = self.current_bitmap.GetWidth(), self.current_bitmap.GetHeight()
            draw_x = max(0, (width - bmp_w) // 2)
            draw_y = max(0, (height - bmp_h) // 2)
            dc.DrawBitmap(self.current_bitmap, draw_x, draw_y, True)
        elif self.show_default_text:
            dc.SetTextForeground(wx.Colour(200, 200, 200))
            font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
            font.SetPointSize(12)
            dc.SetFont(font)
            text_w, text_h = dc.GetTextExtent(DEFAULT_PREVIEW_TEXT)
            dc.DrawText(DEFAULT_PREVIEW_TEXT, (width - text_w) // 2, (height - text_h) // 2)

    def OnFileActivated(self, event):
        if self.is_scanning:
            self.log_message("扫描正在进行中，请稍候...", True)
            return
        
        filepath = self.dir_ctrl.GetFilePath()
        if filepath and os.path.isfile(filepath):
            if not os.path.exists(self.exe_path):
                self.log_message("找不到 svr_converter.exe 后端程序！", True)
                return
            
            self.current_file_path = filepath
            self.log_message(f"开始扫描文件: {filepath}")
            self.list_ctrl.DeleteAllItems()
            self.list_ctrl.itemDataMap.clear()
            self.show_default_text = True
            self.current_bitmap = wx.NullBitmap
            self.preview_panel.Refresh()
            
            self.scan_gauge.Show()
            self.scan_gauge.Pulse()
            self.Layout()
            
            threading.Thread(target=self._scan_thread, args=(filepath,), daemon=True).start()

    def _scan_thread(self, filepath):
        self.is_scanning = True
        try:
            print("正在调用 svr_converter 执行扫描...")
            result = subprocess.run(
                [self.exe_path, "-scan", filepath],
                capture_output=True, text=True, check=True
            )
            
            output = result.stdout.strip()
            if output:
                images = json.loads(output)
                wx.CallAfter(self._scan_complete, images, None)
            else:
                wx.CallAfter(self._scan_complete, [], None)
                
        except subprocess.CalledProcessError as e:
            wx.CallAfter(self._scan_complete, None, f"后端运行错误: {e.stderr}")
        except json.JSONDecodeError:
            wx.CallAfter(self._scan_complete, None, f"后端返回了无效的数据格式 (JSON 解析失败)")
        except Exception as e:
            wx.CallAfter(self._scan_complete, None, str(e))
        finally:
            self.is_scanning = False

    def _scan_complete(self, images, error):
        self.scan_gauge.Hide()
        self.Layout()
        
        if error:
            self.log_message(f"扫描失败: {error}", True)
        elif images is not None:
            self.log_message(f"扫描完成。找到 {len(images)} 个GBIX图像。")
            self.list_ctrl.PopulateList(images)
            if len(images) > 0:
                self.list_ctrl.Select(0)
                self.list_ctrl.EnsureVisible(0)

    def PreviewImage(self, info):
        if not self.current_file_path:
            return
            
        offset = info['offset']
        threading.Thread(target=self._extract_preview_thread, args=(offset,), daemon=True).start()
        
    def _extract_preview_thread(self, offset):
        try:
            result = subprocess.run(
                [self.exe_path, "-extract", str(offset), "-outdir", WORK_DIR, self.current_file_path],
                capture_output=True, text=True, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            out_png = result.stdout.strip()
            if out_png and os.path.exists(out_png):
                wx.CallAfter(self._load_preview, out_png)
            else:
                wx.CallAfter(self.log_message, f"提取失败，未收到输出文件路径或文件不存在: {out_png}", True)
        except subprocess.CalledProcessError as e:
            wx.CallAfter(self.log_message, f"提取图像后端错误: {e.stderr}", True)
        except Exception as e:
            wx.CallAfter(self.log_message, f"意外错误: {e}", True)

    def _load_preview(self, img_path):
        try:
            with open(img_path, 'rb') as f:
                img_data = f.read()
            import io
            stream = io.BytesIO(img_data)
            img = wx.Image(stream)
            
            if img.IsOk():
                w, h = img.GetWidth(), img.GetHeight()
                tw, th = self.preview_target_size
                
                if w > tw or h > th:
                    ratio = min(tw/w, th/h)
                    new_w, new_h = max(1, int(w * ratio)), max(1, int(h * ratio))
                    img = img.Scale(new_w, new_h, wx.IMAGE_QUALITY_HIGH)
                    
                self.current_bitmap = wx.Bitmap(img)
                self.show_default_text = False
                self.preview_panel.Refresh()
            else:
                self.log_message(f"加载预览图失败: 图像格式无效或损坏", True)
        except Exception as e:
            self.log_message(f"加载预览图失败 (异常): {e}", True)

    def ShowContextMenu(self, info, invoking_window, point):
        try:
            menu = wx.Menu()
            menu.current_info = info
            item_export = menu.Append(wx.ID_ANY, "导出为PNG")
            menu.AppendSeparator()
            item_import = menu.Append(wx.ID_ANY, "插入新图像")
            
            self.Bind(wx.EVT_MENU, self.OnMenuExportSingle, item_export)
            self.Bind(wx.EVT_MENU, self.OnMenuImportSingle, item_import)
            
            invoking_window.PopupMenu(menu, point)
            menu.Destroy()
        except Exception as e:
            self.log_message(f"[Error] ShowContextMenu failed: {e}", True)

    def OnMenuExportSingle(self, event):
        menu = event.GetEventObject()
        if hasattr(menu, 'current_info'):
            self.ExportSingle(menu.current_info)

    def OnMenuImportSingle(self, event):
        menu = event.GetEventObject()
        if hasattr(menu, 'current_info'):
            self.ImportSingle(menu.current_info)

    def ExportSingle(self, info):
        if not self.current_file_path: return
        
        default_name = f"{os.path.basename(self.current_file_path)}_offset_{info['offset']}.png"
        with wx.FileDialog(self, "导出 PNG", defaultDir=os.getcwd(), defaultFile=default_name, wildcard="PNG 文件 (*.png)|*.png", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            save_path = dlg.GetPath()
            
        threading.Thread(target=self._export_thread, args=(info['offset'], os.path.dirname(save_path), os.path.basename(save_path)), daemon=True).start()

    def _export_thread(self, offset, outdir, filename):
        try:
            print(f"正在调用 svr_converter 导出图像，偏移: {offset} 到 {outdir}")
            result = subprocess.run(
                [self.exe_path, "-extract", str(offset), "-outdir", outdir, self.current_file_path],
                capture_output=True, text=True, check=True
            )
            out_png = result.stdout.strip()
            if out_png and os.path.exists(out_png):
                # Rename to user requested filename
                target_path = os.path.join(outdir, filename)
                if out_png != target_path:
                    shutil.move(out_png, target_path)
                wx.CallAfter(self.log_message, f"图像成功导出至: {target_path}")
            else:
                wx.CallAfter(self.log_message, f"导出失败。", True)
        except Exception as e:
            wx.CallAfter(self.log_message, f"导出发生错误: {e}", True)

    def ImportSingle(self, info):
        if not self.current_file_path: return
        
        with wx.FileDialog(self, "选择要注入的 PNG 图像", defaultDir=os.getcwd(), wildcard="PNG 文件 (*.png)|*.png", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            png_path = dlg.GetPath()
            
        threading.Thread(target=self._import_thread, args=(info['offset'], png_path), daemon=True).start()

    def _import_thread(self, offset, png_path):
        try:
            wx.CallAfter(self.log_message, f"正在调用 svr_converter 注入图像至偏移: {offset}...")
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            result = subprocess.run(
                [self.exe_path, "-inject", str(offset), "-png", png_path, self.current_file_path],
                capture_output=True, text=True, startupinfo=startupinfo
            )
            
            if result.returncode == 0:
                wx.CallAfter(self.log_message, f"注入成功！")
                # Reload preview to show injected result
                info = None
                for orig_idx, (idx, meta) in self.list_ctrl.itemDataMap.items():
                    if meta['offset'] == offset:
                        info = meta
                        break
                if info:
                    wx.CallAfter(self.PreviewImage, info)
            else:
                wx.CallAfter(self.log_message, f"注入失败: {result.stderr}\n{result.stdout}", True)
        except Exception as e:
            wx.CallAfter(self.log_message, f"注入发生错误: {e}", True)

    def OnExportAll(self, event):
        if not self.current_file_path or self.list_ctrl.GetItemCount() == 0:
            self.log_message("没有可导出的图像。")
            return
            
        with wx.DirDialog(self, "选择导出目录", defaultPath=os.getcwd(), style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            export_dir = dlg.GetPath()
            
        self.log_message(f"正在导出全部图像到: {export_dir}")
        items = list(self.list_ctrl.itemDataMap.values())
        threading.Thread(target=self._export_all_thread, args=(items, export_dir), daemon=True).start()

    def _export_all_thread(self, items, export_dir):
        success_count = 0
        for i, (_, info) in enumerate(items):
            try:
                print(f"[{i+1}/{len(items)}] 正在提取偏移 {info['offset']}...")
                subprocess.run(
                    [self.exe_path, "-extract", str(info['offset']), "-outdir", export_dir, self.current_file_path],
                    capture_output=True, check=True
                )
                success_count += 1
            except Exception as e:
                wx.CallAfter(self.log_message, f"导出偏移 {info['offset']} 失败: {e}", True)
                
        wx.CallAfter(self.log_message, f"批量导出完成，成功 {success_count}/{len(items)}。")

    def OnClearWorkDir(self, event):
        count = 0
        for f in os.listdir(WORK_DIR):
            fp = os.path.join(WORK_DIR, f)
            if os.path.isfile(fp):
                try:
                    os.remove(fp)
                    count += 1
                except:
                    pass
        print("清理工作目录...")
        self.log_message(f"已清理临时工作目录，删除了 {count} 个文件。")

if __name__ == '__main__':
    app = wx.App()
    wx.InitAllImageHandlers()
    frame = SVRistFrame(None)
    app.MainLoop()
