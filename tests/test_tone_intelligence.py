from types import SimpleNamespace

from app.ai.tone_intelligence import ToneIntelligenceService


class _FailingProvider:
    def generate_structured_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("provider unavailable")


class _StaticProvider:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def generate_structured_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return dict(self.payload)


def test_tone_score_returns_percentage_like_output() -> None:
    service = ToneIntelligenceService()
    service.providers = SimpleNamespace(get_text_provider=lambda *_args, **_kwargs: _FailingProvider())

    result = service.evaluate(
        content="Bold premium messaging with trust and clarity.",
        brand_context={
            "voice_tone": {"tone_attributes": ["Bold", "Premium"]},
            "guardrails": {"positive_word_bank": ["clarity"], "blocked_words": []},
        },
        persona_context={},
    )
    assert 0 <= result["score"] <= 100
    assert isinstance(result["rewrite_suggestions"], list)
    assert isinstance(result["persuasion_dimensions"], dict)
    assert isinstance(result["field_guidance"], dict)


def test_tone_qa_flags_generic_proof_light_and_objection_blind_copy() -> None:
    service = ToneIntelligenceService()
    service.providers = SimpleNamespace(get_text_provider=lambda *_args, **_kwargs: _FailingProvider())

    result = service.evaluate(
        content=(
            "Premium smarter growth for modern teams. "
            "Premium smarter growth for modern teams. "
            "Premium smarter growth for modern teams. "
            "Learn more."
        ),
        brand_context={
            "voice_tone": {"tone_attributes": ["Bold"]},
            "guardrails": {"positive_word_bank": ["clarity"], "blocked_words": []},
        },
        persona_context={
            "audience_goals": ["Reduce reporting time"],
            "motivations": ["Move faster"],
            "fears_and_pain_points": ["Wasting hours on manual reporting"],
            "objections": ["Not sure switching tools is worth the risk"],
            "content_behavior": {"preferred_proof": ["benchmarks", "before-after evidence"]},
        },
    )

    assert any("under-supported by proof" in item for item in result["deviations"])
    assert any("generic marketing language" in item for item in result["deviations"])
    assert any("likely objections or pain points" in item for item in result["deviations"])
    assert any("repetitive or samey" in item for item in result["deviations"])
    assert any("claim-and-evidence support" in item for item in result["rewrite_suggestions"])
    assert any("audience objection directly" in item for item in result["rewrite_suggestions"])


def test_tone_qa_uses_structured_metadata_for_proof_and_objection_scoring() -> None:
    service = ToneIntelligenceService()
    service.providers = SimpleNamespace(get_text_provider=lambda *_args, **_kwargs: _FailingProvider())

    result = service.evaluate(
        content="Close the books faster with guided onboarding. Book a demo.",
        brand_context={
            "voice_tone": {"tone_attributes": ["Confident"]},
            "guardrails": {"positive_word_bank": ["clarity"], "blocked_words": []},
        },
        persona_context={
            "fears_and_pain_points": ["Manual reporting delays"],
            "objections": ["Switching tools feels risky"],
        },
        content_payload={
            "headline": "Close the books faster",
            "body": "Guided onboarding helps finance teams move without disruption.",
            "cta": "Book a demo",
            "metadata": {
                "hook_type": "problem-led",
                "proof_points": ["Finance teams save 6 hours a week on recurring reporting"],
                "trust_builders": ["SOC 2 ready", "Used by multi-entity finance teams"],
                "objection_handling": ["Switching feels risky, so onboarding is guided end-to-end."],
                "claim_evidence_pairs": [
                    {
                        "claim": "Reduce close prep time",
                        "evidence": "Finance teams save 6 hours a week on recurring reporting",
                    }
                ],
            },
        },
        message_strategy={
            "primary_campaign_theme": "Faster close visibility with less manual work",
            "important_keywords": ["close", "reporting", "finance"],
        },
        objective_context={"name": "Demo generation", "description": "Drive finance demo requests"},
    )

    assert result["persuasion_dimensions"]["proof_strength"] >= 75
    assert result["persuasion_dimensions"]["objection_handling"] >= 75
    assert any("Claim/evidence pairs" in item for item in result["matched_signals"])
    assert any("Structured objection handling" in item for item in result["matched_signals"])
    assert not any("under-supported by proof" in item for item in result["deviations"])
    assert not any("likely objections or pain points" in item for item in result["deviations"])


