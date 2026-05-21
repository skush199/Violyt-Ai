from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.ai.brand_intelligence import BrandIntelligenceService


def test_brand_intelligence_merges_guardrail_section_metadata() -> None:
    service = BrandIntelligenceService()
    brand = SimpleNamespace(
        id=uuid4(),
        name="Acme",
        description="Clear brand",
        industry_category="Technology / SaaS",
    )
    guardrail = SimpleNamespace(
        id=uuid4(),
        positive_word_bank=["clarity"],
        replaceable_words=[],
        negative_word_bank=[],
        dos=["Be clear"],
        donts=["Be vague"],
        forbidden_prompt_patterns=[],
        restricted_topics=[],
        restricted_claims=[],
        blocked_words=[],
        custom_rules=["Avoid hype claims"],
    )

    context = service.build_context(
        brand_space=brand,
        sections=[
            {
                "section_code": "guardrails",
                "payload": {
                    "positive_word_bank_asset_ids": [str(uuid4())],
                    "word_bank_assets": {"positive": [{"name": "approved-words.pdf"}]},
                },
            }
        ],
        personas=[],
        guardrails=[guardrail],
        objectives=[],
    )

    assert context["guardrails"]["positive_word_bank"] == ["clarity"]
    assert context["guardrails"]["custom_rules"] == ["Avoid hype claims"]
    assert context["guardrails"]["positive_word_bank_asset_ids"]
    assert context["guardrails"]["word_bank_assets"]["positive"][0]["name"] == "approved-words.pdf"


def test_brand_intelligence_preserves_section_payloads_for_generation_context() -> None:
    service = BrandIntelligenceService()
    brand = SimpleNamespace(
        id=uuid4(),
        name="Fallback Name",
        description="Fallback description",
        industry_category="Fallback category",
    )

    context = service.build_context(
        brand_space=brand,
        sections=[
            {
                "section_code": "identity",
                "payload": {
                    "brand_name": "Mapped Name",
                    "brand_description": "Mapped description",
                    "industry_category": "Finance",
                },
            },
            {
                "section_code": "knowledge",
                "payload": {
                    "website": "https://example.com",
                    "competitor_brand_name": "Competitor Co",
                },
            },
            {
                "section_code": "personas",
                "payload": {
                    "personas": [
                        {
                            "name": "Mass Affluent Investor",
                            "content_behavior": {"selected_audiences": ["Investors"]},
                        }
                    ]
                },
            },
            {
                "section_code": "objectives",
                "payload": {
                    "objectives": [
                        {
                            "name": "Lead Gen",
                            "configuration": {"market_positioning": "Premium trust"},
                        }
                    ]
                },
            },
        ],
        personas=[],
        guardrails=[],
        objectives=[],
    )

    assert context["brand_name"] == "Mapped Name"
    assert context["brand_description"] == "Mapped description"
    assert context["industry_category"] == "Finance"
    assert context["knowledge"]["website"] == "https://example.com"
    assert context["personas"]["personas"][0]["name"] == "Mass Affluent Investor"
    assert context["objectives"]["objectives"][0]["name"] == "Lead Gen"
