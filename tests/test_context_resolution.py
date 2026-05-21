from app.ai.context_resolution import ContextResolutionService


def test_context_resolution_prioritizes_strategy_before_metadata() -> None:
    service = ContextResolutionService()
    plan = service.build_plan(
        brand_context={"brand_name": "Sample"},
        persona_context={"name": "Persona"},
        objective_context={"name": "Objective"},
        retrieved_knowledge={
            "metadata": [{"content": "metadata"}],
            "strategy": [{"content": "strategy"}],
            "brand": [{"content": "brand"}],
            "audience_insights": [{"content": "audience"}],
            "guardrail_support": [{"content": "guardrails"}],
        },
    )
    assert list(plan.ordered_knowledge.keys()) == [
        "strategy",
        "brand",
        "audience_insights",
        "guardrail_support",
        "metadata",
    ]
    assert "guardrails" in plan.priority_order
    assert "audience_insights" in plan.priority_order
