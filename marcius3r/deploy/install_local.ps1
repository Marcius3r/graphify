# MARCIUS3R — instalación en Windows con GPU NVIDIA (PowerShell, no hace falta admin).
# Uso: abre PowerShell en la carpeta graphify\marcius3r y ejecuta:  powershell -ExecutionPolicy Bypass -File deploy\install_local.ps1
$ErrorActionPreference = "Stop"
$Commit = "38758d3c73366422efcf609abb63cab8385f3552"   # versión de Wan2GP revisada
$W = "$HOME\Wan2GP"
function Need($cmd, $hint) { if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Falta $cmd. $hint" } }
Need git    "Instala Git: winget install Git.Git"
Need python "Instala Python 3.11: winget install Python.Python.3.11"
Need ffmpeg "Instala FFmpeg: winget install Gyan.FFmpeg"
Need nvidia-smi "No se detecta GPU NVIDIA/driver. Instala el driver de NVIDIA (o usa Kaggle, ver README §2B)."
nvidia-smi --query-gpu=name,memory.total --format=csv
if (-not (Test-Path $W)) { git clone https://github.com/deepbeepmeep/Wan2GP $W }
Push-Location $W; git fetch -q; git checkout -q $Commit
if (Test-Path .\install.bat) { cmd /c install.bat } else { python -m venv venv; .\venv\Scripts\pip install -r requirements.txt }
Pop-Location
python -m venv .venv
.\.venv\Scripts\pip install -q --upgrade pip
.\.venv\Scripts\pip install -q -e ".[dev,kaggle]"
.\.venv\Scripts\pip install -q faster-whisper
# ruta de Wan2GP en la config (python del venv de Windows)
(Get-Content config\settings.yaml) -replace 'path: ~/Wan2GP', "path: $($W -replace '\\','/')" -replace 'python: null               # por defecto', "python: $($W -replace '\\','/')/venv/Scripts/python.exe  #" | Set-Content config\settings.yaml
New-Item -ItemType Directory -Force "$HOME\.marcius3r" | Out-Null
if (-not (Test-Path "$HOME\.marcius3r\secrets.env")) { Copy-Item deploy\secrets.env.example "$HOME\.marcius3r\secrets.env" }
.\.venv\Scripts\python -m pytest -q -m "not slow" tests
Write-Host "`nOK. Prueba la muestra:  .\.venv\Scripts\python -m marcius3r produce --script samples\sample_01_leonida.json"
