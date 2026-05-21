from __future__ import annotations

from datetime import datetime, timezone

from app.services.analytics import AnalyticsService


def test_summarize_token_usage_aggregates_totals_and_months() -> None:
    summary = AnalyticsService.summarize_token_usage(
        [
            (
                datetime(2026, 3, 4, tzinfo=timezone.utc),
                {"token_usage": {"input_tokens": 120, "output_tokens": 80, "total_tokens": 200}},
            ),
            (
                datetime(2026, 3, 18, tzinfo=timezone.utc),
                {"token_usage": {"input_tokens": 30, "output_tokens": 20, "total_tokens": 50}},
            ),
            (
                datetime(2026, 4, 2, tzinfo=timezone.utc),
                {"token_usage": {"input_tokens": 90, "output_tokens": 60, "total_tokens": 150}},
            ),
            (datetime(2026, 4, 10, tzinfo=timezone.utc), {}),
        ]
    )

    assert summary["input_tokens"] == 240
    assert summary["output_tokens"] == 160
    assert summary["total_tokens"] == 400
    assert summary["monthly_token_usage"] == [
        {
            "month": "2026-03",
            "input_tokens": 150,
            "output_tokens": 100,
            "total_tokens": 250,
        },
        {
            "month": "2026-04",
            "input_tokens": 90,
            "output_tokens": 60,
            "total_tokens": 150,
        },
    ]