def test_tone_qa_flags_persuasion_metadata_that_is_not_grounded_in_audience_evidence() -> None:
    service = ToneIntelligenceService()
    service.providers = SimpleNamespace(get_text_provider=lambda *_args, **_kwargs: _FailingProvider())

    result = service.evaluate(
        content="Automate reporting with total peace of mind. Book a demo.",
        brand_context={
            "voice_tone": {"tone_attributes": ["Confident"]},
            "guardrails": {"positive_word_bank": ["clarity"], "blocked_words": []},
            "audience_insights": {
                "objections": ["Needs proof that risk and returns are explained clearly"],
                "pain_points": ["Finds fixed-income language opaque"],
                "trust_signals": ["Transparent downside framing builds confidence"],
                "proof_cues": ["Concrete proof beats abstract trust language"],
                "comparison_points": ["Compare fixed-income options against deposits"],
            },
        },
        persona_context={},
        content_payload={
            "headline": "Automate reporting with total peace of mind",
            "body": "Enterprise-ready workflows make reporting easier.",
            "cta": "Book a demo",
            "metadata": {
                "hook_type": "proof-led",
                "trust_builders": ["Used by fast-growing SaaS teams"],
                "objection_handling": ["No need to change your process overnight."],
                "claim_evidence_pairs": [
                    {
                        "claim": "Cut close time",
                        "evidence": "Finance teams move faster with guided workflows",
                    }
                ],
            },
        },
    )

    assert any("weakly grounded in known audience evidence" in item for item in result["deviations"])
    assert any("not clearly tied to known audience friction" in item for item in result["deviations"])
    assert any("Ground claim/evidence pairs" in item for item in result["rewrite_suggestions"])


def test_tone_qa_does_not_credit_raw_objection_metadata_without_response_language() -> None:
    service = ToneIntelligenceService()
    service.providers = SimpleNamespace(get_text_provider=lambda *_args, **_kwargs: _FailingProvider())

    result = service.evaluate(
        content="Switching tools feels risky. Book a demo.",
        brand_context={
            "voice_tone": {"tone_attributes": ["Confident"]},
            "guardrails": {"positive_word_bank": ["clarity"], "blocked_words": []},
        },
        persona_context={
            "objections": ["Switching tools feels risky"],
        },
        content_payload={
            "headline": "Switching tools feels risky",
            "body": "Switching tools feels risky.",
            "cta": "Book a demo",
            "metadata": {
                "objection_handling": ["Switching tools feels risky"],
            },
        },
    )

    assert not any("Structured objection handling" in item for item in result["matched_signals"])
    assert any("repeats friction without answering it" in item for item in result["deviations"])
    assert any("Rewrite objection_handling as a response line" in item for item in result["rewrite_suggestions"])
    assert result["persuasion_dimensions"]["objection_handling"] < 60


