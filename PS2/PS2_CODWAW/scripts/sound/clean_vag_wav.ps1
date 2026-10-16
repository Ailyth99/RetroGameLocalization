$ErrorActionPreference = 'Stop'
$subtitleRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../SOUND/subtitles')).TrimEnd('\')
if (-not (Test-Path -LiteralPath $subtitleRoot -PathType Container)) {
    throw "Subtitle directory not found: $subtitleRoot"
}
$cleanupTargets = @()
foreach ($level in Get-ChildItem -LiteralPath $subtitleRoot -Directory) {
    if ($level.Name -notmatch '^L\d+_[A-Za-z0-9_-]+_am$') { continue }
    if ($level.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked level directory: $($level.FullName)" }
    foreach ($kind in @('vag', 'wav')) {
        $candidate = Join-Path $level.FullName $kind
        if (-not (Test-Path -LiteralPath $candidate)) { continue }
        $resolved = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $candidate).Path)
        $info = Get-Item -LiteralPath $resolved -Force
        if (-not $resolved.StartsWith($subtitleRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
            $info.Parent.Parent.FullName -ne $subtitleRoot -or $info.Name -notin @('vag', 'wav') -or
            -not $info.PSIsContainer -or ($info.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Unexpected cleanup path: $resolved"
        }
        $children = @(Get-ChildItem -LiteralPath $resolved -Force)
        foreach ($child in $children) {
            if ($child.PSIsContainer -or $child.Extension -ne ('.' + $kind) -or
                ($child.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Unexpected file; leaving all directories unchanged: $($child.FullName)"
            }
        }
        $cleanupTargets += $resolved
    }
}
if ($cleanupTargets.Count -eq 0) {
    Write-Host 'No exported VAG/WAV directories to clean. MP3 and JSON are kept.'
    exit 0
}
foreach ($target in $cleanupTargets) {
    Write-Host "Removing exported audio directory: $target"
    Remove-Item -LiteralPath $target -Recurse -ErrorAction Stop
}
Write-Host "Done. Removed $($cleanupTargets.Count) directories. MP3, JSON and AM files are kept."
