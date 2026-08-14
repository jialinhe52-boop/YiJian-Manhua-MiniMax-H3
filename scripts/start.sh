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
COMFY_PID=$!

cleanup() {
  kill "${COMFY_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

READY=0
for _ in $(seq 1 "${H3_STARTUP_WAIT_SECONDS:-180}"); do
  if ! kill -0 "${COMFY_PID}" 2>/dev/null; then
    echo "ComfyUI 启动失败，请查看 ${LOG_DIR}/comfyui.log" >&2
    exit 1
  fi
  if curl -fsS --max-time 2 http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if [[ "${READY}" != "1" ]]; then
  echo "ComfyUI 在等待时间内未就绪，请查看 ${LOG_DIR}/comfyui.log" >&2
  exit 1
fi

cd "${APP_DIR}"
uvicorn gateway.main:app --host 0.0.0.0 --port 6006
