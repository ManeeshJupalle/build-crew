#!/usr/bin/env bash
# build-crew manual install for macOS / Linux / Git Bash. Windows PowerShell: use install.ps1.
#   ./install.sh               install or upgrade (safe to re-run)
#   ./install.sh --uninstall   remove
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$here/scripts/py" scripts/install.py "$@"
