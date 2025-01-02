import wx
import json
import os
from pathlib import Path

class GSPImporterFrame(wx.Frame):
    def __init__(self):
        super().__init__(parent=None, title='GSP导入', size=(600, 400))
        
        
        panel = wx.Panel(self)
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        GSP_box = wx.BoxSizer(wx.HORIZONTAL)
        self.GSP_text = wx.TextCtrl(panel, style=wx.TE_READONLY)
        GSP_btn = wx.Button(panel, label='选择GSP文件')
        GSP_box.Add(wx.StaticText(panel, label='目标GSP:'), 0, wx.ALL | wx.CENTER, 5)
        GSP_box.Add(self.GSP_text, 1, wx.EXPAND | wx.ALL, 5)
        GSP_box.Add(GSP_btn, 0, wx.ALL, 5)
        
        json_box = wx.BoxSizer(wx.HORIZONTAL)
        self.json_text = wx.TextCtrl(panel, style=wx.TE_READONLY)
        json_btn = wx.Button(panel, label='选择JSON文件')
        json_box.Add(wx.StaticText(panel, label='信息JSON:'), 0, wx.ALL | wx.CENTER, 5)
        json_box.Add(self.json_text, 1, wx.EXPAND | wx.ALL, 5)
        json_box.Add(json_btn, 0, wx.ALL, 5)
        
        GS_box = wx.BoxSizer(wx.HORIZONTAL)
        self.GS_text = wx.TextCtrl(panel, style=wx.TE_READONLY)
        GS_btn = wx.Button(panel, label='选择GS文件')
        GS_box.Add(wx.StaticText(panel, label='待导入GS:'), 0, wx.ALL | wx.CENTER, 5)
        GS_box.Add(self.GS_text, 1, wx.EXPAND | wx.ALL, 5)
        GS_box.Add(GS_btn, 0, wx.ALL, 5)
        
        self.info_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        
        self.import_btn = wx.Button(panel, label='导入')
        self.import_btn.Enable(False)
        
        vbox.Add(GSP_box, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(json_box, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(GS_box, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(self.info_text, 1, wx.EXPAND | wx.ALL, 5)
        vbox.Add(self.import_btn, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        
        panel.SetSizer(vbox)
        
        GSP_btn.Bind(wx.EVT_BUTTON, self.on_select_GSP)
        json_btn.Bind(wx.EVT_BUTTON, self.on_select_json)
        GS_btn.Bind(wx.EVT_BUTTON, self.on_select_GS)
        self.import_btn.Bind(wx.EVT_BUTTON, self.on_import)
        
        self.GSP_path = None
        self.json_path = None
        self.GS_path = None
        self.json_data = None
        
        
    def log(self, message):
        self.info_text.AppendText(f"{message}\n")
        
    def check_files(self):
        if all([self.GSP_path, self.json_path, self.GS_path]):
            self.import_btn.Enable(True)
        else:
            self.import_btn.Enable(False)
            
    def on_select_GSP(self, event):
        with wx.FileDialog(self, "选择目标GSP文件", wildcard="GSP files (*.GSP)|*.GSP",
                         style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            self.GSP_path = fileDialog.GetPath()
            self.GSP_text.SetValue(self.GSP_path)
            self.log(f"已选择GSP文件: {self.GSP_path}")
            self.check_files()
            
    def on_select_json(self, event):
        with wx.FileDialog(self, "选择信息JSON文件", wildcard="JSON files (*.json)|*.json",
                         style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            self.json_path = fileDialog.GetPath()
            self.json_text.SetValue(self.json_path)
            
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    self.json_data = json.load(f)
                self.log(f"已加载JSON文件: {self.json_path}")
            except Exception as e:
                self.log(f"JSON读取失败: {str(e)}")
                self.json_path = None
                self.json_data = None
                
            self.check_files()
            
    def on_select_GS(self, event):
        with wx.FileDialog(self, "选择待导入的GS文件", wildcard="GS files (*.gs)|*.gs",
                         style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            self.GS_path = fileDialog.GetPath()
            self.GS_text.SetValue(self.GS_path)
            self.log(f"已选择GS文件: {self.GS_path}")
            self.check_files()
            
    def on_import(self, event):
        try:
            GS_name = os.path.basename(self.GS_path)
            GS_size = os.path.getsize(self.GS_path)
            
            GS_info = None
            for texture in self.json_data["textures"]:
                if texture["filename"] == GS_name:
                    GS_info = texture
                    break
            
            if not GS_info:
                raise ValueError(f"在JSON中未找到 {GS_name} 的信息")
            
            # 检查文件大小
            if GS_size != GS_info["size"]:
                raise ValueError(
                    f"文件大小不匹配\n"
                    f"原始: {GS_info['size']} 字节\n"
                    f"实际: {GS_size} 字节"
                )
            
            
            with open(self.GS_path, 'rb') as f:
                GS_data = f.read()
            
            # 写入GSP
            with open(self.GSP_path, 'r+b') as f:
                f.seek(GS_info["offset_start"])
                f.write(GS_data)
            
            self.log(f"成功导入 {GS_name} 到GSP!")
            wx.MessageBox("导入成功！", "成功", wx.OK | wx.ICON_INFORMATION)
            
        except Exception as e:
            self.log(f"导入失败: {str(e)}")
            wx.MessageBox(f"导入失败: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)

if __name__ == '__main__':
    app = wx.App()
    frame = GSPImporterFrame()
    frame.Show()
    app.MainLoop()