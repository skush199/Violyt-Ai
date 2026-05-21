from uuid import uuid4

import pytest

from app.ai.brand_asset_analysis import AssetProcessingOutcome
from app.models.brand_assets import AudienceInsightAsset, AudienceInsightStructuredData
from app.models.knowledge import KnowledgeAsset
from app.services.brand_assets import BrandAssetService


class _SessionStub:
    def __init__(self, asset_repo, structured_repo) -> None:
        self.asset_repo = asset_repo
        self.structured_repo = structured_repo

    def add(self, value) -> None:
        if isinstance(value, AudienceInsightAsset):
            self.asset_repo.record = value
        if isinstance(value, AudienceInsightStructuredData):
            self.structured_repo.record = value

    async def flush(self) -> None:
        return None


class _AudienceAssetRepoStub:
    def __init__(self) -> None:
        self.record = None

    async def get_by_knowledge_asset(self, _asset_id):
        return self.record


class _AudienceStructuredRepoStub:
    def __init__(self) -> None:
        self.record = None

    async def get_by_audience_asset(self, _asset_id):
        return self.record


@pytest.mark.asyncio
async def test_persist_audience_stores_quality_and_provenance_on_structured_row() -> None:
    audience_assets = _AudienceAssetRepoStub()
    audience_structured = _AudienceStructuredRepoStub()
    service = BrandAssetService.__new__(BrandAssetService)
    service.audience_assets = audience_assets
    service.audience_structured = audience_structured
    service.session = _SessionStub(audience_assets, audience_structured)

    tenant_id = uuid4()
    brand_space_id = uuid4()
    knowledge_asset_id = uuid4()
    asset = KnowledgeAsset(
        id=knowledge_asset_id,
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        name="Audience memo",
        original_filename="audience-memo.pdf",
        mime_type="application/pdf",
        storage_path="tenant/brand/audience-memo.pdf",
        lifecycle_state="indexed",
        channel="audience",
        metadata_json={},
        structured_data_json={},
        normalized_data_json={},
        validation_summary_json={},
    )
    outcome = AssetProcessingOutcome(
        routed_category="audience",
        channel="audience",
        extracted_text="Audience evidence",
        page_count=1,
        structured_data={
            "audience_segments": [{"label": "Mass Affluent Investor"}],
            "behaviors": ["Compares deposits with fixed-income alternatives."],
            "motivations": ["Needs predictable income with clear trade-offs."],
            "pain_points": ["Distrusts vague return language."],
            "objections": ["Needs proof that downside risk is explained clearly."],
            "desired_outcomes": ["Preserve capital while improving yield visibility."],
            "preferences": ["Concrete comparisons over abstract trust language."],
            "trust_signals": ["Transparent downside framing builds confidence."],
            "proof_cues": ["Specific return-versus-deposit comparisons increase credibility."],
            "comparison_points": ["Fixed-income options compared with deposits."],
            "demographics": {},
            "psychographics": {},
            "research_summary": "Specific comparisons and downside clarity increase trust.",
            "research_evidence": {
                "proof_cues": [
                    {
                        "value": "Specific return-versus-deposit comparisons increase credibility.",
                        "source_snippet": "Specific return-versus-deposit comparisons increase credibility.",
                        "confidence": 0.84,
                    }
                ]
            },
            "research_signal_count": 4,
            "analysis_quality": {
                "analysis_quality_score": 8.7,
                "summary_quality_score": 7.9,
                "source_agreement_score": 0.76,
                "source_agreement_types": ["audience", "proof_cues"],
            },
        },
        normalized_data={"research_summary": "Specific comparisons and downside clarity increase trust."},
        confidence=0.81,
        source_format="pdf",
    )

    await service._persist_audience(asset, outcome)

    assert audience_assets.record is not None
    assert audience_structured.record is not None
    assert audience_structured.record.research_signal_count == 4
    assert audience_structured.record.evidence_confidence == 0.81
    assert audience_structured.record.source_agreement_score == 0.76
    assert audience_structured.record.analysis_quality["analysis_quality_score"] == 8.7
    assert audience_structured.record.research_evidence["proof_cues"][0]["confidence"] == 0.84
    assert audience_assets.record.source_metadata_json["analysis_metadata"]["analysis_quality"]["source_agreement_score"] == 0.76
