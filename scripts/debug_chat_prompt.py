from __future__ import annotations

import argparse
import asyncio
import json
import logging
import traceback
from pathlib import Path
from uuid import UUID

from app.db.session import AsyncSessionLocal
from app.repositories.content import AssetRepository, ContentRepository, SessionRepository
from app.schemas.chat import ChatMessageCreateRequest, ChatSessionCreateRequest
from app.schemas.common import StudioPanelSelection
from app.services.chat import ChatService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Debug a chat prompt directly against ChatService.")
    parser.add_argument("--session-id", help="Existing chat session UUID")
    parser.add_argument("--tenant-id", help="Tenant UUID for creating a fresh session")
    parser.add_argument("--brand-space-id", help="Brand space UUID for creating a fresh session")
    parser.add_argument("--user-id", help="User UUID for creating a fresh session")
    parser.add_argument("--create-session", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--message", help="Prompt/message to send")
    parser.add_argument("--prompt-file", help="Path to a UTF-8 text file containing the prompt")
    parser.add_argument("--generate-image", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--studio-panel-json",
        help="Optional JSON override for studio panel, e.g. '{\"format\":\"carousel\",\"platform_preset\":\"linkedin\",\"file_type\":\"png\"}'",
    )
    parser.add_argument("--persona-id")
    parser.add_argument("--objective-id")
    parser.add_argument("--template-id")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def _load_message(args: argparse.Namespace) -> str:
    if args.message:
        return args.message.strip()
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8").strip()
    raise SystemExit("Provide --message or --prompt-file")


def _print_json(label: str, value: object) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


async def _run(args: argparse.Namespace) -> int:
    message = _load_message(args)
    async with AsyncSessionLocal() as db:
        sessions = SessionRepository(db)
        contents = ContentRepository(db)
        assets = AssetRepository(db)
        chat = ChatService(db)

        studio_panel = None
        if args.studio_panel_json:
            studio_panel = StudioPanelSelection.model_validate(json.loads(args.studio_panel_json))
        else:
            studio_panel = StudioPanelSelection.model_validate(
                {"format": "carousel", "platform_preset": "linkedin", "file_type": "png"}
            )

        if args.create_session:
            if not (args.tenant_id and args.brand_space_id and args.user_id):
                raise SystemExit("--create-session requires --tenant-id, --brand-space-id, and --user-id")
            session = await chat.create_session(
                tenant_id=UUID(args.tenant_id),
                brand_space_id=UUID(args.brand_space_id),
                user_id=UUID(args.user_id),
                payload=ChatSessionCreateRequest(
                    title="Debug Chat Prompt Session",
                    studio_panel=studio_panel,
                ),
            )
        else:
            if not args.session_id:
                raise SystemExit("Provide --session-id or use --create-session with tenant/brand/user ids")
            session_id = UUID(args.session_id)
            session = await sessions.get(session_id)
            if not session:
                print(f"Session not found: {session_id}")
                return 1

        payload = ChatMessageCreateRequest(
            message=message,
            studio_panel=studio_panel,
            persona_id=UUID(args.persona_id) if args.persona_id else None,
            objective_id=UUID(args.objective_id) if args.objective_id else None,
            template_id=UUID(args.template_id) if args.template_id else None,
            generate_image=args.generate_image,
        )

        intent = chat.intent_router.route(message, session.conversational_context)
        _print_json(
            "PRE-ROUTE",
            {
                "session_id": str(session.id),
                "tenant_id": str(session.tenant_id),
                "brand_space_id": str(session.brand_space_id),
                "user_id": str(session.user_id),
                "last_response_mode": (session.conversational_context or {}).get("last_response_mode"),
                "last_content_version_id": (session.conversational_context or {}).get("last_content_version_id"),
                "intent": {
                    "mode": intent.mode,
                    "reason": intent.reason,
                    "uses_previous_output": intent.uses_previous_output,
                    "deliverable_type": intent.deliverable_type,
                    "revision_scope": intent.revision_scope,
                    "workflow_plan": intent.workflow_plan,
                },
                "studio_panel": studio_panel.model_dump() if studio_panel else session.studio_panel,
            },
        )

        try:
            user_message, assistant_message = await chat.send_message(
                tenant_id=session.tenant_id,
                brand_space_id=session.brand_space_id,
                user_id=session.user_id,
                session_id=session.id,
                payload=payload,
            )
        except Exception as exc:  # pragma: no cover - debug script
            print("\n=== EXCEPTION ===")
            traceback.print_exception(exc)
            return 1

        _print_json(
            "POST-CHAT",
            {
                "user_message_id": str(user_message.id),
                "assistant_message_id": str(assistant_message.id),
                "assistant_role": assistant_message.role,
                "assistant_text": assistant_message.message_text,
                "assistant_payload": assistant_message.structured_payload,
            },
        )

        if assistant_message.content_version_id:
            content = await contents.get_scoped(
                assistant_message.content_version_id,
                session.tenant_id,
                session.brand_space_id,
            )
            content_assets = await assets.list_by_content(assistant_message.content_version_id)
            explainability = (content.explainability_metadata if content else {}) or {}
            _print_json(
                "CONTENT-VERSION",
                {
                    "content_version_id": str(assistant_message.content_version_id),
                    "parent_version_id": str(content.parent_version_id) if content and content.parent_version_id else None,
                    "render_authority": explainability.get("render_authority"),
                    "generation_trace_id": explainability.get("generation_trace_id"),
                    "final_render_assets_meta_count": len(explainability.get("final_render_assets") or []),
                    "selective_regeneration_plan": explainability.get("selective_regeneration_plan"),
                    "asset_count": len(content_assets),
                    "asset_roles": [
                        {
                            "role": asset.asset_role,
                            "storage_path": asset.storage_path,
                            "render_source": (asset.metadata_json or {}).get("render_source"),
                            "slide_index": (asset.metadata_json or {}).get("slide_index"),
                        }
                        for asset in content_assets
                    ],
                },
            )

        await db.rollback()
        return 0


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