def test_tone_qa_does_not_credit_generic_overlap_as_grounded_audience_evidence() -> None:
    service = ToneIntelligenceService()
    service.providers = SimpleNamespace(get_text_provider=lambda *_args, **_kwargs: _FailingProvider())

    result = service.evaluate(
        content="Proof-led comparison for lower risk. Learn more.",
        brand_context={
            "voice_tone": {"tone_attributes": ["Confident"]},
            "guardrails": {"positive_word_bank": ["clarity"], "blocked_words": []},
            "audience_insights": {
                "objections": ["Needs downside risk framed clearly for treasury teams"],
                "pain_points": ["Hard to compare fixed-income options against deposits"],
                "trust_signals": ["Treasury buyers trust issuer-level downside context"],
                "proof_cues": ["Evidence should explain rate impact with issuer examples"],
                "comparison_points": ["Compare issuer quality, duration, and yield against deposits"],
            },
        },
        persona_context={},
        content_payload={
            "headline": "Proof-led comparison",
            "body": "Risk, proof, and comparison are covered.",
            "cta": "Learn more",
            "metadata": {
                "trust_builders": ["Risk review support"],
                "objection_handling": ["Risk feels high, but proof is available."],
                "claim_evidence_pairs": [
                    {
                        "claim": "Compare options faster",
                        "evidence": "Proof and comparison for risk review",
                    }
                ],
            },
        },
    )

    assert any("weakly grounded in known audience evidence" in item for item in result["deviations"])
    assert not any("Objection handling aligns with known audience friction" in item for item in result["matched_signals"])
    assert result["persuasion_dimensions"]["objection_handling"] < 75
    assert result["persuasion_dimensions"]["proof_strength"] < 75


def test_tone_qa_accepts_specific_grounding_without_exact_phrase_reuse() -> None:
    service = ToneIntelligenceService()
    service.providers = SimpleNamespace(get_text_provider=lambda *_args, **_kwargs: _FailingProvider())

    result = service.evaluate(
        content="Reduce rollout drag with guided onboarding and side-by-side comparisons. Book a demo.",
        brand_context={
            "voice_tone": {"tone_attributes": ["Confident"]},
            "guardrails": {"positive_word_bank": ["clarity"], "blocked_words": []},
            "audience_insights": {
                "objections": ["Switching systems feels risky for lean finance teams"],
                "pain_points": ["Manual close work makes spreadsheet comparisons hard"],
                "trust_signals": ["Security review and guided onboarding reduce rollout risk"],
                "proof_cues": ["Evidence should compare spreadsheet workflows side by side"],
            },
        },
        persona_context={},
        content_payload={
            "headline": "Reduce rollout drag",
            "body": "Guided onboarding keeps switching risk low while your team compares spreadsheet workflows side by side.",
            "cta": "Book a demo",
            "metadata": {
                "trust_builders": ["Security-reviewed onboarding keeps rollout low-risk"],
                "objection_handling": ["Switching can feel risky, but guided onboarding keeps the rollout low-risk."],
                "claim_evidence_pairs": [
                    {
                        "claim": "See the trade-off before switching",
                        "evidence": "Compare your spreadsheet workflow side by side before rollout.",
                    }
                ],
            },
        },
    )

    assert any("Claim/evidence pairs align with known audience evidence" in item for item in result["matched_signals"])
    assert any("Objection handling aligns with known audience friction" in item for item in result["matched_signals"])
    assert not any("weakly grounded in known audience evidence" in item for item in result["deviations"])
    assert not any("not clearly tied to known audience friction" in item for item in result["deviations"])


def test_tone_provider_output_is_grounded_by_heuristics() -> None:
    service = ToneIntelligenceService()
    service.providers = SimpleNamespace(
        get_text_provider=lambda *_args, **_kwargs: _StaticProvider(
            {
                "score": 96,
                "matched_signals": ["Assertive tone"],
                "deviations": ["Could tighten phrasing"],
                "rewrite_suggestions": ["Sharpen the first line."],
            }
        )
    )

    result = service.evaluate(
        content="Premium premium premium solution for everyone. Discover more.",
        brand_context={
            "voice_tone": {"tone_attributes": ["Confident"]},
            "guardrails": {"positive_word_bank": [], "blocked_words": []},
        },
        persona_context={
            "fears_and_pain_points": ["Budget risk"],
            "objections": ["Not sure it is worth switching"],
        },
    )

    assert result["score"] < 96
    assert "Assertive tone" in result["matched_signals"]
    assert any("under-supported by proof" in item for item in result["deviations"])
    assert any("generic marketing language" in item for item in result["deviations"])
    assert any("audience objection directly" in item for item in result["rewrite_suggestions"])
    assert "proof_strength" in result["persuasion_dimensions"]
    assert "headline" in result["field_guidance"]
