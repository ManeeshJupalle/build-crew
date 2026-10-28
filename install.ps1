# build-crew manual install for Windows (alternative to the plugin install in README).
# Installs globally into ~/.claude so it works in every project. Same behaviour as install.sh:
#   - files it installs carry a "build-crew" marker; anything else with the same
#     name is backed up first, never silently overwritten
#   - settings.json: only build-crew's own hook entries are added/replaced, a
#     timestamped backup is kept, and an unreadable settings file aborts the install
# Run it from PowerShell 5.1+ (or pwsh 7):
#   powershell -ExecutionPolicy Bypass -File .\build-crew\install.ps1
# Keep this file ASCII: Windows PowerShell 5.1 misreads UTF-8 without a BOM.
[CmdletBinding()]
param(
  [string]$ClaudeDir = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.claude')
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

$Kit = $PSScriptRoot
$Claude = [IO.Path]::GetFullPath($ClaudeDir)
$Root = Join-Path $Claude 'build-crew'                 # gates + hooks live here
$Marker = '<!-- installed by build-crew -->'
$Bk = Join-Path $Root ('backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$OnWindows = [Environment]::OSVersion.Platform -eq 'Win32NT'
$Utf8 = New-Object Text.UTF8Encoding $false            # no BOM: a BOM breaks frontmatter

function Slash([string]$p) { $p -replace '\\', '/' }   # forward slashes work in Git Bash, cmd and Python

function Find-Python {  # first command that runs Python 3.9+; skips the Microsoft Store stub
  $ErrorActionPreference = 'Continue'
  foreach ($c in @(@('python3'), @('py', '-3'), @('python'))) {
    if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
    $rest = @($c | Select-Object -Skip 1)
    try {
      $out = & $c[0] @rest -c 'import sys; print(sys.version_info >= (3, 9))' 2>$null
      if ($LASTEXITCODE -eq 0 -and "$out".Trim() -eq 'True') { return , $c }
    } catch { }
  }
  return $null
}

function Find-Bash {  # Git Bash on Windows (Claude Code needs it anyway), never WSL's bash.exe
  $cands = @()
  if ($env:CLAUDE_CODE_GIT_BASH_PATH) { $cands += $env:CLAUDE_CODE_GIT_BASH_PATH }
  $git = Get-Command git -ErrorAction SilentlyContinue
  if ($git -and $git.Source) { $cands += Join-Path (Split-Path (Split-Path $git.Source)) 'bin/bash.exe' }
  if ($OnWindows) {
    $cands += Join-Path $env:ProgramFiles 'Git/bin/bash.exe'
  } else {
    $b = Get-Command bash -ErrorAction SilentlyContinue
    if ($b) { $cands += $b.Source }
  }
  foreach ($c in $cands) { if ($c -and (Test-Path -LiteralPath $c -PathType Leaf)) { return $c } }
  return $null
}

function Backup([string]$file) {  # move a file into this run's backup folder, keeping its relative path
  $rel = $file.Substring($Claude.Length).TrimStart('\', '/')
  $dest = Join-Path $Bk $rel
  New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
  Move-Item -LiteralPath $file -Destination $dest -Force
}

function Test-Contains([string]$file, [string]$text) {
  (Test-Path -LiteralPath $file -PathType Leaf) -and [IO.File]::ReadAllText($file).Contains($text)
}

$Py = Find-Python
if (-not $Py) { Write-Host 'Python 3.9+ is required (python3, py -3 or python on PATH)'; exit 1 }
$PyCmd = $Py -join ' '
$PyRest = @($Py | Select-Object -Skip 1)
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Write-Host 'WARNING: GitHub CLI not found: install it from https://cli.github.com before using /ship'
}
$Bash = Find-Bash
if (-not $Bash) { Write-Host 'WARNING: Git Bash not found: the session-start hook will be skipped' }

foreach ($d in 'agents', 'commands') { New-Item -ItemType Directory -Force -Path (Join-Path $Claude $d) | Out-Null }
New-Item -ItemType Directory -Force -Path $Root | Out-Null

# 1. Retire files from the pre-plugin kit, recognised by the report line only that kit wrote.
$retire = [ordered]@{
  'agents/spec-writer.md'   = 'SPEC_WRITER_RESULT'
  'agents/docs-keeper.md'   = 'DOCS_KEEPER_RESULT'
  'agents/pr-merger.md'     = 'PR_MERGER_RESULT'
  'agents/build-planner.md' = 'BUILD_PLANNER_RESULT'
  'commands/spec.md'        = 'spec-writer'
}
foreach ($rel in $retire.Keys) {
  $f = Join-Path $Claude $rel
  if ((Test-Contains $f $retire[$rel]) -and -not (Test-Contains $f $Marker)) { Backup $f }
}
foreach ($name in 'guard.py', 'session_start.sh') {
  $f = Join-Path (Join-Path $Claude 'hooks') $name
  if ((Test-Path -LiteralPath $f -PathType Leaf) -and ([IO.File]::ReadAllText($f) -match 'build-crew|pr-agents')) { Backup $f }
}

# 2. Gates and hooks (build-crew's own folder: replaced wholesale).
foreach ($d in 'gates', 'hooks') {
  $dest = Join-Path $Root $d
  if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
  Copy-Item -LiteralPath (Join-Path $Kit $d) -Destination $Root -Recurse
}
# Git for Windows may have checked scripts out with CRLF, which bash can't run.
foreach ($f in Get-ChildItem -LiteralPath (Join-Path $Root 'hooks') -Filter '*.sh') {
  [IO.File]::WriteAllText($f.FullName, ([IO.File]::ReadAllText($f.FullName) -replace "`r`n", "`n"), $Utf8)
}

# 3. Agents and commands: resolve the plugin path variable and namespace, add the marker.
$RootSlash = Slash $Root
$installed = @()
foreach ($kind in 'agents', 'commands') {
  foreach ($src in Get-ChildItem -LiteralPath (Join-Path $Kit $kind) -Filter '*.md' | Sort-Object Name) {
    $dest = Join-Path (Join-Path $Claude $kind) $src.Name
    if ((Test-Path -LiteralPath $dest -PathType Leaf) -and -not (Test-Contains $dest $Marker)) {
      Backup $dest   # includes files from the pre-plugin kit: harmless, and nothing is ever lost
      Write-Host "Backed up existing $kind/$($src.Name)"
    }
    $text = [IO.File]::ReadAllText($src.FullName)
    $text = $text.Replace('python3 "${CLAUDE_PLUGIN_ROOT}', $PyCmd + ' "${CLAUDE_PLUGIN_ROOT}')
    $text = $text.Replace('${CLAUDE_PLUGIN_ROOT}', $RootSlash)
    $text = $text -replace '`build-crew:([a-z-]*)`', '`$1`'
    [IO.File]::WriteAllText($dest, $text + "`n" + $Marker + "`n", $Utf8)
    $installed += "$kind/$($src.BaseName)"
  }
}

# 4. Settings: add/replace only build-crew hook entries; add deny rules.
$Settings = Join-Path $Claude 'settings.json'
if (Test-Path -LiteralPath $Settings) {
  New-Item -ItemType Directory -Force -Path $Bk | Out-Null
  Copy-Item -LiteralPath $Settings -Destination (Join-Path $Bk 'settings.json')
}
# Commands go through the environment: Windows PowerShell 5.1 mangles quotes in native arguments.
$env:BUILD_CREW_GUARD_CMD = "$PyCmd `"$RootSlash/hooks/guard.py`""
$env:BUILD_CREW_SESSION_CMD = if ($Bash) { "`"$(Slash $Bash)`" `"$RootSlash/hooks/session_start.sh`"" } else { '' }
$env:BUILD_CREW_CLAUDE = Slash $Claude
$merge = @'
import json, os, sys
path = sys.argv[1]
guard, session, claude = (os.environ.get(k, "") for k in ("BUILD_CREW_GUARD_CMD", "BUILD_CREW_SESSION_CMD", "BUILD_CREW_CLAUDE"))
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8-sig") as f:   # tolerate a BOM from Windows editors
            s = json.load(f)
    except (ValueError, UnicodeDecodeError) as e:
        sys.exit("X %s is not valid JSON (%s); fix it and re-run. Nothing was changed." % (path, e))
else:
    s = {}

OLD = (claude + "/hooks/guard.py", claude + "/hooks/session_start.sh",
       "$HOME/.claude/hooks/guard.py", "$HOME/.claude/hooks/session_start.sh")
def ours(h):  # one hook handler
    cmd = h.get("command", "").replace("\\", "/")
    return "build-crew/hooks/" in cmd or any(o in cmd for o in OLD)

hooks = s.setdefault("hooks", {})
mine = {"PreToolUse": {"matcher": "Bash", "hooks": [{"type": "command", "command": guard}]}}
if session:
    mine["SessionStart"] = {"hooks": [{"type": "command", "command": session}]}
for event in ("PreToolUse", "SessionStart"):
    groups = []
    for g in hooks.get(event, []):
        kept = [h for h in g.get("hooks", []) if not ours(h)]   # drop only our handlers
        if kept:
            groups.append(dict(g, hooks=kept))
    if event in mine:
        hooks[event] = groups + [mine[event]]
    elif event in hooks:
        hooks[event] = groups

deny = s.setdefault("permissions", {}).setdefault("deny", [])
if "Read(./.env.*)" in deny:  # older versions also blocked .env.example
    deny.remove("Read(./.env.*)")
for rule in ["Bash(git push --force:*)", "Bash(git push -f:*)", "Bash(gh pr merge:*)", "Bash(gh repo delete:*)",
             "Read(./.env)", "Read(./.env.local)", "Read(./.env.development)", "Read(./.env.production)",
             "Read(./.env.staging)", "Read(./.env.test)"]:
    if rule not in deny:
        deny.append(rule)

tmp = path + ".build-crew.tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(s, f, indent=2)
os.replace(tmp, path)   # atomic: never leaves a half-written settings.json
'@
$script = Join-Path ([IO.Path]::GetTempPath()) "build-crew-settings-$PID.py"
[IO.File]::WriteAllText($script, $merge, $Utf8)
try {
  $ErrorActionPreference = 'Continue'   # let Python's own error message through
  & $Py[0] @PyRest $script $Settings
  $code = $LASTEXITCODE
} finally {
  $ErrorActionPreference = 'Stop'
  Remove-Item -LiteralPath $script -Force -ErrorAction SilentlyContinue
}
if ($code -ne 0) { exit 1 }

if (Test-Path -LiteralPath $Bk) { Write-Host "Backups: $Bk" }
Write-Host "Installed: $($installed -join ', ')"
Write-Host "Gates and hooks: $Root (Python: $PyCmd)"
Write-Host "OK: build-crew installed globally. Restart Claude Code in any repo."
Write-Host '   /kickoff -> /build-phase -> /ship -> /release -> /deploy   (+ /fix /research /handoff)'
