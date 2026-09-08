param(
    [Parameter(Mandatory = $true)]
    [string]$NeuroSanPath
)

$ErrorActionPreference = "Stop"
$packageRoot = Split-Path -Parent $PSScriptRoot
$target = (Resolve-Path -LiteralPath $NeuroSanPath).Path
$manifest = Join-Path $target "registries\industry\manifest.hocon"

if (-not (Test-Path -LiteralPath $manifest)) {
    throw "Target is not a Neuro SAN Studio checkout: $target"
}

New-Item -ItemType Directory -Path (Join-Path $target "coded_tools\aep_batch_recovery") -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $packageRoot "coded_tools\aep_batch_recovery") -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName `
        -Destination (Join-Path $target "coded_tools\aep_batch_recovery") -Recurse -Force
}

New-Item -ItemType Directory -Path (Join-Path $target "aep_batch_recovery") -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $packageRoot "aep_batch_recovery") -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName `
        -Destination (Join-Path $target "aep_batch_recovery") -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $packageRoot "README.md") `
    -Destination (Join-Path $target "aep_batch_recovery\README.md") -Force

Copy-Item -LiteralPath (Join-Path $packageRoot "registries\industry\aep_batch_recovery.hocon") `
    -Destination (Join-Path $target "registries\industry\aep_batch_recovery.hocon") -Force

$text = Get-Content -LiteralPath $manifest -Raw
if ($text -notmatch '"industry/aep_batch_recovery\.hocon"') {
    $first = [regex]::Match($text, '(?m)^\s*"industry/[^\r\n]+$')
    if (-not $first.Success) { throw "Industry entries were not found in $manifest" }
    $text = $text.Insert($first.Index, "    `"industry/aep_batch_recovery.hocon`": true,`r`n")
    [IO.File]::WriteAllText($manifest, $text, [Text.UTF8Encoding]::new($false))
}

Write-Host "AEP Batch Recovery Agent installed into $target"
Write-Host "Neuro SAN network: industry/aep_batch_recovery"
Write-Host "Custom frontend: python -m aep_batch_recovery.frontend_server"
