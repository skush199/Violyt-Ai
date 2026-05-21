from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(slots=True)
class ChatIntentDecision:
    mode: str
    deliverable_type: str | None = None
    reason: str = ""
    uses_previous_output: bool = False
    revision_scope: dict[str, Any] | None = None
    workflow_plan: dict[str, Any] | None = None


class IntentRouterService:
    _GREETING_PATTERN = re.compile(
        r"^(?:hi|hello|hey|good morning|good afternoon|good evening|hola|namaste)\b[!. ]*$",
        re.IGNORECASE,
    )
    _VISUAL_KEYWORDS = {
        "carousel",
        "infographic",
        "static",
        "visual",
        "creative",
        "poster",
        "banner",
        "image",
        "ad creative",
        "social creative",
        "slides",
        "slide",
    }
    _TEXT_DELIVERABLES = {
        "blog": "blog",
        "article": "blog",
        "linkedin post": "linkedin_post",
        "linkedin caption": "linkedin_post",
        "instagram caption": "instagram_caption",
        "instagram post": "instagram_caption",
        "caption": "social_caption",
        "x post": "x_post",
        "tweet": "x_post",
        "thread": "x_thread",
        "youtube description": "youtube_description",
        "description": "long_description",
        "newsletter": "newsletter",
        "email": "email",
        "script": "script",
    }
    _TEXT_ACTION_PATTERN = re.compile(
        r"\b(?:write|draft|create|generate|give me|prepare|turn this into|make)\b",
        re.IGNORECASE,
    )
    _EVALUATION_PATTERN = re.compile(
        r"\b(?:check|review|score|audit|evaluate|assess|analyze)\b.*\b(?:tone|brand|guideline|compliance|consistency)\b"
        r"|\b(?:tone consistency|brand consistency|brand guidelines|compliance review)\b",
        re.IGNORECASE,
    )
    _REWRITE_PATTERN = re.compile(
        r"\b(?:rewrite|revise|improve|refine|shorten|expand|tighten|make it|change this|rework|edit)\b",
        re.IGNORECASE,
    )
    _CHAIN_PATTERN = re.compile(
        r"\b(?:then|and then|turn it into|convert (?:it|this)|repurpose|based on (?:that|the review|review))\b",
        re.IGNORECASE,
    )
    _STRATEGY_PATTERN = re.compile(
        r"\b(?:what should|how should|which angle|is this angle|brainstorm|ideas for|strategy for|help me think)\b",
        re.IGNORECASE,
    )
    _VISUAL_FOLLOW_UP_PATTERN = re.compile(
        r"\b(?:slide|slides|hook|cta|layout|visual|image|text density|reduce the text|shorten the text|make .* sharper)\b",
        re.IGNORECASE,
    )
    _FRESH_VISUAL_REQUEST_PATTERN = re.compile(
        r"^(?:write|create|generate|design|draft|prepare|make)\b",
        re.IGNORECASE,
    )
    _PREVIOUS_OUTPUT_REFERENCE_PATTERN = re.compile(
        r"\b(?:make|turn|convert|repurpose|use|reuse|revise|rewrite|edit|change|rework|improve)\s+(?:it|this|that)\b"
        r"|\bkeep\s+(?:this|that|the same|same)\b"
        r"|\b(?:this|that|same|previous|earlier|last)\s+(?:one|creative|design|post|layout|format|version|carousel|slide)\b",
        re.IGNORECASE,
    )
    # Stricter version: only explicit named-previous-creative references.
    # Used inside _is_fresh_visual_generation_request so that action phrases like
    # "Make it scroll-friendly" inside a "Create..." brief do not block fresh detection.
    _EXPLICIT_PREVIOUS_CREATIVE_PATTERN = re.compile(
        r"\bkeep\s+(?:this|that|the same|same)\b"
        r"|\b(?:this|that|same|previous|earlier|last)\s+(?:one|creative|design|post|layout|format|version|carousel|slide)\b",
        re.IGNORECASE,
    )
    _REVISION_INTENT_PATTERN = re.compile(
        r"\b(?:change|update|revise|rewrite|edit|modify|shorten|reduce|expand|tighten|improve|refine|rework|replace|swap|move|rearrange|reposition|resize)\b",
        re.IGNORECASE,
    )
    _VISUAL_POLISH_PATTERN = re.compile(
        r"\bmake\b.{0,20}\b(?:sharper|bolder|clearer|cleaner|simpler)\b",
        re.IGNORECASE,
    )
    _PRESERVE_EXISTING_PATTERN = re.compile(
        r"\b(?:keep|preserve|reuse)\b.{0,30}\b(?:same|existing|current)\b"
        r"|\b(?:same|existing|current)\b.{0,20}\b(?:visual|visuals|design|layout|image|images|artwork|copy|content|text|messaging)\b",
        re.IGNORECASE,
    )
    _SLIDE_INDEX_PATTERN = re.compile(r"\b(?:slide|page)\s+(\d+)\b", re.IGNORECASE)
    _TARGETED_FIELD_HINTS: dict[str, tuple[str, ...]] = {
        "headline": ("headline", "title", "hook", "opening line", "subject line"),
        "body": ("body", "body copy", "copy", "content", "text", "caption", "description", "post"),
        "cta": ("cta", "call to action", "button", "closing line", "close"),
        "hashtags": ("hashtag", "hashtags", "tags"),
        "layout": ("layout", "composition", "spacing", "positioning"),
        "visuals": ("visual", "visuals", "image", "images", "design", "artwork"),
    }

    def route(self, message: str, session_context: dict[str, Any] | None = None) -> ChatIntentDecision:
        text = " ".join(str(message or "").split()).strip()
        lowered = text.casefold()
        session_context = session_context or {}
        prior_mode = str(session_context.get("last_response_mode") or "").strip().casefold()
        effective_prior_mode = prior_mode
        if prior_mode == "evaluation":
            effective_prior_mode = str(session_context.get("last_non_evaluation_response_mode") or "").strip().casefold()

        if not text:
            return ChatIntentDecision(mode="small_talk", reason="empty_message")

        if self._GREETING_PATTERN.match(text):
            return ChatIntentDecision(mode="small_talk", reason="greeting")

        deliverable_type = self._text_deliverable_type(lowered)
        visual_requested = self._is_visual_request(lowered)
        review_keywords = self._EVALUATION_PATTERN.search(text) is not None or lowered.startswith(("review ", "check ", "analyze ", "assess ", "audit ", "score ", "evaluate "))
        rewrite_keywords = self._REWRITE_PATTERN.search(text) is not None
        workflow_plan = self._mixed_workflow_plan(
            text=text,
            lowered=lowered,
            session_context=session_context,
            prior_mode=prior_mode,
            effective_prior_mode=effective_prior_mode,
            deliverable_type=deliverable_type,
            visual_requested=visual_requested,
            review_keywords=review_keywords,
            rewrite_keywords=rewrite_keywords,
        )
        if workflow_plan:
            target_mode = str(workflow_plan.get("target_mode") or "content_only").strip() or "content_only"
            return ChatIntentDecision(
                mode=target_mode,
                deliverable_type=deliverable_type or str(session_context.get("last_text_deliverable_type") or "").strip() or None,
                reason=str(workflow_plan.get("reason") or "mixed_workflow"),
                uses_previous_output=bool(workflow_plan.get("uses_previous_output")),
                revision_scope=self._extract_revision_scope(text, prior_mode=effective_prior_mode),
                workflow_plan=workflow_plan,
            )

        if review_keywords:
            return ChatIntentDecision(
                mode="evaluation",
                reason="evaluation_keywords",
                uses_previous_output=effective_prior_mode in {"content_only", "visual_generation"},
            )

        revision_scope = self._extract_revision_scope(text, prior_mode=effective_prior_mode)
        if (
            effective_prior_mode == "visual_generation"
            and visual_requested
            and self._is_fresh_visual_generation_request(text, lowered)
        ):
            return ChatIntentDecision(
                mode="visual_generation",
                reason="fresh_visual_generation_request",
                uses_previous_output=False,
            )
        if rewrite_keywords and effective_prior_mode == "visual_generation":
            return ChatIntentDecision(
                mode="visual_generation",
                reason="visual_rewrite_follow_up",
                uses_previous_output=True,
                revision_scope=revision_scope,
            )
        # Explicit named references to a previous creative — e.g. "same carousel",
        # "previous post", "keep the same design" — are always follow-ups even when
        # the prompt starts with "Create" or "Generate".
        if (
            effective_prior_mode == "visual_generation"
            and self._EXPLICIT_PREVIOUS_CREATIVE_PATTERN.search(text)
        ):
            return ChatIntentDecision(
                mode="visual_generation",
                reason="visual_previous_creative_reference",
                uses_previous_output=True,
                revision_scope=revision_scope,
            )
        if (
            effective_prior_mode == "visual_generation"
            and self._VISUAL_FOLLOW_UP_PATTERN.search(text)
            and self._looks_like_previous_output_visual_follow_up(
                text,
                lowered,
                revision_scope=revision_scope,
            )
        ):
            return ChatIntentDecision(
                mode="visual_generation",
                reason="visual_follow_up_reference",
                uses_previous_output=True,
                revision_scope=revision_scope,
            )

        if visual_requested:
            return ChatIntentDecision(
                mode="visual_generation",
                reason="visual_keywords",
                uses_previous_output=rewrite_keywords and effective_prior_mode == "visual_generation",
            )

        # Catch revision instructions that target visual elements but contain no
        # visual format keywords — e.g. "change the headline", "update the body copy",
        # "improve the hook text".  These are follow-ups to the previous visual.
        if (
            effective_prior_mode == "visual_generation"
            and not visual_requested
            and self._REVISION_INTENT_PATTERN.search(text)
        ):
            return ChatIntentDecision(
                mode="visual_generation",
                reason="visual_element_revision",
                uses_previous_output=True,
                revision_scope=revision_scope,
            )

        if deliverable_type and self._TEXT_ACTION_PATTERN.search(text):
            return ChatIntentDecision(
                mode="content_only",
                deliverable_type=deliverable_type,
                reason="text_deliverable",
                uses_previous_output=rewrite_keywords and effective_prior_mode == "content_only",
                revision_scope=revision_scope if effective_prior_mode == "content_only" else None,
            )

        if rewrite_keywords and effective_prior_mode == "content_only":
            return ChatIntentDecision(
                mode="content_only",
                deliverable_type=str(session_context.get("last_text_deliverable_type") or "").strip() or None,
                reason="content_rewrite_follow_up",
                uses_previous_output=True,
                revision_scope=revision_scope,
            )

        if self._STRATEGY_PATTERN.search(text) or text.endswith("?"):
            return ChatIntentDecision(mode="strategy_chat", reason="strategy_or_question")

        return ChatIntentDecision(mode="content_only", deliverable_type=deliverable_type or "general_copy", reason="default_content")

    def _is_visual_request(self, lowered: str) -> bool:
        if any(keyword in lowered for keyword in self._VISUAL_KEYWORDS):
            return True
        return bool(re.search(r"\b(?:generate|create|design|make)\b.*\b(?:image|visual|creative|poster|banner|slide)\b", lowered))

    def _text_deliverable_type(self, lowered: str) -> str | None:
        for trigger, deliverable_type in self._TEXT_DELIVERABLES.items():
            if trigger in lowered:
                return deliverable_type
        return None

    @classmethod
    def _is_fresh_visual_generation_request(cls, text: str, lowered: str) -> bool:
        if not cls._FRESH_VISUAL_REQUEST_PATTERN.search(text):
            return False
        if re.search(r"\b(?:slide|page)\s+\d+\b", lowered):
            return False
        # Long standalone briefs (>=18 tokens) are always fresh regardless of phrases.
        token_count = len(re.findall(r"[a-z0-9']+", lowered))
        if token_count >= 18:
            return True
        # For short prompts that start with Create/Generate/etc., only block on
        # explicit named references ("same carousel", "previous version", "keep the
        # same design"). Action phrases like "Make it scroll-friendly" or "Make it
        # about savings" inside a Create brief are creative direction, not references
        # to a previous output.
        if cls._EXPLICIT_PREVIOUS_CREATIVE_PATTERN.search(text):
            return False
        if cls._PRESERVE_EXISTING_PATTERN.search(text):
            return False
        if cls._REVISION_INTENT_PATTERN.search(text):
            return False
        if cls._VISUAL_POLISH_PATTERN.search(text):
            return False
        return True

    @classmethod
    def _looks_like_previous_output_visual_follow_up(
        cls,
        text: str,
        lowered: str,
        *,
        revision_scope: dict[str, Any] | None,
    ) -> bool:
        if cls._PREVIOUS_OUTPUT_REFERENCE_PATTERN.search(text):
            return True
        if cls._PRESERVE_EXISTING_PATTERN.search(text):
            return True
        if re.search(r"\b(?:slide|page)\s+\d+\b", lowered):
            return True
        if cls._REVISION_INTENT_PATTERN.search(text):
            return True
        if cls._VISUAL_POLISH_PATTERN.search(text):
            return True
        if isinstance(revision_scope, dict) and (
            revision_scope.get("slide_indexes")
            or revision_scope.get("slide_targets")
            or revision_scope.get("preserve_visuals")
            or revision_scope.get("preserve_copy")
        ):
            return True
        return False

    @classmethod
    def _extract_revision_scope(cls, message: str, *, prior_mode: str) -> dict[str, Any] | None:
        text = " ".join(str(message or "").split()).strip()
        lowered = text.casefold()
        if not text:
            return None

        has_follow_up_signal = cls._looks_like_follow_up_edit_instruction(text, lowered)
        targeted_fields: list[str] = []
        for field, hints in cls._TARGETED_FIELD_HINTS.items():
            if has_follow_up_signal and any(hint in lowered for hint in hints):
                targeted_fields.append(field)

        slide_indexes = sorted({int(match) for match in cls._SLIDE_INDEX_PATTERN.findall(text)})
        slide_targets: list[str] = []
        if "cover slide" in lowered or "first slide" in lowered:
            slide_targets.append("cover")
        if "last slide" in lowered or "closing slide" in lowered or "final slide" in lowered:
            slide_targets.append("last")

        preserve_visuals = has_follow_up_signal and bool(
            re.search(r"\bkeep\b.{0,30}\b(?:visual|visuals|design|layout|image|images|artwork)\b", lowered)
            or re.search(r"\b(?:copy|text|content)\s+only\b", lowered)
        )
        preserve_copy = has_follow_up_signal and bool(
            re.search(r"\bkeep\b.{0,30}\b(?:copy|content|text|messaging)\b", lowered)
            or re.search(r"\b(?:layout|visual|visuals|design|image|images)\s+only\b", lowered)
        )
        change_layout = has_follow_up_signal and bool(
            "layout" in lowered
            or re.search(r"\b(?:rearrange|reposition|move|resize|swap)\b", lowered)
        )
        change_tone = has_follow_up_signal and bool(
            "tone" in lowered
            or "voice" in lowered
            or re.search(r"\bsound\s+more\b", lowered)
            or re.search(r"\bmore\s+(?:analytical|conversational|formal|casual|professional|playful|sharp|sharper)\b", lowered)
            or re.search(r"\bless\s+(?:promotional|salesy|formal|casual|playful)\b", lowered)
        )
        only_targeted = has_follow_up_signal and bool(re.search(r"\b(?:only|just)\b", lowered))

        scope = {
            "targeted_fields": targeted_fields,
            "slide_indexes": slide_indexes,
            "slide_targets": slide_targets,
            "preserve_visuals": preserve_visuals,
            "preserve_copy": preserve_copy,
            "change_layout": change_layout,
            "change_tone": change_tone,
            "only_targeted": only_targeted,
            "prior_mode": prior_mode or None,
        }
        if any(
            [
                targeted_fields,
                slide_indexes,
                slide_targets,
                preserve_visuals,
                preserve_copy,
                change_layout,
                change_tone,
                only_targeted,
            ]
        ):
            return scope
        return None

    @classmethod
    def _looks_like_follow_up_edit_instruction(cls, text: str, lowered: str) -> bool:
        if cls._PREVIOUS_OUTPUT_REFERENCE_PATTERN.search(text):
            return True
        if cls._PRESERVE_EXISTING_PATTERN.search(text):
            return True
        if re.search(r"\b(?:slide|page)\s+\d+\b", lowered):
            return True
        if cls._REVISION_INTENT_PATTERN.search(text):
            return True
        if cls._VISUAL_POLISH_PATTERN.search(text):
            return True
        return False

    def _mixed_workflow_plan(
        self,
        *,
        text: str,
        lowered: str,
        session_context: dict[str, Any],
        prior_mode: str,
        effective_prior_mode: str,
        deliverable_type: str | None,
        visual_requested: bool,
        review_keywords: bool,
        rewrite_keywords: bool,
    ) -> dict[str, Any] | None:
        if review_keywords and (deliverable_type or visual_requested or rewrite_keywords):
            target_mode = "visual_generation" if visual_requested else "content_only"
            return {
                "type": "review_then_generate",
                "target_mode": target_mode,
                "uses_previous_output": rewrite_keywords and effective_prior_mode in {"content_only", "visual_generation"},
                "reason": "review_then_generate",
                "review_source": "reference_assets_or_previous",
                "apply_review_to_rewrite": rewrite_keywords,
            }

        if effective_prior_mode == "content_only" and visual_requested and self._CHAIN_PATTERN.search(text):
            return {
                "type": "repurpose_text_to_visual",
                "target_mode": "visual_generation",
                "uses_previous_output": False,
                "reason": "repurpose_text_to_visual",
            }

        if prior_mode == "evaluation" and rewrite_keywords:
            target_mode = "visual_generation" if effective_prior_mode == "visual_generation" else "content_only"
            return {
                "type": "apply_last_review",
                "target_mode": target_mode,
                "uses_previous_output": True,
                "reason": "apply_last_review",
                "review_source": "last_evaluation",
            }

        if prior_mode == "evaluation" and visual_requested and self._CHAIN_PATTERN.search(text):
            return {
                "type": "review_then_generate",
                "target_mode": "visual_generation",
                "uses_previous_output": effective_prior_mode == "visual_generation",
                "reason": "evaluation_guided_visual_generation",
                "review_source": "last_evaluation",
            }

        if prior_mode == "evaluation" and deliverable_type and self._CHAIN_PATTERN.search(text):
            return {
                "type": "review_then_generate",
                "target_mode": "content_only",
                "uses_previous_output": effective_prior_mode == "content_only",
                "reason": "evaluation_guided_content_generation",
                "review_source": "last_evaluation",
            }

        return None
