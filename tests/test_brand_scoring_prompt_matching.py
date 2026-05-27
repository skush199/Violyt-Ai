from app.services.brand_scoring import BrandScoringService


def test_prompt_alignment_treats_close_semantic_equivalents_as_matches() -> None:
    prompt = "Use a quiet warning tone about how safe savings erodes over time."
    observed = "A sharp reminder that traditional savings declines subtly over time."

    score = BrandScoringService._prompt_alignment_score(prompt, observed, [])

    assert score >= 80


def test_prompt_term_diagnostics_do_not_flag_semantic_equivalents_as_missing() -> None:
    prompt = "Use a quiet warning tone about how safe savings erodes over time."
    observed = "A sharp reminder that traditional savings declines subtly over time."

    matched, missing = BrandScoringService._prompt_term_diagnostics(prompt, observed, [])

    assert "traditional" in matched
    assert "savings" in matched
    assert "erode" in matched
    assert "subtle" in matched
    assert "warning" in matched
    assert "quiet" not in missing
    assert "safe" not in missing
    assert "erode" not in missing


def test_prompt_term_diagnostics_uses_content_intents_not_instruction_words() -> None:
    prompt = (
        "Create a LinkedIn static post about FD Bonds and explain the actual differences between "
        "FD Bonds, Floating Rate Bonds, and Fixed Rate Bonds. Also include guidance on which type "
        "of bond is more suitable for beginner investors"
    )
    observed = (
        "FD Bonds offer fixed returns and are beginner-friendly. "
        "Floating Rate Bonds adjust with market rates."
    )

    matched, missing = BrandScoringService._prompt_term_diagnostics(prompt, observed, [])

    assert "fd bonds" in matched
    assert "floating rate bonds" in matched
    assert "fixed rate bonds" in missing
    assert "beginner suitability guidance" not in missing
    assert "bond comparison" in missing
    assert "explain" not in missing
    assert "actual" not in missing
    assert "differences" not in missing


def test_static_format_diagnostics_include_content_distillation() -> None:
    prompt = (
        "Create a LinkedIn static post about FD Bonds and explain the actual differences between "
        "FD Bonds, Floating Rate Bonds, and Fixed Rate Bonds. Also include guidance on which type "
        "of bond is more suitable for beginner investors"
    )
    visual_review = {
        "page_count": 1,
        "layout_readability_score": 92,
        "hierarchy_score": 84,
        "crowding_score": 86,
        "page_balance_score": 82,
        "style_alignment_score": 80,
        "density_score": 78,
        "page_reviews": [
            {
                "ocr_text_excerpt": (
                    "FD Bonds offer fixed returns. Floating Rate Bonds adjust with market rates. "
                    "Good for beginners."
                ),
                "hierarchy_score": 84,
                "prompt_alignment_score": 54,
                "word_count": 18,
                "text_box_count": 2,
            }
        ],
    }

    diagnostics = BrandScoringService._format_fit_details(
        prompt=prompt,
        studio_panel={"format": "static"},
        visual_review=visual_review,
        output_assets=[{"asset_kind": "image"}],
        generated_payload={
            "headline": "FD Bonds vs Floating Rate Bonds",
            "body": "FD Bonds offer fixed returns. Floating Rate Bonds adjust with market rates. Good for beginners.",
        },
    )

    content_distillation = next(check for check in diagnostics["checks"] if check["name"] == "content_distillation")

    assert content_distillation["score"] < 90
    assert diagnostics["format"] == "static"


def test_carousel_progression_reacts_to_prompt_complexity() -> None:
    visual_review = {
        "page_count": 2,
        "layout_readability_score": 88,
        "hierarchy_score": 80,
        "crowding_score": 84,
        "page_balance_score": 81,
        "style_alignment_score": 78,
        "density_score": 75,
        "page_reviews": [
            {
                "ocr_text_excerpt": "FD Bonds offer fixed returns.",
                "hierarchy_score": 80,
                "prompt_alignment_score": 62,
                "word_count": 8,
                "text_box_count": 2,
            },
            {
                "ocr_text_excerpt": "Floating Rate Bonds adjust with market rates.",
                "hierarchy_score": 78,
                "prompt_alignment_score": 60,
                "word_count": 9,
                "text_box_count": 2,
            },
        ],
    }
    complex_prompt = (
        "Create a carousel comparing FD Bonds, Floating Rate Bonds, and Fixed Rate Bonds, "
        "and explain which is best for beginner investors"
    )
    simple_prompt = "Create a carousel about FD Bonds for beginner investors"

    complex_diagnostics = BrandScoringService._format_fit_details(
        prompt=complex_prompt,
        studio_panel={"format": "carousel"},
        visual_review=visual_review,
        output_assets=[{"asset_kind": "image"}, {"asset_kind": "image"}],
        generated_payload={"headline": "FD Bonds vs Floating Rate Bonds"},
    )
    simple_diagnostics = BrandScoringService._format_fit_details(
        prompt=simple_prompt,
        studio_panel={"format": "carousel"},
        visual_review=visual_review,
        output_assets=[{"asset_kind": "image"}, {"asset_kind": "image"}],
        generated_payload={"headline": "FD Bonds for Beginners"},
    )

    complex_progression = next(check for check in complex_diagnostics["checks"] if check["name"] == "slide_progression")
    simple_progression = next(check for check in simple_diagnostics["checks"] if check["name"] == "slide_progression")

    assert complex_progression["score"] < simple_progression["score"]


def test_infographic_format_diagnostics_penalize_sparse_complex_content() -> None:
    prompt = (
        "Create an infographic that compares FD Bonds, Floating Rate Bonds, and Fixed Rate Bonds, "
        "with guidance for beginners"
    )
    visual_review = {
        "page_count": 1,
        "layout_readability_score": 82,
        "hierarchy_score": 78,
        "crowding_score": 80,
        "page_balance_score": 76,
        "style_alignment_score": 79,
        "density_score": 70,
        "page_reviews": [
            {
                "ocr_text_excerpt": "FD Bonds are simple for beginners.",
                "hierarchy_score": 78,
                "prompt_alignment_score": 52,
                "word_count": 10,
                "text_box_count": 1,
            }
        ],
    }

    diagnostics = BrandScoringService._format_fit_details(
        prompt=prompt,
        studio_panel={"format": "infographic"},
        visual_review=visual_review,
        output_assets=[{"asset_kind": "image"}],
        generated_payload={"headline": "Bond Types Explained"},
    )

    content_coverage = next(check for check in diagnostics["checks"] if check["name"] == "content_coverage")
    section_structure = next(check for check in diagnostics["checks"] if check["name"] == "section_structure")

    assert content_coverage["score"] < 60
    assert section_structure["score"] < 70
