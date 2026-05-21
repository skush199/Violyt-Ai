from __future__ import annotations

import re
from typing import Any


class SessionMemoryPlanner:
    FRESH_STANDALONE_PATTERN = re.compile(
        r"^(?:write|create|generate|design|draft|prepare|make)\b",
        re.IGNORECASE,
    )
    MODIFY_PATTERNS = [
        re.compile(pattern, re.IGNORECASE)
        for pattern in [
            r"\b(change|update|revise|rewrite|edit|modify|tweak|adjust|reword|replace|swap|move)\b",
            r"\b(make it|turn it|keep the same|same layout|same design|same template|same post)\b",
            r"\b(previous|earlier|last one|last post|this one|that one)\b",
            r"\b(shorter|longer|clearer|sharper|bolder|softer|friendlier|more premium|more direct)\b",
        ]
    ]
    VARIANT_PATTERNS = [
        re.compile(pattern, re.IGNORECASE)
        for pattern in [
            r"\b(another version|alternative|variant|new angle|more options|different version)\b",
            r"\b(same but|another option|give me another)\b",
            r"\b(regenerate|redo|try again|another creative|another layout)\b",
        ]
    ]
    NEW_CONTENT_PATTERNS = [
        re.compile(pattern, re.IGNORECASE)
        for pattern in [
            r"\b(new content|new post|fresh post|from scratch|start over|completely new)\b",
            r"\b(different topic|separate campaign|new campaign)\b",
            r"\b(create a new|generate a new)\b",
        ]
    ]
    PREVIOUS_OUTPUT_REFERENCE_PATTERN = re.compile(
        r"\b(?:make|turn|convert|repurpose|use|reuse|revise|rewrite|edit|change|rework|improve)\s+(?:it|this|that)\b"
        r"|\b(?:this|that|same|previous|earlier|last)\s+(?:one|creative|design|post|layout|format|version|carousel|slide)\b",
        re.IGNORECASE,
    )
    REFERENCE_PRONOUNS = {"it", "this", "that", "previous", "earlier", "same"}

    def build(
        self,
        *,
        current_prompt: str,
        recent_messages: list[dict[str, Any]],
        recent_content_versions: list[dict[str, Any]],
        session_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        recent_messages = list(recent_messages or [])
        recent_content_versions = list(recent_content_versions or [])
        latest_content = recent_content_versions[0] if recent_content_versions else None
        follow_up_intent = self.detect_follow_up_intent(
            current_prompt=current_prompt,
            recent_messages=recent_messages,
            latest_content=latest_content,
        )
        return {
            "follow_up_intent": follow_up_intent,
            "recent_messages": recent_messages,
            "recent_content_versions": recent_content_versions,
            "latest_content_version": latest_content,
            "inherited_persona_id": latest_content.get("persona_id") if latest_content and follow_up_intent["uses_previous_output"] else None,
            "inherited_objective_id": latest_content.get("objective_id") if latest_content and follow_up_intent["uses_previous_output"] else None,
            "inherited_template_id": latest_content.get("template_id") if latest_content and follow_up_intent["uses_previous_output"] else None,
            "session_context": session_context or {},
        }

    def detect_follow_up_intent(
        self,
        *,
        current_prompt: str,
        recent_messages: list[dict[str, Any]],
        latest_content: dict[str, Any] | None,
    ) -> dict[str, Any]:
        prompt = (current_prompt or "").strip()
        lowered = prompt.lower()
        if not prompt or not latest_content:
            return self._intent_payload("new_content", 0.25, "No previous generated content is available to reference.")

        has_new_signal = any(pattern.search(prompt) for pattern in self.NEW_CONTENT_PATTERNS)
        has_modify_signal = any(pattern.search(prompt) for pattern in self.MODIFY_PATTERNS)
        has_variant_signal = any(pattern.search(prompt) for pattern in self.VARIANT_PATTERNS)
        tokens = [token.strip(".,!?") for token in lowered.split()]
        has_reference_pronoun = any(token in self.REFERENCE_PRONOUNS for token in tokens)
        is_short_follow_up = len(tokens) <= 12
        has_history = bool(recent_messages)
        if self._looks_like_fresh_standalone_request(prompt, latest_content):
            return self._intent_payload(
                "new_content",
                0.9,
                "Prompt reads like a fresh standalone brief and does not explicitly reference the previous output.",
            )

        if has_new_signal and not (has_modify_signal or has_variant_signal):
            return self._intent_payload("new_content", 0.92, "User explicitly asked for a new or separate piece of content.")

        if has_variant_signal:
            return self._intent_payload("variant_of_previous", 0.82, "Prompt asks for another version or alternative based on the previous output.")

        if has_modify_signal or (has_reference_pronoun and is_short_follow_up):
            return self._intent_payload("modify_previous", 0.88 if has_modify_signal else 0.72, "Prompt refers to the previous generated content and requests edits.")

        if has_history and is_short_follow_up:
            return self._intent_payload("modify_previous", 0.58, "Short follow-up in an active session; treat it as referring to the last generated output.")

        return self._intent_payload("new_content", 0.55, "Prompt looks standalone, so prior outputs are background context only.")

    @classmethod
    def _topic_tokens(cls, text: str | None) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9']+", str(text or "").casefold())
            if len(token) > 2
            and token
            not in {
                "about",
                "brand",
                "brief",
                "carousel",
                "content",
                "create",
                "design",
                "draft",
                "financial",
                "future",
                "generate",
                "image",
                "india",
                "indian",
                "insightful",
                "investing",
                "investment",
                "investments",
                "investor",
                "investors",
                "layout",
                "linkedin",
                "money",
                "platform",
                "post",
                "prompt",
                "slide",
                "slides",
                "visual",
                "wealth",
                "write",
            }
        }

    @classmethod
    def _looks_like_fresh_standalone_request(
        cls,
        prompt: str,
        latest_content: dict[str, Any] | None,
    ) -> bool:
        text = str(prompt or "").strip()
        if not text or latest_content is None:
            return False
        if not cls.FRESH_STANDALONE_PATTERN.search(text):
            return False
        if cls.PREVIOUS_OUTPUT_REFERENCE_PATTERN.search(text):
            return False
        token_count = len(re.findall(r"[a-z0-9']+", text.casefold()))
        if token_count >= 18:
            return True
        latest_prompt = str(latest_content.get("prompt") or "").strip()
        latest_headline = str(latest_content.get("headline") or "").strip()
        current_tokens = cls._topic_tokens(text)
        previous_tokens = cls._topic_tokens(" ".join(part for part in (latest_prompt, latest_headline) if part))
        if len(current_tokens) < 4 or not previous_tokens:
            return False
        overlap = current_tokens & previous_tokens
        overlap_ratio = len(overlap) / max(len(current_tokens), 1)
        return overlap_ratio <= 0.25 and len(current_tokens - overlap) >= 4

    @staticmethod
    def _intent_payload(mode: str, confidence: float, rationale: str) -> dict[str, Any]:
        return {
            "mode": mode,
            "confidence": confidence,
            "rationale": rationale,
            "uses_previous_output": mode in {"modify_previous", "variant_of_previous"},
            "new_content_request": mode == "new_content",
        }
