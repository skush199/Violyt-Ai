from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx
import psycopg


@dataclass
class SmokeResult:
    name: str
    ok: bool
    detail: str
    status_code: int | None = None


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def get_config() -> dict[str, Any]:
    return {
        "base_url": _env("SMOKE_BASE_URL", "http://127.0.0.1:8001"),
        "db_url": _env("SMOKE_DB_URL", "postgresql://violyt:violyt@localhost:5432/violyt"),
        "email": _env("SMOKE_EMAIL", "admin@sampletenant.com"),
        "password": _env("SMOKE_PASSWORD", "DemoPass123!"),
        "activation_token": _env("SMOKE_ACTIVATION_TOKEN", "sample-activation-token-admin"),
        "brand_space_id": _env("SMOKE_BRAND_SPACE_ID", "66666666-6666-6666-6666-666666666666"),
        "persona_id": _env("SMOKE_PERSONA_ID", "99999999-9999-9999-9999-999999999999"),
        "objective_id": _env("SMOKE_OBJECTIVE_ID", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "start_server": _env("SMOKE_START_SERVER", "1") == "1",
        "startup_timeout": int(_env("SMOKE_STARTUP_TIMEOUT_SECONDS", "30")),
    }


def probe_database(db_url: str) -> None:
    conn = psycopg.connect(db_url, connect_timeout=5)
    try:
        with conn.cursor() as cursor:
            cursor.execute("select 1")
            cursor.fetchone()
    finally:
        conn.close()


def start_server(base_url: str) -> subprocess.Popen[str]:
    port = base_url.rsplit(":", 1)[-1]
    env = os.environ.copy()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", port],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(os.getcwd()),
        env=env,
    )
    return process


