param(
    [Parameter(Mandatory = $true)]
    [string]$NeuroSanPath,

    # Skip the post-install verification pass (registry validation, tool import).
    [switch]$SkipChecks,

    # Do not append empty AEP_* placeholders to the target checkout's .env.
    [switch]$SkipEnvSeed
)

$ErrorActionPreference = "Stop"
$packageRoot = Split-Path -Parent $PSScriptRoot
$target = (Resolve-Path -LiteralPath $NeuroSanPath).Path

# [IO.Path]::GetRelativePath is .NET Core only; this script has to run on the
# Windows PowerShell 5.1 that ships with Windows.
function Get-RelativeToTarget {
    param([string]$Path)
    $prefix = $target.TrimEnd('\') + '\'
    if ($Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        return $Path.Substring($prefix.Length)
    }
    return $Path
}

# Two registry layouts are supported:
#   * upstream neuro-san-studio, where networks are grouped in registries/<domain>/
#   * flat checkouts, where registries/manifest.hocon lists *.hocon siblings directly
$industryManifest = Join-Path $target "registries\industry\manifest.hocon"
$flatManifest = Join-Path $target "registries\manifest.hocon"

if (Test-Path -LiteralPath $industryManifest) {
    $manifest = $industryManifest
    $hoconDestDir = Join-Path $target "registries\industry"
    $manifestEntry = "industry/aep_batch_recovery.hocon"
    $networkName = "industry/aep_batch_recovery"
}
elseif (Test-Path -LiteralPath $flatManifest) {
    $manifest = $flatManifest
    $hoconDestDir = Join-Path $target "registries"
    $manifestEntry = "aep_batch_recovery.hocon"
    $networkName = "aep_batch_recovery"
}
else {
    throw "Target is not a Neuro SAN checkout (no registries\manifest.hocon or registries\industry\manifest.hocon): $target"
}

# Some checkouts rename the tool package to agent_tools because site-packages
# ships a top-level coded_tools package that would shadow a local one.
$toolRoot = if (Test-Path -LiteralPath (Join-Path $target "agent_tools")) { "agent_tools" } else { "coded_tools" }
$toolDest = Join-Path $target "$toolRoot\aep_batch_recovery"

New-Item -ItemType Directory -Path $toolDest -Force | Out-Null

# An earlier install (or an install script that assumed the upstream name) may have
# left a copy under coded_tools. Leaving it there is confusing at best and shadowed
# by site-packages at worst, so clear it out when agent_tools is the real location.
$staleToolDir = Join-Path $target "coded_tools\aep_batch_recovery"
if ($toolRoot -eq "agent_tools" -and (Test-Path -LiteralPath $staleToolDir)) {
    Remove-Item -LiteralPath $staleToolDir -Recurse -Force
    Write-Host "Removed stale copy at coded_tools\aep_batch_recovery"
    $codedToolsRoot = Join-Path $target "coded_tools"
    if (-not (Get-ChildItem -LiteralPath $codedToolsRoot -Force)) {
        Remove-Item -LiteralPath $codedToolsRoot -Force
    }
}

Get-ChildItem -LiteralPath (Join-Path $packageRoot "coded_tools\aep_batch_recovery") -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $toolDest -Recurse -Force
}

New-Item -ItemType Directory -Path (Join-Path $target "aep_batch_recovery") -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $packageRoot "aep_batch_recovery") -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName `
        -Destination (Join-Path $target "aep_batch_recovery") -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $packageRoot "README.md") `
    -Destination (Join-Path $target "aep_batch_recovery\README.md") -Force

