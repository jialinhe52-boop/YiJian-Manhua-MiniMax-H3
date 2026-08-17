from __future__ import annotations

from typing import Literal


GenerationMode = Literal["t2va", "i2va", "fl2va", "l2va", "ref2va"]
GENERATION_MODES = frozenset({"t2va", "i2va", "fl2va", "l2va", "ref2va"})


def validate_reference_assets(
    image_count: int,
    video_count: int,
    audio_count: int,
) -> None:
    if image_count > 9 or video_count > 3 or audio_count > 3:
        raise ValueError("reference limits are 9 images, 3 videos and 3 audios")
    if image_count + video_count + audio_count > 12:
        raise ValueError("reference assets cannot exceed 12 files in total")
    if audio_count and not (image_count or video_count):
        raise ValueError("audio references require at least one image or video reference")


def resolve_generation_mode(
    generation_mode: str | None,
    *,
    has_first_frame: bool = False,
    has_last_frame: bool = False,
    has_references: bool = False,
) -> str:
    """Resolve legacy requests while keeping an explicit mode authoritative."""
    if generation_mode is not None:
        if generation_mode not in GENERATION_MODES:
            raise ValueError(f"unsupported generation_mode: {generation_mode}")
        return generation_mode
    if has_references:
        return "ref2va"
    if has_first_frame and has_last_frame:
        return "fl2va"
    if has_first_frame:
        return "i2va"
    if has_last_frame:
        return "l2va"
    return "t2va"


def validate_generation_inputs(
    generation_mode: str,
    *,
    has_first_frame: bool = False,
    has_last_frame: bool = False,
    has_references: bool = False,
) -> None:
    if generation_mode == "ref2va":
        if has_first_frame or has_last_frame:
            raise ValueError("ref2va cannot be combined with first/last frames")
        if not has_references:
            raise ValueError("ref2va requires at least one reference asset")
        return
    if has_references:
        raise ValueError(f"{generation_mode} cannot be combined with multi-reference assets")
    expected = {
        "t2va": (False, False),
        "i2va": (True, False),
        "fl2va": (True, True),
        "l2va": (False, True),
    }[generation_mode]
    actual = (has_first_frame, has_last_frame)
    if actual != expected:
        raise ValueError(
            f"{generation_mode} requires first_frame={expected[0]} and last_frame={expected[1]}"
        )
