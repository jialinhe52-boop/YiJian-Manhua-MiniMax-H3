from __future__ import annotations

import os
import tempfile
from pathlib import Path


TEST_DATA_DIR = Path(tempfile.gettempdir()) / "h3-api-contract-tests"
os.environ.setdefault("H3_GATEWAY_DATA_DIR", str(TEST_DATA_DIR))
os.environ.setdefault("COMFYUI_INPUT_DIR", str(TEST_DATA_DIR / "input"))
os.environ.setdefault("COMFYUI_OUTPUT_DIR", str(TEST_DATA_DIR / "output"))

from gateway.main import PreflightRequest, _capability_payload, _preflight_result


def test_plugin_schema_exposes_dynamic_workflow_contract() -> None:
    payload = _capability_payload()
    assert payload["api_version"] == "1.3"
    assert payload["mode_inputs"]["fl2va"] == ["first_frame", "last_frame"]
    assert payload["reference_limits"] == {"images": 9, "videos": 3, "audios": 3}
    assert payload["reference_total_limit"] == 12
    assert payload["supports"]["preflight"] is True
    assert payload["prompt_boundary"]["prompt_inference_does_not_inject_style_or_aspect_ratio"] is True
    assert payload["prompt_boundary"]["generation_submission_appends_style_and_aspect_ratio"] is True
    assert payload["extensions"]["storyboard_grid"]["available"] is False
    assert payload["extensions"]["postprocess_upscale"]["available"] is False


def test_preflight_warns_without_changing_fifteen_second_request() -> None:
    result = _preflight_result(PreflightRequest(
        duration=15,
        aspect_ratio="9:16",
        preset="quality",
        generation_mode="ref2va",
        hardware_profile="rtx5090_32g",
        reference_image_size="max",
    ))
    assert result["risk"] == "high"
    assert result["requested_duration"] == 15
    assert result["duration_will_not_be_changed"] is True
    assert result["width"] == 736
    assert result["height"] == 1280
    assert result["steps"] == 16
    assert len(result["warnings"]) >= 2
