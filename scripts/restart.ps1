[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
& python (Join-Path $PSScriptRoot 'dev.py') restart
exit $LASTEXITCODE
