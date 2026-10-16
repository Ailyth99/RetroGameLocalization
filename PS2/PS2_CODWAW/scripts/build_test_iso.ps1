$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $projectRoot 'tools/mkps2iso.exe') -q -y -o (Join-Path $projectRoot 'COD5_TEST.iso') (Join-Path $projectRoot 'ISO_UNPACK')
if ($LASTEXITCODE -ne 0) { throw "MKPS2ISO failed: $LASTEXITCODE" }
