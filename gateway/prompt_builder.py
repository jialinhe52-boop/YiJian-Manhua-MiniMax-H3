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
            f"<Subject {index}> 是由 <Picture {index}> 定义的可复用可见内容（{description}），只保留分配给它的人物、环境、物品、服装、构图或视觉风格属性。",
            f"<Picture {index}> 是 <Subject {index}> 的实际参考图，标签编号严格按上传顺序保持。",
        ))
        retention_lines.append(
            f"<Subject {index}>、<Picture {index}>: fully_preserved - 保持指定身份、外观、空间结构、物品细节、构图或风格，不与其他参考混用。"
        )
    audio_index = 1
    for index, (description, use_audio) in enumerate(reference_videos, start=1):
        definition_lines.append(
            f"<Video {index}> 是“{description}”的动作、运镜或时间结构参考，只用于用户点名的职责。"
        )
        retention_lines.append(
            f"<Video {index}>: weak_reference - 只借用指定动作、摄影机路径、节奏或时间结构。"
        )
        if use_audio:
            definition_lines.append(
                f"<Audio {audio_index}> 是 <Video {index}> 中已启用的同步音轨，只用于用户指定的声音职责。"
            )
            retention_lines.append(
                f"<Audio {audio_index}>: reference - 只参考 <Video {index}> 中指定的音色、环境声、音效、节奏或连续性。"
            )
            audio_index += 1
    for description in reference_audios:
        definition_lines.append(
            f"<Audio {audio_index}> 是“{description}”的独立音频参考。"
        )
        retention_lines.append(
            f"<Audio {audio_index}>: reference - 只使用分配给它的音色、语速、发音习惯、环境声、音效、节奏或音乐特征；人物音色参考不得复制原台词内容，也不得与其他人物串音。"
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
            "<Subject 1> 是用户明确描述的主要可见主体，整段视频保持其身份和既定外观。"
        )
        retention_lines.append(
            "<Subject 1>: fully_preserved - 所有镜头保持既定身份、外观与连续性。"
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
            + f"[reference generation] 生成一条 {duration} 秒连续视听片段，提交插件时采用作品统一视觉风格：{style_hint}。严格遵循用户指定的剧情、镜头顺序和参考职责，不新增无关人物、物品或事件。"
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
