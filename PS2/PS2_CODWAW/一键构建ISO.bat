@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
echo Save your translation edits in the review page before building.
echo Output: %~dp0COD5_TEST.iso
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_chinese_test.ps1" %*
set "buildExitCode=%ERRORLEVEL%"
echo.
if not "%buildExitCode%"=="0" (
    echo BUILD FAILED. See the error above and the log below.
) else (
    echo BUILD SUCCEEDED: %~dp0COD5_TEST.iso
)
echo Log: %~dp0TEMP\builds\one_click_build\latest.log
pause
exit /b %buildExitCode%
