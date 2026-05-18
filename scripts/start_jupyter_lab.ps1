$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$jupyterRoot = Join-Path $projectRoot ".jupyter_local"
$env:JUPYTER_CONFIG_DIR = Join-Path $jupyterRoot "config"
$env:JUPYTER_DATA_DIR = Join-Path $jupyterRoot "data"
$env:JUPYTER_RUNTIME_DIR = Join-Path $jupyterRoot "runtime"
$env:IPYTHONDIR = Join-Path $jupyterRoot "ipython"

New-Item -ItemType Directory -Force -Path $env:JUPYTER_CONFIG_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $env:JUPYTER_DATA_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $env:JUPYTER_RUNTIME_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $env:IPYTHONDIR | Out-Null

Write-Host "Starting Jupyter Lab with project-local settings..." -ForegroundColor Cyan
Write-Host "Notebook path: $projectRoot\notebooks\01_display_bcfb_chorale.ipynb"

python -m jupyter lab $projectRoot
