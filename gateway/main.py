from __future__ import annotations

import base64
import binascii
import asyncio
import os
import re
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .comfy_client import ComfyClient, find_error_message, find_output_file
from .job_store import JobStore
from .modes import (
    GenerationMode,
    resolve_generation_mode,
    validate_generation_inputs,
    validate_reference_assets,
)
from .prompt_builder import append_generation_controls, build_prompt
from .settings import Settings, load_presets
from .workflow_builder import build_workflow, dimensions, frame_count


IMAGE_DATA_URL = re.compile(r"^data:image/(?P<ext>png|jpeg|jpg|webp);base64,(?P<data>.+)$", re.I)
VIDEO_DATA_URL = re.compile(r"^data:video/(?P<ext>mp4|webm|quicktime|x-matroska);base64,(?P<data>.+)$", re.I)
AUDIO_DATA_URL = re.compile(r"^data:audio/(?P<ext>mpeg|mp3|wav|x-wav|wave|ogg|webm|mp4|m4a|x-m4a|aac|flac);base64,(?P<data>.+)$", re.I)


class ReferenceImage(BaseModel):
    data: str
    role: Literal["character", "scene", "item", "style", "other"] = "character"
    name: str = Field(default="参考图", min_length=1, max_length=120)


class ReferenceVideo(BaseModel):
    data: str
    name: str = Field(default="参考视频", min_length=1, max_length=120)
    use_audio: bool = True


class ReferenceAudio(BaseModel):
    data: str
    name: str = Field(default="参考音频", min_length=1, max_length=120)


class VideoRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)
    duration: int = Field(default=5, ge=5, le=15)
    aspect_ratio: Literal["9:16", "16:9", "1:1", "3:4", "4:3"] = "9:16"
    preset: Literal["draft", "balanced", "quality"] = "balanced"
    prompt_mode: Literal["raw", "jimeng", "structured"] = "jimeng"
    generation_mode: GenerationMode | None = None
    style: str = Field(default="manhua", max_length=100)
    seed: int = Field(default=-1, ge=-1, le=2**63 - 1)
    first_frame: str | None = None
    last_frame: str | None = None
    reference_images: list[ReferenceImage] = Field(default_factory=list, max_length=9)
    reference_videos: list[ReferenceVideo] = Field(default_factory=list, max_length=3)
    reference_audios: list[ReferenceAudio] = Field(default_factory=list, max_length=3)
    reference_image_size: Literal["match", "max"] = "match"
    hardware_profile: Literal["auto", "low_vram_24g", "rtx5090_32g", "high_vram_48g"] = "auto"
    accepted_terms: bool = False


class PreflightRequest(BaseModel):
    duration: int = Field(default=5, ge=5, le=15)
    aspect_ratio: Literal["9:16", "16:9", "1:1", "3:4", "4:3"] = "9:16"
    preset: Literal["draft", "balanced", "quality"] = "balanced"
    generation_mode: GenerationMode = "t2va"
    hardware_profile: Literal["auto", "low_vram_24g", "rtx5090_32g", "high_vram_48g"] = "auto"
    reference_image_size: Literal["match", "max"] = "match"


HARDWARE_PROFILES = {
    "auto": {"label": "自动识别", "memory_gb": None},
    "low_vram_24g": {"label": "24GB 低显存", "memory_gb": 24},
    "rtx5090_32g": {"label": "RTX 5090 32GB", "memory_gb": 32},
    "high_vram_48g": {"label": "48GB 及以上", "memory_gb": 48},
}


REFERENCE_IMAGE_DUTIES = {
    "character": "只定义人物身份、五官、发型、体型和服装；不得复制背景、姿势、构图或光线",
    "scene": "只定义场景空间结构、材质、关键陈设和主光方向；不得改变人物身份、服装或动作",
    "item": "只定义物品外形、尺寸关系、材质、颜色和状态；不得改变人物、场景或镜头",
    "style": "只定义笔触、材质表现和色彩语言；不得复制其中的人物、场景、构图或文字",
    "other": "只用于名称中明确说明的职责；不得覆盖其他参考的身份、空间、动作或声音",
}


