#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WINDOWS_SCRIPT="$(wslpath -w "$SCRIPT_DIR/restart.ps1" 2>/dev/null || printf '%s' "$SCRIPT_DIR/restart.ps1")"

if command -v pwsh.exe >/dev/null 2>&1; then
    POWERSHELL="pwsh.exe"
elif command -v powershell.exe >/dev/null 2>&1; then
    POWERSHELL="powershell.exe"
elif [[ -x "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe" ]]; then
    POWERSHELL="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
elif [[ -x "/mnt/c/Program Files/PowerShell/7/pwsh.exe" ]]; then
    POWERSHELL="/mnt/c/Program Files/PowerShell/7/pwsh.exe"
else
    echo "找不到 Windows PowerShell。" >&2
    exit 1
fi

exec "$POWERSHELL" -NoProfile -ExecutionPolicy Bypass -File "$WINDOWS_SCRIPT" "$@"
