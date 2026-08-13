#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${H3_APP_DIR:-/root/h3-app}"
COMFY_DIR="${COMFYUI_DIR:-/root/ComfyUI}"
LOG_DIR="${H3_LOG_DIR:-/root/h3-app/logs}"
mkdir -p "${LOG_DIR}"

CUDA_COMPAT_DIR="${H3_CUDA_COMPAT_DIR:-/root/cuda-compat}"
if [[ -f /usr/local/cuda/lib64/libcudart.so.12 ]]; then
  mkdir -p "${CUDA_COMPAT_DIR}"
  ln -sf /usr/local/cuda/lib64/libcudart.so.12 "${CUDA_COMPAT_DIR}/libcudart.so.13"
  export LD_LIBRARY_PATH="${CUDA_COMPAT_DIR}:/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
fi

cd "${COMFY_DIR}"
nohup python main.py --listen 0.0.0.0 --port 8188 >"${LOG_DIR}/comfyui.log" 2>&1 &

cd "${APP_DIR}"
exec uvicorn gateway.main:app --host 0.0.0.0 --port 6006
