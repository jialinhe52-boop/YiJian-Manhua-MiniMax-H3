from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from gateway.comfy_client import find_output_file
from gateway.prompt_builder import build_prompt
from gateway.settings import ROOT, load_presets
from gateway.workflow_builder import build_workflow, dimensions, frame_count


def main() -> None:
    presets = load_presets()
    assert frame_count(4) == 107
    assert frame_count(15) == 362
    assert dimensions("9:16", 480) == (480, 864)
    assert dimensions("16:9", 480) == (864, 480)

    for name, preset in presets.items():
        graph = build_workflow(
            prompt="古装少女回头，镜头推近",
            duration=15,
            aspect_ratio="9:16",
            seed=1,
            preset=preset,
            first_frame="first.png",
            last_frame="last.png",
        )
        assert graph["5"]["inputs"]["length"] == 362
        assert graph["5"]["inputs"]["first_frame"] == ["30", 0]
        assert graph["5"]["inputs"]["last_frame"] == ["31", 0]
        assert graph["11"]["inputs"]["samples"] == ["10", 0]
        assert graph["12"]["inputs"]["samples"] == ["10", 0]
        assert sum(node["class_type"] == "SaveVideo" for node in graph.values()) == 1
        assert graph["14"]["inputs"]["codec"] == {"codec": "auto"}
        if name == "quality":
            assert "20" not in graph and "21" not in graph
        else:
            assert graph["20"]["class_type"] == "MiniMaxH3TurboLoRA"
            assert graph["21"]["class_type"] == "MiniMaxH3TurboSampler"

    multi_reference = build_workflow(
        prompt="<Picture 1> 锁定角色，<Picture 2> 锁定场景",
        duration=8,
        aspect_ratio="9:16",
        seed=1,
        preset=presets["draft"],
        reference_images=["character.png", "scene.png"],
    )
    assert multi_reference["5"]["class_type"] == "MiniMaxH3ReferenceToVideo"
    assert multi_reference["1"]["inputs"]["unet_name"].startswith("minimax_h3_ref2va")
    assert multi_reference["5"]["inputs"]["ref_images.ref_image_1"] == ["31", 0]
    assert multi_reference["7"]["inputs"]["steps"] == 12
    assert multi_reference["7"]["inputs"]["scheduler"] == "beta"

    omni_reference = build_workflow(
        prompt="参考动作、运镜、视频原声和独立音频",
        duration=8,
        aspect_ratio="16:9",
        seed=1,
        preset=presets["balanced"],
        reference_videos=[("motion.mp4", True)],
        reference_audios=["voice.wav"],
    )
    assert omni_reference["5"]["inputs"]["ref_videos.ref_video_0"] == ["31", 0]
    assert omni_reference["5"]["inputs"]["ref_video_audios.ref_video_audio_0"] == ["31", 1]
    assert omni_reference["5"]["inputs"]["ref_audios.ref_audio_0"] == ["32", 0]

    prompt = build_prompt(
        "女孩回头，镜头推近",
        mode="jimeng",
        duration=8,
        has_first_frame=True,
        has_last_frame=True,
    )
    assert "女孩回头" in prompt and "8 秒" in prompt and "人物身份" in prompt
    assert "0.00 秒" in prompt and "8.00 秒" in prompt
    for section in (
        "integrated_multimodal_description:", "overall_soundscape:",
        "non_diegetic_music:",
    ):
        assert section in prompt
    assert "subject_definitions:" not in prompt
    reference_prompt = build_prompt(
        "人物走入车站",
        mode="jimeng",
        duration=8,
        reference_images=["character：林晚"],
        reference_videos=[("推镜动作", True)],
        reference_audios=["风铃环境声"],
    )
    for tag in ("<Picture 1>", "<Video 1>", "<Audio 1>", "<Audio 2>"):
        assert tag in reference_prompt
    for section in (
        "subject_definitions:", "summary:", "retention_analysis:",
        "detailed_description:", "overall_soundscape:", "non_diegetic_music:",
    ):
        assert section in reference_prompt
    assert find_output_file(
        {"outputs": {"14": {"ui": {"videos": [{"filename": "x.mp4"}]}}}}
    ) == Path("x.mp4")

    for name in ("official_h3_fl2va.json", "official_h3_ref2va.json", "turbo_h3_example.json"):
        path = ROOT / "workflows" / "upstream" / name
        assert path.stat().st_size > 1000
        json.loads(path.read_text(encoding="utf-8"))
    for name in (
        "h3_manhua_draft.json", "h3_manhua_balanced.json", "h3_manhua_quality.json",
        "h3_manhua_multi_reference_api.json", "h3_manhua_omni_reference_api.json",
    ):
        path = ROOT / "workflows" / "generated" / name
        assert path.stat().st_size > 1000
        json.loads(path.read_text(encoding="utf-8"))
    for name in ("index.html", "style.css", "app.js", "terms.html"):
        assert (ROOT / "web" / name).stat().st_size > 100
    print("本地自检通过：时长、比例、首尾帧、多参、全能参考、单输出和提示词均有效。")


if __name__ == "__main__":
    main()