settings = Settings()
presets = load_presets()
comfy = ComfyClient(settings.comfy_url, settings.request_timeout_seconds)
store = JobStore(settings.data_dir / "jobs.sqlite3")
web_dir = Path(__file__).resolve().parents[1] / "web"


class CreateRateLimiter:
    def __init__(self, limit: int) -> None:
        self.limit = max(1, limit)
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self._requests[key]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise HTTPException(429, "too many generation requests; retry in one minute")
        bucket.append(now)


create_rate_limiter = CreateRateLimiter(settings.create_requests_per_minute)


def _safe_file(root: Path, relative: str | None) -> Path | None:
    if not relative:
        return None
    resolved_root = root.resolve()
    target = (resolved_root / relative).resolve()
    if resolved_root not in target.parents:
        return None
    return target


def _remove_inputs(job: dict[str, object]) -> None:
    for filename in job.get("input_files") or []:
        target = _safe_file(settings.comfy_input_dir, str(filename))
        if target and target.is_file():
            target.unlink(missing_ok=True)
    store.clear_input_files(str(job["id"]))


def _remove_output(job: dict[str, object]) -> None:
    target = _safe_file(settings.comfy_output_dir, str(job.get("output_file") or ""))
    if target and target.is_file():
        target.unlink(missing_ok=True)


def cleanup_expired_jobs() -> int:
    cutoff = time.time() - max(1, settings.job_ttl_hours) * 3600
    expired = store.expired(cutoff)
    for job in expired:
        _remove_inputs(job)
        _remove_output(job)
        store.delete(job["id"])
    return len(expired)


async def _maintenance_loop() -> None:
    while True:
        await asyncio.sleep(max(60, settings.cleanup_interval_seconds))
        cleanup_expired_jobs()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    cleanup_expired_jobs()
    maintenance = asyncio.create_task(_maintenance_loop())
    try:
        yield
    finally:
        maintenance.cancel()
        with suppress(asyncio.CancelledError):
            await maintenance


app = FastAPI(title="H3 漫剧云端 API", version="1.3.0", lifespan=lifespan)


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    if not settings.api_key:
        return
    if authorization != f"Bearer {settings.api_key}":
        raise HTTPException(401, "invalid API key")


def require_generation_access(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    require_api_key(authorization)
    client = request.client.host if request.client else "unknown"
    create_rate_limiter.check(client)


def _save_data_url(
    value: str,
    label: str,
    pattern: re.Pattern[str],
    extensions: dict[str, str],
    max_bytes: int,
) -> str:
    match = pattern.match(value)
    if not match:
        raise HTTPException(422, f"{label} has an unsupported data URL")
    extension = extensions.get(match.group("ext").lower(), match.group("ext").lower())
    try:
        content = base64.b64decode(match.group("data"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, f"{label} contains invalid base64 data") from exc
    if len(content) > max_bytes:
        raise HTTPException(413, f"{label} exceeds {max_bytes // 1024 // 1024} MB")
    settings.comfy_input_dir.mkdir(parents=True, exist_ok=True)
    filename = f"h3_{uuid.uuid4().hex}.{extension}"
    (settings.comfy_input_dir / filename).write_bytes(content)
    return filename


@app.get("/health")
async def health() -> JSONResponse:
    try:
        queue_size = await comfy.queue_size()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "comfyui": "unavailable", "detail": str(exc)[:300]},
        )
    return JSONResponse({"status": "ok", "comfyui": "ready", "queue_size": queue_size})


