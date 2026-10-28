# Remove a manual (install.ps1) build-crew install. Plugin installs: use /plugin instead.
# Only removes files carrying the build-crew marker and build-crew's own hook entries.
# Run:  powershell -ExecutionPolicy Bypass -File .\build-crew\uninstall.ps1
[CmdletBinding()]
param(
  [string]$ClaudeDir = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.claude')
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

$Kit = $PSScriptRoot
$Claude = [IO.Path]::GetFullPath($ClaudeDir)
$Marker = '<!-- installed by build-crew -->'

foreach ($kind in 'agents', 'commands') {
  foreach ($src in Get-ChildItem -LiteralPath (Join-Path $Kit $kind) -Filter '*.md') {
    $dest = Join-Path (Join-Path $Claude $kind) $src.Name
    if ((Test-Path -LiteralPath $dest -PathType Leaf) -and [IO.File]::ReadAllText($dest).Contains($Marker)) {
      Remove-Item -LiteralPath $dest -Force
    }
  }
}

$Settings = Join-Path $Claude 'settings.json'
if (Test-Path -LiteralPath $Settings) {
  $py = $null
  foreach ($c in @(@('python3'), @('py', '-3'), @('python'))) {
    if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
    $rest = @($c | Select-Object -Skip 1)
    $ErrorActionPreference = 'Continue'
    try { & $c[0] @rest -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>$null } catch { }
    $ok = $LASTEXITCODE -eq 0
    $ErrorActionPreference = 'Stop'
    if ($ok) { $py = $c; break }
  }
  if (-not $py) { Write-Host 'Python 3.9+ is required to clean settings.json'; exit 1 }
  $pyRest = @($py | Select-Object -Skip 1)
  Copy-Item -LiteralPath $Settings -Destination "$Settings.build-crew-uninstall.bak" -Force
  $strip = @'
import json, os, sys
p = sys.argv[1]
with open(p, encoding="utf-8-sig") as f:
    s = json.load(f)
for event in ("PreToolUse", "SessionStart"):
    groups = []
    for g in s.get("hooks", {}).get(event, []):
        kept = [h for h in g.get("hooks", []) if "build-crew/hooks/" not in h.get("command", "").replace("\\", "/")]
        if kept:
            groups.append(dict(g, hooks=kept))
    if event in s.get("hooks", {}):
        s["hooks"][event] = groups
tmp = p + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(s, f, indent=2)
os.replace(tmp, p)
'@
  $script = Join-Path ([IO.Path]::GetTempPath()) "build-crew-uninstall-$PID.py"
  [IO.File]::WriteAllText($script, $strip, (New-Object Text.UTF8Encoding $false))
  try {
    $ErrorActionPreference = 'Continue'
    & $py[0] @pyRest $script $Settings
    $code = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = 'Stop'
    Remove-Item -LiteralPath $script -Force -ErrorAction SilentlyContinue
  }
  if ($code -ne 0) { exit 1 }
}
foreach ($d in 'gates', 'hooks') {
  $p = Join-Path (Join-Path $Claude 'build-crew') $d
  if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force }
}
Write-Host 'OK: build-crew removed. Deny rules were left in settings.json; a backup is at settings.json.build-crew-uninstall.bak'
