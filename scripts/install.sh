#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${H3_APP_DIR:-/root/h3-app}"
COMFY_DIR="${COMFYUI_DIR:-/root/ComfyUI}"
COMFY_REF="${COMFYUI_REF:-bd34f338ac505ea79e43968753968a464060e609}"
TURBO_REF="${H3_TURBO_REF:-55fee864dd7b2976b1c4ce3c3d5f7968f181409f}"

if [[ ! -d "${COMFY_DIR}/.git" ]]; then
  git clone --filter=blob:none https://github.com/Comfy-Org/ComfyUI.git "${COMFY_DIR}"
  git -C "${COMFY_DIR}" checkout "${COMFY_REF}"
fi

if [[ ! -d "${COMFY_DIR}/custom_nodes/ComfyUI-MiniMax-H3-Turbo/.git" ]]; then
  git clone --filter=blob:none \
    https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo.git \
    "${COMFY_DIR}/custom_nodes/ComfyUI-MiniMax-H3-Turbo"
  git -C "${COMFY_DIR}/custom_nodes/ComfyUI-MiniMax-H3-Turbo" checkout "${TURBO_REF}"
fi

python -m pip install --upgrade pip
python -m pip install -r "${COMFY_DIR}/requirements.txt"
python -m pip install -r "${APP_DIR}/requirements.txt"
python -m pip install --no-deps "torchaudio==2.8.0"

mkdir -p "${APP_DIR}/data" "${COMFY_DIR}/input" "${COMFY_DIR}/output"
echo "安装完成。下一步运行: bash ${APP_DIR}/scripts/download_models.sh all"
