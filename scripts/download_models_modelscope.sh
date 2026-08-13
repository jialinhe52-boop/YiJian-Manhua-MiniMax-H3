#!/usr/bin/env bash
set -euo pipefail

MODEL_ROOT="${H3_MODEL_ROOT:-/root/ComfyUI/models}"
BASE_URL="${H3_MODELSCOPE_BASE:-https://modelscope.cn/models/Comfy-Org/MiniMax-H3/resolve/master}"
LORA_URL="${H3_LORA_URL:-https://hf-mirror.com/larryvrh/MiniMax-H3-Turbo-Lora/resolve/main/minimax_h3_turbo_v4_step600_ema.safetensors}"
CHUNK_SIZE="${H3_DOWNLOAD_CHUNK_SIZE:-33554432}"
PARALLEL="${H3_DOWNLOAD_PARALLEL:-8}"

download() {
  local url="$1" out="$2" size="$3"
  mkdir -p "$(dirname "$out")"
  if [[ -f "$out" && "$(stat -c%s "$out")" == "$size" ]]; then
    echo "READY $out"
    return
  fi
  echo "DOWNLOAD $out"
  rm -f "$out"
  local source_url="$url"
  if [[ "$url" == https://modelscope.cn/* ]]; then
    local headers
    headers="$(mktemp)"
    curl -ksS -D "$headers" -o /dev/null --range 0-0 "$url"
    source_url="$(grep -i '^Location:' "$headers" | head -n1 | cut -d' ' -f2- | tr -d '\r\n')"
    rm -f "$headers"
    [[ "$source_url" == https://cdn-lfs-*.modelscope.cn/* ]]
  fi
  local parts_dir="$out.parts" assembling="$out.assembling"
  local start end expected index part pid
  local -a pids=()
  mkdir -p "$parts_dir"
  for ((start=0, index=0; start<size; start+=CHUNK_SIZE, index++)); do
    end=$((start + CHUNK_SIZE - 1))
    ((end >= size)) && end=$((size - 1))
    expected=$((end - start + 1))
    printf -v part '%s/%05d.part' "$parts_dir" "$index"
    if [[ -f "$part" && "$(stat -c%s "$part")" == "$expected" ]]; then
      continue
    fi
    rm -f "$part"
    (
      curl -k --http1.1 --fail --retry 50 --retry-all-errors --retry-delay 1 --connect-timeout 30 \
        --speed-time 60 --speed-limit 1024 --silent --show-error \
        --range "$start-$end" "$source_url" -o "$part"
      [[ "$(stat -c%s "$part")" == "$expected" ]]
    ) &
    pids+=("$!")
    if (( ${#pids[@]} >= PARALLEL )); then
      wait "${pids[0]}"
      pids=("${pids[@]:1}")
    fi
  done
  for pid in "${pids[@]}"; do wait "$pid"; done
  : > "$assembling"
  for part in "$parts_dir"/*.part; do cat "$part" >> "$assembling"; done
  [[ "$(stat -c%s "$assembling")" == "$size" ]]
  mv -f "$assembling" "$out"
  rm -rf "$parts_dir"
  echo "READY $out"
}

download "$BASE_URL/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors" \
  "$MODEL_ROOT/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors" 20970379616
download "$BASE_URL/vae/minimax_h3_video_vae_fp16.safetensors" \
  "$MODEL_ROOT/vae/minimax_h3_video_vae_fp16.safetensors" 5207808496
download "$BASE_URL/vae/minimax_h3_audio_vae_fp32.safetensors" \
  "$MODEL_ROOT/vae/minimax_h3_audio_vae_fp32.safetensors" 605254808
download "$BASE_URL/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" \
  "$MODEL_ROOT/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" 15687142551
download "$BASE_URL/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" \
  "$MODEL_ROOT/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" 20970379616
download "$LORA_URL" \
  "$MODEL_ROOT/loras/minimax_h3_turbo_v4_step600_ema.safetensors" 779849816
echo "ALL_MODELS_READY"
