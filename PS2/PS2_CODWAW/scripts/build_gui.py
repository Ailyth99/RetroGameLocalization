"""wxPython front end for the project's complete Chinese ISO build."""
import copy
from functools import lru_cache
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

import wx
import wx.lib.scrolledpanel
from PIL import Image, ImageFont
from fontTools.ttLib import TTFont

from build_settings import (DEFAULTS, FONT_NAMES, ROOT, SETTINGS_PATH,
                            ensure_build_idle, import_font, load_settings,
                            normalize, save_settings)
from unified_fonts import render_glyph

ISO_PATH = ROOT / 'COD5_TEST.iso'
LOG_PATH = ROOT / 'TEMP/builds/one_click_build/latest.log'
GUI_LOG = ROOT / 'TEMP/builds/one_click_build/gui.log'
FONT_LABELS = ('大字 · 标题 / 武器 / 人名', '小字 · 菜单 / HUD', '字幕 · 对话 / 提示')
BG = '#F3F5F8'
INK = '#1D2939'
MUTED = '#667085'
ACCENT = '#2563EB'


def local_path(value):
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


@lru_cache(maxsize=12)
def preview_face(path, stamp, size, pixels):
    # Only the on-screen preview is cached. The build always rereads every font.
    with TTFont(path, lazy=True) as font:
        codes = frozenset(font.getBestCmap() or {})
    return ImageFont.truetype(path, pixels * 4), codes


def face_for_preview(path, pixels):
    path = local_path(path)
    stat = path.stat()
    return preview_face(str(path), stat.st_mtime_ns, stat.st_size, pixels)


def preview_line(face, fallback, text, tiny=False, heading=False, bold=0):
    pixels = 12 if tiny else 24
    width, height, baseline = (14, 16, 14) if tiny else (28, 31, 26) if heading else (26, 32, 27)
    primary, codes = face_for_preview(face, pixels)
    backup, backup_codes = face_for_preview(fallback, pixels)
    row = Image.new('L', (len(text) * width, height))
    missing = set()
    for i, char in enumerate(text):
        code = ord(char)
        font = primary if code in codes else backup
        if code not in codes and code not in backup_codes and not char.isspace():
            missing.add(char)
        row.paste(render_glyph(font, code, width, height, baseline, bold), (i * width, 0))
    return row, missing


class Preview(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent, size=(-1, 180))
        self.SetMinSize((-1, 180))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.rows = []
        self.error = ''
        self.Bind(wx.EVT_PAINT, self.on_paint)

    def update(self, settings, sample):
        rows, missing = [], set()
        for i, name in enumerate(FONT_NAMES):
            content = ('百式冲锋枪　弹药 4x 47', '寻找掩护　清理战壕系统', sample or '散开，小心埋伏！')[i]
            mask, unavailable = preview_line(settings['fonts'][name], settings['fallback_font'],
                content[:48], tiny=i == 1, heading=i == 0,
                bold=settings['synthetic_bold_px'].get(name, 0))
            missing.update(unavailable)
            # The preview enlarges the native glyph tiles; game layout also depends on advance/kerning.
            scale = 1.25 * (settings['subtitles']['scale_percent'] / 100 if i == 2 else 1)
            mask = mask.resize((round(mask.width * scale), round(mask.height * scale)), Image.Resampling.NEAREST)
            color = settings['subtitles']['color'] if i == 2 else '#E6EDF5'
            rgb = Image.new('RGB', mask.size, color)
            rgba = rgb.convert('RGBA'); rgba.putalpha(mask)
            if i == 2 and settings['subtitles']['shadow']:
                # Approximate the native 1.5-unit shadow at the preview's 1.25x zoom.
                offset = 2
                shadow = Image.new('RGBA', mask.size, '#000000')
                shadow.putalpha(mask.point(lambda value: round(value * 160 / 255)))
                composite = Image.new('RGBA', (rgba.width + offset, rgba.height + offset))
                composite.alpha_composite(shadow, (offset, offset))
                composite.alpha_composite(rgba)
                rgba = composite
            rows.append(wx.Bitmap.FromBufferRGBA(*rgba.size, rgba.tobytes()))
        self.rows, self.error = rows, ''
        self.Refresh()
        return missing

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush('#182231')); dc.Clear()
        dc.SetFont(self.GetFont()); dc.SetTextForeground('#9CAFC7')
        if self.error:
            dc.DrawText(self.error[:90], 16, 20)
            return
        for i, (label, bitmap) in enumerate(zip(('大字', '小字', '字幕'), self.rows)):
            top = (7, 52, 86)[i]
            dc.DrawText(label, 16, top + 8)
            dc.DrawBitmap(bitmap, 68, top, True)


class BuildFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title='COD5 汉化构建工具', size=(1060, 920))
        self.SetMinSize((880, 720))
        self.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                             wx.FONTWEIGHT_NORMAL, faceName='Microsoft YaHei UI'))
        self.events = queue.Queue()
        self.building = False
        self.loading = True
        self.dirty = False
        self.preview_pending = None
        self.started = 0
        self.process = None
        self.output_unavailable = False
        panel = wx.Panel(self); panel.SetBackgroundColour(BG)
        outer = wx.BoxSizer(wx.VERTICAL)
        title = wx.StaticText(panel, label='COD5  汉化构建')
        title.SetFont(self.GetFont().Larger().Larger().Bold()); title.SetForegroundColour(INK)
        outer.Add(title, 0, wx.LEFT | wx.TOP, 22)
        intro = wx.StaticText(panel, label='选字体、调字幕，构建完整游戏镜像。')
        intro.SetForegroundColour(MUTED)
        outer.Add(intro, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 12)

        self.book = wx.Notebook(panel)
        self.settings_panel = wx.lib.scrolledpanel.ScrolledPanel(self.book)
        self.settings_panel.SetBackgroundColour(wx.WHITE)
        self.book.AddPage(self.settings_panel, '字体与字幕')
        self.make_settings()
        log_panel = wx.Panel(self.book)
        log_sizer = wx.BoxSizer(wx.VERTICAL)
        log_sizer.Add(wx.StaticText(log_panel, label='构建期间会持续显示进度，完成后可直接打开输出目录。'),
                      0, wx.ALL, 12)
        self.log = wx.TextCtrl(log_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.TE_RICH2)
        self.log.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.log.SetBackgroundColour('#182231'); self.log.SetForegroundColour('#E6EDF5')
        log_sizer.Add(self.log, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        log_panel.SetSizer(log_sizer)
        self.book.AddPage(log_panel, '构建日志')
        outer.Add(self.book, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 18)

        self.status = wx.StaticText(panel, label='就绪')
        self.status.SetForegroundColour(MUTED)
        outer.Add(self.status, 0, wx.EXPAND | wx.ALL, 10)
        self.progress = wx.Gauge(panel, range=100, style=wx.GA_HORIZONTAL)
        outer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 18)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.save_button = wx.Button(panel, label='保存设置')
        self.save_button.Bind(wx.EVT_BUTTON, self.on_save)
        buttons.Add(self.save_button, 0, wx.RIGHT, 8)
        for label, handler in (('打开输出目录', lambda e: self.open_path(ROOT)),
                               ('打开日志', lambda e: self.open_path(GUI_LOG if GUI_LOG.exists() else LOG_PATH))):
            button = wx.Button(panel, label=label); button.Bind(wx.EVT_BUTTON, handler)
            buttons.Add(button, 0, wx.RIGHT, 8)
        buttons.AddStretchSpacer()
        self.build_button = wx.Button(panel, label='保存并构建 ISO', size=(190, 38))
        self.build_button.SetFont(self.GetFont().Bold())
        self.build_button.Bind(wx.EVT_BUTTON, self.on_build)
        buttons.Add(self.build_button, 0)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        output = wx.StaticText(panel, label=f'输出：{ISO_PATH}')
        output.SetForegroundColour(MUTED)
        outer.Add(output, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        panel.SetSizer(outer)
        self.load_controls(load_settings())
        self.loading = False
        self.update_preview()
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer); self.timer.Start(100)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Centre()

    def make_settings(self):
        parent = self.settings_panel
        layout = wx.BoxSizer(wx.VERTICAL)
        fonts_box = wx.StaticBoxSizer(wx.VERTICAL, parent, '源字体（TTF / OTF）')
        grid = wx.FlexGridSizer(cols=3, vgap=6, hgap=10); grid.AddGrowableCol(1)
        self.font_fields = {}
        for key, label in [*zip(FONT_NAMES, FONT_LABELS), ('fallback_font', '备用字体 · 缺字时使用')]:
            grid.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            field = wx.TextCtrl(parent)
            field.SetToolTip('可以直接填写路径，或点击“选择…”导入字体。')
            field.Bind(wx.EVT_TEXT, self.on_change)
            self.font_fields[key] = field
            grid.Add(field, 1, wx.EXPAND)
            button = wx.Button(parent, label='选择…')
            button.Bind(wx.EVT_BUTTON, lambda event, name=key: self.choose_font(name))
            grid.Add(button, 0)
        fonts_box.Add(grid, 0, wx.EXPAND | wx.ALL, 8)
        hint = wx.StaticText(parent, label='外部字体保存时自动复制到 FONT/source；每次构建都重新读取并重绘。')
        hint.SetForegroundColour(MUTED)
        fonts_box.Add(hint, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        weights = wx.BoxSizer(wx.HORIZONTAL)
        self.weights = {}
        for name, label in ((FONT_NAMES[1], '小字仿粗体'), (FONT_NAMES[2], '字幕仿粗体')):
            weights.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
            control = wx.SpinCtrlDouble(parent, min=0, max=1, inc=0.25, size=(95, -1))
            control.SetDigits(2)
            control.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_change)
            control.Bind(wx.EVT_TEXT, self.on_change)
            self.weights[name] = control
            weights.Add(control, 0, wx.RIGHT, 20)
        weights.Add(wx.StaticText(parent, label='0 = 原字重，步进 0.25 px'), 0, wx.ALIGN_CENTER_VERTICAL)
        fonts_box.Add(weights, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        layout.Add(fonts_box, 0, wx.EXPAND | wx.ALL, 10)

        style_box = wx.StaticBoxSizer(wx.VERTICAL, parent, '字幕样式')
        controls = wx.BoxSizer(wx.HORIZONTAL)
        controls.Add(wx.StaticText(parent, label='颜色'), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.color_picker = wx.ColourPickerCtrl(parent, colour='#CCFFFF', size=(55, -1))
        self.color_picker.Bind(wx.EVT_COLOURPICKER_CHANGED, self.on_color)
        controls.Add(self.color_picker, 0, wx.RIGHT, 8)
        self.color_hex = wx.TextCtrl(parent, value='#CCFFFF', size=(110, -1))
        self.color_hex.Bind(wx.EVT_TEXT, self.on_hex)
        controls.Add(self.color_hex, 0, wx.RIGHT, 24)
        controls.Add(wx.StaticText(parent, label='大小'), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.scale = wx.SpinCtrlDouble(parent, min=50, max=200, inc=2.5, size=(95, -1))
        self.scale.SetDigits(1)
        self.scale.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_change); self.scale.Bind(wx.EVT_TEXT, self.on_change)
        controls.Add(self.scale, 0, wx.RIGHT, 8)
        controls.Add(wx.StaticText(parent, label='%（100 = 游戏原生比例）'), 0, wx.ALIGN_CENTER_VERTICAL)
        style_box.Add(controls, 0, wx.EXPAND | wx.ALL, 8)
        self.subtitle_shadow = wx.CheckBox(parent, label='字幕阴影（黑色，向右下轻微偏移）')
        self.subtitle_shadow.Bind(wx.EVT_CHECKBOX, self.on_change)
        style_box.Add(self.subtitle_shadow, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        example = wx.BoxSizer(wx.HORIZONTAL)
        example.Add(wx.StaticText(parent, label='预览文字'), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.sample = wx.TextCtrl(parent, value='散开，小心埋伏。米勒，你打头阵！')
        self.sample.Bind(wx.EVT_TEXT, lambda event: self.schedule_preview())
        example.Add(self.sample, 1, wx.EXPAND)
        style_box.Add(example, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.preview = Preview(parent)
        style_box.Add(self.preview, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        self.preview_hint = wx.StaticText(parent,
            label='预览放大显示字形与笔画；实际字距、换行和画面效果以游戏为准。')
        self.preview_hint.SetForegroundColour(MUTED)
        style_box.Add(self.preview_hint, 0, wx.EXPAND | wx.ALL, 8)
        layout.Add(style_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.hardware_frame_safe = wx.CheckBox(parent, label='启用实机闪烁修复')
        self.hardware_frame_safe.Bind(wx.EVT_CHECKBOX, self.on_change)
        layout.Add(self.hardware_frame_safe, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 14)
        hardware_hint = wx.StaticText(parent,
            label='默认开启。保存后，GUI 和“一键构建ISO.bat”均使用此设置。')
        hardware_hint.SetForegroundColour(MUTED)
        layout.Add(hardware_hint, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 14)
        reuse = wx.BoxSizer(wx.HORIZONTAL)
        self.reviewed = wx.CheckBox(parent, label='仅同步已校对的通用 / 剧情译文')
        self.reviewed.Bind(wx.EVT_CHECKBOX, self.on_change)
        reuse.Add(self.reviewed, 0, wx.ALIGN_CENTER_VERTICAL)
        reuse.AddStretchSpacer()
        defaults = wx.Button(parent, label='恢复默认参数')
        defaults.Bind(wx.EVT_BUTTON, self.on_defaults)
        reuse.Add(defaults, 0)
        layout.Add(reuse, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 14)
        hint = wx.StaticText(parent, label='默认同步全部已保存译文。完成网页校对后，先保存译文，再构建 ISO。')
        hint.SetForegroundColour(MUTED)
        layout.Add(hint, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 14)
        parent.SetSizer(layout); parent.SetupScrolling(scroll_x=False)

    def load_controls(self, settings):
        self.loading = True
        for name in FONT_NAMES: self.font_fields[name].ChangeValue(settings['fonts'][name])
        self.font_fields['fallback_font'].ChangeValue(settings['fallback_font'])
        for name, field in self.weights.items(): field.SetValue(settings['synthetic_bold_px'][name])
        self.color_hex.ChangeValue(settings['subtitles']['color'])
        self.color_picker.SetColour(settings['subtitles']['color'])
        self.scale.SetValue(settings['subtitles']['scale_percent'])
        self.subtitle_shadow.SetValue(settings['subtitles']['shadow'])
        self.reviewed.SetValue(settings['build']['reviewed_only'])
        self.hardware_frame_safe.SetValue(settings['build']['hardware_frame_safe'])
        self.loading = False

    def read_controls(self):
        value = copy.deepcopy(DEFAULTS)
        value['fonts'] = {name: self.font_fields[name].GetValue().strip() for name in FONT_NAMES}
        value['fallback_font'] = self.font_fields['fallback_font'].GetValue().strip()
        value['synthetic_bold_px'] = {name: field.GetValue() for name, field in self.weights.items()}
        value['subtitles'] = dict(color=self.color_hex.GetValue().strip(), scale_percent=self.scale.GetValue(),
                                  shadow=self.subtitle_shadow.GetValue())
        value['build']['reviewed_only'] = self.reviewed.GetValue()
        value['build']['hardware_frame_safe'] = self.hardware_frame_safe.GetValue()
        return value

    def choose_font(self, key):
        current = local_path(self.font_fields[key].GetValue())
        with wx.FileDialog(self, '选择源字体', defaultDir=str(current.parent),
                           wildcard='字体文件 (*.ttf;*.otf)|*.ttf;*.otf',
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.font_fields[key].SetValue(dialog.GetPath())

    def on_color(self, event):
        self.color_hex.ChangeValue(self.color_picker.GetColour().GetAsString(wx.C2S_HTML_SYNTAX))
        self.on_change(event)

    def on_hex(self, event):
        color = self.color_hex.GetValue().strip()
        if re.fullmatch(r'#[0-9a-fA-F]{6}', color): self.color_picker.SetColour(color)
        self.on_change(event)

    def on_change(self, event=None):
        if self.loading: return
        self.dirty = True
        self.status.SetForegroundColour(MUTED)
        self.status.SetLabel('参数已修改，尚未保存。')
        self.schedule_preview()

    def schedule_preview(self):
        if self.loading: return
        if self.preview_pending: self.preview_pending.Stop()
        self.preview_pending = wx.CallLater(300, self.update_preview)

    def update_preview(self):
        try:
            value = self.read_controls()
            # Preview accepts external paths before import; validate the other settings normally.
            check = copy.deepcopy(value)
            check['fonts'] = DEFAULTS['fonts']; check['fallback_font'] = DEFAULTS['fallback_font']
            normalize(check)
            missing = self.preview.update(value, self.sample.GetValue())
            self.preview_hint.SetLabel('预览文字缺字：' + ''.join(sorted(missing)) if missing else
                '预览放大显示字形与笔画；实际字距、换行和画面效果以游戏为准。')
        except Exception as error:
            self.preview.error = '预览暂不可用：' + str(error)
            self.preview.Refresh()

    def on_defaults(self, event):
        self.load_controls(copy.deepcopy(DEFAULTS))
        self.on_change()

    def persist(self):
        ensure_build_idle()
        value = self.read_controls()
        # Reject invalid colors/weights before importing any files.
        check = copy.deepcopy(value)
        check['fonts'] = DEFAULTS['fonts']; check['fallback_font'] = DEFAULTS['fallback_font']
        normalize(check)
        value['fonts'] = {name: import_font(path) for name, path in value['fonts'].items()}
        value['fallback_font'] = import_font(value['fallback_font'])
        ensure_build_idle()
        value = save_settings(value)
        self.load_controls(value)
        self.dirty = False
        return value

    def on_save(self, event=None):
        if self.building: return
        try:
            self.persist()
            self.status.SetLabel('已保存。原有“一键构建ISO.bat”也会使用这些设置。')
        except Exception as error:
            wx.MessageBox(str(error), '设置未保存', wx.OK | wx.ICON_ERROR, self)

    def on_build(self, event=None):
        if self.building: return
        try:
            self.persist()
        except Exception as error:
            wx.MessageBox(str(error), '无法开始构建', wx.OK | wx.ICON_ERROR, self)
            return
        self.building = True; self.started = time.monotonic()
        self.output_unavailable = False
        self.settings_panel.Disable(); self.save_button.Disable(); self.build_button.Disable()
        self.log.Clear(); self.book.SetSelection(1)
        self.stage = '启动构建'
        self.status.SetForegroundColour(MUTED)
        self.status.SetLabel('正在启动完整构建…')
        self.worker = threading.Thread(target=self.build_worker, daemon=False)
        self.worker.start()

    def build_worker(self):
        exit_code = -1
        try:
            python = Path(sys.executable)
            if python.name.lower() == 'pythonw.exe': python = python.with_name('python.exe')
            env = os.environ.copy()
            env.update(PYTHONUTF8='1', PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1')
            GUI_LOG.parent.mkdir(parents=True, exist_ok=True)
            with GUI_LOG.open('w', encoding='utf-8', buffering=1) as log:
                command = ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
                           '-ExecutionPolicy', 'Bypass', '-File',
                           str(ROOT / 'scripts/build_chinese_test.ps1'), '-Python', str(python)]
                self.process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, encoding='utf-8', errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW)
                for line in self.process.stdout:
                    log.write(line); self.events.put(('log', line))
                self.process.stdout.close()
                exit_code = self.process.wait()
        except Exception as error:
            self.events.put(('log', f'\n构建启动或日志读取失败：{error}\n'))
            if self.process is not None and self.process.poll() is None:
                self.process.wait()
        finally:
            self.events.put(('done', exit_code))

    def on_timer(self, event):
        lines, done = [], None
        for _ in range(500):
            try: kind, value = self.events.get_nowait()
            except queue.Empty: break
            if kind == 'log':
                lines.append(value)
                if 'ISO_OUTPUT_UNAVAILABLE:' in value: self.output_unavailable = True
                for marker, label in (('[1/3]', '1/3 同步译文、重建字库与字幕'),
                                      ('[2/3]', '2/3 打包 ISO'), ('[3/3]', '3/3 回读构建结果')):
                    if marker in value: self.stage = label
            else: done = value
        if lines: self.log.AppendText(''.join(lines))
        if self.building:
            self.progress.Pulse()
            elapsed = int(time.monotonic() - self.started)
            self.status.SetLabel(f'{self.stage}　·　已用 {elapsed // 60:02d}:{elapsed % 60:02d}')
        if done is not None: self.finish_build(done)

    def finish_build(self, exit_code):
        self.building = False
        self.settings_panel.Enable(); self.save_button.Enable(); self.build_button.Enable()
        self.progress.SetValue(100 if exit_code == 0 else 0)
        if exit_code == 0:
            self.status.SetForegroundColour('#16713B')
            self.status.SetLabel('构建成功：COD5_TEST.iso 已更新。')
            self.log.AppendText('\n构建成功，可在输出目录中使用 COD5_TEST.iso。\n')
            self.show_build_summary()
        else:
            self.status.SetForegroundColour('#B42318')
            self.status.SetLabel('镜像无法写入：请先结束正在运行的游戏，释放 COD5_TEST.iso 后重试。'
                                 if self.output_unavailable else f'构建失败（退出码 {exit_code}），请查看上方日志。')
            self.log.AppendText('\n本次构建未完成；现有或部分写入的 ISO 不能作为本次成功产物。\n')

    def show_build_summary(self):
        try:
            report = json.loads((ROOT / 'SOUND/research/dynamic_font_cache/installed_build.json').read_text(encoding='utf-8'))
            enabled = report['hardware_frame']['enabled']
            self.log.AppendText('实机闪烁修复：' + ('已启用' if enabled else '未启用') + '（已回读 ISO 验证）。\n')
            shadow = report['subtitle_style']['shadow']['enabled']
            self.log.AppendText('字幕阴影：' + ('已启用原生深色阴影' if shadow else '未启用') + '（已回读 ISO 验证）。\n')
            for item in report['source_font_reports']:
                codes = item.get('unavailable_special_codes_preserved', [])
                if codes:
                    self.log.AppendText(item['font'] + '：源字体缺少特殊字符 ' +
                        ', '.join(f'U+{c:04X}' for c in codes) + '，已保留原特殊字形。\n')
        except (OSError, ValueError, KeyError) as error:
            self.log.AppendText(f'构建报告摘要读取失败：{error}\n')

    def open_path(self, path):
        try: os.startfile(str(path))
        except OSError as error: wx.MessageBox(str(error), '无法打开', wx.OK | wx.ICON_ERROR, self)

    def on_close(self, event):
        if self.building and event.CanVeto():
            self.status.SetLabel('构建仍在进行，请完成后关闭窗口。')
            event.Veto(); return
        if self.dirty and event.CanVeto():
            result = wx.MessageBox('参数尚未保存，是否保存后退出？', '未保存的设置',
                                   wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION, self)
            if result == wx.CANCEL: event.Veto(); return
            if result == wx.YES:
                try: self.persist()
                except Exception as error:
                    wx.MessageBox(str(error), '设置未保存', wx.OK | wx.ICON_ERROR, self)
                    event.Veto(); return
        self.timer.Stop()
        if self.preview_pending: self.preview_pending.Stop()
        event.Skip()


def main():
    app = wx.App(False)
    app.SetAppName('COD5BuildGUI')
    # Prevent two GUI windows from racing to save settings or append the same log.
    instance = wx.SingleInstanceChecker('PS2CODWAW-BuildGUI-' + wx.GetUserId())
    if instance.IsAnotherRunning():
        wx.MessageBox('构建工具已经打开，请使用已有窗口。', 'COD5 汉化构建', wx.OK)
        return
    try:
        frame = BuildFrame()
    except Exception as error:
        wx.MessageBox(f'无法打开构建工具：\n{error}\n\n配置文件：{SETTINGS_PATH}',
                      '启动失败', wx.OK | wx.ICON_ERROR)
        raise
    frame.Show(); app.MainLoop()


if __name__ == '__main__':
    main()
