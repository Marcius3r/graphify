#!/usr/bin/env bash
# MARCIUS3R — instalación en Linux/WSL2 con GPU NVIDIA. Uso: ./deploy/install_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."
COMMIT=38758d3c73366422efcf609abb63cab8385f3552   # versión de Wan2GP revisada
W="$HOME/Wan2GP"
for c in git python3 ffmpeg; do command -v $c >/dev/null || { echo "Falta $c (sudo apt install -y $c)"; exit 1; }; done
nvidia-smi --query-gpu=name,memory.total --format=csv || { echo "Sin GPU NVIDIA: usa Kaggle (README §2B)"; exit 1; }
[ -d "$W" ] || git clone https://github.com/deepbeepmeep/Wan2GP "$W"
(cd "$W" && git fetch -q && git checkout -q $COMMIT && { [ -x ./install.sh ] && ./install.sh || { python3 -m venv venv && venv/bin/pip install -r requirements.txt; }; })
python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e ".[dev,kaggle]" faster-whisper
sed -i "s#path: ~/Wan2GP#path: $W#" config/settings.yaml
mkdir -p ~/.marcius3r && chmod 700 ~/.marcius3r
[ -f ~/.marcius3r/secrets.env ] || { cp deploy/secrets.env.example ~/.marcius3r/secrets.env; chmod 600 ~/.marcius3r/secrets.env; }
.venv/bin/python -m pytest -q -m "not slow" tests
echo "OK. Prueba la muestra: .venv/bin/python -m marcius3r produce --script samples/sample_01_leonida.json"
