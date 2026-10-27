# build-crew manual install for Windows PowerShell (5.1 or 7+).
#   .\install.ps1              install or upgrade (safe to re-run)
#   .\install.ps1 -Uninstall   remove
# If scripts are blocked:  powershell -ExecutionPolicy Bypass -File .\install.ps1
param([switch]$Uninstall)

# Find a real Python 3.9+ (the Microsoft Store "python3" stub exists but can't run code).
$exe = $null
$pre = @()
foreach ($candidate in "py -3", "python", "python3") {
    $parts = $candidate -split " "
    if (-not (Get-Command $parts[0] -ErrorAction SilentlyContinue)) { continue }
    $args0 = @($parts | Select-Object -Skip 1)
    $null = & $parts[0] @args0 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>&1
    if ($LASTEXITCODE -eq 0) { $exe = $parts[0]; $pre = $args0; break }
}
if (-not $exe) {
    Write-Host "Python 3.9+ not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then re-run." -ForegroundColor Red
    exit 1
}

$installer = Join-Path $PSScriptRoot "scripts\install.py"
$extra = @()
if ($Uninstall) { $extra = @("--uninstall") }
$env:PYTHONUTF8 = "1"
& $exe @pre $installer @extra
exit $LASTEXITCODE
