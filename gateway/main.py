from __future__ import annotations

import base64
import binascii
import os
import re
import uuid
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .comfy_client import ComfyClient, find_output_file
from .job_store import JobStore
from .modes import GenerationMode, resolve_generation_mode, validate_generation_inputs
from .prompt_builder import build_prompt
from .settings import Settings, load_presets
from .workflow_builder import build_workflow


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
    duration: int = Field(default=5, ge=4, le=15)
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
    accepted_terms: bool = False


settings = Settings()
presets = load_presets()
comfy = ComfyClient(settings.comfy_url, settings.request_timeout_seconds)
store = JobStore(settings.data_dir / "jobs.sqlite3")
app = FastAPI(title="H3 漫剧云端 API", version="1.0.0")
web_dir = Path(__file__).resolve().parents[1] / "web"


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    if not settings.api_key:
        return
    if authorization != f"Bearer {settings.api_key}":
        raise HTTPException(401, "invalid API key")


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
async def health() -> dict[str, str]:
    return {"status": "ok", "comfyui": settings.comfy_url}


@app.post("/v1/videos", status_code=202, dependencies=[Depends(require_api_key)])
async def create_video(request: VideoRequest) -> dict[str, object]:
    if not request.accepted_terms:
        raise HTTPException(422, "MiniMax H3 usage terms must be accepted")
    has_references = bool(request.reference_images or request.reference_videos or request.reference_audios)
    try:
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
    seed = request.seed if request.seed >= 0 else int.from_bytes(os.urandom(8), "big") >> 1
    final_prompt = build_prompt(
        request.prompt,
        mode=request.prompt_mode,
        generation_mode=generation_mode,
        style=request.style,
        duration=request.duration,
        has_first_frame=bool(first),
        has_last_frame=bool(last),
        reference_images=[f"{item.role}：{item.name}" for item in request.reference_images],
        reference_videos=[(item.name, item.use_audio) for item in request.reference_videos],
        reference_audios=[item.name for item in request.reference_audios],
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
        filename_prefix=f"h3_manhua/{job_id}",
    )
    try:
        queued = await comfy.queue_size()
        if queued >= settings.max_queue_size:
            raise HTTPException(429, "generation queue is full")
        prompt_id = await comfy.queue(workflow, client_id=job_id)
    except HTTPException:
        raise
    except Exception as exc:
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
    store.put(job_id, prompt_id, payload)
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
    if job["output_file"]:
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
        elif history and history.get("status", {}).get("status_str") == "error":
            status = "failed"
        else:
            status = "processing"
    response: dict[str, object] = {
        "id": job_id,
        "status": status,
        "requested_duration": job["payload"]["duration"],
        "output_count": 1,
    }
    if status == "completed":
        response["content_url"] = f"/v1/videos/{job_id}/content"
    return response


@app.get("/v1/videos/{job_id}/content", dependencies=[Depends(require_api_key)])
async def download_video(job_id: str) -> FileResponse:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if not job["output_file"]:
        raise HTTPException(409, "video is not ready")
    output = (settings.comfy_output_dir / job["output_file"]).resolve()
    root = settings.comfy_output_dir.resolve()
    if root not in output.parents or not output.is_file():
        raise HTTPException(404, "video output is missing")
    return FileResponse(output, media_type="video/mp4", filename=output.name)


app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
