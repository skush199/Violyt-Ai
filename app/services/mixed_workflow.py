from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class WorkflowStep:
    key: str
    label: str
    status: str
    mode: str


@dataclass(slots=True)
class WorkflowState:
    workflow_type: str | None
    source_mode: str | None
    target_mode: str | None
    current_step: str | None
    steps: list[WorkflowStep]
    recovery_hint: str | None = None
    reviewed_asset_ids: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_type": self.workflow_type,
            "source_mode": self.source_mode,
            "target_mode": self.target_mode,
            "current_step": self.current_step,
            "steps": [asdict(step) for step in self.steps],
            "recovery_hint": self.recovery_hint,
            "reviewed_asset_ids": list(self.reviewed_asset_ids or []),
        }


@dataclass(slots=True)
class MixedWorkflowContext:
    prompt: str
    reference_asset_ids: list[UUID]
    review_result: dict[str, Any] | None = None
    workflow_type: str | None = None
    source_mode: str | None = None
    workflow_state: dict[str, Any] | None = None


class MixedWorkflowService:
    def prepare_generation_context(
        self,
        *,
        message: str,
        workflow_plan: dict[str, Any] | None,
        session_context: dict[str, Any] | None,
        review_result: dict[str, Any] | None = None,
        reference_asset_ids: list[UUID] | None = None,
    ) -> MixedWorkflowContext:
        session_context = session_context or {}
        workflow_plan = workflow_plan or {}
        workflow_type = str(workflow_plan.get("type") or "").strip() or None
        source_mode = str(
            session_context.get("last_non_evaluation_response_mode")
            or session_context.get("last_response_mode")
            or ""
        ).strip() or None

        effective_reference_asset_ids = list(reference_asset_ids or [])
        if not effective_reference_asset_ids:
            for raw_asset_id in session_context.get("last_reviewed_asset_ids") or []:
                parsed = self._parse_uuid_or_none(raw_asset_id)
                if parsed:
                    effective_reference_asset_ids.append(parsed)

        prompt = " ".join(str(message or "").split()).strip()
        review_summary = ""
        if isinstance(review_result, dict):
            review_summary = str(review_result.get("summary") or "").strip()
        if not review_summary:
            review_summary = str(session_context.get("last_evaluation_summary") or "").strip()

        last_text_output = str(session_context.get("last_text_output") or "").strip()
        last_deliverable_type = str(session_context.get("last_text_deliverable_type") or "").strip()

        if workflow_type == "repurpose_text_to_visual" and last_text_output:
            prompt = (
                f"{prompt}\n\n"
                f"Source text to repurpose into a visual deliverable ({last_deliverable_type or 'text draft'}):\n"
                f"{last_text_output}\n\n"
                "Treat the source text as the authoritative content base. Adapt structure and pacing for the requested visual format without changing the underlying topic."
            )
        elif workflow_type == "review_then_generate" and review_summary:
            prompt = (
                f"{prompt}\n\n"
                f"Review findings to use as source guidance:\n"
                f"{review_summary}\n\n"
                "Use the review findings as authoritative source guidance for the next deliverable. Preserve the important observations, fix the diagnosed weaknesses, and keep the output aligned to the reviewed source material."
            )
            if last_text_output and source_mode == "content_only":
                prompt = (
                    f"{prompt}\n\n"
                    f"Previous approved/source draft:\n{last_text_output}\n\n"
                    "Repurpose or improve this draft using the review findings instead of starting from a blank slate."
                )
        elif workflow_type == "apply_last_review" and review_summary:
            prompt = (
                f"{prompt}\n\n"
                f"Use these review findings while rewriting:\n"
                f"{review_summary}\n\n"
                "Apply the review findings directly to the rewrite while preserving everything outside the requested rewrite scope."
            )

        workflow_state = self.build_state(
            workflow_plan=workflow_plan,
            session_context=session_context,
            review_result=review_result,
            reviewed_asset_ids=[str(value) for value in session_context.get("last_reviewed_asset_ids") or [] if str(value).strip()],
            source_mode=source_mode,
        )

        return MixedWorkflowContext(
            prompt=prompt,
            reference_asset_ids=effective_reference_asset_ids,
            review_result=review_result,
            workflow_type=workflow_type,
            source_mode=source_mode,
            workflow_state=workflow_state.to_dict() if workflow_state else None,
        )

    def build_state(
        self,
        *,
        workflow_plan: dict[str, Any] | None,
        session_context: dict[str, Any] | None,
        review_result: dict[str, Any] | None,
        reviewed_asset_ids: list[str] | None,
        source_mode: str | None,
    ) -> WorkflowState | None:
        workflow_plan = workflow_plan or {}
        workflow_type = str(workflow_plan.get("type") or "").strip() or None
        if not workflow_type:
            return None
        target_mode = str(workflow_plan.get("target_mode") or "").strip() or None
        steps: list[WorkflowStep] = []
        recovery_hint = None
        if workflow_type == "repurpose_text_to_visual":
            steps = [
                WorkflowStep("reuse_source_text", "Reuse previous text draft", "completed", "content_only"),
                WorkflowStep("restructure_for_visual", "Restructure for visual format", "in_progress", "visual_generation"),
                WorkflowStep("generate_visual", "Generate visual output", "pending", "visual_generation"),
            ]
            recovery_hint = "If the visual output fails, keep the same source draft and retry only the visual generation step."
        elif workflow_type == "review_then_generate":
            review_status = "completed" if isinstance(review_result, dict) else "in_progress"
            steps = [
                WorkflowStep("review_source", "Review source material", review_status, "evaluation"),
                WorkflowStep("apply_review_findings", "Apply review findings to generation", "in_progress", target_mode or "content_only"),
                WorkflowStep("generate_target", "Generate the requested deliverable", "pending", target_mode or "content_only"),
            ]
            recovery_hint = "If generation fails, keep the review findings and retry only the target generation step."
        elif workflow_type == "apply_last_review":
            steps = [
                WorkflowStep("reuse_last_review", "Reuse last review findings", "completed", "evaluation"),
                WorkflowStep("rewrite_with_review", "Rewrite using review findings", "in_progress", target_mode or source_mode or "content_only"),
            ]
            recovery_hint = "If the rewrite is weak, preserve the review findings and retry the rewrite step without rerunning evaluation."
        return WorkflowState(
            workflow_type=workflow_type,
            source_mode=source_mode,
            target_mode=target_mode,
            current_step=next((step.key for step in steps if step.status == "in_progress"), None),
            steps=steps,
            recovery_hint=recovery_hint,
            reviewed_asset_ids=list(reviewed_asset_ids or []),
        )

    @staticmethod
    def _parse_uuid_or_none(value: Any) -> UUID | None:
        if isinstance(value, UUID):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return UUID(text)
        except (TypeError, ValueError):
            return None
