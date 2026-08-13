#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${H3_APP_DIR:-/root/h3-app}"
python -m pip install "huggingface_hub>=0.28,<2"
python "${APP_DIR}/scripts/download_models.py" "${1:-all}"
