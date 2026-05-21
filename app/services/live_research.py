from __future__ import annotations

import asyncio
import json
from html import unescape
from html.parser import HTMLParser
import re
import threading
from typing import Any

import httpx
from openai import OpenAI

from app.ai.providers.base import PromptEnvelope
from app.ai.providers.router import ProviderRouter
from app.core.config import get_settings


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = " ".join(data.split()).strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return " ".join(self._chunks).strip()


class LiveResearchService:
    CURRENT_SIGNAL_PATTERN = re.compile(
        r"\b(?:latest|current|today|recent|as of|202[4-9]|repo rate|policy rate|market size|fdi|inflow|cagr|xirr|returns?)\b",
        re.IGNORECASE,
    )
    URL_PATTERN = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)

    def __init__(self) -> None:
        self.settings = get_settings()
        self.providers = ProviderRouter()
        self.research_provider = self.providers.get_text_provider("research")
        self.openai_search_client = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None

    @staticmethod
    def _normalize_text(value: Any, limit: int | None = None) -> str:
        text = " ".join(str(value or "").split()).strip()
        if limit is None or not text:
            return text
        return text[:limit].rstrip(" ,.;:")

    def _urls_from_context(self, prompt: str, compiled_context: dict[str, Any]) -> list[str]:
        urls = self.URL_PATTERN.findall(prompt or "")
        knowledge_brief = compiled_context.get("knowledge_brief", []) or []
        for item in knowledge_brief:
            if not isinstance(item, dict):
                continue
            for field in ("url", "source_url", "link", "content"):
                urls.extend(self.URL_PATTERN.findall(str(item.get(field) or "")))
        deduped: list[str] = []
        seen: set[str] = set()
        for url in urls:
            normalized = url.rstrip(".,);]")
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        return deduped[:6]

    def _heuristic_query_plan(self, prompt: str, studio_panel: dict[str, Any], compiled_context: dict[str, Any]) -> dict[str, Any]:
        prompt_text = self._normalize_text(prompt, limit=300)
        platform = self._normalize_text(studio_panel.get("platform_preset"), limit=32)
        format_name = self._normalize_text(studio_panel.get("format"), limit=32)
        knowledge = compiled_context.get("knowledge_brief", []) or []
        knowledge_line = ""
        if knowledge and isinstance(knowledge[0], dict):
            knowledge_line = self._normalize_text(knowledge[0].get("content"), limit=180)
        needs_live = bool(self.CURRENT_SIGNAL_PATTERN.search(prompt_text))
        queries = [prompt_text]
        if knowledge_line:
            queries.append(f"{prompt_text} {knowledge_line}")
        queries.append(f"{prompt_text} {platform} {format_name}")
        return {
            "needs_live_research": needs_live,
            "queries": [query for query in queries if query][: self.settings.live_research_max_queries],
            "facts_to_verify": ["exact values", "dates", "percentages", "chart labels", "sources"],
            "preferred_sources": [],
        }

    def _has_live_search_backend(self) -> bool:
        backend = str(self.settings.live_research_search_backend or "openai").strip().lower()
        if backend == "openai":
            return self.openai_search_client is not None
        if backend == "brave":
            return bool(self.settings.brave_search_api_key)
        return self.openai_search_client is not None or bool(self.settings.brave_search_api_key)

    def _normalize_verified_facts(self, facts: Any) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for fact in facts if isinstance(facts, list) else []:
            if not isinstance(fact, dict):
                continue
            label = self._normalize_text(fact.get("label"), limit=120)
            value = self._normalize_text(fact.get("value"), limit=240)
            source_title = self._normalize_text(fact.get("source_title"), limit=160)
            source_url = self._normalize_text(fact.get("source_url"), limit=400)
            if not value and not label:
                continue
            key = (label.casefold(), value.casefold(), (source_url or source_title).casefold())
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                {
                    "label": label or "Fact",
                    "value": value or label,
                    "source_title": source_title,
                    "source_url": source_url,
                }
            )
        return normalized[:8]

    def _rank_sources(
        self,
        *,
        sources: list[dict[str, str]],
        verified_facts: list[dict[str, str]],
        preferred_sources: list[str],
    ) -> list[dict[str, Any]]:
        fact_title_hits = {
            self._normalize_text(fact.get("source_title"), limit=160).casefold()
            for fact in verified_facts
            if self._normalize_text(fact.get("source_title"), limit=160)
        }
        fact_url_hits = {
            self._normalize_text(fact.get("source_url"), limit=400).casefold()
            for fact in verified_facts
            if self._normalize_text(fact.get("source_url"), limit=400)
        }
        preferred = {self._normalize_text(item, limit=160).casefold() for item in preferred_sources if self._normalize_text(item, limit=160)}
        ranked: list[dict[str, Any]] = []
        for index, source in enumerate(sources, start=1):
            title = self._normalize_text(source.get("title"), limit=180)
            url = self._normalize_text(source.get("url"), limit=400)
            title_key = title.casefold()
            url_key = url.casefold()
            support_count = sum(
                1
                for fact in verified_facts
                if (
                    title_key
                    and title_key == self._normalize_text(fact.get("source_title"), limit=160).casefold()
                )
                or (
                    url_key
                    and url_key == self._normalize_text(fact.get("source_url"), limit=400).casefold()
                )
            )
            rank_score = 0
            if title_key in fact_title_hits or url_key in fact_url_hits:
                rank_score += 4
            if title_key in preferred or url_key in preferred:
                rank_score += 2
            rank_score += max(0, 5 - index)
            ranked.append(
                {
                    "rank": index,
                    "title": title,
                    "url": url,
                    "support_count": support_count,
                    "rank_score": rank_score,
                    "is_preferred": title_key in preferred or url_key in preferred,
                    "is_fact_backed": title_key in fact_title_hits or url_key in fact_url_hits,
                }
            )
        ranked.sort(key=lambda item: (-int(item.get("rank_score") or 0), -int(item.get("support_count") or 0), int(item.get("rank") or 0)))
        for index, item in enumerate(ranked, start=1):
            item["rank"] = index
        return ranked[:6]

    def _build_inferences(self, *, summary: str, verified_facts: list[dict[str, str]]) -> list[str]:
        sentences = [self._normalize_text(part, limit=260) for part in re.split(r"(?<=[.!?])\s+", summary or "") if self._normalize_text(part, limit=260)]
        exact_fact_values = {
            self._normalize_text(fact.get("value"), limit=180).casefold()
            for fact in verified_facts
            if self._normalize_text(fact.get("value"), limit=180)
        }
        exact_fact_labels = {
            self._normalize_text(fact.get("label"), limit=120).casefold()
            for fact in verified_facts
            if self._normalize_text(fact.get("label"), limit=120)
        }
        inference_markers = (
            "suggest",
            "implies",
            "could",
            "may",
            "likely",
            "signals",
            "points to",
            "means",
            "matters",
            "strategic",
            "undercovered",
            "trade-off",
            "second-order",
        )
        inferences: list[str] = []
        for sentence in sentences:
            lowered = sentence.casefold()
            if any(marker in lowered for marker in inference_markers):
                if not any(value and value in lowered for value in exact_fact_values) or any(label and label in lowered for label in exact_fact_labels):
                    inferences.append(sentence)
        if not inferences and sentences:
            for sentence in sentences[:2]:
                lowered = sentence.casefold()
                if not any(value and value in lowered for value in exact_fact_values):
                    inferences.append(sentence)
        deduped: list[str] = []
        seen: set[str] = set()
        for sentence in inferences:
            key = sentence.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(sentence)
        return deduped[:4]

    def _build_uncertainties(
        self,
        *,
        summary: str,
        facts_to_verify: list[str],
        verified_facts: list[dict[str, str]],
        sources: list[dict[str, Any]],
    ) -> list[str]:
        uncertainties: list[str] = []
        lowered = (summary or "").casefold()
        if any(marker in lowered for marker in ("expected", "pending", "subject to", "phased", "not yet clear", "unclear")):
            uncertainties.append("Some implications remain conditional or phased, so avoid overstating certainty.")
        if not verified_facts:
            uncertainties.append("No externally verified facts were confirmed, so claims should stay cautious.")
        if len(sources) < 2:
            uncertainties.append("Source depth is limited; treat conclusions as provisional until more corroboration is available.")
        if facts_to_verify and len(verified_facts) < min(2, len(facts_to_verify)):
            missing = ", ".join(str(item).strip() for item in facts_to_verify[:3] if str(item).strip())
            if missing:
                uncertainties.append(f"Some important details still need verification: {missing}.")
        deduped: list[str] = []
        seen: set[str] = set()
        for item in uncertainties:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:4]

    async def _plan_queries(self, prompt: str, studio_panel: dict[str, Any], compiled_context: dict[str, Any]) -> dict[str, Any]:
        fallback = self._heuristic_query_plan(prompt, studio_panel, compiled_context)
        if not getattr(self.research_provider, "client", None):
            return fallback
        envelope = PromptEnvelope(
            system=(
                "You are a live research planner for social/content generation. "
                "Return JSON only with keys: needs_live_research, queries, facts_to_verify, preferred_sources. "
                "needs_live_research must be true when the prompt needs current values, dates, rankings, rates, market data, policy data, or chart numbers that should be externally verified."
            ),
            user=(
                f"Prompt: {prompt}\n"
                f"Studio panel: {studio_panel}\n"
                f"Compiled context: {compiled_context}"
            ),
        )
        try:
            planned = await asyncio.to_thread(
                self.research_provider.generate_structured_json,
                envelope,
                fallback,
            )
        except Exception:
            return fallback
        if not isinstance(planned, dict):
            return fallback
        queries = planned.get("queries")
        planned["queries"] = [
            self._normalize_text(query, limit=220)
            for query in (queries if isinstance(queries, list) else [])
            if self._normalize_text(query, limit=220)
        ][: self.settings.live_research_max_queries] or fallback["queries"]
        if not isinstance(planned.get("facts_to_verify"), list):
            planned["facts_to_verify"] = fallback["facts_to_verify"]
        if not isinstance(planned.get("preferred_sources"), list):
            planned["preferred_sources"] = []
        planned["needs_live_research"] = bool(planned.get("needs_live_research") or fallback["needs_live_research"])
        return planned

    async def _brave_search(self, client: httpx.AsyncClient, query: str) -> list[dict[str, str]]:
        if not self.settings.brave_search_api_key:
            return []
        response = await client.get(
            self.settings.brave_search_api_base,
            params={"q": query, "count": self.settings.live_research_max_results_per_query},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.settings.brave_search_api_key,
            },
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
        web_results = ((payload.get("web") or {}).get("results") or []) if isinstance(payload, dict) else []
        results: list[dict[str, str]] = []
        for item in web_results[: self.settings.live_research_max_results_per_query]:
            if not isinstance(item, dict):
                continue
            url = self._normalize_text(item.get("url"), limit=400)
            title = self._normalize_text(item.get("title"), limit=180)
            description = self._normalize_text(item.get("description"), limit=320)
            if url:
                results.append({"url": url, "title": title, "snippet": description})
        return results

    @classmethod
    def _collect_web_search_sources(cls, node: Any, results: list[dict[str, str]]) -> None:
        if isinstance(node, dict):
            source = None
            source_blob = node.get("url_citation")
            if isinstance(source_blob, dict):
                source = {
                    "url": cls._normalize_text(source_blob.get("url"), limit=400),
                    "title": cls._normalize_text(source_blob.get("title"), limit=180),
                    "snippet": cls._normalize_text(source_blob.get("text") or source_blob.get("snippet"), limit=320),
                }
            elif "url" in node and any(key in node for key in ("title", "snippet", "description")):
                source = {
                    "url": cls._normalize_text(node.get("url"), limit=400),
                    "title": cls._normalize_text(node.get("title"), limit=180),
                    "snippet": cls._normalize_text(node.get("snippet") or node.get("description") or node.get("text"), limit=320),
                }
            if source and source["url"]:
                results.append(source)
            for value in node.values():
                cls._collect_web_search_sources(value, results)
            return
        if isinstance(node, list):
            for item in node:
                cls._collect_web_search_sources(item, results)

    def _normalize_search_results(self, results: list[dict[str, str]]) -> list[dict[str, str]]:
        deduped: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in results:
            if not isinstance(item, dict):
                continue
            url = self._normalize_text(item.get("url"), limit=400)
            if not url:
                continue
            key = url.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(
                {
                    "url": url,
                    "title": self._normalize_text(item.get("title"), limit=180),
                    "snippet": self._normalize_text(item.get("snippet"), limit=320),
                }
            )
        return deduped[: self.settings.live_research_max_results_per_query]

    def _openai_web_search_sync(self, query: str) -> list[dict[str, str]]:
        if not self.openai_search_client:
            return []
        response = self.openai_search_client.responses.create(
            model=self.settings.live_research_search_model or self.settings.llm_model,
            input=query,
            tools=[
                {
                    "type": "web_search",
                    "search_context_size": self.settings.live_research_search_context_size,
                }
            ],
        )
        results: list[dict[str, str]] = []
        payload: Any = response.model_dump() if hasattr(response, "model_dump") else response
        self._collect_web_search_sources(payload, results)
        return self._normalize_search_results(results)

    async def _openai_web_search(self, query: str) -> list[dict[str, str]]:
        try:
            return await asyncio.to_thread(self._openai_web_search_sync, query)
        except Exception:
            return []

    async def _search_web(self, client: httpx.AsyncClient, query: str) -> list[dict[str, str]]:
        backend = str(self.settings.live_research_search_backend or "openai").strip().lower()
        if backend == "openai":
            return await self._openai_web_search(query)
        if backend == "brave":
            return await self._brave_search(client, query)
        results = await self._openai_web_search(query)
        if results:
            return results
        return await self._brave_search(client, query)

    @staticmethod
    def _html_to_text(html: str) -> str:
        parser = _HTMLTextExtractor()
        parser.feed(html)
        text = parser.text()
        if text:
            return text
        return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split()).strip()

    async def _fetch_url_text(self, client: httpx.AsyncClient, url: str) -> dict[str, str] | None:
        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
        except Exception:
            return None
        content_type = str(response.headers.get("content-type") or "").lower()
        title = self._normalize_text(url, limit=180)
        body = ""
        if "application/json" in content_type:
            try:
                payload = response.json()
                body = self._normalize_text(json.dumps(payload, ensure_ascii=False), limit=6000)
            except Exception:
                body = self._normalize_text(response.text, limit=6000)
        else:
            body = self._html_to_text(response.text)
            title_match = re.search(r"<title[^>]*>(.*?)</title>", response.text, flags=re.IGNORECASE | re.DOTALL)
            if title_match:
                title = self._normalize_text(unescape(title_match.group(1)), limit=180) or title
            body = self._normalize_text(body, limit=6000)
        if not body:
            return None
        return {"url": url, "title": title, "content": body}

    def gather_sync(
        self,
        prompt: str,
        studio_panel: dict[str, Any],
        compiled_context: dict[str, Any],
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.gather(
                    prompt,
                    studio_panel,
                    compiled_context,
                    force=force,
                )
            )
        result: dict[str, Any] = {}
        failure: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(
                    self.gather(
                        prompt,
                        studio_panel,
                        compiled_context,
                        force=force,
                    )
                )
            except BaseException as exc:  # pragma: no cover - propagated to caller
                failure["error"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if failure:
            raise failure["error"]
        return result.get("value", {})

    async def gather(
        self,
        prompt: str,
        studio_panel: dict[str, Any],
        compiled_context: dict[str, Any],
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        if not self.settings.live_research_enabled:
            if force:
                return {
                    "status": "unavailable",
                    "summary": (
                        "Live research is disabled in configuration, so current values and external facts "
                        "could not be verified for this generation."
                    ),
                    "verified_facts": [],
                    "sources": [],
                    "queries": [],
                    "facts_to_verify": ["exact values", "dates", "percentages", "chart labels", "sources"],
                }
            return {}
        plan = await self._plan_queries(prompt, studio_panel, compiled_context)
        prompt_urls = self._urls_from_context(prompt, compiled_context)
        if not force and not plan.get("needs_live_research") and not prompt_urls:
            return {
                "status": "not_required",
                "summary": "",
                "verified_facts": [],
                "sources": [],
                "queries": plan.get("queries", []),
                "facts_to_verify": plan.get("facts_to_verify", []),
            }
        if force or plan.get("needs_live_research") or prompt_urls:
            if not self._has_live_search_backend() and not prompt_urls:
                # "not_configured" means no search backend is set up at all — this is a
                # configuration choice, not a failure.  The research guard must not
                # hard-fail on "not_configured" because the system was never asked to
                # fetch live data; it simply lacks the capability by design.
                # "unavailable" is reserved for when a backend IS configured but the
                # actual search/fetch attempt failed at runtime.
                return {
                    "status": "not_configured",
                    "summary": (
                        "Live research was requested but no live web-search backend is configured. "
                        "Provide a source URL/document or enable OpenAI web search for externally verified facts."
                    ),
                    "verified_facts": [],
                    "sources": [],
                    "queries": plan.get("queries", []),
                    "facts_to_verify": plan.get("facts_to_verify", []),
                    "preferred_sources": plan.get("preferred_sources", []),
                }
        timeout = httpx.Timeout(self.settings.live_research_timeout_seconds)
        raw_sources: list[dict[str, str]] = []
        try:
            async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "ViolytResearch/1.0"}) as client:
                discovered_urls = list(prompt_urls)
                for query in plan.get("queries", []):
                    for result in await self._search_web(client, query):
                        url = result.get("url")
                        if url and url not in discovered_urls:
                            discovered_urls.append(url)
                for url in discovered_urls[: max(4, self.settings.live_research_max_results_per_query * self.settings.live_research_max_queries)]:
                    fetched = await self._fetch_url_text(client, url)
                    if fetched:
                        raw_sources.append(fetched)
        except Exception:
            raw_sources = []
        if not raw_sources:
            return {
                "status": "unavailable",
                "summary": (
                    "Live research was requested but no external search results or fetchable source URLs were available. "
                    "Use retrieved knowledge conservatively and require verification for current values."
                ),
                "sources": [],
                "queries": plan.get("queries", []),
                "facts_to_verify": plan.get("facts_to_verify", []),
            }
        synthesis_fallback = {
            "summary": self._normalize_text(
                " ".join(
                    f"{source.get('title')}: {source.get('content')[:320]}"
                    for source in raw_sources[:3]
                ),
                limit=1200,
            ),
            "verified_facts": [],
        }
        synthesis = synthesis_fallback
        if getattr(self.research_provider, "client", None):
            envelope = PromptEnvelope(
                system=(
                    "You are a factual live-research synthesizer for branded content generation. "
                    "Return JSON only with keys: summary, verified_facts. "
                    "summary should state the most important exact values, dates, graph labels, and source-backed caveats. "
                    "verified_facts must be a list of objects with keys: label, value, source_title, source_url. "
                    "Only include facts directly supported by the provided sources."
                ),
                user=(
                    f"Prompt: {prompt}\n"
                    f"Studio panel: {studio_panel}\n"
                    f"Facts to verify: {plan.get('facts_to_verify', [])}\n"
                    f"Fetched sources: {json.dumps(raw_sources[:5], ensure_ascii=False)}"
                ),
            )
            try:
                synthesis = await asyncio.to_thread(
                    self.research_provider.generate_structured_json,
                    envelope,
                    synthesis_fallback,
                )
            except Exception:
                synthesis = synthesis_fallback
        summary = self._normalize_text((synthesis or {}).get("summary"), limit=1400)
        verified_facts = self._normalize_verified_facts((synthesis or {}).get("verified_facts"))
        sources = [
            {
                "title": self._normalize_text(source.get("title"), limit=180),
                "url": self._normalize_text(source.get("url"), limit=400),
            }
            for source in raw_sources[:5]
        ]
        ranked_sources = self._rank_sources(
            sources=sources,
            verified_facts=verified_facts,
            preferred_sources=[str(item).strip() for item in plan.get("preferred_sources", []) if str(item).strip()],
        )
        inferences = self._build_inferences(summary=summary, verified_facts=verified_facts)
        uncertainties = self._build_uncertainties(
            summary=summary,
            facts_to_verify=[str(item).strip() for item in plan.get("facts_to_verify", []) if str(item).strip()],
            verified_facts=verified_facts,
            sources=ranked_sources,
        )
        return {
            "status": "completed",
            "summary": summary,
            "verified_facts": verified_facts[:8],
            "inferences": inferences,
            "uncertainties": uncertainties,
            "sources": sources,
            "ranked_sources": ranked_sources,
            "queries": plan.get("queries", []),
            "facts_to_verify": plan.get("facts_to_verify", []),
            "preferred_sources": plan.get("preferred_sources", []),
        }
