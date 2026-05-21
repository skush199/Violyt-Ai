from app.ai.blueprint import BlueprintService


def test_blueprint_is_deterministic_for_same_input() -> None:
    service = BlueprintService()
    payload = {"headline": "Launch Faster", "body": "Brand-safe content", "cta": "Get started"}
    studio_panel = {"format": "static", "platform_preset": "instagram", "file_type": "png"}
    first = service.build(payload, studio_panel)
    second = service.build(payload, studio_panel)
    assert first.model_dump() == second.model_dump()
