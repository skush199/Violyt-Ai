import json
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from app.ai.context_compiler import ContextCompilerService
from app.core.config import get_settings
from app.services.data_validation import DataValidatorService
from app.services.generation_trace import GenerationTraceService


def _reference_sample(
    asset_id: str,
    *,
    design_style: str,
    image_style: str,
    depth_style: str,
    rendering_style: str,
    scene_type: str,
    primary_subjects: list[str],
    human_presence: str = "none",
    abstraction_level: str = "literal",
    icons: str = "none",
    graphs: str = "none",
    format_family: str = "carousel",
    story_arc_roles: list[str] | None = None,
    closing_style: str = "reflective_close",
) -> dict:
    return {
        "asset_id": asset_id,
        "style_characteristics": {
            "design_style": design_style,
            "image_treatment": {"style": image_style},
            "visual_craft_dna": {
                "depth_style": depth_style,
                "rendering_style": rendering_style,
            },
            "subject_semantics": {
                "scene_type": scene_type,
                "primary_subjects": primary_subjects,
                "human_presence": human_presence,
                "abstraction_level": abstraction_level,
            },
            "infographic_elements": {
                "icons": icons,
                "graphs": graphs,
            },
            "editorial_dna": {
                "format_family": format_family,
                "story_arc_roles": story_arc_roles or ["detail"],
                "closing_style": closing_style,
            },
        },
        "reusable_zones": [],
        "brand_score": 0.85,
    }


def _reference_creatives_from_samples(samples: list[dict]) -> list[dict]:
    creatives: list[dict] = []
    for sample in samples:
        style_characteristics = dict(sample.get("style_characteristics", {}))
        profile = DataValidatorService._visual_style_profile_from_record(
            {
                "design_style": style_characteristics.get("design_style"),
                "image_treatment": style_characteristics.get("image_treatment", {}),
                "visual_craft_dna": style_characteristics.get("visual_craft_dna", {}),
                "subject_semantics": style_characteristics.get("subject_semantics", {}),
                "infographic_elements": style_characteristics.get("infographic_elements", {}),
                "editorial_dna": style_characteristics.get("editorial_dna", {}),
                "visual_style_profile": style_characteristics.get("visual_style_profile", {}),
            }
        )
        style_characteristics["visual_style_profile"] = profile
        creatives.append(
            {
                "asset_id": sample["asset_id"],
                "style_characteristics": style_characteristics,
                "visual_style_profile": profile,
            }
        )
    return creatives


def _phase1_synthesis(samples: list[dict]) -> dict:
    return DataValidatorService._synthesize_reference_system(samples, [])


