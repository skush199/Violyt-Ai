from __future__ import annotations

from typing import Any

from app.ai.providers.base import PromptEnvelope
from app.ai.providers.router import ProviderRouter


class ConversationService:
    def __init__(self) -> None:
        self.providers = ProviderRouter()

    def reply(
        self,
        *,
        message: str,
        brand_name: str | None = None,
        session_context: dict[str, Any] | None = None,
        mode: str = "small_talk",
    ) -> dict[str, Any]:
        session_context = session_context or {}
        provider = self.providers.get_text_provider("generation")
        fallback = self._fallback_reply(message=message, brand_name=brand_name, mode=mode)
        reply_text = provider.generate_text(
            PromptEnvelope(
                system=(
                    "You are a conversational content copilot inside a brand-safe content studio. "
                    "Reply naturally like a thoughtful teammate. "
                    "Do not generate an image unless the user explicitly asks for one. "
                    "When the user is greeting you, greet them back and offer concise help. "
                    "When the user is exploring a strategy, stay conversational and practical."
                ),
                user=(
                    f"Brand: {brand_name or 'the current brand'}\n"
                    f"Mode: {mode}\n"
                    f"Session context: {session_context}\n"
                    f"User message: {message}\n"
                    "Return only the assistant reply."
                ),
            ),
            fallback=fallback,
        )
        return {
            "message_text": reply_text.strip() or fallback,
            "structured_payload": {
                "mode": "conversation",
                "conversation_mode": mode,
                "brand_name": brand_name,
            },
        }

    @staticmethod
    def _fallback_reply(*, message: str, brand_name: str | None, mode: str) -> str:
        if mode == "small_talk":
            return (
                f"Hi! I'm ready to help with {brand_name or 'your brand'} content. "
                "You can ask me to brainstorm, write copy, review tone, or generate visuals."
            )
        return (
            "I can help you think this through. "
            "Tell me the channel, audience, and what outcome you want, and I'll shape the next step with you."
        )
