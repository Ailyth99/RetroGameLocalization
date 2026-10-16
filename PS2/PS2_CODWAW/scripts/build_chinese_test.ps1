param([switch]$ReviewedOnly, [string]$Python = 'python',
    [switch]$HardwareFreezeGlyphs, [switch]$HardwareNativeSync, [switch]$HardwareSelectiveTextures,
    [switch]$HardwareFrameSafe, [switch]$NoHardwareFrameSafe)

$ErrorActionPreference = 'Stop'
if (([int][bool]$HardwareFreezeGlyphs + [int][bool]$HardwareNativeSync + [int][bool]$HardwareSelectiveTextures + [int][bool]$HardwareFrameSafe + [int][bool]$NoHardwareFrameSafe) -gt 1) {
    throw 'The hardware mode switches are mutually exclusive. Select one mode.'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUNBUFFERED = '1'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$logDirectory = Join-Path $projectRoot 'TEMP/builds/one_click_build'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$logPath = Join-Path $logDirectory 'latest.log'
# A double click on the launcher must not start overlapping builds.
try {
    $buildLock = [System.IO.File]::Open((Join-Path $logDirectory 'build.lock'),
        [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None)
} catch { throw 'Another build is running. Wait for its window to finish.' }
$transcriptStarted = $false
try {
    Start-Transcript -Path $logPath -Force | Out-Null
    $transcriptStarted = $true
    # Fail before font rendering when PCSX2 still holds the fixed output ISO.
    $isoPath = Join-Path $projectRoot 'COD5_TEST.iso'
    if (Test-Path -LiteralPath $isoPath) {
        try {
            $isoProbe = [System.IO.File]::Open($isoPath, [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::ReadWrite)
            $isoProbe.Dispose()
        } catch {
            throw 'ISO_OUTPUT_UNAVAILABLE: Cannot write COD5_TEST.iso. End the running game and release the ISO, or check file permissions.'
        }
    }
    Write-Host '[1/3] Merge saved translations; rebuild all subtitles, menus and dynamic fonts.'
    $buildArguments = @('-B', '-X', 'utf8', (Join-Path $PSScriptRoot 'build_dynamic_fonts.py'), '--install')
    if ($ReviewedOnly) { $buildArguments += '--reviewed-only' }
    if ($HardwareFreezeGlyphs) {
        Write-Host 'HARDWARE DIAGNOSTIC: glyph-cache updates freeze in levels. Question marks are expected.' -ForegroundColor Yellow
        $buildArguments += '--hardware-freeze-glyphs'
    }
    if ($HardwareNativeSync) {
        Write-Host 'HARDWARE SYNC TEST: full Chinese text; native DMA waits without the extra GS FINISH handshake.' -ForegroundColor Yellow
        $buildArguments += '--hardware-native-sync'
    }
    if ($HardwareSelectiveTextures) {
        Write-Host 'HARDWARE TEXTURE TEST: full Chinese text; original DMA/GS sync; invalidate modified font textures only.' -ForegroundColor Yellow
        $buildArguments += '--hardware-selective-textures'
    }
    if ($HardwareFrameSafe) {
        $buildArguments += '--hardware-frame-safe'
    }
    if ($NoHardwareFrameSafe) { $buildArguments += '--no-hardware-frame-safe' }
    & $Python @buildArguments
    if ($LASTEXITCODE -ne 0) { throw "Text/font build failed: $LASTEXITCODE" }

    Write-Host '[2/3] Build COD5_TEST.iso.'
    & (Join-Path $PSScriptRoot 'build_test_iso.ps1')

    Write-Host '[3/3] Read back packed text, subtitle and dynamic-font resources.'
    & $Python -B -X utf8 (Join-Path $PSScriptRoot 'verify_dynamic_iso.py')
    if ($LASTEXITCODE -ne 0) { throw "ISO readback failed: $LASTEXITCODE" }
    Write-Host ('BUILD SUCCEEDED: ' + (Join-Path $projectRoot 'COD5_TEST.iso'))
    if ($HardwareFreezeGlyphs) {
        Write-Host 'DIAGNOSTIC ISO ONLY. Compare whole-screen flashes at subtitle onset; placeholder text is intentional.' -ForegroundColor Yellow
    }
    if ($HardwareNativeSync) {
        Write-Host 'HARDWARE TEST ISO. Check full Chinese text and whole-screen flashes on PS2. Normal launcher uses the shared build settings.' -ForegroundColor Yellow
    }
    if ($HardwareSelectiveTextures) {
        Write-Host 'HARDWARE TEXTURE TEST ISO. Check subtitle flashes and normal scene/HUD rendering on PS2.' -ForegroundColor Yellow
    }
    $installedBuild = Get-Content -LiteralPath (Join-Path $projectRoot 'SOUND/research/dynamic_font_cache/installed_build.json') -Encoding UTF8 -Raw | ConvertFrom-Json
    Write-Host ('HARDWARE FLICKER FIX IN VERIFIED ISO: ' + [bool]$installedBuild.hardware_frame.enabled)
    Write-Host ('SUBTITLE SHADOW IN VERIFIED ISO: ' + [bool]$installedBuild.subtitle_style.shadow.enabled)
} catch {
    Write-Host ('BUILD FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'An existing or partially written COD5_TEST.iso is not a successful build.'
    throw
} finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
    $buildLock.Dispose()
}
