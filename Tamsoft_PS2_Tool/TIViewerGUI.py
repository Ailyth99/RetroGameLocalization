import wx
import struct
import sys
import os
import datetime
import subprocess
import tempfile
import shutil
import threading
import mmap
from wx.lib.mixins.listctrl import ColumnSorterMixin

try:
    from PIL import Image
except ImportError:
    Image = None

TI_SIGNATURE = b'\x10\x00\x00\x00\x01\x00\x01\x00\x30\x00\x00\x00\x00\x00\x00\x00'
SIGNATURE_LEN = len(TI_SIGNATURE)
OFF_BPP = 0x16
OFF_W = 0x22
OFF_H = 0x24
OFF_CLUT = 0x30
CREATE_NO_WINDOW = 0x08000000 

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def calculate_ti_size(mm, offset):
    try:
        if offset + 0x26 > len(mm): return None
        bpp_type = struct.unpack_from('<B', mm, offset + OFF_BPP)[0]
        if bpp_type not in [0, 1]: return None
        bpp = 4 if bpp_type == 0 else 8
        width = struct.unpack_from('<H', mm, offset + OFF_W)[0]
        height = struct.unpack_from('<H', mm, offset + OFF_H)[0]
        if width == 0 or height == 0 or width > 8192 or height > 8192: return None
        clut_size = 16 * 4 if bpp == 4 else 256 * 4
        pixel_data_size = (width * height + 1) // 2 if bpp == 4 else width * height
        total_size = OFF_CLUT + clut_size + pixel_data_size
        if offset + total_size > len(mm): return None
        return total_size, width, height, bpp
    except Exception:
        return None

def scan_ti_files_threaded(filename, progress_callback):
    ti_images = []
    error_msg = None
    file_size = 0
    update_interval_bytes = 1024 * 1024
    next_update_offset = update_interval_bytes
    try:
        file_size = os.path.getsize(filename)
        with open(filename, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            wx.CallAfter(progress_callback, 0, file_size, None, None)
            current_offset = 0
            ti_index = 1
            while current_offset < file_size:
                if current_offset >= next_update_offset:
                    wx.CallAfter(progress_callback, current_offset, file_size, None, None)
                    next_update_offset += update_interval_bytes
                found_offset = mm.find(TI_SIGNATURE, current_offset)
                if found_offset == -1: break
                calc_result = calculate_ti_size(mm, found_offset)
                if calc_result:
                    ti_size, width, height, bpp = calc_result
                    if ti_size > SIGNATURE_LEN:
                        end_offset = found_offset + ti_size - 1
                        ti_images.append({'index': ti_index, 'offset_start': found_offset, 'offset_end': end_offset, 'width': width, 'height': height, 'bpp': bpp, 'size': ti_size})
                        ti_index += 1
                        current_offset = found_offset + ti_size
                    else: current_offset = found_offset + 1
                else: current_offset = found_offset + 1
            wx.CallAfter(progress_callback, file_size, file_size, ti_images, None)
    except IOError as e: error_msg = f"IOError: {e}"; wx.CallAfter(progress_callback, -1, 0, None, error_msg)
    except ValueError as e: error_msg = f"MMap Error: {e}"; wx.CallAfter(progress_callback, -1, 0, None, error_msg)
    except Exception as e: error_msg = f"Unexpected Scan Error: {e}"; wx.CallAfter(progress_callback, -1, 0, None, error_msg)

class TIListCtrl(wx.ListCtrl, ColumnSorterMixin):
    def __init__(self, parent, frame):
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.frame = frame
        self.itemDataMap = {}
        self.InsertColumn(0, "Index", width=50)
        self.InsertColumn(1, "Offset Start", width=90)
        self.InsertColumn(2, "Offset End", width=90)
        self.InsertColumn(3, "Size (Bytes)", width=90, format=wx.LIST_FORMAT_RIGHT)
        self.InsertColumn(4, "Dimensions", width=90)
        self.InsertColumn(5, "BPP", width=40)
        ColumnSorterMixin.__init__(self, 6)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected)
    def PopulateList(self, ti_images):
        self.DeleteAllItems()
        self.itemDataMap.clear()
        for idx, info in enumerate(ti_images):
            start_hex, end_hex = hex(info['offset_start']), hex(info['offset_end'])
            dim_str, bpp_str, size_str = f"{info['width']}x{info['height']}", str(info['bpp']), str(info['size'])
            sort_key = (info['index'], info['offset_start'], info['offset_end'], info['size'], info['width'], info['height'], info['bpp'])
            self.itemDataMap[idx] = (sort_key, info)
            self.InsertItem(idx, str(info['index']))
            self.SetItem(idx, 1, start_hex); self.SetItem(idx, 2, end_hex); self.SetItem(idx, 3, size_str)
            self.SetItem(idx, 4, dim_str); self.SetItem(idx, 5, bpp_str)
            self.SetItemData(idx, idx)
        if self.itemDataMap: self.SortListItems(0, True)
    def OnItemSelected(self, event):
        list_index = event.GetIndex()
        if list_index in self.itemDataMap: _, info = self.itemDataMap[list_index]; wx.CallAfter(self.frame.PreviewTIImage, info)
    def GetListCtrl(self): return self
    def GetSortKeyFromTuple(self, sort_tuple, col):
        try: return sort_tuple[col]
        except IndexError: return 0
    def GetItemData(self, item): return item

