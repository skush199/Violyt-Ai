from types import SimpleNamespace

import pytest

from app.services.live_research import LiveResearchService


@pytest.mark.asyncio
async def test_live_research_force_returns_unavailable_when_no_sources_exist() -> None:
    service = LiveResearchService()
    service.settings.live_research_enabled = True
    service.settings.brave_search_api_key = None
    service.openai_search_client = None

    result = await service.gather(
        "Create a static post about savings habits.",
        {"platform_preset": "instagram", "format": "static"},
        {"knowledge_brief": []},
        force=True,
    )

    assert result["status"] == "unavailable"
    assert result["summary"]
    assert result["queries"]


@pytest.mark.asyncio
async def test_live_research_uses_openai_web_search_when_configured() -> None:
    service = LiveResearchService()
    service.settings.live_research_enabled = True
    service.settings.live_research_search_backend = "openai"
    service.settings.brave_search_api_key = None
    service.openai_search_client = object()
    service.research_provider = SimpleNamespace(
        client=True,
        generate_structured_json=lambda envelope, fallback: {
            "summary": "The FTA was signed on 27 April 2026.",
            "verified_facts": [
                {
                    "label": "FTA signing date",
                    "value": "27 April 2026",
                    "source_title": "Trade ministry note",
                    "source_url": "https://example.com/fta",
                }
            ],
        },
    )

    async def _fake_plan_queries(prompt, studio_panel, compiled_context):  # noqa: ARG001
        return {
            "needs_live_research": True,
            "queries": ["India New Zealand FTA 27 April 2026"],
            "facts_to_verify": ["signing date"],
            "preferred_sources": [],
        }

    async def _fake_openai_web_search(query):  # noqa: ARG001
        return [{"url": "https://example.com/fta", "title": "Trade ministry note", "snippet": "FTA signed"}]

    async def _fake_fetch_url_text(client, url):  # noqa: ARG001
        return {
            "url": url,
            "title": "Trade ministry note",
            "content": "India and New Zealand signed the FTA on 27 April 2026.",
        }

    service._plan_queries = _fake_plan_queries
    service._openai_web_search = _fake_openai_web_search
    service._fetch_url_text = _fake_fetch_url_text

    result = await service.gather(
        "Write a LinkedIn carousel about the India-New Zealand FTA signed on 27 April 2026.",
        {"platform_preset": "linkedin", "format": "carousel"},
        {"knowledge_brief": []},
        force=True,
    )

    assert result["status"] == "completed"
    assert result["verified_facts"][0]["value"] == "27 April 2026"
    assert result["sources"][0]["url"] == "https://example.com/fta"


@pytest.mark.asyncio
async def test_live_research_gather_synthesizes_verified_facts_from_mocked_sources() -> None:
    service = LiveResearchService()
    service.settings.live_research_enabled = True
    service.settings.live_research_search_backend = "brave"
    service.settings.brave_search_api_key = "test-key"
    service.research_provider = SimpleNamespace(
        client=True,
        generate_structured_json=lambda envelope, fallback: {
            "summary": "FDI inflow reached USD 100 billion in 2025.",
            "verified_facts": [
                {
                    "label": "FDI inflow",
                    "value": "USD 100 billion",
                    "source_title": "Economic report",
                    "source_url": "https://example.com/fdi",
                }
            ],
        },
    )

    async def _fake_plan_queries(prompt, studio_panel, compiled_context):  # noqa: ARG001
        return {
            "needs_live_research": True,
            "queries": ["india fdi inflow 2025"],
            "facts_to_verify": ["exact values"],
            "preferred_sources": [],
        }

    async def _fake_brave_search(client, query):  # noqa: ARG001
        return [{"url": "https://example.com/fdi", "title": "Economic report", "snippet": "FDI inflow data"}]

    async def _fake_fetch_url_text(client, url):  # noqa: ARG001
        return {
            "url": url,
            "title": "Economic report",
            "content": "FDI inflow reached USD 100 billion in 2025.",
        }

    service._plan_queries = _fake_plan_queries
    service._brave_search = _fake_brave_search
    service._fetch_url_text = _fake_fetch_url_text

    result = await service.gather(
        "Create a data-led post about FDI inflows into India.",
        {"platform_preset": "linkedin", "format": "static"},
        {"knowledge_brief": []},
        force=True,
    )

    assert result["status"] == "completed"
    assert result["verified_facts"][0]["value"] == "USD 100 billion"
    assert result["sources"][0]["url"] == "https://example.com/fdi"
