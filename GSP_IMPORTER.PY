import wx
import json
import os
from pathlib import Path

class GSPImporterFrame(wx.Frame):
    def __init__(self):
        super().__init__(parent=None, title='GSP图片导入工具', size=(600, 400))
        
        # 创建面板
        panel = wx.Panel(self)
        
        # 创建垂直布局
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # GSP文件选择
        GSP_box = wx.BoxSizer(wx.HORIZONTAL)
        self.GSP_text = wx.TextCtrl(panel, style=wx.TE_READONLY)
        GSP_btn = wx.Button(panel, label='选择GSP文件')
        GSP_box.Add(wx.StaticText(panel, label='目标GSP:'), 0, wx.ALL | wx.CENTER, 5)
        GSP_box.Add(self.GSP_text, 1, wx.EXPAND | wx.ALL, 5)
        GSP_box.Add(GSP_btn, 0, wx.ALL, 5)
        
        # JSON文件选择
        json_box = wx.BoxSizer(wx.HORIZONTAL)
        self.json_text = wx.TextCtrl(panel, style=wx.TE_READONLY)
        json_btn = wx.Button(panel, label='选择JSON文件')
        json_box.Add(wx.StaticText(panel, label='信息JSON:'), 0, wx.ALL | wx.CENTER, 5)
        json_box.Add(self.json_text, 1, wx.EXPAND | wx.ALL, 5)
        json_box.Add(json_btn, 0, wx.ALL, 5)
        
        # GS文件选择
        GS_box = wx.BoxSizer(wx.HORIZONTAL)
        self.GS_text = wx.TextCtrl(panel, style=wx.TE_READONLY)
        GS_btn = wx.Button(panel, label='选择GS文件')
        GS_box.Add(wx.StaticText(panel, label='待导入GS:'), 0, wx.ALL | wx.CENTER, 5)
        GS_box.Add(self.GS_text, 1, wx.EXPAND | wx.ALL, 5)
        GS_box.Add(GS_btn, 0, wx.ALL, 5)
        
        # 信息显示区域
        self.info_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        
        # 导入按钮
        self.import_btn = wx.Button(panel, label='导入')
        self.import_btn.Enable(False)
        
        # 添加所有控件到垂直布局
        vbox.Add(GSP_box, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(json_box, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(GS_box, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(self.info_text, 1, wx.EXPAND | wx.ALL, 5)
        vbox.Add(self.import_btn, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        
        # 设置面板布局
        panel.SetSizer(vbox)
        
        # 绑定事件
        GSP_btn.Bind(wx.EVT_BUTTON, self.on_select_GSP)
        json_btn.Bind(wx.EVT_BUTTON, self.on_select_json)
        GS_btn.Bind(wx.EVT_BUTTON, self.on_select_GS)
        self.import_btn.Bind(wx.EVT_BUTTON, self.on_import)
        
        # 初始化变量
        self.GSP_path = None
        self.json_path = None
        self.GS_path = None
        self.json_data = None
        
        # 设置图标
        self.SetIcon(wx.Icon("icon.ico")) if os.path.exists("icon.ico") else None
        
    def log(self, message):
        """添加日志到信息显示区域"""
        self.info_text.AppendText(f"{message}\n")
        
    def check_files(self):
        """检查是否可以启用导入按钮"""
        if all([self.GSP_path, self.json_path, self.GS_path]):
            self.import_btn.Enable(True)
        else:
            self.import_btn.Enable(False)
            
    def on_select_GSP(self, event):
        """选择GSP文件"""
        with wx.FileDialog(self, "选择目标GSP文件", wildcard="GSP files (*.GSP)|*.GSP",
                         style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            self.GSP_path = fileDialog.GetPath()
            self.GSP_text.SetValue(self.GSP_path)
            self.log(f"已选择GSP文件: {self.GSP_path}")
            self.check_files()
            
    def on_select_json(self, event):
        """选择JSON文件"""
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
                self.log(f"❌ JSON文件读取失败: {str(e)}")
                self.json_path = None
                self.json_data = None
                
            self.check_files()
            
    def on_select_GS(self, event):
        """选择GS文件"""
        with wx.FileDialog(self, "选择待导入的GS文件", wildcard="GS files (*.GS)|*.GS",
                         style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            self.GS_path = fileDialog.GetPath()
            self.GS_text.SetValue(self.GS_path)
            self.log(f"已选择GS文件: {self.GS_path}")
            self.check_files()
            
    def on_import(self, event):
        """执行导入操作"""
        try:
            # 获取GS文件名和大小
            GS_name = os.path.basename(self.GS_path)
            GS_size = os.path.getsize(self.GS_path)
            
            # 在JSON中查找对应信息
            GS_info = None
            for texture in self.json_data["textures"]:
                if texture["filename"] == GS_name:
                    GS_info = texture
                    break
            
            if not GS_info:
                raise ValueError(f"在JSON中未找到 {GS_name} 的信息")
            
            # 检查文件大小是否匹配
            if GS_size != GS_info["size"]:
                raise ValueError(
                    f"文件大小不匹配\n"
                    f"期望: {GS_info['size']} bytes\n"
                    f"实际: {GS_size} bytes"
                )
            
            # 读取GS数据
            with open(self.GS_path, 'rb') as f:
                GS_data = f.read()
            
            # 写入GSP文件
            with open(self.GSP_path, 'r+b') as f:
                f.seek(GS_info["offset_start"])
                f.write(GS_data)
            
            self.log(f"✨ 成功导入 {GS_name} 到GSP!")
            wx.MessageBox("导入成功！", "成功", wx.OK | wx.ICON_INFORMATION)
            
        except Exception as e:
            self.log(f"❌ 导入失败: {str(e)}")
            wx.MessageBox(f"导入失败: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)

if __name__ == '__main__':
    app = wx.App()
    frame = GSPImporterFrame()
    frame.Show()
    app.MainLoop()