class TIViewFr(wx.Frame):
    def __init__(self, *args, **kw):
        super(TIViewFr, self).__init__(*args, **kw, title="TI Viewer GUI", size=(1000, 600))
        if Image is None:
            wx.MessageBox("Pillow library not found!\n\nPlease install it by running:\npip install Pillow\n\nImage replacement will be disabled.", "Missing Dependency", wx.ICON_ERROR | wx.OK)
        self.ti_converter_path = resource_path("ti-converter.exe")
        self.tool_check()
        self.container_file_path, self.base_filename = None, None
        self.is_scanning = False
        self.selected_ti_list_index = -1
        self.current_preview_ti_info = None
        self._init_ui()
        self._bind_events()
        self.Centre(); self.Show(True)
        self.log_message("TI Viewer GUI Initialized. Select a file to scan.")
    def _init_ui(self):
        panel = wx.Panel(self); main_h_sizer = wx.BoxSizer(wx.HORIZONTAL)
        left_v_sizer = wx.BoxSizer(wx.VERTICAL)
        self.dir_ctrl = wx.GenericDirCtrl(panel, -1, dir=os.getcwd(), style=wx.DIRCTRL_DEFAULT_STYLE | wx.BORDER_SUNKEN)
        left_v_sizer.Add(self.dir_ctrl, 1, wx.EXPAND | wx.ALL, 5); main_h_sizer.Add(left_v_sizer, 1, wx.EXPAND)
        middle_v_sizer = wx.BoxSizer(wx.VERTICAL)
        self.ti_list = TIListCtrl(panel, self)
        self.scan_gauge = wx.Gauge(panel, range=100, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH); self.scan_gauge.Hide()
        middle_v_sizer.Add(self.ti_list, 1, wx.EXPAND | wx.ALL, 5); middle_v_sizer.Add(self.scan_gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5); main_h_sizer.Add(middle_v_sizer, 2, wx.EXPAND)
        right_v_sizer = wx.BoxSizer(wx.VERTICAL)
        self.preview_panel = wx.Panel(panel, size=(256, 256)); self.preview_panel.SetBackgroundColour(wx.LIGHT_GREY)
        self.preview_bitmap = wx.StaticBitmap(self.preview_panel, wx.ID_ANY, wx.NullBitmap); self.preview_bitmap.SetBackgroundColour(wx.LIGHT_GREY)
        preview_panel_sizer = wx.BoxSizer(wx.VERTICAL); preview_panel_sizer.Add(self.preview_bitmap, 1, wx.CENTER | wx.ALL, 5); self.preview_panel.SetSizer(preview_panel_sizer)
        self.log_text_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        right_v_sizer.Add(self.preview_panel, 0, wx.EXPAND | wx.ALL, 5); right_v_sizer.Add(self.log_text_ctrl, 1, wx.EXPAND | wx.ALL, 5); main_h_sizer.Add(right_v_sizer, 1, wx.EXPAND)
        panel.SetSizer(main_h_sizer); panel.Layout()
    def _bind_events(self):
        self.ti_list_menu = wx.Menu()
        self.export_item = self.ti_list_menu.Append(wx.ID_ANY, "Export TI...")
        self.export_png_item = self.ti_list_menu.Append(wx.ID_ANY, "Export to PNG...")
        self.replace_item = self.ti_list_menu.Append(wx.ID_ANY, "Replace TI with Image...")
        self.Bind(wx.EVT_MENU, self.OnExportTI, self.export_item)
        self.Bind(wx.EVT_MENU, self.OnExportPNG, self.export_png_item)
        self.Bind(wx.EVT_MENU, self.OnReplaceTI, self.replace_item)
        self.dir_ctrl.Bind(wx.EVT_DIRCTRL_FILEACTIVATED, self.OnDirCtrlFileActivated)
        self.ti_list.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnListRightClick)
    def tool_check(self):
        missing = []
        if not os.path.exists(self.ti_converter_path): missing.append(self.ti_converter_path)
        if missing: wx.MessageBox(f"Error: Tools not found:\n" + "\n".join(missing) + f"\nPlace them in same directory.", "Missing Tools", wx.ICON_ERROR | wx.OK)
    def log_message(self, message, is_error=False):
        try:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S"); entry = f"[{timestamp}] {message}\n"
            start_pos = self.log_text_ctrl.GetLastPosition(); self.log_text_ctrl.AppendText(entry); end_pos = self.log_text_ctrl.GetLastPosition()
            color = wx.RED if is_error else wx.BLACK; attr = wx.TextAttr(color)
            self.log_text_ctrl.SetStyle(start_pos, end_pos, attr); self.log_text_ctrl.ShowPosition(end_pos)
        except Exception as e: print(f"Error writing to log: {e}")
    def _run_subprocess(self, cmd_list, cwd=None, check=True):
        startupinfo, creationflags = None, 0
        if os.name == 'nt': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE; creationflags = CREATE_NO_WINDOW
        try: process = subprocess.run(cmd_list, check=check, capture_output=True, cwd=cwd, startupinfo=startupinfo, creationflags=creationflags, text=True, errors='ignore'); return process
        except FileNotFoundError: self.log_message(f"Error: Command not found: {cmd_list[0]}", True); raise
        except subprocess.CalledProcessError as e: self.log_message(f"Error running {' '.join(cmd_list)} (code {e.returncode}):\n{e.stderr}", True); raise
        except Exception as e: self.log_message(f"Unexpected error running subprocess: {e}", True); raise
    def ToggleScanControls(self, enable):
        self.dir_ctrl.Enable(enable); self.ti_list.Enable(enable)
        cursor_id = wx.CURSOR_DEFAULT if enable else wx.CURSOR_WAIT; cursor_obj = wx.Cursor(cursor_id); self.SetCursor(cursor_obj)
        if not enable: self.ti_list.Unbind(wx.EVT_LIST_ITEM_RIGHT_CLICK)
        else: self.ti_list.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnListRightClick)
    def OnDirCtrlFileActivated(self, event):
        if self.is_scanning: self.log_message("Scan currently in progress...", True); return
        filepath = self.dir_ctrl.GetFilePath()
        if filepath and os.path.isfile(filepath): self.LoadAndScanFile(filepath)
    def LoadAndScanFile(self, filepath):
        self.is_scanning = True; self.ToggleScanControls(False); self.container_file_path = filepath
        self.base_filename = os.path.splitext(os.path.basename(filepath))[0]
        self.SetTitle(f"TI Viewer GUI - Scanning: {os.path.basename(filepath)}")
        self.ti_list.DeleteAllItems(); self.ti_list.itemDataMap.clear()
        self.preview_bitmap.SetBitmap(wx.NullBitmap); self.preview_panel.Layout(); self.current_preview_ti_info = None
        self.log_message(f"Starting scan: {filepath}"); self.scan_gauge.SetValue(0); self.scan_gauge.Show(); self.Layout()
        scan_thread = threading.Thread(target=scan_ti_files_threaded, args=(filepath, self._handle_scan_progress)); scan_thread.daemon = True; scan_thread.start()
    def _handle_scan_progress(self, current_bytes, total_bytes, results, error_msg):
        base_title = "TI Viewer GUI"; current_file_title = f"{base_title} - {os.path.basename(self.container_file_path)}" if self.container_file_path else base_title
        if error_msg:
            self.log_message(f"Scan Error: {error_msg}", True); self.scan_gauge.SetValue(0); self.scan_gauge.Hide(); self.is_scanning = False; self.ToggleScanControls(True); self.SetTitle(current_file_title)
        elif results is not None:
            self.log_message(f"Scan complete. Found {len(results)} potential TI file(s).")
            self.scan_gauge.SetValue(100); wx.CallLater(500, self.scan_gauge.Hide)
            self.ti_list.PopulateList(results)
            self.is_scanning = False; self.ToggleScanControls(True); self.SetTitle(current_file_title)
            if self.ti_list.GetItemCount() > 0:
                if 0 in self.ti_list.itemDataMap: _, first_info = self.ti_list.itemDataMap[0]; self.ti_list.Select(0); self.ti_list.Focus(0); self.ti_list.EnsureVisible(0); wx.CallAfter(self.PreviewTIImage, first_info)
        else:
            if not self.scan_gauge.IsShown(): self.scan_gauge.Show(); self.Layout()
            if total_bytes > 0: percent = int((current_bytes / total_bytes) * 100); self.scan_gauge.SetValue(min(percent, 100))
            else: self.scan_gauge.Pulse()
    def PreviewTIImage(self, ti_info):
        self.current_preview_ti_info = ti_info
        self.preview_bitmap.SetBitmap(wx.NullBitmap); self.preview_panel.Layout()
        if not self.container_file_path: self.log_message("Error: Container file path not set.", True); return
        if not os.path.exists(self.ti_converter_path): self.log_message("Error: ti-converter.exe not found.", True); return
        temp_dir = None; temp_ti_fd, temp_ti_path = -1, ""
        try:
            temp_dir = tempfile.mkdtemp(prefix="ti_preview_")
            temp_ti_fd, temp_ti_path = tempfile.mkstemp(suffix=".ti", dir=temp_dir)
            expected_png_path = os.path.splitext(temp_ti_path)[0] + ".png"
            self.log_message(f"Extracting TI #{ti_info['index']}...")
            with open(self.container_file_path, 'rb') as f_in, os.fdopen(temp_ti_fd, 'wb') as f_temp_ti:
                f_in.seek(ti_info['offset_start']); ti_data = f_in.read(ti_info['size'])
                if len(ti_data) != ti_info['size']: self.log_message(f"Warning: Extracted size != expected.", True)
                f_temp_ti.write(ti_data)
            temp_ti_fd = -1
            self.log_message(f"Running ti-converter.exe...")
            cmd = [self.ti_converter_path, "-o", expected_png_path, temp_ti_path]
            process = self._run_subprocess(cmd, cwd=temp_dir, check=False)
            if process.returncode != 0: self.log_message(f"ti-converter.exe failed (code {process.returncode}):\n{process.stderr}", True); return
            if not os.path.exists(expected_png_path): self.log_message(f"Error: ti-converter.exe created no output: {expected_png_path}", True); return
            self.log_message("Loading preview image...")
            log_level = wx.Log.GetLogLevel(); wx.Log.SetLogLevel(0)
            try: img = wx.Image(expected_png_path, wx.BITMAP_TYPE_PNG)
            finally: wx.Log.SetLogLevel(log_level)
            if not img.IsOk(): self.log_message(f"Error: Failed to load generated PNG: {expected_png_path}", True); return
            img_w, img_h = img.GetWidth(), img.GetHeight()
            panel_w, panel_h = self.preview_panel.GetClientSize(); max_dim = min(panel_w, panel_h) - 10
            if img_w > max_dim or img_h > max_dim:
                 scale = min(max_dim / img_w, max_dim / img_h); new_w, new_h = int(img_w * scale), int(img_h * scale)
                 img = img.Scale(new_w, new_h, wx.IMAGE_QUALITY_HIGH)
            bmp = wx.Bitmap(img)
            if bmp.IsOk(): self.preview_bitmap.SetBitmap(bmp); self.preview_panel.Layout(); self.log_message(f"Preview loaded for TI #{ti_info['index']}.")
            else: self.log_message("Error creating bitmap.", True)
        except Exception as e: self.log_message(f"Unexpected error during preview: {e}", True)
        finally:
            if temp_ti_fd != -1:
                try: os.close(temp_ti_fd)
                except OSError: pass
            if temp_dir and os.path.exists(temp_dir):
                try: shutil.rmtree(temp_dir)
                except Exception as e: self.log_message(f"Error cleaning temp dir '{temp_dir}': {e}", True)
    def OnListRightClick(self, event):
        if self.is_scanning: return
        self.selected_ti_list_index = event.GetIndex()
        if self.selected_ti_list_index != -1 and self.selected_ti_list_index < self.ti_list.GetItemCount():
             if self.selected_ti_list_index in self.ti_list.itemDataMap: self.ti_list.PopupMenu(self.ti_list_menu, event.GetPoint())
             else: self.selected_ti_list_index = -1
        else: self.selected_ti_list_index = -1
    def _get_selected_ti_info(self):
        if self.selected_ti_list_index != -1 and self.selected_ti_list_index in self.ti_list.itemDataMap: _, info = self.ti_list.itemDataMap[self.selected_ti_list_index]; return info
        self.log_message("Error: No valid TI selected.", True); return None
    def OnExportTI(self, event):
        if self.is_scanning: return
        ti_info = self._get_selected_ti_info()
        if not ti_info or not self.container_file_path: return
        default_filename = f"{self.base_filename}_idx{ti_info['index']}_off{hex(ti_info['offset_start'])}.ti"
        dlg = wx.FileDialog(self, "Export Selected TI", defaultDir=os.path.dirname(self.container_file_path), defaultFile=default_filename, wildcard="TI (*.ti)|*.ti|All (*.*)|*.*", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            save_path = dlg.GetPath(); self.log_message(f"Exporting TI #{ti_info['index']} to {save_path}...")
            try:
                with open(self.container_file_path, 'rb') as f_in: f_in.seek(ti_info['offset_start']); ti_data = f_in.read(ti_info['size'])
                with open(save_path, 'wb') as f_out: f_out.write(ti_data)
                self.log_message("Export successful."); wx.MessageBox(f"TI exported to:\n{save_path}", "Export Complete", wx.ICON_INFORMATION)
            except Exception as e: self.log_message(f"Export failed: {e}", True); wx.MessageBox(f"Export failed:\n{e}", "Error", wx.ICON_ERROR)
        else: self.log_message("Export cancelled.")
        dlg.Destroy(); self.selected_ti_list_index = -1
    def OnExportPNG(self, event):
        if self.is_scanning: return
        ti_info = self._get_selected_ti_info()
        if not ti_info or not self.container_file_path: return
        default_filename = f"{self.base_filename}_idx{ti_info['index']}_off{hex(ti_info['offset_start'])}.png"
        dlg = wx.FileDialog(self, "Export TI to PNG", defaultDir=os.path.dirname(self.container_file_path), defaultFile=default_filename, wildcard="PNG files (*.png)|*.png", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK: self.log_message("PNG export cancelled."); dlg.Destroy(); return
        save_path = dlg.GetPath(); dlg.Destroy()
        self.log_message(f"Exporting TI #{ti_info['index']} to PNG: {save_path}...")
        temp_dir = None; temp_ti_fd, temp_ti_path = -1, ""
        success = False
        try:
            temp_dir = tempfile.mkdtemp(prefix="ti_export_")
            temp_ti_fd, temp_ti_path = tempfile.mkstemp(suffix=".ti", dir=temp_dir)
            with open(self.container_file_path, 'rb') as f_in, os.fdopen(temp_ti_fd, 'wb') as f_temp_ti:
                f_in.seek(ti_info['offset_start']); ti_data = f_in.read(ti_info['size'])
                f_temp_ti.write(ti_data)
            temp_ti_fd = -1 
            cmd = [self.ti_converter_path, "-o", save_path, temp_ti_path]
            process = self._run_subprocess(cmd, cwd=temp_dir, check=False)
            if process.returncode == 0 and os.path.exists(save_path):
                self.log_message("PNG export successful."); wx.MessageBox(f"TI successfully exported to:\n{save_path}", "Export Complete", wx.ICON_INFORMATION); success = True
            else: self.log_message(f"ti-converter.exe failed (code {process.returncode}):\n{process.stderr}", True)
        except Exception as e: self.log_message(f"An error occurred during PNG export: {e}", True)
        finally:
            if temp_ti_fd != -1: 
                try: os.close(temp_ti_fd)
                except OSError: pass
            if temp_dir and os.path.exists(temp_dir):
                try: shutil.rmtree(temp_dir)
                except Exception as e: self.log_message(f"Error cleaning temp dir '{temp_dir}': {e}", True)
        if not success: wx.MessageBox("PNG export failed. Please check the log for details.", "Error", wx.ICON_ERROR)
        self.selected_ti_list_index = -1
    def OnReplaceTI(self, event):
        if self.is_scanning: return
        if Image is None:
            self.log_message("Pillow library not found, cannot replace image.", True)
            wx.MessageBox("Pillow is required for image replacement.", "Error", wx.ICON_ERROR)
            return
        ti_info = self._get_selected_ti_info()
        if not ti_info or not self.container_file_path: return
        if not os.access(self.container_file_path, os.W_OK): self.log_message(f"Error: Container file not writable.", True); wx.MessageBox("Container file not writable.", "Error", wx.ICON_ERROR); return
        if not os.path.exists(self.ti_converter_path): self.log_message("Error: ti-converter.exe not found.", True); return
        dlg_png = wx.FileDialog(self, f"Select Image to replace TI #{ti_info['index']}", wildcard="Image files (*.png;*.jpg;*.gif)|*.png;*.jpg;*.gif", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg_png.ShowModal() != wx.ID_OK: self.log_message("Replacement cancelled."); dlg_png.Destroy(); return
        user_png_path = dlg_png.GetPath(); dlg_png.Destroy()
        self.log_message(f"Replacing TI #{ti_info['index']} with {os.path.basename(user_png_path)}...")
        temp_dir = None; success = False; processed_png_path = ""
        try:
            temp_dir = tempfile.mkdtemp(prefix="ti_replace_")
            self.log_message("Processing input image with Pillow...")
            img = Image.open(user_png_path)
            if img.width != ti_info['width'] or img.height != ti_info['height']:
                msg = f"Dimension mismatch! TI is {ti_info['width']}x{ti_info['height']}, but image is {img.width}x{img.height}."
                self.log_message(msg, True); wx.MessageBox(msg, "Error", wx.ICON_ERROR); return
            target_colors = 16 if ti_info['bpp'] == 4 else 256
            needs_quantization = True
            if img.mode == 'P':
                palette_colors = len(img.getpalette()) // 3 if img.getpalette() else 0
                if palette_colors <= target_colors:
                    self.log_message("Input image is already a valid paletted image.")
                    needs_quantization = False
            if needs_quantization:
                self.log_message(f"Quantizing image to {target_colors} colors with dithering...")
                quantized_img = img.convert('RGB').quantize(colors=target_colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
                img_to_save = quantized_img
            else: img_to_save = img
            processed_png_path = os.path.join(temp_dir, "processed.png")
            img_to_save.save(processed_png_path, "PNG")
            self.log_message(f"Processed PNG saved to temporary file: {processed_png_path}")
            original_temp_ti_fd, original_temp_ti_path = tempfile.mkstemp(suffix="_orig.ti", dir=temp_dir)
            self.log_message("Extracting original TI to temp file...")
            with open(self.container_file_path, 'rb') as f_in, os.fdopen(original_temp_ti_fd, 'wb') as f_temp_orig:
                f_in.seek(ti_info['offset_start']); original_ti_data = f_in.read(ti_info['size'])
                f_temp_orig.write(original_ti_data)
            original_temp_ti_fd = -1
            self.log_message(f"Running ti-converter.exe...")
            modified_temp_ti_path = os.path.join(temp_dir, "modified.ti")
            cmd = [self.ti_converter_path, "-o", modified_temp_ti_path, original_temp_ti_path, processed_png_path]
            process = self._run_subprocess(cmd, cwd=temp_dir, check=False)
            if process.returncode != 0: self.log_message(f"ti-converter.exe failed (code {process.returncode}):\n{process.stderr}", True); return
            if not os.path.exists(modified_temp_ti_path): self.log_message(f"Error: ti-converter.exe created no output TI", True); return
            self.log_message("Reading modified TI data...")
            with open(modified_temp_ti_path, 'rb') as f_mod: modified_ti_data = f_mod.read()
            original_size, modified_size = ti_info['size'], len(modified_ti_data)
            if modified_size != original_size: 
                msg = f"Size Mismatch Error!\nOriginal: {original_size}\nNew: {modified_size}\nAborted."
                self.log_message(msg.replace('\n', ' '), True); wx.MessageBox(msg, "Replacement Failed", wx.ICON_ERROR); return
            self.log_message(f"Size validated. Writing {modified_size} bytes back at {hex(ti_info['offset_start'])}...")
            with open(self.container_file_path, 'r+b') as f_container:
                f_container.seek(ti_info['offset_start']); f_container.write(modified_ti_data)
                success = True; self.log_message("Replacement write successful.")
        except Exception as e: self.log_message(f"An unexpected error occurred during replacement: {e}", True)
        finally:
            if 'original_temp_ti_fd' in locals() and original_temp_ti_fd != -1:
                try: os.close(original_temp_ti_fd)
                except OSError: pass
            if temp_dir and os.path.exists(temp_dir):
                try: shutil.rmtree(temp_dir)
                except Exception as e: self.log_message(f"Error cleaning temp dir '{temp_dir}': {e}", True)
        if success: wx.MessageBox("TI replaced successfully!\nSelect item again to refresh preview.", "Success", wx.ICON_INFORMATION)
        else: wx.MessageBox("Replacement failed. Check log.", "Error", wx.ICON_ERROR)
        self.selected_ti_list_index = -1

def main():
    try: _ = resource_path("dummy")
    except Exception as e:
         try: pre_app = wx.App(False); wx.MessageBox(f"Critical Error: Cannot determine path.\n{e}", "Startup Error", wx.ICON_ERROR | wx.OK); pre_app.Destroy()
         except: print(f"CRITICAL STARTUP ERROR: {e}")
         sys.exit(1)
    app = wx.App(False); frame = TIViewFr(None); frame.Show(); app.MainLoop()

if __name__ == '__main__':
    main()