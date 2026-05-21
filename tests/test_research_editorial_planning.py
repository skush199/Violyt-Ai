from app.services.research_editorial_planning import ResearchEditorialPlanningService


def test_research_editorial_planning_activates_for_research_heavy_carousel() -> None:
    service = ResearchEditorialPlanningService()

    brief = service.build(
        prompt=(
            "Write a LinkedIn carousel on the India-New Zealand Free Trade Agreement signed on 27 April 2026. "
            "Go beyond the headline numbers and explain why it matters strategically."
        ),
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
        brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={"name": "Thought Leadership"},
        knowledge_brief=[{"channel": "strategy", "content": "Explain what India negotiated, not just what it gained."}],
        live_research={
            "status": "completed",
            "summary": "The agreement included tariff reductions and phased access commitments.",
            "verified_facts": [
                {
                    "label": "Signing date",
                    "value": "27 April 2026",
                    "source_title": "Official release",
                    "source_url": "https://example.com/release",
                }
            ],
            "sources": [{"title": "Official release", "url": "https://example.com/release"}],
        },
        content_format_guide={"format_expectations": {"carousel": {"preferred_slide_count": 5}}},
    )

    assert brief["active"] is True
    assert brief["mode"] == "research_editorial"
    assert brief["format_family"] == "carousel"
    assert brief["preferred_slide_count"] == 5
    assert any(item["role"] == "hook" for item in brief["outline"])
    assert any("Signing date: 27 April 2026" in item for item in brief["insight_hierarchy"])
    assert brief["fact_model"]["verified_facts"][0]["label"] == "Signing date"
    assert brief["ranked_sources"][0]["label"] == "Official release"
    assert brief["citation_rules"]["style"] == "light_on_canvas_citations"
    assert any("Treat verified_facts as the only claims" in item for item in brief["source_backing_rules"])


def test_research_editorial_planning_separates_inference_and_uncertainty() -> None:
    service = ResearchEditorialPlanningService()

    brief = service.build(
        prompt="Write a blog analyzing what the rate cut could mean for fixed-income investors.",
        studio_panel={"platform_preset": "linkedin", "format": "static", "file_type": "png"},
        brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        knowledge_brief=[{"channel": "macro", "content": "The market may be underpricing duration sensitivity."}],
        live_research={
            "status": "completed",
            "summary": "The move may signal a softer policy stance, but the transmission path is still unclear and likely phased.",
            "verified_facts": [
                {
                    "label": "Policy move",
                    "value": "25 bps cut announced",
                    "source_title": "Central bank statement",
                    "source_url": "https://example.com/cb",
                }
            ],
            "sources": [{"title": "Central bank statement", "url": "https://example.com/cb"}],
            "ranked_sources": [{"rank": 1, "title": "Central bank statement", "url": "https://example.com/cb", "support_count": 1}],
            "inferences": ["The move may signal a softer policy stance."],
            "uncertainties": ["The transmission path is still unclear and likely phased."],
        },
    )

    assert brief["fact_model"]["verified_facts"][0]["value"] == "25 bps cut announced"
    assert "softer policy stance" in brief["fact_model"]["inferences"][0]
    assert "still unclear" in brief["fact_model"]["uncertainties"][0]
    assert brief["citation_rules"]["style"] in {"light_source_cues", "light_on_canvas_citations"}


def test_research_editorial_planning_stays_standard_for_simple_social_prompt() -> None:
    service = ResearchEditorialPlanningService()

    brief = service.build(
        prompt="Create an Instagram post about investing confidence with Jiraaf.",
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
        brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        knowledge_brief=[],
        live_research={},
    )

    assert brief["active"] is False
    assert brief["mode"] == "standard"
    assert brief["format_family"] == "static"


def test_research_editorial_planning_filters_visual_template_knowledge_from_insights() -> None:
    service = ResearchEditorialPlanningService()

    brief = service.build(
        prompt="Write a LinkedIn carousel explaining why the latest trade agreement matters strategically.",
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
        brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        knowledge_brief=[
            {"channel": "strategy", "content": "Look at what India negotiated, not just the tariff headline."},
            {"channel": "logo", "content": "Logo palette uses blue and yellow with curved shapes."},
            {"channel": "reference_creative", "content": "Reference creative uses an editorial composition and premium spacing."},
        ],
        live_research={"status": "unavailable", "summary": "", "verified_facts": []},
    )

    assert any("India negotiated" in item for item in brief["insight_hierarchy"])
    assert not any("palette" in item.casefold() for item in brief["insight_hierarchy"])
    assert not any("reference creative" in item.casefold() for item in brief["insight_hierarchy"])


def test_research_editorial_planning_enforces_source_backing_without_verified_facts() -> None:
    payload = {
        "headline": "65% of women now prefer fixed income",
        "body": "Women participation has risen 20% since 2023 according to market data.",
        "cta": "Explore Jiraaf",
        "hashtags": ["#Jiraaf"],
        "metadata": {
            "supporting_line": "65% of women choose bonds first.",
            "proof_points": ["20% growth since 2023", "Stable long-term wealth"],
            "stat_highlights": ["65% prefer fixed income"],
            "claim_evidence_pairs": [{"claim": "Women participation up 20%", "evidence": "Market data"}],
        },
    }
    brief = {
        "active": True,
        "needs_live_research": True,
        "research_status": "unavailable",
        "topic_focus": "Women borrowers are reshaping credit markets",
        "angle": "Explain the structural shift without overstating unsupported current numbers.",
        "reader_payoff": "Reader should understand the shift without relying on unsupported stats.",
        "insight_hierarchy": ["The change is real, but exact current figures still need verification."],
        "fact_model": {
            "verified_facts": [],
            "inferences": ["The shift appears meaningful, but exact current figures still need verification."],
            "uncertainties": ["External verification was unavailable, so current percentages should stay qualitative."],
        },
        "ranked_sources": [],
    }

    sanitized = ResearchEditorialPlanningService.enforce_source_backing(
        payload,
        prompt_text="Create a LinkedIn post about how women borrowers are reshaping credit markets.",
        brief=brief,
    )

    assert sanitized["headline"] == "Women borrowers are reshaping credit markets"
    assert "20%" not in sanitized["body"]
    assert sanitized["metadata"]["stat_highlights"] == []
    assert sanitized["metadata"]["claim_evidence_pairs"] == []
    assert sanitized["metadata"]["proof_points"]


def test_research_editorial_planning_marks_hard_fail_when_fresh_research_is_required_but_unavailable() -> None:
    brief = ResearchEditorialPlanningService().build(
        prompt="Write a LinkedIn carousel analyzing the latest India-New Zealand FTA signed on 27 April 2026.",
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
        brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        knowledge_brief=[],
        live_research={"status": "unavailable", "summary": "", "verified_facts": [], "ranked_sources": []},
    )

    assert brief["research_guard"]["strict_mode"] is True
    assert brief["research_guard"]["hard_fail"] is True
