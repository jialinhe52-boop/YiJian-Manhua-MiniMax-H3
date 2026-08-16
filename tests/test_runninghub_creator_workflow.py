from __future__ import annotations

from pathlib import Path
import sys

if str(ROOT := Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_runninghub_creator_workflow import build


def _node(workflow: dict, node_id: int) -> dict:
    return next(node for node in workflow["nodes"] if node["id"] == node_id)


def test_creator_workflow_has_complete_reference_surface() -> None:
    workflow = build()
    reference = _node(workflow, 50)
    names = {item["name"] for item in reference["inputs"]}
    for index in range(9):
        assert f"ref_images.ref_image_{index}" in names
    for index in range(3):
        assert f"ref_videos.ref_video_{index}" in names
        assert f"ref_video_audios.ref_video_audio_{index}" in names
        assert f"ref_audios.ref_audio_{index}" in names


def test_creator_workflow_defaults_to_cost_effective_five_second_mode() -> None:
    workflow = build()
    assert _node(workflow, 10)["widgets_values"] == ["9:16 (Portrait Widescreen)", 0.6, 32]
    assert _node(workflow, 11)["widgets_values"] == [5]
    assert _node(workflow, 11)["inputs"][0]["widget"]["name"] == "value"
    assert _node(workflow, 52)["widgets_values"] == ["simple", 4, 1]
    assert _node(workflow, 42)["mode"] == 4
    assert _node(workflow, 43)["mode"] == 0


def test_all_optional_reference_assets_start_bypassed() -> None:
    workflow = build()
    for node_id in list(range(20, 29)) + list(range(30, 36)):
        assert _node(workflow, node_id)["mode"] == 4


def test_workflow_is_single_output_and_has_no_community_attribution() -> None:
    workflow = build()
    assert sum(node["type"] == "SaveVideo" for node in workflow["nodes"]) == 1
    serialized = str(workflow)
    assert "学AI的曹同学" not in serialized
    assert "工作流仅供学习交流" not in serialized
    assert "一键漫剧" in serialized


def test_every_link_is_bidirectionally_registered() -> None:
    workflow = build()
    nodes = {node["id"]: node for node in workflow["nodes"]}
    for link_id, source_id, source_slot, target_id, target_slot, _ in workflow["links"]:
        assert link_id in nodes[source_id]["outputs"][source_slot]["links"]
        assert nodes[target_id]["inputs"][target_slot]["link"] == link_id


def test_prompt_and_provenance_are_explicit() -> None:
    workflow = build()
    prompt = _node(workflow, 14)["widgets_values"][0]
    provenance = _node(workflow, 2)["widgets_values"][0]
    for section in (
        "subject_definitions:", "summary:", "retention_analysis:",
        "detailed_description:", "overall_soundscape:", "non_diegetic_music:",
    ):
        assert section in prompt
    assert "integrated_multimodal_description:" not in prompt
    assert "严格保持脸型" in prompt
    assert "is the main character" not in prompt
    assert "overall_soundscape:" in prompt
    assert "non_diegetic_music:" in prompt
    assert "模型与节点不声明原创" in provenance
    assert "ComfyUI" in provenance


def test_runninghub_string_widgets_are_array_encoded() -> None:
    workflow = build()
    for node_id in (1, 2, 12, 14, 45, 46, 53):
        assert isinstance(_node(workflow, node_id)["widgets_values"], list)
    assert _node(workflow, 12)["widgets_values"][0].startswith("max(5, round(a * 24))")
    assert _node(workflow, 45)["widgets_values"] == ["minimax_h3_video_vae_fp16.safetensors"]
    assert _node(workflow, 46)["widgets_values"] == ["minimax_h3_audio_vae_fp32.safetensors"]
    assert _node(workflow, 53)["widgets_values"] == ["res_multistep"]


if __name__ == "__main__":
    for name, function in sorted(globals().copy().items()):
        if name.startswith("test_") and callable(function):
            function()
    print("RunningHub 创作者工作流结构自检通过。")