def _phase1_compiled_visual_brief(monkeypatch, *, samples: list[dict], format_family: str = "carousel") -> dict:
    monkeypatch.setenv("DEBUG", "false")
    get_settings.cache_clear()
    synthesis = _phase1_synthesis(samples)
    compiler = ContextCompilerService()
    compiled = compiler.compile(
        prompt="Create a carousel with brand-aligned visuals.",
        brand_context={
            "brand_name": "Phase1 Eval Brand",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {},
            "visual_identity": {
                "reference_creatives": _reference_creatives_from_samples(samples),
                "design_system": synthesis,
            },
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={
            "platform_preset": "linkedin",
            "format": format_family,
            "file_type": "png",
            "size": {"width": 1080, "height": 1350},
        },
        conversation_context={},
        session_memory={},
        layout_decision={"mode": "adapted_template"},
        template_context={
            "sequence_pack": {
                "family_name": "PHASE1-EVAL",
                "slides": [{"slide_index": 1, "story_role": "hook"}],
            }
        }
        if format_family == "carousel"
        else None,
        reference_assets=[],
    )
    return compiled["brand_visual_brief"]


def _phase1_evaluation_trace(monkeypatch, *, samples: list[dict], format_family: str = "carousel") -> dict:
    synthesis = _phase1_synthesis(samples)
    brief = _phase1_compiled_visual_brief(monkeypatch, samples=samples, format_family=format_family)
    return {
        "synthesis_policy": synthesis.get("visual_style_policy", {}),
        "format_policy": synthesis.get("format_visual_style_profiles", {}).get(format_family, {}),
        "compiled_policy": brief.get("visual_style_policy", {}),
        "visual_style_summary": brief.get("visual_style_summary", ""),
        "reference_visual_profiles": brief.get("reference_visual_profiles", []),
    }


def _write_phase1_trace_payload(base_dir: Path, payload: dict) -> tuple[dict, Path]:
    trace_service = GenerationTraceService(base_dir=base_dir, enabled=True)
    trace = trace_service.start_trace(
        prompt="Phase 1 visual style evaluation",
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        metadata={"phase": 1, "feature": "dynamic_visual_style_policy"},
    )
    assert trace is not None
    trace_service.write_payload(trace["trace_id"], "phase1_visual_style_eval", payload)
    payload_path = base_dir / trace["trace_id"] / "phase1_visual_style_eval.json"
    return trace, payload_path


def test_phase1_wrapper_photo_led_brand_produces_expected_trace(monkeypatch) -> None:
    samples = [
        _reference_sample(
            "photo-1",
            design_style="photo",
            image_style="photo",
            depth_style="flat",
            rendering_style="photo",
            scene_type="premium seafood hero shot",
            primary_subjects=["food", "prawns"],
            icons="minimal",
            story_arc_roles=["hook"],
        ),
        _reference_sample(
            "photo-2",
            design_style="photo",
            image_style="photo",
            depth_style="flat",
            rendering_style="photo",
            scene_type="plated fish closeup",
            primary_subjects=["food", "fish"],
            story_arc_roles=["detail"],
        ),
        _reference_sample(
            "photo-3",
            design_style="photo",
            image_style="photo",
            depth_style="flat",
            rendering_style="photo",
            scene_type="clean food still life",
            primary_subjects=["food", "seafood"],
            story_arc_roles=["cta"],
            closing_style="cta_close",
        ),
    ]

    evaluation = _phase1_evaluation_trace(monkeypatch, samples=samples)
    print(json.dumps(evaluation, indent=2, sort_keys=True))

    assert evaluation["synthesis_policy"]["dominant_image_mode"] == "photo"
    assert evaluation["synthesis_policy"]["dominant_rendering_mode"] == "photo"
    assert evaluation["synthesis_policy"]["three_d_usage"] == "none"
    assert evaluation["compiled_policy"]["dominant_subject_mode"] == "food"
    assert evaluation["compiled_policy"]["reference_pattern_priority"] == "brand_dominant"
    assert "photo" in evaluation["visual_style_summary"]
    assert len(evaluation["reference_visual_profiles"]) == 3


def test_phase1_wrapper_mixed_brand_flags_reference_specific_priority(monkeypatch) -> None:
    samples = [
        _reference_sample(
            "mix-photo",
            design_style="photo",
            image_style="photo",
            depth_style="flat",
            rendering_style="photo",
            scene_type="human wellness consultation",
            primary_subjects=["coach", "child"],
            human_presence="prominent",
            abstraction_level="literal",
            story_arc_roles=["detail"],
        ),
        _reference_sample(
            "mix-3d",
            design_style="3d",
            image_style="3d",
            depth_style="true_3d",
            rendering_style="3d_render",
            scene_type="isometric finance object scene",
            primary_subjects=["coins", "calculator"],
            abstraction_level="conceptual",
            icons="present",
            graphs="present",
            story_arc_roles=["hook"],
        ),
        _reference_sample(
            "mix-illustration",
            design_style="illustration",
            image_style="illustration",
            depth_style="layered",
            rendering_style="vector",
            scene_type="diagram led explainer",
            primary_subjects=["steps", "process"],
            abstraction_level="conceptual",
            icons="present",
            graphs="none",
            story_arc_roles=["comparison"],
        ),
    ]

    evaluation = _phase1_evaluation_trace(monkeypatch, samples=samples)
    print(json.dumps(evaluation, indent=2, sort_keys=True))

    assert evaluation["synthesis_policy"]["style_consistency"] == "mixed"
    assert evaluation["synthesis_policy"]["reference_pattern_priority"] == "reference_specific"
    assert evaluation["synthesis_policy"]["dominant_image_mode"] == "mixed"
    assert evaluation["synthesis_policy"]["dominant_depth_mode"] == "mixed"
    assert evaluation["compiled_policy"]["dominant_rendering_mode"] == "mixed"
    assert set(evaluation["synthesis_policy"]["image_modes"]) >= {"photo", "3d", "illustration"}
    assert len(evaluation["reference_visual_profiles"]) == 3
    assert {item["image_mode"] for item in evaluation["reference_visual_profiles"]} >= {"photo", "3d", "illustration"}


def test_phase1_wrapper_writes_generation_style_trace_payload(monkeypatch) -> None:
    samples = [
        _reference_sample(
            "trace-3d",
            design_style="3d",
            image_style="3d",
            depth_style="true_3d",
            rendering_style="3d_render",
            scene_type="retirement planning 3d hook visual",
            primary_subjects=["retirement", "coins"],
            abstraction_level="conceptual",
            icons="present",
            graphs="present",
            story_arc_roles=["hook"],
        ),
        _reference_sample(
            "trace-3d-2",
            design_style="3d",
            image_style="3d",
            depth_style="true_3d",
            rendering_style="3d_render",
            scene_type="product mockup finance scene",
            primary_subjects=["dashboard", "laptop"],
            abstraction_level="conceptual",
            icons="present",
            story_arc_roles=["detail"],
        ),
    ]

    trace_base = Path("storage") / "generation_traces" / "test-traces" / str(uuid4())
    try:
        evaluation = _phase1_evaluation_trace(monkeypatch, samples=samples)
        trace, payload_path = _write_phase1_trace_payload(trace_base, evaluation)
        stored_payload = json.loads(payload_path.read_text(encoding="utf-8"))
        print(json.dumps(stored_payload, indent=2, sort_keys=True))

        assert trace["trace_id"]
        assert payload_path.exists()
        assert stored_payload == evaluation
        assert stored_payload["compiled_policy"]["dominant_image_mode"] == "3d"
        assert stored_payload["compiled_policy"]["three_d_usage"] == "often"
        assert stored_payload["compiled_policy"]["reference_pattern_priority"] == "brand_dominant"
    finally:
        if trace_base.exists():
            rmtree(trace_base, ignore_errors=True)


def test_phase1_tgfc_like_brand_resolves_photo_led_food_system(monkeypatch) -> None:
    samples = [
        _reference_sample(
            "tgfc-1",
            design_style="photo",
            image_style="photo",
            depth_style="flat",
            rendering_style="photo",
            scene_type="premium seafood still life on marble",
            primary_subjects=["food", "prawns"],
            icons="minimal",
            story_arc_roles=["hook"],
        ),
        _reference_sample(
            "tgfc-2",
            design_style="photo",
            image_style="photo",
            depth_style="flat",
            rendering_style="photo",
            scene_type="plated fish closeup on aqua backdrop",
            primary_subjects=["food", "fish"],
            story_arc_roles=["detail"],
        ),
        _reference_sample(
            "tgfc-3",
            design_style="photo",
            image_style="photo",
            depth_style="flat",
            rendering_style="photo",
            scene_type="editorial seafood meal beauty shot",
            primary_subjects=["food", "seafood"],
            story_arc_roles=["detail"],
        ),
    ]

    evaluation = _phase1_evaluation_trace(monkeypatch, samples=samples)
    print(json.dumps(evaluation, indent=2, sort_keys=True))

    assert evaluation["compiled_policy"]["dominant_image_mode"] == "photo"
    assert evaluation["compiled_policy"]["dominant_depth_mode"] == "flat"
    assert evaluation["compiled_policy"]["dominant_rendering_mode"] == "photo"
    assert evaluation["compiled_policy"]["dominant_subject_mode"] == "food"
    assert evaluation["compiled_policy"]["three_d_usage"] == "none"
    assert evaluation["compiled_policy"]["reference_pattern_priority"] == "brand_dominant"


def test_phase1_niroggi_like_brand_resolves_photo_led_human_editorial_system(monkeypatch) -> None:
    samples = [
        _reference_sample(
            "niroggi-1",
            design_style="photo",
            image_style="photo",
            depth_style="flat",
            rendering_style="photo",
            scene_type="human coaching consultation lifestyle photo",
            primary_subjects=["coach", "child"],
            human_presence="prominent",
            abstraction_level="literal",
            story_arc_roles=["hook"],
        ),
        _reference_sample(
            "niroggi-2",
            design_style="photo",
            image_style="photo",
            depth_style="flat",
            rendering_style="photo",
            scene_type="parent child support editorial photo",
            primary_subjects=["parent", "child"],
            human_presence="prominent",
            abstraction_level="literal",
            story_arc_roles=["detail"],
        ),
        _reference_sample(
            "niroggi-3",
            design_style="photo",
            image_style="photo",
            depth_style="flat",
            rendering_style="photo",
            scene_type="healthy lifestyle flatlay with light educational overlay",
            primary_subjects=["wellness", "nutrition"],
            human_presence="none",
            abstraction_level="mixed",
            icons="present",
            story_arc_roles=["detail"],
        ),
    ]

    evaluation = _phase1_evaluation_trace(monkeypatch, samples=samples)
    print(json.dumps(evaluation, indent=2, sort_keys=True))

    assert evaluation["compiled_policy"]["dominant_image_mode"] == "photo"
    assert evaluation["compiled_policy"]["dominant_rendering_mode"] == "photo"
    assert evaluation["compiled_policy"]["dominant_subject_mode"] == "human"
    assert evaluation["compiled_policy"]["three_d_usage"] == "none"
    assert evaluation["compiled_policy"]["reference_pattern_priority"] == "brand_dominant"


def test_phase1_jiraaf_like_brand_resolves_three_d_finance_system(monkeypatch) -> None:
    samples = [
        _reference_sample(
            "jiraaf-1",
            design_style="3d",
            image_style="3d",
            depth_style="true_3d",
            rendering_style="3d_render",
            scene_type="retirement planning 3d finance object scene",
            primary_subjects=["retirement", "coins"],
            abstraction_level="conceptual",
            icons="present",
            graphs="present",
            story_arc_roles=["hook"],
        ),
        _reference_sample(
            "jiraaf-2",
            design_style="3d",
            image_style="3d",
            depth_style="true_3d",
            rendering_style="3d_render",
            scene_type="calculator notebook coins 3d explainer cluster",
            primary_subjects=["calculator", "coins"],
            abstraction_level="conceptual",
            icons="present",
            story_arc_roles=["detail"],
        ),
        _reference_sample(
            "jiraaf-3",
            design_style="3d",
            image_style="3d",
            depth_style="3d_illusion",
            rendering_style="3d_render",
            scene_type="financial concept metaphor with 3d modules",
            primary_subjects=["wealth", "income"],
            abstraction_level="conceptual",
            icons="present",
            graphs="present",
            story_arc_roles=["detail"],
        ),
        _reference_sample(
            "jiraaf-4",
            design_style="photo",
            image_style="photo",
            depth_style="flat",
            rendering_style="photo",
            scene_type="product mockup finance dashboard",
            primary_subjects=["dashboard", "laptop"],
            abstraction_level="mixed",
            story_arc_roles=["cta"],
            closing_style="cta_close",
        ),
    ]

    evaluation = _phase1_evaluation_trace(monkeypatch, samples=samples)
    print(json.dumps(evaluation, indent=2, sort_keys=True))

    assert evaluation["compiled_policy"]["dominant_image_mode"] == "3d"
    assert evaluation["compiled_policy"]["dominant_rendering_mode"] == "3d_render"
    assert evaluation["compiled_policy"]["three_d_usage"] in {"often", "sometimes"}
    assert evaluation["compiled_policy"]["reference_pattern_priority"] == "brand_dominant"
    assert "3d" in evaluation["compiled_policy"]["image_modes"]
