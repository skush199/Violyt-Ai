from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ResolutionPlan:
    ordered_knowledge: dict[str, list[dict[str, Any]]]
    priority_order: list[str]
    instructions: str
    metadata: dict[str, Any]


class ContextResolutionService:
    PRIORITY_ORDER = [
        "guardrails",
        "identity",
        "foundations",
        "voice_tone",
        "personas",
        "audience_insights",
        "visual_identity",
        "knowledge",
        "prompt_intelligence",
        "persona_context",
        "objective_context",
        "strategy",
        "brand",
        "guardrail_support",
        "reference_creative",
        "mood_board",
        "campaign_history",
        "template",
        "metadata",
        "chat_reference",
        "user_prompt",
    ]

    KNOWLEDGE_PRIORITY = [
        "strategy",
        "brand",
        "audience_insights",
        "guardrail_support",
        "reference_creative",
        "mood_board",
        "visual_identity",
        "template",
        "campaign_history",
        "metadata",
        "chat_reference",
    ]

    def build_plan(
        self,
        brand_context: dict[str, Any],
        persona_context: dict[str, Any],
        objective_context: dict[str, Any],
        retrieved_knowledge: dict[str, list[dict[str, Any]]],
    ) -> ResolutionPlan:
        ordered_knowledge = {
            channel: retrieved_knowledge.get(channel, [])
            for channel in self.KNOWLEDGE_PRIORITY
            if retrieved_knowledge.get(channel)
        }
        metadata = {
            "priority_order": self.PRIORITY_ORDER,
            "knowledge_channel_priority": self.KNOWLEDGE_PRIORITY,
            "policy": [
                "Brand guardrails and blocked claims override all lower-level inputs.",
                "Brand form/config sections override retrieved documents when instructions conflict.",
                "Selected persona and objective override generic knowledge context.",
                "Audience insights and guardrail support files should refine messaging, but not override saved brand rules.",
                "Strategy documents take priority over campaign history, template hints, and metadata snippets.",
                "Reference creatives, mood boards, visual identity assets, and metadata are supplemental and must not override brand configuration.",
            ],
            "active_knowledge_channels": list(ordered_knowledge.keys()),
            "has_brand_config": bool(brand_context),
            "has_persona": bool(persona_context),
            "has_objective": bool(objective_context),
        }
        instructions = (
            "Conflict resolution order: guardrails first; then current brand form/config sections; "
            "then selected persona and objective; then strategy knowledge; then brand knowledge; "
            "then campaign history; then template/metadata hints; finally the user prompt. "
            "Never let lower-priority sources override higher-priority brand rules."
        )
        return ResolutionPlan(
            ordered_knowledge=ordered_knowledge,
            priority_order=self.PRIORITY_ORDER,
            instructions=instructions,
            metadata=metadata,
        )
