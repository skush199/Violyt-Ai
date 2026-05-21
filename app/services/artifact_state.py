from __future__ import annotations

from copy import deepcopy
from typing import Any


class ArtifactStateService:
    SCHEMA_VERSION = 1

    def build_content_state(
        self,
        *,
        mode: str,
        prompt: str,
        studio_panel: dict[str, Any] | None,
        research_objects: dict[str, Any] | None = None,
        planning_objects: dict[str, Any] | None = None,
        evaluation_history: list[dict[str, Any]] | None = None,
        revision_lineage: dict[str, Any] | None = None,
        source_linked_artifacts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "mode": str(mode or "").strip() or "unknown",
            "prompt": " ".join(str(prompt or "").split()).strip(),
            "studio_panel": self._clean_dict(studio_panel),
            "research_objects": self._clean_dict(research_objects),
            "planning_objects": self._clean_dict(planning_objects),
            "evaluation_history": self._clean_list(evaluation_history or []),
            "revision_lineage": self._clean_dict(revision_lineage),
            "source_linked_artifacts": self._clean_dict(source_linked_artifacts),
        }

    def build_evaluation_entry(self, review_result: dict[str, Any] | None) -> dict[str, Any]:
        review_result = review_result if isinstance(review_result, dict) else {}
        scorecard = review_result.get("scorecard") if isinstance(review_result.get("scorecard"), dict) else {}
        return {
            "review_type": str(review_result.get("review_type") or "").strip(),
            "evaluation_scope": str(review_result.get("evaluation_scope") or "").strip(),
            "overall_score": scorecard.get("overall_score"),
            "summary": str(review_result.get("summary") or "").strip(),
            "reviewed_asset_ids": [str(item).strip() for item in (review_result.get("reviewed_asset_ids") or []) if str(item).strip()],
            "asset_diagnostics": self._clean_dict(review_result.get("asset_diagnostics")),
            "review_sources": self._clean_list(review_result.get("review_sources") or []),
        }

    def build_revision_lineage(
        self,
        *,
        parent_version_id: Any = None,
        source_content_version_id: Any = None,
        rewrite_mode: str | None = None,
        rewrite_instruction: str | None = None,
        revision_scope: dict[str, Any] | None = None,
        prior_lineage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prior_lineage = prior_lineage if isinstance(prior_lineage, dict) else {}
        ancestor_version_ids = [
            str(item).strip()
            for item in (prior_lineage.get("ancestor_version_ids") or [])
            if str(item).strip()
        ]
        parent_id = str(parent_version_id or "").strip()
        source_id = str(source_content_version_id or "").strip()
        if parent_id and parent_id not in ancestor_version_ids:
            ancestor_version_ids.append(parent_id)
        if source_id and source_id not in ancestor_version_ids:
            ancestor_version_ids.append(source_id)
        return {
            "parent_version_id": parent_id or None,
            "source_content_version_id": source_id or None,
            "rewrite_mode": str(rewrite_mode or "").strip() or None,
            "rewrite_instruction": " ".join(str(rewrite_instruction or "").split()).strip() or None,
            "revision_scope": self._clean_dict(revision_scope),
            "depth": int(prior_lineage.get("depth") or 0) + (1 if (parent_id or source_id) else 0),
            "ancestor_version_ids": ancestor_version_ids[-8:],
        }

    def build_session_state(
        self,
        session_context: dict[str, Any] | None,
        *,
        content_artifact_state: dict[str, Any] | None = None,
        evaluation_entry: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_context = session_context if isinstance(session_context, dict) else {}
        existing = deepcopy(session_context.get("artifact_state")) if isinstance(session_context.get("artifact_state"), dict) else {}
        state = {
            "schema_version": self.SCHEMA_VERSION,
            "research_objects": self._clean_dict(existing.get("research_objects")),
            "planning_objects": self._clean_dict(existing.get("planning_objects")),
            "evaluation_history": self._clean_list(existing.get("evaluation_history") or []),
            "revision_lineage": self._clean_dict(existing.get("revision_lineage")),
            "source_linked_artifacts": self._clean_dict(existing.get("source_linked_artifacts")),
            "last_artifact_state": self._clean_dict(existing.get("last_artifact_state")),
        }
        if isinstance(content_artifact_state, dict) and content_artifact_state:
            state["research_objects"] = self._clean_dict(content_artifact_state.get("research_objects"))
            state["planning_objects"] = self._clean_dict(content_artifact_state.get("planning_objects"))
            state["revision_lineage"] = self._clean_dict(content_artifact_state.get("revision_lineage"))
            state["source_linked_artifacts"] = self._clean_dict(content_artifact_state.get("source_linked_artifacts"))
            state["last_artifact_state"] = self._clean_dict(content_artifact_state)
        if isinstance(evaluation_entry, dict) and evaluation_entry:
            history = state["evaluation_history"] + [self._clean_dict(evaluation_entry)]
            state["evaluation_history"] = history[-6:]
        return state

    @classmethod
    def _clean_dict(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if item is None:
                continue
            if isinstance(item, dict):
                nested = cls._clean_dict(item)
                if nested:
                    cleaned[str(key)] = nested
            elif isinstance(item, list):
                nested_list = cls._clean_list(item)
                if nested_list:
                    cleaned[str(key)] = nested_list
            else:
                cleaned[str(key)] = item
        return cleaned

    @classmethod
    def _clean_list(cls, value: list[Any]) -> list[Any]:
        cleaned: list[Any] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, dict):
                nested = cls._clean_dict(item)
                if nested:
                    cleaned.append(nested)
            elif isinstance(item, list):
                nested_list = cls._clean_list(item)
                if nested_list:
                    cleaned.append(nested_list)
            else:
                cleaned.append(item)
        return cleaned
