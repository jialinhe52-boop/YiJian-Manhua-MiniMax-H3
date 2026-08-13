from __future__ import annotations

from .modes import resolve_generation_mode, validate_generation_inputs

STYLE_HINTS = {
    "realistic": "写实电影质感，自然光影，人物五官稳定",
    "anime": "精致二维动画，线条干净，角色造型稳定",
    "manhua": "国风漫剧质感，角色设定稳定，画面层次清晰",
}


def build_prompt(
    prompt: str,
    *,
    mode: str = "jimeng",
    generation_mode: str | None = None,
    style: str = "manhua",
    duration: int = 5,
    preserve_identity: bool = True,
    has_first_frame: bool = False,
    has_last_frame: bool = False,
    reference_images: list[str] | None = None,
    reference_videos: list[tuple[str, bool]] | None = None,
    reference_audios: list[str] | None = None,
) -> str:
    source = prompt.strip()
    clean = " ".join(source.split())
    if not clean:
        raise ValueError("prompt cannot be empty")
    reference_images = reference_images or []
    reference_videos = reference_videos or []
    reference_audios = reference_audios or []
    resolved_generation_mode = resolve_generation_mode(
        generation_mode,
        has_first_frame=has_first_frame,
        has_last_frame=has_last_frame,
        has_references=bool(reference_images or reference_videos or reference_audios),
    )
    validate_generation_inputs(
        resolved_generation_mode,
        has_first_frame=has_first_frame,
        has_last_frame=has_last_frame,
        has_references=bool(reference_images or reference_videos or reference_audios),
    )
    definition_lines: list[str] = []
    retention_lines: list[str] = []
    for index, description in enumerate(reference_images, start=1):
        definition_lines.extend((
            f"<Subject {index}> is the reusable visible content defined by <Picture {index}> ({description}); preserve only its assigned character, environment, object, costume, composition or visual-style attributes.",
            f"<Picture {index}> is the concrete reference image for <Subject {index}> and retains its upload-order label.",
        ))
        retention_lines.append(
            f"<Subject {index}> and <Picture {index}>: fully_preserved - preserve the assigned identity, appearance, layout, object details, composition or style without mixing it with another reference."
        )
    audio_index = 1
    for index, (description, use_audio) in enumerate(reference_videos, start=1):
        definition_lines.append(
            f"<Video {index}> is the motion, camera or temporal-structure reference for {description}; use only the role named by the user."
        )
        retention_lines.append(
            f"<Video {index}>: weak_reference - borrow only the requested motion, camera path, rhythm or temporal structure."
        )
        if use_audio:
            definition_lines.append(
                f"<Audio {audio_index}> is the enabled synchronized audio track of <Video {index}> and is used only for its assigned sound role."
            )
            retention_lines.append(
                f"<Audio {audio_index}>: reference - follow only the requested voice, ambience, effects, rhythm or continuity characteristics of <Video {index}>."
            )
            audio_index += 1
    for description in reference_audios:
        definition_lines.append(
            f"<Audio {audio_index}> is an independent audio reference for {description}."
        )
        retention_lines.append(
            f"<Audio {audio_index}>: reference - use only the assigned voice, ambience, effect, rhythm or music characteristic."
        )
        audio_index += 1
    if mode == "raw":
        return clean
    if mode not in {"jimeng", "structured"}:
        raise ValueError(f"unsupported prompt_mode: {mode}")

    identity = "人物身份、五官、发型、服饰、关键物品和空间关系连续一致" if preserve_identity else ""
    style_hint = STYLE_HINTS.get(style, style.strip())
    required_sections = (
        "subject_definitions:",
        "summary:",
        "retention_analysis:",
        "detailed_description:",
        "overall_soundscape:",
        "non_diegetic_music:",
    )
    if resolved_generation_mode == "ref2va" and all(section in source for section in required_sections):
        return source

    if resolved_generation_mode != "ref2va" and "integrated_multimodal_description:" in source:
        return source

    if resolved_generation_mode == "fl2va":
        alignment = (
            "How the reference pictures align with the target video — Picture 1 (from Shot 1) "
            f"aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the {duration:.2f}-second mark of the target video. "
            f"首帧图对应目标视频 0.00 秒，尾帧图对应目标视频 {duration:.2f} 秒。"
        )
        path = "从首帧状态连续发展并自然落到尾帧状态，优先使用单镜头连接两帧"
    elif resolved_generation_mode == "i2va":
        alignment = (
            "For the target video, at 0.00 seconds into the target video, <Picture 1> "
            "(from [Shot 1]) is fully referenced. 首帧图完整对应目标视频 0.00 秒，"
            "并作为第一个镜头的构图与角色锚点。"
        )
        path = "从首帧的构图、人物和场景状态连续向前发展"
    elif resolved_generation_mode == "l2va":
        alignment = (
            "How the reference pictures align with the target video — <Picture 1> (from [Shot N]) "
            f"aligns with the {duration:.2f}-second mark of the target video. "
            f"尾帧图完整对应目标视频 {duration:.2f} 秒，所有动作在结尾自然落到该画面。"
        )
        path = "从合理的前置状态逐步收敛到尾帧"
    else:  # t2va
        alignment = ""
        path = "按用户原意建立完整、连续的视听时间线"

    if not definition_lines:
        definition_lines.append(
            "<Subject 1> is the primary visible subject explicitly described by the user; preserve its identity and stated appearance throughout the target video."
        )
        retention_lines.append(
            "<Subject 1>: fully_preserved - keep the stated identity, appearance and continuity across all shots."
        )

    continuity = f"；{identity}" if identity else ""
    alignment_line = f"{alignment}\n\n" if alignment else ""
    instruction = (
        "镜头运动应说明运动类型、幅度和速度；除非原提示词明确要求，避免无意义切镜。"
        f"总时长约 {duration} 秒。对白内容和标点必须逐字保留，不翻译、不改写。"
    )
    audio_sections = (
        "\n\noverall_soundscape:\n保留原提示词中指定的环境声、动作声和非语言人声，"
        "并与画面动作同步；未指定时仅使用符合场景的轻微自然环境声。\n"
        "\nnon_diegetic_music:\n仅在原提示词明确指定背景配乐时生成；否则 N/A。"
    )
    if resolved_generation_mode == "ref2va":
        return (
            "subject_definitions:\n" + "\n".join(definition_lines)
            + "\n\nsummary:\n"
            + f"[reference generation] Create one {duration}-second audiovisual result in {style_hint}. Follow the user's requested story, shot order and reference roles without inventing unrelated characters, objects or events."
            + "\n\nretention_analysis:\n" + "\n".join(retention_lines)
            + "\n\ndetailed_description:\n"
            + f"[Shot 1] {style_hint}。{clean}。{path}{continuity}。{instruction}"
            + audio_sections
        )
    return (
        "integrated_multimodal_description:\n"
        + f"[Shot 1] {style_hint}。{alignment_line}{clean}。{path}{continuity}。{instruction}"
        + audio_sections
    )
