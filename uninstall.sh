#!/usr/bin/env bash
# Remove a manual build-crew install (plugin installs: use /plugin instead).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$here/scripts/py" scripts/install.py --uninstall
