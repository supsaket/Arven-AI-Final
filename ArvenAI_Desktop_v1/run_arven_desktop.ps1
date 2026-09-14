$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python was not found." -ForegroundColor Red
    exit 1
}
python -m pip install -r requirements-desktop.txt
python desktop_app.py
