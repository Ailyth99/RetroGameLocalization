@echo off
setlocal
for %%I in ("%~dp0..") do set "projectRoot=%%~fI"
cd /d "%projectRoot%"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
python -B -X utf8 "%projectRoot%\scripts\sound\review_server.py" %*
if errorlevel 1 pause
