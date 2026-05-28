from pathlib import Path
import json
from uuid import uuid4

from app.services.brand_scoring import BrandScoringService


def test_brand_scoring_service_builds_deterministic_scorecard() -> None:
    service = BrandScoringService(session=None)
    service._visual_review_for_assets = lambda **kwargs: {  # type: ignore[method-assign]
        "asset_count": 1,
        "page_count": 1,
        "prompt_alignment_score": 78,
        "layout_readability_score": 84,
        "density_score": 80,
        "brand_alignment_score": 86,
        "hierarchy_score": 82,
        "crowding_score": 79,
        "page_balance_score": 81,
        "ocr_confidence_score": 88,
        "visual_diagnostic_score": 82,
        "page_reviews": [{"ocr_text_excerpt": "Fresh seafood sourced with trust for urban buyers."}],
    }
    scorecard = service.build_scorecard(
        prompt="Create a static post about trusted seafood sourcing for urban buyers.",
        studio_panel={"format": "static", "file_type": "png"},
        generated_payload={
            "headline": "Fresh seafood, sourced with trust.",
            "body": "Built for urban buyers who care about quality and freshness.",
            "cta": "Learn more",
        },
        brand_context={
            "brand_name": "The Good Fish Company",
            "identity": {"brand_name": "The Good Fish Company"},
            "audience_insights": {"desired_outcomes": ["trusted seafood freshness"]},
        },
        persona_context={"name": "Urban seafood buyer", "audience_goals": ["trusted seafood freshness"]},
        objective_context={"name": "Trust building", "description": "Build trust with urban buyers."},
        explainability={
            "input_access_summary": {
                "brand_context": {"used_paths": ["identity.brand_name"], "unused_paths": ["identity.brand_description"]},
                "persona_context": {"used_paths": ["audience_goals[0]"], "unused_paths": []},
                "objective_context": {"used_paths": ["name"], "unused_paths": ["description"]},
            }
        },
        output_assets=[{"storage_path": "tenant/brand/generated/output.png", "mime_type": "image/png", "asset_kind": "image"}],
    )

    assert set(scorecard.keys()) == {"overall_score", "score_breakdown", "weighting", "summary", "developer_explanation"}
    assert scorecard["weighting"] == {
        "on_brand": 0.4,
        "prompt_adherence": 0.35,
        "relevance": 0.25,
    }
    assert set(scorecard["score_breakdown"].keys()) == {"on_brand", "prompt_adherence", "relevance"}
    assert 0 <= scorecard["overall_score"] <= 100
    assert len(scorecard["summary"]) == 3
    assert set(scorecard["developer_explanation"].keys()) == {"overall", "on_brand", "prompt_adherence", "relevance"}
    assert "formula" in scorecard["developer_explanation"]["on_brand"]
    assert "components" in scorecard["developer_explanation"]["prompt_adherence"]
    assert "base_score" in scorecard["developer_explanation"]["overall"]
    assert "boosts" in scorecard["developer_explanation"]["on_brand"]
    assert "penalties" in scorecard["developer_explanation"]["prompt_adherence"]
    assert "semantic_groups" in scorecard["developer_explanation"]["prompt_adherence"]["prompt_details"]
    assert "visual_checks_failed" in scorecard["developer_explanation"]["relevance"]
    assert "payload_semantic_groups" in scorecard["developer_explanation"]["prompt_adherence"]["prompt_details"]
    assert "alignment_evidence" in scorecard["developer_explanation"]["prompt_adherence"]["prompt_details"]


