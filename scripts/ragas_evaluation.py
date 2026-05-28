from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


import logging

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE_ROOT = ROOT / "storage" / "generation_traces"
DEFAULT_OUTPUT_DIR = ROOT / "storage" / "ragas_evaluation"
REPORT_TIMEZONE = ZoneInfo("Asia/Kolkata")
REPORT_TIMEZONE_LABEL = "India"

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass


WORD_RE = re.compile(r"[a-zA-Z0-9]+")

RAGAS_CONTEXT_KEYS = (
    "brand_copy_brief",
    "audience_brief",
    "objective_brief",
    "research_editorial_brief",
)

RAGAS_RELEVANT_CHANNELS = {
    "audience_insights",
    "brand",
    "campaign_history",
    "guardrail_support",
    "metadata",
    "research",
    "strategy",
}


@dataclass
class EvalSample:
    trace_id: str
    sample_id: str
    user_input: str
    response: str
    retrieved_contexts: list[str]
    reference: str
    metadata: dict[str, Any]


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def compact_json(value: Any, *, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def is_empty_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def clean_empty_fields(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            cleaned_item = clean_empty_fields(item)
            if not is_empty_value(cleaned_item):
                cleaned[key] = cleaned_item
        return cleaned
    if isinstance(value, list):
        cleaned_items = [clean_empty_fields(item) for item in value]
        return [item for item in cleaned_items if not is_empty_value(item)]
    return value


def clean_report_content(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: clean_report_content(item)
            for key, item in value.items()
            if not is_empty_value(clean_report_content(item))
        }
    if isinstance(value, list):
        cleaned_items = [clean_report_content(item) for item in value]
        return [item for item in cleaned_items if not is_empty_value(item)]
    if isinstance(value, str):
        return value.replace('"', "'")
    return value


def compact_context(value: Any, *, limit: int = 4000) -> str:
    return compact_json(clean_empty_fields(value), limit=limit)


def token_set(text: str) -> set[str]:
    return {token.lower() for token in WORD_RE.findall(text or "") if len(token) > 2}


def overlap_score(left: str, right: str) -> float:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def safe_mean(values: list[float]) -> float:
    values = [value for value in values if isinstance(value, (int, float)) and not math.isnan(value)]
    return round(sum(values) / len(values), 4) if values else 0.0


def concise_error(exc: Exception) -> str:
    message = re.sub(r"\s+", " ", str(exc)).strip()
    if not message:
        message = repr(exc) or exc.__class__.__name__
    if "Connection error" in message:
        return "Connection error while running RAGAS judge model. Fallback scores were used."
    if "LLM is not set" in message or "set LLM before use" in message:
        return "RAGAS judge model was not configured. Fallback scores were used."
    return (message[:300] + "...") if len(message) > 300 else message


def report_timestamp() -> str:
    return datetime.now(REPORT_TIMEZONE).isoformat(timespec="seconds")


def report_output_dir(base_output_dir: Path, trace_id: str | None) -> Path:
    return base_output_dir / trace_id if trace_id else base_output_dir / "_combined"


def collect_contexts(compiled_context: dict[str, Any], orchestrator_final: dict[str, Any]) -> list[str]:
    contexts: list[str] = []

    for key in RAGAS_CONTEXT_KEYS:
        text = compact_context(compiled_context.get(key), limit=12000)
        if text:
            contexts.append(f"{key}: {text}")

    for item in compiled_context.get("knowledge_brief", []) or []:
        if isinstance(item, dict) and item.get("channel") not in RAGAS_RELEVANT_CHANNELS:
            continue
        text = compact_context(item, limit=1800)
        if text:
            contexts.append(f"knowledge_brief: {text}")

    retrieved = ((orchestrator_final.get("explainability") or {}).get("retrieved_knowledge") or {})
    if isinstance(retrieved, dict):
        for channel, items in retrieved.items():
            if channel not in RAGAS_RELEVANT_CHANNELS:
                continue
            for item in items or []:
                text = compact_context(item, limit=1800)
                if text:
                    contexts.append(f"retrieved_knowledge.{channel}: {text}")

    deduped: list[str] = []
    seen: set[str] = set()
    for context in contexts:
        key = context[:300]
        if key not in seen:
            seen.add(key)
            deduped.append(context)
    return deduped


SOURCE_CHANNEL_MAP = {
    "brand_copy_brief": "brand",
    "brand_visual_brief": "visual_identity",
    "audience_brief": "audience_insights",
    "objective_brief": "strategy",
    "prompt_intelligence_brief": "prompt_intelligence",
    "research_editorial_brief": "research",
    "format_family_plan": "format",
    "content_plan": "content_plan",
    "visual_plan": "visual_plan",
    "template_fit_brief": "template",
    "reference_family_profile": "reference_creative",
    "knowledge_brief": "knowledge",
    "visual_knowledge_item": "visual_identity",
    "reference_asset_brief": "reference_creative",
}

SOURCE_DISPLAY_MAP = {
    "visual_knowledge_item": "visual_knowledge_brief",
}


def build_retrieved_content(contexts: list[str]) -> list[dict[str, Any]]:
    items = []
    for context in contexts:
        source, _, content = context.partition(":")
        source = source.strip() or "context"
        channel = SOURCE_CHANNEL_MAP.get(source)
        parsed_content = content.strip() if content else context
        report_content: Any = parsed_content
        try:
            parsed = json.loads(parsed_content)
            if isinstance(parsed, dict):
                parsed = clean_empty_fields(parsed)
                channel = parsed.get("channel") or parsed.get("role") or channel
                report_content = parsed.get("content") or parsed.get("summary") or parsed.get("text") or parsed
        except Exception:
            report_content = parsed_content
        if source in {"knowledge_brief", "visual_knowledge_item", "reference_asset_brief"}:
            try:
                parsed = json.loads(parsed_content)
                if isinstance(parsed, dict):
                    parsed = clean_empty_fields(parsed)
                    channel = parsed.get("channel") or parsed.get("role") or channel
                    report_content = (
                        parsed.get("content")
                        or parsed.get("summary")
                        or parsed.get("text")
                        or parsed
                    )
            except Exception:
                pass
        elif source.startswith("retrieved_knowledge."):
            channel = source.split(".", 1)[1]
            source = "orchestrator_retrieved_knowledge"
        source = SOURCE_DISPLAY_MAP.get(source, source)
        report_content = clean_report_content(report_content)
        item: dict[str, Any] = {
            "source": source,
            "content": report_content,
        }
        if is_empty_value(report_content):
            continue
        if channel:
            item["channel"] = channel
        items.append(item)
    return items


def collect_retrieved_evidence(compiled_context: dict[str, Any], orchestrator_final: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    for item in compiled_context.get("knowledge_brief", []) or []:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if content:
            items.append(
                {
                    "source": "knowledge_brief",
                    "channel": item.get("channel"),
                    "content": content,
                }
            )

    visual_knowledge = compiled_context.get("visual_knowledge_brief", {}) or {}
    for item in visual_knowledge.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if content:
            items.append(
                {
                    "source": "visual_knowledge_brief",
                    "channel": item.get("channel"),
                    "content": content,
                }
            )

    retrieved = (
        ((orchestrator_final.get("explainability") or {}).get("retrieved_knowledge") or {})
        or ((orchestrator_final.get("explainability") or {}).get("input_access_summary") or {}).get("retrieved_knowledge")
        or {}
    )
    if isinstance(retrieved, dict):
        for channel, channel_items in retrieved.items():
            if channel in {"used_paths", "unused_paths", "read_counts", "access_types", "events"}:
                continue
            if not isinstance(channel_items, list):
                continue
            for item in channel_items:
                content = item.get("content") if isinstance(item, dict) else str(item)
                if content:
                    items.append(
                        {
                            "source": "orchestrator_retrieved_knowledge",
                            "channel": channel,
                            "content": content,
                        }
                    )

    return {
        "item_count": len(items),
        "items": items,
    }


def build_reference(compiled_context: dict[str, Any]) -> str:
    pieces = [
        compiled_context.get("research_summary"),
        compiled_context.get("brand_copy_brief"),
        compiled_context.get("brand_visual_brief"),
        compiled_context.get("reference_family_profile"),
        compiled_context.get("render_constraints"),
    ]
    return "\n".join(compact_json(piece, limit=2500) for piece in pieces if compact_json(piece))


def generated_image_count(trace_dir: Path, final_render_generation: dict[str, Any] | None) -> dict[str, Any]:
    prompt_files = sorted(trace_dir.glob("final_render_prompt_slide_*.json"))
    assets = (final_render_generation or {}).get("assets", []) if isinstance(final_render_generation, dict) else []
    render_assets = [
        asset
        for asset in assets
        if isinstance(asset, dict)
        and ((asset.get("metadata") or {}).get("generation_stage") == "final_render")
    ]
    return {
        "slide_prompt_file_count": len(prompt_files),
        "final_render_asset_count": len(render_assets),
        "generated_image_count": max(len(prompt_files), len(render_assets)),
        "prompt_files": [path.name for path in prompt_files],
        "asset_storage_paths": [asset.get("storage_path") for asset in render_assets if asset.get("storage_path")],
    }


def quoted_after(label: str, text: str) -> str:
    match = re.search(re.escape(label) + r'\s*:\s*"([^"]+)"', text)
    return match.group(1).strip() if match else ""


def extract_slide_response(prompt_payload: dict[str, Any]) -> str:
    prompt_text = str(prompt_payload.get("prompt") or "")
    parts = [
        f"Slide {prompt_payload.get('slide_index')} of {prompt_payload.get('slide_count')}",
        f"Role: {prompt_payload.get('role')}",
    ]
    for label, name in (
        ("Use this headline verbatim in the headline zone", "Headline"),
        ("Use this supporting line verbatim in the support zone", "Support"),
        ("Use this body copy verbatim in the body zone", "Body"),
        ("Use this CTA verbatim in the CTA zone", "CTA"),
    ):
        value = quoted_after(label, prompt_text)
        if value:
            parts.append(f"{name}: {value}")

    visual_focus = re.search(r"Visual focus for this slide:\s*(.*?)(?:Brand palette to honor:|Strict palette contract:)", prompt_text)
    if visual_focus:
        visual_focus_text = re.sub(r"\s+", " ", visual_focus.group(1)).strip()[:1000]
        parts.append(f"Visual focus: {visual_focus_text}")

    response = "\n".join(part for part in parts if part and not part.endswith(": None"))
    return response if len(response.strip()) > 30 else compact_json(prompt_payload, limit=5000)


def build_samples_for_trace(trace_dir: Path) -> tuple[list[EvalSample], dict[str, Any], str]:
    compiled_context = load_json(trace_dir / "compiled_context.json") or {}
    content_request = load_json(trace_dir / "content_request.json") or {}
    orchestrator_final = load_json(trace_dir / "orchestrator_final.json") or {}
    final_render_generation = load_json(trace_dir / "final_render_generation.json") or {}

    prompt = content_request.get("prompt") or compact_json(content_request.get("request") or "")
    contexts = collect_contexts(compiled_context, orchestrator_final)
    reference = build_reference(compiled_context)
    trace_id = trace_dir.name
    count_info = generated_image_count(trace_dir, final_render_generation)

    count_info["retrieved_evidence"] = collect_retrieved_evidence(compiled_context, orchestrator_final)
    count_info["retrieved_content"] = build_retrieved_content(contexts)

    text_payload = orchestrator_final.get("text") or {}
    overall_response = compact_json(text_payload, limit=12000)
    samples: list[EvalSample] = []
    if overall_response:
        samples.append(
            EvalSample(
                trace_id=trace_id,
                sample_id=f"{trace_id}:overall_content",
                user_input=prompt,
                response=overall_response,
                retrieved_contexts=contexts,
                reference=reference,
                metadata={"sample_type": "overall_content", **count_info},
            )
        )

    return samples, count_info, prompt


def build_carousel_slide_samples_for_trace(trace_dir: Path) -> tuple[list[EvalSample], dict[str, Any], str]:
    compiled_context = load_json(trace_dir / "compiled_context.json") or {}
    content_request = load_json(trace_dir / "content_request.json") or {}
    orchestrator_final = load_json(trace_dir / "orchestrator_final.json") or {}
    final_render_generation = load_json(trace_dir / "final_render_generation.json") or {}

    prompt = content_request.get("prompt") or compact_json(content_request.get("request") or "")
    contexts = collect_contexts(compiled_context, orchestrator_final)
    reference = build_reference(compiled_context)
    trace_id = trace_dir.name
    count_info = generated_image_count(trace_dir, final_render_generation)

    count_info["retrieved_evidence"] = collect_retrieved_evidence(compiled_context, orchestrator_final)
    count_info["retrieved_content"] = build_retrieved_content(contexts)

    prompt_files = sorted(trace_dir.glob("final_render_prompt_slide_*.json"))
    if len(prompt_files) <= 1:
        return [], count_info, prompt

    samples: list[EvalSample] = []
    for prompt_file in prompt_files:
        prompt_payload = load_json(prompt_file) or {}
        slide_index = int(prompt_payload.get("slide_index") or len(samples) + 1)
        slide_count = int(prompt_payload.get("slide_count") or len(prompt_files))
        samples.append(
            EvalSample(
                trace_id=trace_id,
                sample_id=f"{trace_id}:slide_{slide_index:02d}",
                user_input=f"{prompt} | Evaluate carousel slide {slide_index} of {slide_count}",
                response=extract_slide_response(prompt_payload),
                retrieved_contexts=contexts,
                reference=reference,
                metadata={
                    "sample_type": "carousel_slide",
                    "slide_index": slide_index,
                    "slide_count": slide_count,
                    "prompt_file": prompt_file.name,
                    **count_info,
                },
            )
        )

    return samples, count_info, prompt


def heuristic_scores(sample: EvalSample) -> dict[str, float]:
    context_blob = "\n".join(sample.retrieved_contexts)
    return {
        "faithfulness": round(overlap_score(sample.response, context_blob), 4),
        "response_relevancy": round(overlap_score(sample.user_input, sample.response), 4),
        "context_precision": round(
            safe_mean([overlap_score(context, sample.user_input + " " + sample.response) for context in sample.retrieved_contexts]),
            4,
        ),
        "context_recall": round(overlap_score(sample.reference, context_blob), 4),
    }


def try_run_ragas(samples: list[EvalSample]) -> tuple[str, dict[str, dict[str, float]], str | None]:
    logger.debug("ragas_evaluation.try_run_ragas samples=%d", len(samples))

    _import_errors: list[str] = []
    for pkg, stmt in [
        ("datasets", "from datasets import Dataset"),
        ("langchain_openai", "from langchain_openai import ChatOpenAI, OpenAIEmbeddings"),
        ("ragas", "from ragas import evaluate"),
        ("ragas.embeddings", "from ragas.embeddings import LangchainEmbeddingsWrapper"),
        ("ragas.llms", "from ragas.llms import LangchainLLMWrapper"),
        ("ragas.metrics", "from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness"),
        ("ragas.run_config", "from ragas.run_config import RunConfig"),
    ]:
        try:
            exec(stmt, globals())  # noqa: S102
        except Exception as exc:
            logger.error("ragas_evaluation.import_failed pkg=%s error=%s", pkg, exc)
            _import_errors.append(f"{pkg}: {exc}")

    if _import_errors:
        msg = "RAGAS unavailable: " + "; ".join(_import_errors)
        logger.warning("ragas_evaluation.import_blocked errors=%s", _import_errors)
        return "heuristic_fallback", {}, msg

    try:
        api_key_present = bool(os.getenv("OPENAI_API_KEY"))
        logger.debug("ragas_evaluation.api_key_present=%s", api_key_present)
        if not api_key_present:
            logger.warning("ragas_evaluation.no_api_key using heuristic fallback")
            return "heuristic_fallback", {}, "RAGAS judge model was not configured. Fallback scores were used."

        llm_model = os.getenv("RAGAS_LLM_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        embedding_model = (
            os.getenv("RAGAS_EMBEDDING_MODEL")
            or os.getenv("EMBEDDING_MODEL")
            or "text-embedding-3-small"
        )

        evaluator_llm = LangchainLLMWrapper(
            ChatOpenAI(
                model=llm_model,
                temperature=0,
            )
        )
        evaluator_embeddings = LangchainEmbeddingsWrapper(
            OpenAIEmbeddings(model=embedding_model)
        )
        dataset = Dataset.from_dict(
            {
                "user_input": [sample.user_input for sample in samples],
                "response": [sample.response for sample in samples],
                "retrieved_contexts": [sample.retrieved_contexts for sample in samples],
                "reference": [sample.reference for sample in samples],
            }
        )
        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()
        with contextlib.redirect_stdout(captured_stdout), contextlib.redirect_stderr(captured_stderr):
            result = evaluate(
                dataset,
                metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
                llm=evaluator_llm,
                embeddings=evaluator_embeddings,
                run_config=RunConfig(
                    timeout=int(os.getenv("RAGAS_TIMEOUT_SECONDS", "180")),
                    max_retries=int(os.getenv("RAGAS_MAX_RETRIES", "2")),
                ),
                raise_exceptions=True,
                batch_size=1,
                show_progress=False,
            )
        frame = result.to_pandas()
        scores: dict[str, dict[str, float]] = {}
        for index, sample in enumerate(samples):
            row = frame.iloc[index].to_dict()
            scores[sample.sample_id] = {
                metric: round(float(row.get(metric, 0.0) or 0.0), 4)
                for metric in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
            }
        return "ragas", scores, None
    except Exception as exc:
        return "heuristic_fallback", {}, f"RAGAS execution failed: {concise_error(exc)}"


def append_evaluation_report(production_path: Path, new_report: dict[str, Any]) -> dict[str, Any]:
    existing = load_json(production_path)
    existing_evaluations = []
    if isinstance(existing, dict):
        existing_evaluations = list(existing.get("evaluations") or [])

    merged_by_generation: dict[str, dict[str, Any]] = {}
    for evaluation in existing_evaluations:
        if not isinstance(evaluation, dict):
            continue
        if evaluation.get("evaluator") != "ragas":
            continue
        generation_id = str(evaluation.get("generation_id") or "").strip()
        if generation_id:
            merged_by_generation[generation_id] = evaluation

    if new_report.get("evaluator") == "ragas":
        for evaluation in new_report.get("evaluations") or []:
            if not isinstance(evaluation, dict):
                continue
            generation_id = str(evaluation.get("generation_id") or "").strip()
            if not generation_id:
                continue
            merged_by_generation[generation_id] = {
                **evaluation,
                "evaluated_at": new_report.get("generated_at"),
                "evaluator": "ragas",
                "warning": None,
            }

    evaluations = list(merged_by_generation.values())

    return {
        "generated_at": new_report.get("generated_at"),
        "timezone": new_report.get("timezone", REPORT_TIMEZONE_LABEL),
        "evaluator": "ragas",
        "warning": None,
        "total_evaluations": len(evaluations),
        "total_evaluation_samples": sum(int(item.get("evaluation_samples") or 0) for item in evaluations),
        "total_generated_images": sum(int(item.get("generated_images") or 0) for item in evaluations),
        "evaluations": evaluations,
    }


def append_fallback_report(fallback_path: Path, fallback_report: dict[str, Any]) -> dict[str, Any]:
    existing = load_json(fallback_path)
    existing_evaluations = []
    if isinstance(existing, dict):
        existing_evaluations = list(existing.get("evaluations") or [])

    merged_by_generation: dict[str, dict[str, Any]] = {}
    for evaluation in existing_evaluations:
        if not isinstance(evaluation, dict):
            continue
        generation_id = str(evaluation.get("generation_id") or "").strip()
        if generation_id:
            merged_by_generation[generation_id] = evaluation

    for evaluation in fallback_report.get("evaluations") or []:
        if not isinstance(evaluation, dict):
            continue
        generation_id = str(evaluation.get("generation_id") or "").strip()
        if not generation_id:
            continue
        merged_by_generation[generation_id] = {
            **evaluation,
            "evaluated_at": fallback_report.get("generated_at"),
            "evaluator": fallback_report.get("evaluator", "heuristic_fallback"),
            "warning": fallback_report.get("warning"),
        }

    evaluations = list(merged_by_generation.values())
    return {
        "generated_at": fallback_report.get("generated_at"),
        "timezone": fallback_report.get("timezone", REPORT_TIMEZONE_LABEL),
        "evaluator": "heuristic_fallback",
        "warning": fallback_report.get("warning"),
        "total_evaluations": len(evaluations),
        "total_evaluation_samples": sum(int(item.get("evaluation_samples") or 0) for item in evaluations),
        "total_generated_images": sum(int(item.get("generated_images") or 0) for item in evaluations),
        "evaluations": evaluations,
    }


def append_carousel_slide_report(output_path: Path, new_report: dict[str, Any]) -> dict[str, Any]:
    existing = load_json(output_path)
    existing_evaluations = []
    if isinstance(existing, dict):
        existing_evaluations = list(existing.get("evaluations") or [])

    merged_by_generation: dict[str, dict[str, Any]] = {}
    for evaluation in existing_evaluations:
        if not isinstance(evaluation, dict):
            continue
        generation_id = str(evaluation.get("generation_id") or "").strip()
        if generation_id:
            merged_by_generation[generation_id] = evaluation

    if new_report.get("evaluator") == "ragas":
        for evaluation in new_report.get("evaluations") or []:
            if not isinstance(evaluation, dict):
                continue
            generation_id = str(evaluation.get("generation_id") or "").strip()
            if generation_id:
                merged_by_generation[generation_id] = {
                    **evaluation,
                    "evaluated_at": new_report.get("generated_at"),
                    "evaluator": "ragas",
                    "warning": None,
                }

    evaluations = list(merged_by_generation.values())
    return {
        "generated_at": new_report.get("generated_at"),
        "timezone": new_report.get("timezone", REPORT_TIMEZONE_LABEL),
        "evaluator": "ragas",
        "warning": None,
        "total_carousel_evaluations": len(evaluations),
        "total_slide_evaluation_samples": sum(int(item.get("slide_evaluation_samples") or 0) for item in evaluations),
        "evaluations": evaluations,
    }


def build_carousel_slide_report(
    trace_summaries: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    mode: str,
    warning: str | None,
) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    for trace in trace_summaries:
        trace_rows = [row for row in rows if row["trace_id"] == trace["trace_id"]]
        if not trace_rows:
            continue
        slide_scores = []
        for row in sorted(trace_rows, key=lambda item: int((item.get("metadata") or {}).get("slide_index") or 0)):
            metadata = row.get("metadata") or {}
            slide_scores.append(
                {
                    "slide_index": metadata.get("slide_index"),
                    "prompt_file": metadata.get("prompt_file"),
                    "scores": row.get("scores") or {},
                }
            )
        evaluations.append(
            {
                "generation_id": trace["trace_id"],
                "prompt": trace["prompt"],
                "generated_images": trace.get("generated_image_count", 0),
                "slide_evaluation_samples": len(trace_rows),
                "retrieved_content": trace.get("retrieved_content", []),
                "slide_scores": slide_scores,
            }
        )

    return {
        "generated_at": report_timestamp(),
        "timezone": REPORT_TIMEZONE_LABEL,
        "evaluator": mode,
        "warning": warning,
        "total_slide_evaluation_samples": len(rows),
        "evaluations": evaluations,
    }


def evaluate_carousel_slides(trace_dirs: list[Path], output_dir: Path) -> None:
    all_samples: list[EvalSample] = []
    trace_summaries: list[dict[str, Any]] = []
    for trace_dir in trace_dirs:
        samples, count_info, prompt = build_carousel_slide_samples_for_trace(trace_dir)
        if not samples:
            continue
        all_samples.extend(samples)
        trace_summaries.append(
            {
                "trace_id": trace_dir.name,
                "prompt": prompt,
                "sample_count": len(samples),
                **count_info,
            }
        )

    if not all_samples:
        return

    mode, ragas_scores, warning = try_run_ragas(all_samples)
    rows = []
    for sample in all_samples:
        scores = ragas_scores.get(sample.sample_id) if ragas_scores else heuristic_scores(sample)
        if "answer_relevancy" in scores and "response_relevancy" not in scores:
            scores["response_relevancy"] = scores["answer_relevancy"]
        rows.append(
            {
                "trace_id": sample.trace_id,
                "sample_id": sample.sample_id,
                "metadata": sample.metadata,
                "scores": scores,
                "input_preview": sample.user_input[:500],
                "response_preview": sample.response[:1000],
                "retrieved_context_count": len(sample.retrieved_contexts),
                "reference_preview": sample.reference[:1000],
            }
        )

    slide_report = build_carousel_slide_report(trace_summaries, rows, mode, warning)
    if mode == "ragas":
        slide_path = output_dir / "ragas_carousel_slide_evaluation.json"
        slide_report = append_carousel_slide_report(slide_path, slide_report)
        slide_path.write_text(json.dumps(slide_report, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        fallback_path = output_dir / "ragas_carousel_slide_evaluation_fallback.json"
        fallback_report = append_fallback_report(fallback_path, slide_report)
        fallback_path.write_text(json.dumps(fallback_report, indent=2, ensure_ascii=False), encoding="utf-8")


def evaluate_traces(trace_root: Path, output_dir: Path, trace_id: str | None = None) -> dict[str, Any]:
    logger.debug(
        "ragas_evaluation.evaluate_traces trace_root=%s trace_id=%s exists=%s",
        trace_root, trace_id, trace_root.exists(),
    )
    if trace_id:
        trace_dir_check = trace_root / trace_id
        logger.debug(
            "ragas_evaluation.trace_dir=%s exists=%s files=%s",
            trace_dir_check,
            trace_dir_check.exists(),
            [f.name for f in trace_dir_check.iterdir()] if trace_dir_check.exists() else [],
        )
        trace_dirs = [trace_dir_check]
    else:
        trace_dirs = [
            path
            for path in sorted(trace_root.iterdir())
            if path.is_dir() and (path / "compiled_context.json").exists()
        ]

    all_samples: list[EvalSample] = []
    trace_summaries: list[dict[str, Any]] = []
    for trace_dir in trace_dirs:
        if not trace_dir.exists():
            continue
        samples, count_info, prompt = build_samples_for_trace(trace_dir)
        all_samples.extend(samples)
        trace_summaries.append(
            {
                "trace_id": trace_dir.name,
                "prompt": prompt,
                "sample_count": len(samples),
                **count_info,
            }
        )

    logger.debug("ragas_evaluation.samples_built count=%d", len(all_samples))
    mode, ragas_scores, warning = try_run_ragas(all_samples)
    logger.debug("ragas_evaluation.mode=%s warning=%s", mode, warning)
    rows = []
    for sample in all_samples:
        scores = ragas_scores.get(sample.sample_id) if ragas_scores else heuristic_scores(sample)
        if "answer_relevancy" in scores and "response_relevancy" not in scores:
            scores["response_relevancy"] = scores["answer_relevancy"]
        rows.append(
            {
                "trace_id": sample.trace_id,
                "sample_id": sample.sample_id,
                "metadata": sample.metadata,
                "scores": scores,
                "input_preview": sample.user_input[:500],
                "response_preview": sample.response[:1000],
                "retrieved_context_count": len(sample.retrieved_contexts),
                "reference_preview": sample.reference[:1000],
            }
        )

    metric_names = ["faithfulness", "response_relevancy", "context_precision", "context_recall"]
    summary_scores = {
        metric: safe_mean([row["scores"].get(metric, row["scores"].get("answer_relevancy", 0.0)) for row in rows])
        for metric in metric_names
    }

    trace_scores: dict[str, dict[str, float]] = {}
    for trace in trace_summaries:
        trace_rows = [row for row in rows if row["trace_id"] == trace["trace_id"]]
        trace_scores[trace["trace_id"]] = {
            metric: safe_mean(
                [row["scores"].get(metric, row["scores"].get("answer_relevancy", 0.0)) for row in trace_rows]
            )
            for metric in metric_names
        }

    production_evaluations = [
        {
            "generation_id": trace["trace_id"],
            "prompt": trace["prompt"],
            "generated_images": trace.get("generated_image_count", 0),
            "evaluation_samples": trace["sample_count"],
            "retrieved_content": trace.get("retrieved_content", []),
            "scores": trace_scores.get(trace["trace_id"], {}),
        }
        for trace in trace_summaries
    ]

    production_report = {
        "generated_at": report_timestamp(),
        "timezone": REPORT_TIMEZONE_LABEL,
        "evaluator": mode,
        "warning": warning,
        "total_evaluation_samples": len(rows),
        "total_generated_images": sum(item.get("generated_image_count", 0) for item in trace_summaries),
        "evaluations": production_evaluations,
    }

    write_dir = report_output_dir(output_dir, trace_id)
    write_dir.mkdir(parents=True, exist_ok=True)
    production_path = write_dir / "ragas_evaluation.json"
    fallback_path = write_dir / "ragas_evaluation_fallback.json"

    if mode == "ragas":
        production_report = append_evaluation_report(production_path, production_report)
        production_path.write_text(json.dumps(production_report, indent=2, ensure_ascii=False), encoding="utf-8")
        return_report = production_report
    else:
        fallback_report = append_fallback_report(fallback_path, production_report)
        fallback_path.write_text(json.dumps(fallback_report, indent=2, ensure_ascii=False), encoding="utf-8")
        return_report = fallback_report

    evaluate_carousel_slides(trace_dirs, write_dir)
    return return_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate generation trace RAG grounding with RAGAS-compatible samples.")
    parser.add_argument("--trace-root", type=Path, default=DEFAULT_TRACE_ROOT)
    parser.add_argument("--trace-id", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    report = evaluate_traces(args.trace_root, args.output_dir, args.trace_id)
    write_dir = report_output_dir(args.output_dir, args.trace_id)
    print(json.dumps({
        "output_dir": str(write_dir),
        "output": str(write_dir / "ragas_evaluation.json"),
        "carousel_slide_output": str(write_dir / "ragas_carousel_slide_evaluation.json"),
        "fallback_output": str(write_dir / "ragas_evaluation_fallback.json"),
        "carousel_slide_fallback_output": str(write_dir / "ragas_carousel_slide_evaluation_fallback.json"),
        "evaluator": report["evaluator"],
        "total_evaluation_samples": report["total_evaluation_samples"],
        "total_generated_images": report["total_generated_images"],
        "evaluations": report["evaluations"],
        "warning": report["warning"],
    }, indent=2))


if __name__ == "__main__":
    main()
