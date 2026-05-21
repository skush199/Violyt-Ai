from uuid import uuid4

import pytest
from types import SimpleNamespace

from app.models.brand_assets import BrandLogoAsset, BrandLogoMetadata
from app.models.knowledge import KnowledgeAsset
from app.services.data_validation import DataValidatorService


@pytest.mark.asyncio
async def test_resolve_logos_exposes_underlying_storage_path() -> None:
    service = DataValidatorService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    knowledge_asset_id = uuid4()
    logo_asset_id = uuid4()

    class _LogoAssetsRepo:
        async def list_for_brand(self, tenant_id, brand_space_id):
            return [
                BrandLogoAsset(
                    id=logo_asset_id,
                    tenant_id=tenant_id,
                    brand_space_id=brand_space_id,
                    knowledge_asset_id=knowledge_asset_id,
                    variant_label="primary",
                    compatibility=["light", "dark"],
                    usage_metadata={"placement": "top_right"},
                    source_metadata_json={},
                )
            ]

    class _LogoMetadataRepo:
        async def get_by_logo_asset(self, brand_logo_asset_id):
            return BrandLogoMetadata(
                tenant_id=tenant_id,
                brand_space_id=brand_space_id,
                brand_logo_asset_id=brand_logo_asset_id,
                logo_colors=[{"hex": "#102A83"}],
                size_rules={"min_width": 120},
                font_details={"family": "Brand Serif"},
                tagline="Trusted guidance",
                inference_metadata={},
            )

    class _KnowledgeAssetsRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return KnowledgeAsset(
                id=asset_id,
                tenant_id=tenant_id,
                brand_space_id=brand_space_id,
                name="Jiraaf logo",
                original_filename="jiraaf-logo.png",
                mime_type="image/png",
                storage_path="tenant/brand/uploads/jiraaf-logo.png",
                lifecycle_state="indexed",
                channel="brand",
                metadata_json={},
                structured_data_json={},
                normalized_data_json={},
                validation_summary_json={},
            )

        async def list_by_field(self, brand_space_id, field_key, tenant_id=None, active_only=False):
            return []

    service.logo_assets = _LogoAssetsRepo()
    service.logo_metadata = _LogoMetadataRepo()
    service.assets = _KnowledgeAssetsRepo()

    resolved = await service._resolve_logos(tenant_id, brand_space_id)

    assert resolved["primary_storage_path"] == "tenant/brand/uploads/jiraaf-logo.png"
    assert resolved["logos"][0]["storage_path"] == "tenant/brand/uploads/jiraaf-logo.png"
    assert resolved["logos"][0]["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_resolve_logos_falls_back_to_active_logo_attachments() -> None:
    service = DataValidatorService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    knowledge_asset_id = uuid4()

    class _LogoAssetsRepo:
        async def list_for_brand(self, tenant_id, brand_space_id):
            return []

    class _LogoMetadataRepo:
        async def get_by_logo_asset(self, brand_logo_asset_id):
            return None

    class _KnowledgeAssetsRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

        async def list_by_field(self, brand_space_id, field_key, tenant_id=None, active_only=False):
            assert field_key == "logo"
            assert active_only is True
            return [
                KnowledgeAsset(
                    id=knowledge_asset_id,
                    tenant_id=tenant_id,
                    brand_space_id=brand_space_id,
                    name="Jiraaf logo",
                    original_filename="jiraaf-logo.png",
                    mime_type="image/png",
                    storage_path="tenant/brand/logo/jiraaf-logo.png",
                    lifecycle_state="indexed",
                    channel="brand_asset",
                    field_key="logo",
                    asset_category="logo",
                    metadata_json={"variant_label": "primary"},
                    structured_data_json={
                        "logo_colors": [{"hex": "#102A83"}],
                        "size_rules": {"min_width": 120},
                        "font_details": {"family": "Brand Serif"},
                        "tagline": "Trusted guidance",
                    },
                    normalized_data_json={"usage_metadata": {"compatible_backgrounds": ["light"]}},
                    validation_summary_json={},
                    is_active=True,
                )
            ]

    service.logo_assets = _LogoAssetsRepo()
    service.logo_metadata = _LogoMetadataRepo()
    service.assets = _KnowledgeAssetsRepo()

    resolved = await service._resolve_logos(tenant_id, brand_space_id)

    assert resolved["primary_storage_path"] == "tenant/brand/logo/jiraaf-logo.png"
    assert resolved["logos"][0]["asset_id"] == str(knowledge_asset_id)
    assert resolved["logos"][0]["storage_path"] == "tenant/brand/logo/jiraaf-logo.png"
    assert resolved["logos"][0]["variant_label"] == "primary"
    assert resolved["logo_rules"]["compatibility"] == ["light"]
    assert resolved["logo_rules"]["taglines"] == ["Trusted guidance"]


def test_normalized_palette_role_map_preserves_explicit_roles() -> None:
    resolved = DataValidatorService._normalized_palette_role_map(
        [
            {"role": "primary", "hex_code": "#003975", "color_name": "Regal Blue"},
            {"role": "secondary", "hex_code": "#F4C542", "color_name": "Golden Sand"},
            {"role": "accent", "hex_code": "#00CB91", "color_name": "Caribbean Green"},
            {"role": "background", "hex_code": "#F8F2E6", "color_name": "Warm Ivory"},
        ]
    )

    assert resolved["primary"] == "#003975"
    assert resolved["secondary"] == "#F4C542"
    assert resolved["accent"] == "#00CB91"
    assert resolved["background"] == "#F8F2E6"


def test_normalized_palette_role_map_can_use_template_evidence_for_missing_roles() -> None:
    resolved = DataValidatorService._normalized_palette_role_map(
        [
            {"role": "accent", "hex_code": "#00CB91", "color_name": "Caribbean Green"},
            {"role": "neutral", "hex_code": "#F8F2E6", "color_name": "Warm Ivory"},
            {"role": "secondary", "hex_code": "#003975", "color_name": "Regal Blue"},
            {"role": "primary", "hex_code": "#F4C542", "color_name": "Golden Sand"},
        ]
    )

    assert resolved["primary"] == "#F4C542"
    assert resolved["secondary"] == "#003975"
    assert resolved["background"] == "#F8F2E6"


@pytest.mark.asyncio
async def test_resolve_audience_preserves_distinct_research_summaries() -> None:
    service = DataValidatorService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    asset_one_id = uuid4()
    asset_two_id = uuid4()

    class _AudienceAssetsRepo:
        async def list_for_brand(self, tenant_id, brand_space_id):
            return [
                SimpleNamespace(id=asset_one_id),
                SimpleNamespace(id=asset_two_id),
            ]

    class _AudienceStructuredRepo:
        async def get_by_audience_asset(self, asset_id):
            if asset_id == asset_one_id:
                return SimpleNamespace(
                    audience_segments=[{"label": "Mass Affluent Investor"}],
                    behaviors=["Compares options before committing"],
                    motivations=["Wants steady income without complexity"],
                    pain_points=["Finds fixed-income jargon opaque"],
                    objections=["Needs proof that risk is explained clearly"],
                    desired_outcomes=["Earn predictable income without feeling reckless"],
                    preferences=["Short explainers"],
                    trust_signals=["Transparent downside framing builds confidence"],
                    proof_cues=["Plain-English risk framing outperforms category jargon"],
                    comparison_points=["Deposits vs fixed-income options"],
                    demographics={"age_band": "30-45"},
                    psychographics={"mindset": "careful planner"},
                    research_summary="Investors respond better when risk is explained in plain English with clear downside framing.",
                )
            if asset_id == asset_two_id:
                return SimpleNamespace(
                    audience_segments=[{"label": "Mass Affluent Investor"}],
                    behaviors=["Needs proof before acting"],
                    motivations=["Values capital preservation"],
                    pain_points=["Distrusts inflated return language"],
                    objections=["Does not trust vague return claims"],
                    desired_outcomes=["Preserve capital while improving yield visibility"],
                    preferences=["Credible comparisons"],
                    trust_signals=["Comparisons work better when trade-offs are explicit"],
                    proof_cues=["Concrete proof beats abstract trust language"],
                    comparison_points=["Fixed-income options compared with deposits"],
                    demographics={"income_band": "upper middle"},
                    psychographics={"mindset": "evidence seeking"},
                    research_summary="Concrete proof beats abstract trust language, especially when comparing deposits with fixed-income options.",
                )
            return None

    service.audience_assets = _AudienceAssetsRepo()
    service.audience_structured = _AudienceStructuredRepo()

    resolved = await service._resolve_audience(tenant_id, brand_space_id)

    assert resolved["segments"][0]["label"] == "Mass Affluent Investor"
    assert resolved["research_signal_count"] == 2
    assert resolved["research_summaries"] == [
        "Investors respond better when risk is explained in plain English with clear downside framing.",
        "Concrete proof beats abstract trust language, especially when comparing deposits with fixed-income options.",
    ]
    assert resolved["research_highlights"] == [
        "Plain-English risk framing outperforms category jargon",
        "Investors respond better when risk is explained in plain English with clear downside framing.",
        "Transparent downside framing builds confidence",
        "Concrete proof beats abstract trust language, especially when comparing deposits with fixed-income options.",
        "Deposits vs fixed-income options",
        "Needs proof that risk is explained clearly",
    ]
    assert resolved["objections"] == [
        "Needs proof that risk is explained clearly",
        "Does not trust vague return claims",
    ]
    assert resolved["trust_signals"] == [
        "Transparent downside framing builds confidence",
        "Comparisons work better when trade-offs are explicit",
    ]
    assert resolved["proof_cues"] == [
        "Plain-English risk framing outperforms category jargon",
        "Concrete proof beats abstract trust language",
    ]
    assert "plain English with clear downside framing" in resolved["research_summary"]
    assert "Concrete proof beats abstract trust language" in resolved["research_summary"]


@pytest.mark.asyncio
async def test_resolve_audience_merges_source_evidence_with_summary_highlights() -> None:
    service = DataValidatorService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    asset_id = uuid4()

    class _AudienceAssetsRepo:
        async def list_for_brand(self, tenant_id, brand_space_id):
            return [
                SimpleNamespace(
                    id=asset_id,
                    source_metadata_json={
                        "analysis_metadata": {
                            "audience_evidence": {
                                "proof_cues": [
                                    {
                                        "value": "Specific comparisons against deposits increase response quality.",
                                        "source_snippet": "Specific comparisons against deposits increase response quality.",
                                        "confidence": 0.93,
                                    }
                                ],
                                "trust_signals": [
                                    {
                                        "value": "Named downside scenarios increase trust.",
                                        "source_snippet": "Named downside scenarios increase trust.",
                                        "confidence": 0.88,
                                    }
                                ],
                            }
                        }
                    },
                )
            ]

    class _AudienceStructuredRepo:
        async def get_by_audience_asset(self, asset_id):
            return SimpleNamespace(
                audience_segments=[{"label": "Mass Affluent Investor"}],
                behaviors=[],
                motivations=[],
                pain_points=[],
                objections=["Rejects copy that sounds promotional without proof."],
                desired_outcomes=["Wants risk and return trade-offs explained clearly."],
                preferences=[],
                trust_signals=[],
                proof_cues=[],
                comparison_points=[],
                demographics={},
                psychographics={},
                research_summary="People trust the message more when the copy names concrete trade-offs.",
            )

    service.audience_assets = _AudienceAssetsRepo()
    service.audience_structured = _AudienceStructuredRepo()

    resolved = await service._resolve_audience(tenant_id, brand_space_id)

    assert resolved["research_highlights"] == [
        "Specific comparisons against deposits increase response quality.",
        "People trust the message more when the copy names concrete trade-offs.",
        "Named downside scenarios increase trust.",
        "Rejects copy that sounds promotional without proof.",
        "Wants risk and return trade-offs explained clearly.",
    ]
    assert resolved["research_evidence"][0]["field"] == "proof_cues"
    assert resolved["research_evidence"][0]["confidence"] == 0.93


@pytest.mark.asyncio
async def test_resolve_audience_prefers_persisted_structured_evidence_quality_when_ranking() -> None:
    service = DataValidatorService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    weak_asset_id = uuid4()
    strong_asset_id = uuid4()

    class _AudienceAssetsRepo:
        async def list_for_brand(self, tenant_id, brand_space_id):
            return [
                SimpleNamespace(id=weak_asset_id, confidence=0.94, source_metadata_json={}),
                SimpleNamespace(id=strong_asset_id, confidence=0.82, source_metadata_json={}),
            ]

    class _AudienceStructuredRepo:
        async def get_by_audience_asset(self, asset_id):
            if asset_id == weak_asset_id:
                return SimpleNamespace(
                    audience_segments=[],
                    behaviors=[],
                    motivations=[],
                    pain_points=[],
                    objections=[],
                    desired_outcomes=[],
                    preferences=[],
                    trust_signals=[],
                    proof_cues=[],
                    comparison_points=[],
                    demographics={},
                    psychographics={},
                    research_summary="",
                    research_evidence={
                        "proof_cues": [
                            {
                                "value": "Generic reassurance language sounds acceptable.",
                                "source_snippet": "Generic reassurance language sounds acceptable.",
                                "confidence": 0.94,
                            }
                        ]
                    },
                    research_signal_count=1,
                    analysis_quality={"analysis_quality_score": 2.1, "source_agreement_score": 0.0},
                    evidence_confidence=0.94,
                    source_agreement_score=0.0,
                )
            if asset_id == strong_asset_id:
                return SimpleNamespace(
                    audience_segments=[],
                    behaviors=[],
                    motivations=[],
                    pain_points=[],
                    objections=[],
                    desired_outcomes=[],
                    preferences=[],
                    trust_signals=[],
                    proof_cues=[],
                    comparison_points=[],
                    demographics={},
                    psychographics={},
                    research_summary="",
                    research_evidence={
                        "proof_cues": [
                            {
                                "value": "Specific return-versus-deposit comparisons increase credibility.",
                                "source_snippet": "Specific return-versus-deposit comparisons increase credibility.",
                                "confidence": 0.78,
                            }
                        ]
                    },
                    research_signal_count=4,
                    analysis_quality={"analysis_quality_score": 8.6, "source_agreement_score": 0.81},
                    evidence_confidence=0.82,
                    source_agreement_score=0.81,
                )
            return None

    service.audience_assets = _AudienceAssetsRepo()
    service.audience_structured = _AudienceStructuredRepo()

    resolved = await service._resolve_audience(tenant_id, brand_space_id)

    assert resolved["research_highlights"][0] == "Specific return-versus-deposit comparisons increase credibility."
    assert resolved["research_evidence"][0]["source_agreement_score"] == 0.81
    assert resolved["research_evidence"][0]["analysis_quality_score"] == 8.6
    assert resolved["research_quality"]["source_agreement_score"] == 0.81
