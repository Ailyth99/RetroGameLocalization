$ErrorActionPreference = 'Stop'
$projectPath = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
$backupRoot = [IO.Path]::GetFullPath((Join-Path $projectPath 'SOURCE/backups')).TrimEnd('\')

# Fixed obsolete snapshots only. Keep the original ISO, current test ISO,
# ISO_UNPACK, all translations/audio, and the baselines used by the build.
# The three small pre-logo-fix scripts remain available for source rollback.
$relativeTargets = @(
    'l1_logo_subtitles_20261008_115815/ISO_UNPACK',
    'l1_logo_subtitles_20261008_115815/COD5_TEST.iso',
    'l1_logo_subtitles_20261008_115815/SOUND',
    'l1_logo_subtitles_20261008_115815/TEMP',
    'l1_logo_subtitles_20261008_115815/backup_items.json',
    'performance_rework_20261007_100747',
    'training_zh_test_20261004',
    'large_menu_font_20261004',
    'large_texts_zh',
    'options_menu_zh_20261004',
    'subtitle_style'
)
$targets = foreach ($relative in $relativeTargets) {
    $candidate = [IO.Path]::GetFullPath((Join-Path $backupRoot $relative))
    if (-not $candidate.StartsWith($backupRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unexpected backup target: $candidate"
    }
    if (-not (Test-Path -LiteralPath $candidate)) { continue }
    $resolved = (Resolve-Path -LiteralPath $candidate).ProviderPath
    if ($resolved -ne $candidate -or -not $resolved.StartsWith($projectPath + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unexpected resolved path: $resolved"
    }
    $item = Get-Item -LiteralPath $resolved -Force
    $members = if ($item.PSIsContainer) { @(Get-ChildItem -LiteralPath $resolved -Recurse -Force) } else { @() }
    if (@(@($item) + $members | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw "Refusing backup containing links: $resolved"
    }
    $files = if ($item.PSIsContainer) { @($members | Where-Object { -not $_.PSIsContainer }) } else { @($item) }
    [PSCustomObject]@{Path=$resolved; Bytes=[long](($files | Measure-Object Length -Sum).Sum)}
}

[long]$freed = 0
foreach ($target in $targets) {
    Write-Host ('Removing obsolete backup: ' + $target.Path)
    Remove-Item -LiteralPath $target.Path -Recurse -Force -ErrorAction Stop
    $freed += $target.Bytes
}
Write-Host ('Finished. Freed {0:N2} GiB ({1:N0} bytes).' -f ($freed / 1GB), $freed)
Write-Host 'Kept original/current ISO, ISO_UNPACK, translations, audio, required build baselines and the three small rollback scripts.'