def wait_for_server(base_url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "server did not respond"
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/docs", timeout=2.0)
            if response.status_code == 200:
                return
            last_error = f"unexpected status: {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"API did not become ready: {last_error}")


def run_smoke(config: dict[str, Any]) -> list[SmokeResult]:
    results: list[SmokeResult] = []
    base_url = config["base_url"]
    brand_header = {"X-Brand-Space-Id": config["brand_space_id"]}
    studio_panel = {
        "format": "static",
        "platform_preset": "linkedin",
        "file_type": "png",
        "size": {"width": 1200, "height": 627},
    }

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        activation_response = client.post(
            "/api/v1/auth/activate",
            json={"token": config["activation_token"], "password": config["password"]},
        )
        if activation_response.status_code in {200, 400, 401, 409}:
            results.append(
                SmokeResult(
                    name="activate_sample_user",
                    ok=activation_response.status_code in {200, 400, 409},
                    detail=activation_response.text,
                    status_code=activation_response.status_code,
                )
            )
        else:
            results.append(
                SmokeResult(
                    name="activate_sample_user",
                    ok=False,
                    detail=activation_response.text,
                    status_code=activation_response.status_code,
                )
            )

        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": config["email"], "password": config["password"]},
        )
        if login_response.status_code != 200:
            results.append(
                SmokeResult(
                    name="login",
                    ok=False,
                    detail=login_response.text,
                    status_code=login_response.status_code,
                )
            )
            return results
        token = login_response.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        brand_auth_headers = {**auth_headers, **brand_header}
        results.append(SmokeResult(name="login", ok=True, detail="login succeeded", status_code=200))

        me_response = client.get("/api/v1/auth/me", headers=auth_headers)
        results.append(
            SmokeResult(
                name="auth_me",
                ok=me_response.status_code == 200,
                detail=me_response.text,
                status_code=me_response.status_code,
            )
        )

        overview_response = client.get(
            f"/api/v1/brands/{config['brand_space_id']}/overview",
            headers=auth_headers,
        )
        results.append(
            SmokeResult(
                name="brand_overview",
                ok=overview_response.status_code == 200,
                detail=overview_response.text,
                status_code=overview_response.status_code,
            )
        )
        if overview_response.status_code != 200:
            return results

        template_response = client.post(
            "/api/v1/templates/recommend",
            headers=brand_auth_headers,
            json={
                "prompt": "Create a LinkedIn launch post for a premium skincare serum",
                "studio_panel": studio_panel,
                "limit": 3,
            },
        )
        results.append(
            SmokeResult(
                name="template_recommend",
                ok=template_response.status_code == 200,
                detail=template_response.text,
                status_code=template_response.status_code,
            )
        )

        generate_response = client.post(
            "/api/v1/content/generate",
            headers=brand_auth_headers,
            json={
                "prompt": "Create a LinkedIn launch post for our premium skincare serum. Keep it calm, premium, trustworthy, and science-backed.",
                "session_id": None,
                "persona_id": config["persona_id"],
                "objective_id": config["objective_id"],
                "template_id": None,
                "studio_panel": studio_panel,
                "generate_image": True,
                "reference_asset_ids": [],
            },
        )
        results.append(
            SmokeResult(
                name="content_generate",
                ok=generate_response.status_code == 200,
                detail=generate_response.text,
                status_code=generate_response.status_code,
            )
        )
        if generate_response.status_code != 200:
            return results
        content_version_id = generate_response.json()["id"]

        preview_response = client.post(
            "/api/v1/render/preview",
            headers=brand_auth_headers,
            json={
                "content_version_id": content_version_id,
                "blueprint_payload": None,
                "studio_panel": studio_panel,
                "template_id": None,
            },
        )
        results.append(
            SmokeResult(
                name="render_preview",
                ok=preview_response.status_code == 200,
                detail=preview_response.text,
                status_code=preview_response.status_code,
            )
        )

        export_response = client.post(
            "/api/v1/content/export",
            headers=brand_auth_headers,
            json={
                "content_version_id": content_version_id,
                "export_format": "png",
                "studio_panel": studio_panel,
                "blueprint_payload": None,
                "template_id": None,
            },
        )
        results.append(
            SmokeResult(
                name="content_export",
                ok=export_response.status_code == 200,
                detail=export_response.text,
                status_code=export_response.status_code,
            )
        )

        share_response = client.post(
            "/api/v1/review/share-link",
            headers=brand_auth_headers,
            json={
                "content_version_id": content_version_id,
                "title": "Smoke Review",
                "allow_external_comments": True,
            },
        )
        results.append(
            SmokeResult(
                name="review_share_link",
                ok=share_response.status_code == 200,
                detail=share_response.text,
                status_code=share_response.status_code,
            )
        )
        review_token = share_response.json()["token"] if share_response.status_code == 200 else None

        if review_token:
            review_get = client.get(f"/api/v1/review/{review_token}")
            results.append(
                SmokeResult(
                    name="review_get",
                    ok=review_get.status_code == 200,
                    detail=review_get.text,
                    status_code=review_get.status_code,
                )
            )
            review_comment = client.post(
                f"/api/v1/review/{review_token}/comment",
                json={"body": "Smoke test comment", "external_author_name": "Smoke Tester"},
            )
            results.append(
                SmokeResult(
                    name="review_comment",
                    ok=review_comment.status_code == 200,
                    detail=review_comment.text,
                    status_code=review_comment.status_code,
                )
            )

        chat_session = client.post(
            "/api/v1/chat/sessions",
            headers=brand_auth_headers,
            json={"title": "Smoke Session", "studio_panel": studio_panel},
        )
        results.append(
            SmokeResult(
                name="chat_create_session",
                ok=chat_session.status_code == 200,
                detail=chat_session.text,
                status_code=chat_session.status_code,
            )
        )
        if chat_session.status_code == 200:
            session_id = chat_session.json()["id"]
            chat_send = client.post(
                f"/api/v1/chat/sessions/{session_id}/messages",
                headers=brand_auth_headers,
                json={
                    "message": "Create a shorter follow-up version of the same launch message.",
                    "studio_panel": studio_panel,
                    "persona_id": config["persona_id"],
                    "objective_id": config["objective_id"],
                    "template_id": None,
                    "reference_asset_ids": [],
                    "generate_image": False,
                },
            )
            results.append(
                SmokeResult(
                    name="chat_send_message",
                    ok=chat_send.status_code == 200,
                    detail=chat_send.text,
                    status_code=chat_send.status_code,
                )
            )

        analytics_response = client.get(
            f"/api/v1/analytics/brand/{config['brand_space_id']}",
            headers=auth_headers,
        )
        results.append(
            SmokeResult(
                name="brand_analytics",
                ok=analytics_response.status_code == 200,
                detail=analytics_response.text,
                status_code=analytics_response.status_code,
            )
        )

        jobs_response = client.get("/api/v1/jobs/list", headers=auth_headers)
        results.append(
            SmokeResult(
                name="jobs_list",
                ok=jobs_response.status_code == 200,
                detail=jobs_response.text,
                status_code=jobs_response.status_code,
            )
        )

    return results


def main() -> int:
    config = get_config()
    report: dict[str, Any] = {"config": {k: v for k, v in config.items() if "password" not in k and "token" not in k}, "results": []}
    process: subprocess.Popen[str] | None = None
    try:
        probe_database(config["db_url"])
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"database_unreachable:{type(exc).__name__}:{exc}"
        print(json.dumps(report, indent=2))
        return 2

    try:
        if config["start_server"]:
            process = start_server(config["base_url"])
            wait_for_server(config["base_url"], config["startup_timeout"])
        results = run_smoke(config)
        report["results"] = [asdict(item) for item in results]
        report["passed"] = sum(1 for item in results if item.ok)
        report["failed"] = sum(1 for item in results if not item.ok)
        print(json.dumps(report, indent=2))
        return 0 if report["failed"] == 0 else 1
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())