$hoconDest = Join-Path $hoconDestDir "aep_batch_recovery.hocon"
Copy-Item -LiteralPath (Join-Path $packageRoot "registries\industry\aep_batch_recovery.hocon") `
    -Destination $hoconDest -Force

# The network reuses the shared expertise-scoping prompt fragment when the target
# provides it. Checkouts without that file cannot resolve the include, so drop the
# include and its substitution instead of failing to load the network.
if (-not (Test-Path -LiteralPath (Join-Path $target "registries\expertise_scoping_instructions.hocon"))) {
    $hocon = Get-Content -LiteralPath $hoconDest -Raw
    $hocon = $hocon -replace '(?m)^[ \t]*include\s+"(?:[^"]*/)?expertise_scoping_instructions\.hocon",[ \t]*\r?\n', ''
    $hocon = $hocon -replace '\s*\$\{expertise_scoping_instructions\}', ''
    [IO.File]::WriteAllText($hoconDest, $hocon, [Text.UTF8Encoding]::new($false))
    Write-Warning "registries\expertise_scoping_instructions.hocon is absent in the target; installed the network without the shared expertise-scoping prompt fragment."
}

$text = Get-Content -LiteralPath $manifest -Raw
if ($text -notmatch [regex]::Escape("`"$manifestEntry`"")) {
    $first = [regex]::Match($text, '(?m)^([ \t]*)"[^"]+\.hocon"\s*:')
    if (-not $first.Success) { throw "Network entries were not found in $manifest" }
    $indent = $first.Groups[1].Value
    $text = $text.Insert($first.Index, "$indent`"$manifestEntry`": true,`r`n")
    [IO.File]::WriteAllText($manifest, $text, [Text.UTF8Encoding]::new($false))
}

Write-Host ""
Write-Host "AEP Batch Recovery Agent installed into $target"
Write-Host "  network:    $networkName"
Write-Host "  registry:   $(Get-RelativeToTarget $hoconDest)"
Write-Host "  coded tool: $toolRoot\aep_batch_recovery"
Write-Host "  manifest:   $(Get-RelativeToTarget $manifest)"

# --- Adobe credential placeholders -------------------------------------------
# The coded tool reads these from the environment at call time. A missing value
# is not a crash - the tool returns a clean error listing what is absent - but it
# is the most common reason the agent appears not to work after a clean install.
# Only the keys that are actually absent are appended, always with an empty
# value: this script never writes a credential and never edits an existing line.
$envFile = Join-Path $target ".env"
$requiredEnv = @("AEP_ACCESS_TOKEN", "AEP_API_KEY", "AEP_ORG_ID", "AEP_SANDBOX_NAME")
$envText = if (Test-Path -LiteralPath $envFile) { Get-Content -LiteralPath $envFile -Raw } else { "" }
if ($null -eq $envText) { $envText = "" }

# A key already present with a value needs nothing. A key present but empty is
# still a placeholder the user has to fill, so do not duplicate it either.
$missingEnv = @($requiredEnv | Where-Object { $envText -notmatch "(?m)^\s*$_\s*=" })
$unsetEnv = @($requiredEnv | Where-Object {
    -not ($envText -match "(?m)^\s*$_\s*=\s*\S") -and -not [Environment]::GetEnvironmentVariable($_)
})

if ($missingEnv -and -not $SkipEnvSeed) {
    $block = New-Object Text.StringBuilder
    if ($envText -and -not $envText.EndsWith("`n")) { [void]$block.Append("`r`n") }
    [void]$block.Append("`r`n# Adobe Experience Platform credentials for the AEP Batch Recovery Agent.`r`n")
    [void]$block.Append("# Added by install_into_neuro_san.ps1. Fill these in; never commit real values.`r`n")
    foreach ($name in $missingEnv) { [void]$block.Append("$name=`r`n") }

    [IO.File]::AppendAllText($envFile, $block.ToString(), [Text.UTF8Encoding]::new($false))
    Write-Host ""
    if ($envText) {
        Write-Host "Appended $($missingEnv.Count) empty placeholder(s) to $(Get-RelativeToTarget $envFile): $($missingEnv -join ', ')"
    }
    else {
        Write-Host "Created $(Get-RelativeToTarget $envFile) with empty placeholders: $($missingEnv -join ', ')"
    }

    # Seeding a .env is only safe if the host will not commit it.
    $hostIgnore = Join-Path $target ".gitignore"
    $ignoresEnv = (Test-Path -LiteralPath $hostIgnore) -and
        ((Get-Content -LiteralPath $hostIgnore) -match '^\s*\.env\s*$')
    if ((Test-Path -LiteralPath (Join-Path $target ".git")) -and -not $ignoresEnv) {
        Write-Warning "$(Get-RelativeToTarget $envFile) does not appear to be git-ignored in this checkout. Add '.env' to .gitignore before putting real credentials in it."
    }
}

