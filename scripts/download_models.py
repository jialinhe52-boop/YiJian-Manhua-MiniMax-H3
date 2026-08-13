from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download


COMFY = Path(os.getenv("COMFYUI_DIR", "/root/ComfyUI"))

FILES = [
    (
        "Comfy-Org/MiniMax-H3",
        "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        COMFY / "models" / "diffusion_models",
    ),
    (
        "Comfy-Org/MiniMax-H3",
        "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        COMFY / "models" / "text_encoders",
    ),
    (
        "Comfy-Org/MiniMax-H3",
        "vae/minimax_h3_video_vae_fp16.safetensors",
        COMFY / "models" / "vae",
    ),
    (
        "Comfy-Org/MiniMax-H3",
        "vae/minimax_h3_audio_vae_fp32.safetensors",
        COMFY / "models" / "vae",
    ),
    (
        "larryvrh/MiniMax-H3-Turbo-Lora",
        "minimax_h3_turbo_v4_step600_ema.safetensors",
        COMFY / "models" / "loras",
    ),
]

OPTIONAL_REF = (
    "Comfy-Org/MiniMax-H3",
    "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    COMFY / "models" / "diffusion_models",
)


def download(item: tuple[str, str, Path]) -> None:
    repo, filename, target = item
    target.mkdir(parents=True, exist_ok=True)
    destination = target / Path(filename).name
    if destination.exists():
        print(f"已存在: {destination}")
        return
    cached = Path(hf_hub_download(
        repo_id=repo,
        filename=filename,
        force_download=False,
    ))
    try:
        destination.symlink_to(cached)
    except OSError:
        shutil.copy2(cached, destination)
    print(f"已就绪: {destination}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", choices=["fl2va", "ref2va", "all"], default="all", nargs="?")
    args = parser.parse_args()
    for item in FILES:
        download(item)
    if args.bundle in {"ref2va", "all"}:
        download(OPTIONAL_REF)


if __name__ == "__main__":
    main()
