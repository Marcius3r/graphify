#!/usr/bin/env bash
# Instalación en tu PC/VPS Linux (Ubuntu 22.04+). Idempotente.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v ffmpeg >/dev/null || { echo "Instala ffmpeg: sudo apt install -y ffmpeg"; exit 1; }
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[dev]"
.venv/bin/pip install -q faster-whisper || echo "aviso: faster-whisper no instalado (QC de pronunciación desactivado)"
mkdir -p ~/.marcius3r && chmod 700 ~/.marcius3r
[ -f ~/.marcius3r/secrets.env ] || { cp deploy/secrets.env.example ~/.marcius3r/secrets.env; chmod 600 ~/.marcius3r/secrets.env; }
if [ ! -f deploy/.env ]; then
  k=$(openssl rand -hex 32); echo "VOICESTUDIO_API_KEY=$k" > deploy/.env; chmod 600 deploy/.env
  sed -i "s/^VOICESTUDIO_API_KEY=.*/VOICESTUDIO_API_KEY=$k/" ~/.marcius3r/secrets.env
fi
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d
.venv/bin/python -m pytest -q -m "not slow" tests
echo "OK. Siguiente: rellena ~/.marcius3r/secrets.env, pon client_secret.json y ejecuta: .venv/bin/python -m marcius3r auth"