def _capability_payload() -> dict[str, object]:
    return {
        "api_version": "1.3",
        "plugin_schema_version": "1.0",
        "modes": ["t2va", "i2va", "fl2va", "l2va", "ref2va"],
        "mode_inputs": {
            "t2va": [],
            "i2va": ["first_frame"],
            "fl2va": ["first_frame", "last_frame"],
            "l2va": ["last_frame"],
            "ref2va": ["reference_images", "reference_videos", "reference_audios"],
        },
        "prompt_modes": ["raw", "jimeng", "structured"],
        "preset_names": list(presets),
        "presets": {
            name: {
                key: value for key, value in preset.items()
                if key not in {"lora_name", "lora_strength"}
            }
            for name, preset in presets.items()
        },
        "duration": {"min": 5, "max": 15},
        "reference_limits": {"images": 9, "videos": 3, "audios": 3},
        "reference_total_limit": 12,
        "reference_roles": ["character", "scene", "item", "style", "other"],
        "hardware_profiles": HARDWARE_PROFILES,
        "prompt_boundary": {
            "style_and_aspect_ratio_are_request_fields": True,
            "prompt_inference_does_not_inject_style_or_aspect_ratio": True,
            "generation_submission_appends_style_and_aspect_ratio": True,
        },
        "supports": {
            "cancel": True,
            "idempotency": True,
            "single_output": True,
            "preflight": True,
            "video_audio_reference": True,
            "audio_reference_requires_image_or_video": True,
        },
        "extensions": {
            "storyboard_grid": {
                "available": False,
                "planned_layouts": ["2x2", "3x2", "3x3"],
                "activation_gate": "cloud_graph_and_identity_benchmark",
            },
            "postprocess_upscale": {
                "available": False,
                "planned_outputs": ["2k", "4k"],
                "activation_gate": "separate_super_resolution_workflow_benchmark",
            },
        },
        "workflow_contract": {
            "submit": "POST /v1/videos",
            "status": "GET /v1/videos/{job_id}",
            "content": "GET /v1/videos/{job_id}/content",
            "cancel": "DELETE /v1/videos/{job_id}",
            "preflight": "POST /v1/preflight",
        },
    }


@app.get("/v1/capabilities")
async def capabilities() -> dict[str, object]:
    return _capability_payload()


@app.get("/v1/plugin/schema")
async def plugin_schema() -> dict[str, object]:
    return _capability_payload()


def _preflight_result(request: PreflightRequest) -> dict[str, object]:
    preset = presets[request.preset]
    width, height = dimensions(
        request.aspect_ratio,
        int(preset["short_edge"]),
        int(preset["long_edge"]) if preset.get("long_edge") else None,
    )
    reference_mode = request.generation_mode == "ref2va"
    steps = int(preset.get("reference_steps", preset["steps"])) if reference_mode else int(preset["steps"])
    profile = HARDWARE_PROFILES[request.hardware_profile]
    memory_gb = profile["memory_gb"]
    warnings: list[str] = []
    risk = "normal"

    if memory_gb is None:
        warnings.append("未指定显存档位，首次云端运行前请核对实际 GPU 显存")
    if request.reference_image_size == "max" and reference_mode:
        warnings.append("参考图保留至 2048 短边会显著增加 Ref2VA 显存和耗时")
        risk = "elevated"
    if memory_gb is not None and memory_gb <= 24 and request.preset != "draft":
        warnings.append("24GB 显存建议先使用极速预览档，当前组合存在显存不足风险")
        risk = "high"
    if memory_gb is not None and memory_gb <= 32 and request.duration == 15:
        warnings.append("32GB 及以下显存在 15 秒高分辨率生成时可能溢出；不会自动缩短时长")
        risk = "high"
    if memory_gb is not None and memory_gb <= 32 and request.preset == "quality" and request.duration > 12:
        warnings.append("高质成片超过 12 秒建议使用 48GB 及以上显存")
        risk = "high"

    return {
        "risk": risk,
        "warnings": warnings,
        "requested_duration": request.duration,
        "duration_will_not_be_changed": True,
        "generation_mode": request.generation_mode,
        "preset": request.preset,
        "hardware_profile": request.hardware_profile,
        "width": width,
        "height": height,
        "fps": 24,
        "frame_count": frame_count(request.duration),
        "steps": steps,
    }


