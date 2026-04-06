@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "SRC_DIR=ALL"
set "DEST_DIR=ALL_UNPACK"
set "TOOL=pak_unpacker.exe"

if not exist "%TOOL%" (
    echo [ERROR] Tool not found: %TOOL%
    pause
    exit /b
)

if not exist "%SRC_DIR%" (
    echo [ERROR] Source folder "%SRC_DIR%" not found.
    pause
    exit /b
)

if not exist "%DEST_DIR%" (
    mkdir "%DEST_DIR%"
)

echo ========================================================
echo Processing ALL files (Unpacking + Decompressing)
echo ========================================================


for /r "%SRC_DIR%" %%F in (*.pak) do (
    echo [Processing] %%~nxF ...
    
    "%TOOL%" "%%F" "%DEST_DIR%"
)

echo.
echo ========================================================
echo All Finished! Check %DEST_DIR%
echo ========================================================
pause