@echo off
where pwsh.exe >nul 2>&1
if %errorlevel% equ 0 (
    pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart.ps1"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart.ps1"
)
if %errorlevel% neq 0 pause