@app.post("/v1/preflight")
async def preflight(request: PreflightRequest) -> dict[str, object]:
    return _preflight_result(request)


@app.post("/v1/videos", status_code=202, dependencies=[Depends(require_generation_access)])
async def create_video(
    request: VideoRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    if not request.accepted_terms:
        raise HTTPException(422, "MiniMax H3 usage terms must be accepted")
    if idempotency_key:
        idempotency_key = idempotency_key.strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", idempotency_key):
            raise HTTPException(422, "invalid Idempotency-Key")
        existing = store.get_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing["id"],
                "status": existing["status"],
                "requested_duration": existing["payload"]["duration"],
                "output_count": 1,
                "reused": True,
            }
    has_references = bool(request.reference_images or request.reference_videos or request.reference_audios)
    try:
        validate_reference_assets(
            len(request.reference_images),
            len(request.reference_videos),
            len(request.reference_audios),
        )
        generation_mode = resolve_generation_mode(
            request.generation_mode,
            has_first_frame=bool(request.first_frame),
            has_last_frame=bool(request.last_frame),
            has_references=has_references,
        )
        validate_generation_inputs(
            generation_mode,
            has_first_frame=bool(request.first_frame),
            has_last_frame=bool(request.last_frame),
            has_references=has_references,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    image_ext = {"jpeg": "jpg"}
    video_ext = {"quicktime": "mov", "x-matroska": "mkv"}
    audio_ext = {"mpeg": "mp3", "x-wav": "wav", "wave": "wav", "mp4": "m4a", "x-m4a": "m4a"}
    first = _save_data_url(request.first_frame, "first_frame", IMAGE_DATA_URL, image_ext, 25 * 1024 * 1024) if request.first_frame else None
    last = _save_data_url(request.last_frame, "last_frame", IMAGE_DATA_URL, image_ext, 25 * 1024 * 1024) if request.last_frame else None
    reference_images = [
        _save_data_url(item.data, f"reference_image_{index}", IMAGE_DATA_URL, image_ext, 25 * 1024 * 1024)
        for index, item in enumerate(request.reference_images, start=1)
    ]
    reference_videos = [
        (_save_data_url(item.data, f"reference_video_{index}", VIDEO_DATA_URL, video_ext, 250 * 1024 * 1024), item.use_audio)
        for index, item in enumerate(request.reference_videos, start=1)
    ]
    reference_audios = [
        _save_data_url(item.data, f"reference_audio_{index}", AUDIO_DATA_URL, audio_ext, 100 * 1024 * 1024)
        for index, item in enumerate(request.reference_audios, start=1)
    ]
    input_files = [
        item
        for item in (
            first,
            last,
            *reference_images,
            *(filename for filename, _use_audio in reference_videos),
            *reference_audios,
        )
        if item
    ]
    seed = request.seed if request.seed >= 0 else int.from_bytes(os.urandom(8), "big") >> 1
    inferred_prompt = build_prompt(
        request.prompt,
        mode=request.prompt_mode,
        generation_mode=generation_mode,
        style=request.style,
        duration=request.duration,
        has_first_frame=bool(first),
        has_last_frame=bool(last),
        reference_images=[
            f"{item.name}；{REFERENCE_IMAGE_DUTIES[item.role]}"
            for item in request.reference_images
        ],
        reference_videos=[(item.name, item.use_audio) for item in request.reference_videos],
        reference_audios=[item.name for item in request.reference_audios],
    )
    final_prompt = append_generation_controls(
        inferred_prompt,
        style=request.style,
        aspect_ratio=request.aspect_ratio,
    )
    job_id = uuid.uuid4().hex
    workflow = build_workflow(
        prompt=final_prompt,
        duration=request.duration,
        aspect_ratio=request.aspect_ratio,
        seed=seed,
        preset=presets[request.preset],
        generation_mode=generation_mode,
        first_frame=first,
        last_frame=last,
        reference_images=reference_images,
        reference_videos=reference_videos,
        reference_audios=reference_audios,
        reference_image_size=request.reference_image_size,
        low_vram=settings.low_vram,
        filename_prefix=f"h3_manhua/{job_id}",
    )
    try:
        queued = await comfy.queue_size()
        if queued >= settings.max_queue_size:
            raise HTTPException(429, "generation queue is full")
        prompt_id = await comfy.queue(workflow, client_id=job_id)
    except HTTPException:
        for filename in input_files:
            target = _safe_file(settings.comfy_input_dir, filename)
            if target:
                target.unlink(missing_ok=True)
        raise
    except Exception as exc:
        for filename in input_files:
            target = _safe_file(settings.comfy_input_dir, filename)
            if target:
                target.unlink(missing_ok=True)
        raise HTTPException(502, f"ComfyUI rejected the request: {exc}") from exc
    payload = request.model_dump(exclude={
        "first_frame", "last_frame", "reference_images", "reference_videos",
        "reference_audios", "accepted_terms"
    })
    payload["reference_counts"] = {
        "images": len(reference_images), "videos": len(reference_videos), "audios": len(reference_audios)
    }
    payload["generation_mode"] = generation_mode
    payload.update({"seed": seed, "final_prompt": final_prompt, "output_count": 1})
    store.put(
        job_id,
        prompt_id,
        payload,
        input_files=input_files,
        idempotency_key=idempotency_key,
    )
    return {
        "id": job_id,
        "status": "queued",
        "requested_duration": request.duration,
        "output_count": 1,
    }


@app.get("/v1/videos/{job_id}", dependencies=[Depends(require_api_key)])
async def get_video(job_id: str) -> dict[str, object]:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job["status"] in {"failed", "cancelled"}:
        status = job["status"]
    elif job["output_file"]:
        status = "completed"
    else:
        try:
            history = await comfy.history(job["prompt_id"])
        except Exception as exc:
            raise HTTPException(502, f"ComfyUI status request failed: {exc}") from exc
        output = find_output_file(history or {})
        if output:
            store.set_output(job_id, str(output))
            job["output_file"] = str(output)
            status = "completed"
            _remove_inputs(job)
        elif history and history.get("status", {}).get("status_str") == "error":
            status = "failed"
            job["error"] = find_error_message(history)
            store.set_status(job_id, status, job["error"])
            _remove_inputs(job)
        else:
            try:
                status = await comfy.prompt_state(job["prompt_id"]) or "processing"
            except Exception:
                status = "processing"
            store.set_status(job_id, status)
    response: dict[str, object] = {
        "id": job_id,
        "status": status,
        "requested_duration": job["payload"]["duration"],
        "output_count": 1,
        "progress": {"queued": 10, "processing": 55, "running": 55, "completed": 100}.get(status, 0),
    }
    if status == "completed":
        response["content_url"] = f"/v1/videos/{job_id}/content"
    if status in {"failed", "cancelled"}:
        response["error"] = job.get("error") or status
    return response


@app.delete("/v1/videos/{job_id}", dependencies=[Depends(require_api_key)])
async def cancel_video(job_id: str) -> dict[str, object]:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job["status"] not in {"completed", "failed", "cancelled"}:
        try:
            await comfy.cancel(job["prompt_id"])
        except Exception as exc:
            raise HTTPException(502, f"ComfyUI cancel request failed: {exc}") from exc
    _remove_inputs(job)
    _remove_output(job)
    store.set_status(job_id, "cancelled", "cancelled by user")
    return {"id": job_id, "status": "cancelled"}


@app.get("/v1/videos/{job_id}/content", dependencies=[Depends(require_api_key)])
async def download_video(job_id: str) -> FileResponse:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if not job["output_file"]:
        raise HTTPException(409, "video is not ready")
    output = _safe_file(settings.comfy_output_dir, job["output_file"])
    if not output or not output.is_file():
        raise HTTPException(404, "video output is missing")
    return FileResponse(output, media_type="video/mp4", filename=output.name)


app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