# --- Post-install verification -----------------------------------------------
# Everything below only reports; the install itself is already complete.
if ($SkipChecks) { return }

$python = @(
    (Join-Path $target "venv\Scripts\python.exe"),
    (Join-Path $target ".venv\Scripts\python.exe")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $python) {
    Write-Warning "No venv found under $target; skipping verification. Activate the environment and run 'python validate_registries.py' yourself."
    return
}

$problems = @()

# 1. The network must parse the way the server parses it: as a string, with the
#    repo root as the include basedir. This is what catches unresolved
#    substitutions from includes that did not resolve.
Write-Host ""
Write-Host "Checking the network parses the way Neuro SAN loads it..."
$parseScript = @'
import json, logging, sys
# The network lists include paths for more than one parse mode, so the paths that
# do not apply warn here. That is expected; keep the output clean.
logging.getLogger("pyhocon").setLevel(logging.ERROR)
logging.getLogger("pyhocon.config_parser").setLevel(logging.ERROR)
from pyhocon import ConfigFactory
path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    cfg = json.loads(json.dumps(ConfigFactory.parse_string(handle.read())))
print("tools: " + ", ".join(t["name"] for t in cfg["tools"]))
print("model: " + str(cfg.get("llm_config", {}).get("model_name", "<none>")))
'@
$parseFile = Join-Path ([IO.Path]::GetTempPath()) "aep_parse_check.py"
[IO.File]::WriteAllText($parseFile, $parseScript, [Text.UTF8Encoding]::new($false))
Push-Location $target
try {
    # Do not redirect stderr from a native exe here: Windows PowerShell 5.1 wraps
    # each stderr line in an ErrorRecord and reports failure even on exit code 0.
    # pyhocon warns on stderr for every include that does not resolve, which is
    # expected - the network lists include paths for more than one parse mode.
    $parseOut = & $python $parseFile $hoconDest
    if ($LASTEXITCODE -ne 0) {
        $problems += "the network did not parse: $($parseOut | Select-Object -Last 1)"
    }
    else {
        $parseOut | ForEach-Object { Write-Host "  $_" }
    }

    # 2. The coded tool must import from the tool path the server will use.
    Write-Host "Checking the coded tool imports..."
    $importOut = & $python -c "import sys; sys.path.insert(0, sys.argv[1]); from aep_batch_recovery.adobe_failed_batch import AdobeFailedBatch; print('  ' + AdobeFailedBatch.__name__ + ' -> ' + AdobeFailedBatch.__mro__[1].__name__)" (Join-Path $target $toolRoot)
    if ($LASTEXITCODE -ne 0) {
        $problems += "the coded tool did not import: $($importOut | Select-Object -Last 1)"
    }
    else {
        $importOut | ForEach-Object { Write-Host "$_" }
    }

    # 3. Some checkouts gate startup on their own registry validator. Run it here
    #    so a failure surfaces now rather than as an aborted launch.
    $validator = Join-Path $target "validate_registries.py"
    if (Test-Path -LiteralPath $validator) {
        Write-Host "Running the checkout's registry validator..."
        $validatorOut = & $python $validator
        if ($LASTEXITCODE -ne 0) {
            $validatorOut | Select-Object -Last 5 | ForEach-Object { Write-Host "  $_" }
            $problems += "validate_registries.py failed; this checkout may refuse to launch"
        }
        else {
            Write-Host "  all registries valid"
        }
    }
}
finally {
    Pop-Location
    Remove-Item -LiteralPath $parseFile -Force -ErrorAction SilentlyContinue
}

Write-Host ""
if ($problems) {
    Write-Warning "Installed, but verification found problems:"
    $problems | ForEach-Object { Write-Warning "  - $_" }
}
else {
    Write-Host "Verification passed."
}

# The placeholders were written above; these still have no value to use.
if ($unsetEnv) {
    Write-Host ""
    Write-Host "Fill in these values in $(Get-RelativeToTarget $envFile) before using the agent:"
    $unsetEnv | ForEach-Object { Write-Host "  $_=" }
}

Write-Host ""
Write-Host "Start Neuro SAN, then select '$networkName' in the UI."
Write-Host "Standalone app (optional): python -m aep_batch_recovery.frontend_server"
