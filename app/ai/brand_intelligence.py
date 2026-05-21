from __future__ import annotations

from typing import Any

from app.models.brand import BrandSpace, Guardrail, Objective, Persona


class BrandIntelligenceService:
    def build_context(
        self,
        brand_space: BrandSpace,                                                                                                                                                                                                                                                                                                                                                                                                                                         
        sections: list[dict[str, Any]],
        personas: list[Persona],
        guardrails: list[Guardrail],
        objectives: list[Objective],
    ) -> dict[str, Any]:
        merged_sections: dict[str, Any] = {}
        for section in sections:
            merged_sections[section["section_code"]] = section["payload"]

        default_persona = next((persona for persona in personas if persona.is_default), None)
        primary_guardrail = guardrails[0] if guardrails else None
        default_objective = next((objective for objective in objectives if objective.is_default), None)
        guardrail_context = self.guardrail_to_dict(primary_guardrail) if primary_guardrail else {}
        guardrail_context = {
            **guardrail_context,
            **merged_sections.get("guardrails", {}),
        }
        identity_context = merged_sections.get("identity", {})
        brand_name = identity_context.get("brand_name") or brand_space.name
        brand_description = identity_context.get("brand_description") or brand_space.description
        industry_category = identity_context.get("industry_category") or brand_space.industry_category

        return {
            "brand_id": str(brand_space.id),
            "brand_name": brand_name,
            "brand_description": brand_description,
            "industry_category": industry_category,
            "identity": identity_context,
            "foundations": merged_sections.get("foundations", {}),
            "voice_tone": merged_sections.get("voice_tone", {}),
            "visual_identity": merged_sections.get("visual_identity", {}),
            "prompt_intelligence": merged_sections.get("prompt_intelligence", {}),
            "personas": merged_sections.get("personas", {}),
            "knowledge": merged_sections.get("knowledge", {}),
            "objectives": merged_sections.get("objectives", {}),
            "review": merged_sections.get("review", {}),
            "default_persona": self.persona_to_dict(default_persona) if default_persona else {},
            "guardrails": guardrail_context,
            "default_objective": self.objective_to_dict(default_objective) if default_objective else {},
            "context_priority": {
                "highest": ["guardrails", "identity", "foundations", "voice_tone", "visual_identity", "prompt_intelligence"],
                "supplemental": ["strategy", "brand", "campaign_history", "template", "metadata"],
            },
        }

    @staticmethod
    def persona_to_dict(persona: Persona | None) -> dict[str, Any]:
        if not persona:
            return {}
        return {
            "id": str(persona.id),
            "name": persona.name,
            "role": persona.role,
            "psychographics": persona.psychographics,
            "demographics": persona.demographics,
            "audience_goals": persona.audience_goals,
            "motivations": persona.motivations,
            "fears_and_pain_points": persona.fears_and_pain_points,
            "objections": persona.objections,
            "content_behavior": persona.content_behavior,
            "language_preference": persona.language_preference,
        }

    @staticmethod
    def guardrail_to_dict(guardrail: Guardrail | None) -> dict[str, Any]:
        if not guardrail:
            return {}
        return {
            "positive_word_bank": guardrail.positive_word_bank,
            "replaceable_words": guardrail.replaceable_words,
            "negative_word_bank": guardrail.negative_word_bank,
            "dos": guardrail.dos,
            "donts": guardrail.donts,
            "forbidden_prompt_patterns": guardrail.forbidden_prompt_patterns,
            "restricted_topics": guardrail.restricted_topics,
            "restricted_claims": guardrail.restricted_claims,
            "blocked_words": guardrail.blocked_words,
            "custom_rules": guardrail.custom_rules,
        }

    @staticmethod
    def objective_to_dict(objective: Objective | None) -> dict[str, Any]:
        if not objective:
            return {}
        return {
            "id": str(objective.id),
            "name": objective.name,
            "description": objective.description,
            "content_type": objective.content_type,
            "platform_scope": objective.platform_scope,
            "configuration": objective.configuration,
        }
