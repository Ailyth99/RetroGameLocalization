@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
python -B -X utf8 -c "import wx, PIL, fontTools" >nul 2>&1
if errorlevel 1 (
    echo Missing GUI dependencies. Install with:
    echo python -m pip install wxPython Pillow fonttools
    pause
    exit /b 1
)
python -B -X utf8 "%~dp0scripts\build_gui.py"
if errorlevel 1 pause
