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

    assert set(scorecard.keys()) == {"overall_score", "score_breakdown", "weighting", "summary"}
    assert scorecard["weighting"] == {
        "on_brand": 0.4,
        "prompt_adherence": 0.35,
        "relevance": 0.25,
    }
    assert set(scorecard["score_breakdown"].keys()) == {"on_brand", "prompt_adherence", "relevance"}
    assert 0 <= scorecard["overall_score"] <= 100
    assert len(scorecard["summary"]) == 3


def test_brand_scoring_service_saves_json_to_brand_scoring_folder() -> None:
    service = BrandScoringService(session=None)
    output_id = str(uuid4())
    scorecard = {
        "overall_score": 78,
        "score_breakdown": {"on_brand": 82, "prompt_adherence": 75, "relevance": 76},
        "weighting": {"on_brand": 0.4, "prompt_adherence": 0.35, "relevance": 0.25},
        "summary": ["Strong visual brand fit.", "Prompt topic is mostly followed.", "Output is relevant but slightly generic."],
    }
    written = service.save_scorecard(output_id=output_id, scorecard=scorecard)
    path = Path(written)
    try:
        assert path.exists()
        assert path.parent.name == "brand_scoring"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload == scorecard
    finally:
        if path.exists():
            path.unlink()
