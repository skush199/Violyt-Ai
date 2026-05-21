from app.ai.guardrails import GuardrailService
from app.core.exceptions import GuardrailViolationError


def test_guardrail_service_blocks_restricted_content() -> None:
    service = GuardrailService()
    try:
        service.validate_prompt(
            "Write a miracle cure claim now",
            {
                "restricted_claims": ["miracle cure"],
                "blocked_words": [],
                "restricted_topics": [],
                "forbidden_prompt_patterns": [],
            },
        )
    except GuardrailViolationError:
        assert True
    else:
        assert False