def test_brand_scoring_service_marks_render_loss_when_payload_outpaces_visible_output() -> None:
    service = BrandScoringService(session=None)
    service._visual_review_for_assets = lambda **kwargs: {  # type: ignore[method-assign]
        "asset_count": 1,
        "page_count": 1,
        "prompt_alignment_score": 22,
        "layout_readability_score": 85,
        "density_score": 72,
        "brand_alignment_score": 70,
        "hierarchy_score": 78,
        "crowding_score": 80,
        "page_balance_score": 79,
        "ocr_confidence_score": 88,
        "visual_diagnostic_score": 82,
        "page_reviews": [
            {
                "ocr_text_excerpt": "FD Bonds offer fixed, predictable returns similar to traditional fixed deposits.",
                "missing_prompt_terms": [
                    "bond comparison",
                    "beginner suitability guidance",
                    "fixed rate bonds",
                    "floating rate bonds",
                ],
            }
        ],
    }
    scorecard = service.build_scorecard(
        prompt=(
            "Create a LinkedIn static post about FD Bonds and explain the actual differences between "
            "FD Bonds, Floating Rate Bonds, and Fixed Rate Bonds. Also include guidance on which type "
            "of bond is more suitable for beginner investors"
        ),
        studio_panel={"format": "static", "file_type": "png"},
        generated_payload={
            "headline": "FD Bonds vs Fixed and Floating Rate Bonds",
            "body": (
                "FD Bonds offer fixed, predictable returns. Fixed Rate Bonds pay a set interest rate "
                "throughout their tenure. Floating Rate Bonds adjust periodically based on market benchmarks. "
                "For beginners, FD Bonds are usually the easiest starting point."
            ),
            "cta": "Explore now",
        },
        brand_context={"brand_name": "Jiraaf", "audience_insights": {"desired_outcomes": ["stable wealth building"]}},
        persona_context={"name": "Beginner investor", "audience_goals": ["stable wealth building"]},
        objective_context={"name": "Education", "description": "Explain bond choices for beginners."},
        explainability={"input_access_summary": {}},
        output_assets=[{"storage_path": "tenant/brand/generated/output.png", "mime_type": "image/png", "asset_kind": "image"}],
    )

    prompt_details = scorecard["developer_explanation"]["prompt_adherence"]["prompt_details"]

    assert prompt_details["semantic_groups"]["failed"]
    assert "fixed rate bonds" in prompt_details["payload_semantic_groups"]["matched"]
    assert prompt_details["render_loss_detected"] is True
    assert "fixed rate bonds" in prompt_details["render_loss_terms"]
    assert (
        prompt_details["alignment_evidence"]["rendered_text_prompt"]
        < prompt_details["alignment_evidence"]["payload_text_prompt"]
    )
    assert (
        prompt_details["alignment_evidence"]["effective_text_prompt"]
        < prompt_details["alignment_evidence"]["payload_text_prompt"]
    )


def test_brand_scoring_service_saves_json_to_brand_scoring_folder() -> None:
    service = BrandScoringService(session=None)
    tenant_id = uuid4()
    brand_space_id = uuid4()
    output_id = str(uuid4())
    scorecard = {
        "overall_score": 78,
        "score_breakdown": {"on_brand": 82, "prompt_adherence": 75, "relevance": 76},
        "weighting": {"on_brand": 0.4, "prompt_adherence": 0.35, "relevance": 0.25},
        "summary": ["Strong visual brand fit.", "Prompt topic is mostly followed.", "Output is relevant but slightly generic."],
        "developer_explanation": {
            "overall": {"formula": "overall = ...", "computed_from": {}, "weighted_contributions": {}, "final_score": 78},
            "on_brand": {"formula": "on_brand = ...", "score": 82, "components": {}},
            "prompt_adherence": {"formula": "prompt_adherence = ...", "score": 75, "components": {}},
            "relevance": {"formula": "relevance = ...", "score": 76, "components": {}},
        },
    }
    written = service.save_scorecard(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        output_id=output_id,
        scorecard=scorecard,
    )
    path = Path(written)
    try:
        assert path.exists()
        assert path.parent.name == "brand_scoring"
        assert path.parent.parent.name == str(brand_space_id)
        assert path.parent.parent.parent.name == str(tenant_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload == scorecard
    finally:
        if path.exists():
            path.unlink()
