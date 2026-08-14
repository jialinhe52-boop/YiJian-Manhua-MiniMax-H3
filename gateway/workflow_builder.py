from __future__ import annotations

from typing import Any

from .modes import resolve_generation_mode, validate_generation_inputs


DIFFUSION_MODEL = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
REFERENCE_DIFFUSION_MODEL = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
TEXT_ENCODER = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_fp16.safetensors"
AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"


def dimensions(aspect_ratio: str, short_edge: int) -> tuple[int, int]:
    ratios = {
        "9:16": (9, 16),
        "16:9": (16, 9),
        "1:1": (1, 1),
        "3:4": (3, 4),
        "4:3": (4, 3),
    }
    if aspect_ratio not in ratios:
        raise ValueError(f"unsupported aspect_ratio: {aspect_ratio}")
    x, y = ratios[aspect_ratio]
    if x <= y:
        width = short_edge
        height = round(short_edge * y / x / 32) * 32
    else:
        height = short_edge
        width = round(short_edge * x / y / 32) * 32
    # The official H3 template uses 1344x768 for its largest 16:9 preset.
    return min(width, 1344), min(height, 1344)


def frame_count(duration: int) -> int:
    if not 4 <= duration <= 15:
        raise ValueError("duration must be between 4 and 15 seconds")
    raw = max(5, round(duration * 24))
    return raw + (5 - raw % 17) % 17


def build_workflow(
    *,
    prompt: str,
    duration: int,
    aspect_ratio: str,
    seed: int,
    preset: dict[str, Any],
    generation_mode: str | None = None,
    first_frame: str | None = None,
    last_frame: str | None = None,
    reference_images: list[str] | None = None,
    reference_videos: list[tuple[str, bool]] | None = None,
    reference_audios: list[str] | None = None,
    reference_image_size: str = "match",
    low_vram: bool = False,
    filename_prefix: str = "h3_manhua",
) -> dict[str, dict[str, Any]]:
    if not prompt.strip():
        raise ValueError("prompt cannot be empty")
    reference_images = reference_images or []
    reference_videos = reference_videos or []
    reference_audios = reference_audios or []
    resolved_generation_mode = resolve_generation_mode(
        generation_mode,
        has_first_frame=bool(first_frame),
        has_last_frame=bool(last_frame),
        has_references=bool(reference_images or reference_videos or reference_audios),
    )
    reference_mode = resolved_generation_mode == "ref2va"
    validate_generation_inputs(
        resolved_generation_mode,
        has_first_frame=bool(first_frame),
        has_last_frame=bool(last_frame),
        has_references=bool(reference_images or reference_videos or reference_audios),
    )
    if len(reference_images) > 9 or len(reference_videos) > 3 or len(reference_audios) > 3:
        raise ValueError("reference limits are 9 images, 3 videos and 3 audios")
    if reference_mode and (first_frame or last_frame):
        raise ValueError("reference mode cannot be combined with first/last frames")
    if reference_image_size not in {"match", "max"}:
        raise ValueError("reference_image_size must be match or max")

    width, height = dimensions(aspect_ratio, int(preset["short_edge"]))
    diffusion_model = REFERENCE_DIFFUSION_MODEL if reference_mode else DIFFUSION_MODEL
    steps = int(preset.get("reference_steps", 20)) if reference_mode else int(preset["steps"])

    graph: dict[str, dict[str, Any]] = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": diffusion_model, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": TEXT_ENCODER,
                "type": "minimax",
                "device": "default",
            },
        },
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VIDEO_VAE}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": AUDIO_VAE}},
        "5": {
            "class_type": "MiniMaxH3ReferenceToVideo" if reference_mode else "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["2", 0],
                "vae": ["3", 0],
                "prompt": prompt,
                "width": width,
                "height": height,
                "length": frame_count(duration),
                **({"audio_vae": ["4", 0], "ref_image_size": reference_image_size} if reference_mode else {}),
            },
        },
        "6": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": int(seed)},
        },
        "7": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["1", 0],
                "scheduler": "beta" if reference_mode else "simple",
                "steps": steps,
                "denoise": 1.0,
            },
        },
        "8": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "res_multistep"},
        },
        "9": {
            "class_type": "BasicGuider",
            "inputs": {"model": ["1", 0], "conditioning": ["5", 0]},
        },
        "10": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["6", 0],
                "guider": ["9", 0],
                "sampler": ["8", 0],
                "sigmas": ["7", 0],
                "latent_image": ["5", 1],
            },
        },
        "11": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["10", 0], "vae": ["3", 0]},
        },
        "12": {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["10", 0], "vae": ["4", 0]},
        },
        "13": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["11", 0], "audio": ["12", 0], "fps": 24},
        },
        "14": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["13", 0],
                "filename_prefix": filename_prefix,
                "format": "auto",
                "codec": "auto",
            },
        },
    }

    # The currently pinned Turbo package documents FL2VA use. Ref2VA keeps its
    # own conservative step counts until the cloud benchmark validates it.
    lora_name = None if reference_mode else preset.get("lora_name")
    if lora_name:
        graph["20"] = {
            "class_type": "MiniMaxH3TurboLoRA",
            "inputs": {
                "model": ["1", 0],
                "lora_name": lora_name,
                "strength": float(preset.get("lora_strength", 1.0)),
                "low_vram": bool(low_vram),
            },
        }
        graph["21"] = {"class_type": "MiniMaxH3TurboSampler", "inputs": {}}
        graph["7"]["inputs"]["model"] = ["20", 0]
        graph["9"]["inputs"]["model"] = ["20", 0]
        graph["10"]["inputs"]["sampler"] = ["21", 0]

    next_id = 30
    for key, filename in (("first_frame", first_frame), ("last_frame", last_frame)):
        if filename:
            node_id = str(next_id)
            next_id += 1
            graph[node_id] = {
                "class_type": "LoadImage",
                "inputs": {"image": filename},
            }
            graph["5"]["inputs"][key] = [node_id, 0]

    for index, filename in enumerate(reference_images):
        node_id = str(next_id)
        next_id += 1
        graph[node_id] = {"class_type": "LoadImage", "inputs": {"image": filename}}
        graph["5"]["inputs"][f"ref_images.ref_image_{index}"] = [node_id, 0]

    for index, (filename, use_audio) in enumerate(reference_videos):
        load_id = str(next_id)
        components_id = str(next_id + 1)
        next_id += 2
        graph[load_id] = {"class_type": "LoadVideo", "inputs": {"file": filename}}
        graph[components_id] = {
            "class_type": "GetVideoComponents",
            "inputs": {"video": [load_id, 0]},
        }
        graph["5"]["inputs"][f"ref_videos.ref_video_{index}"] = [components_id, 0]
        if use_audio:
            graph["5"]["inputs"][f"ref_video_audios.ref_video_audio_{index}"] = [components_id, 1]

    for index, filename in enumerate(reference_audios):
        node_id = str(next_id)
        next_id += 1
        graph[node_id] = {"class_type": "LoadAudio", "inputs": {"audio": filename}}
        graph["5"]["inputs"][f"ref_audios.ref_audio_{index}"] = [node_id, 0]

    return graph
