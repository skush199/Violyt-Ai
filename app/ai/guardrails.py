from __future__ import annotations

import re

from app.core.exceptions import GuardrailViolationError


class GuardrailService:
    def validate_prompt(self, prompt: str, guardrails: dict) -> dict:
        violations: list[str] = []
        lowered = prompt.lower()
        for blocked in guardrails.get("blocked_words", []):
            if blocked.lower() in lowered:
                violations.append(f"Blocked word detected: {blocked}")
        for topic in guardrails.get("restricted_topics", []):
            if topic.lower() in lowered:
                violations.append(f"Restricted topic detected: {topic}")
        for claim in guardrails.get("restricted_claims", []):
            if claim.lower() in lowered:
                violations.append(f"Restricted claim detected: {claim}")
        for pattern in guardrails.get("forbidden_prompt_patterns", []):
            if re.search(pattern, prompt, flags=re.IGNORECASE):
                violations.append(f"Forbidden prompt pattern detected: {pattern}")
        if violations:
            raise GuardrailViolationError("; ".join(violations))
        return {"status": "passed", "violations": []}

    def validate_output(self, content: str, guardrails: dict) -> dict:
        return self.validate_prompt(content, guardrails)

