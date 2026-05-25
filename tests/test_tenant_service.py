from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.sql.dml import Delete

from app.core.exceptions import DuplicateResourceError
from app.schemas.tenant import (
    TenantCreateRequest,
    TenantLogoUploadRequest,
    TenantUpdateRequest,
    TenantUsageLimitUpdate,
    TenantUserCreateRequest,
)
from app.services.email import EmailDeliveryResult
from app.services.tenant import TenantService


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.refreshed: list[object] = []
        self.scalar = AsyncMock()
        self.execute = AsyncMock()

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, instance: object) -> None:
        self.refreshed.append(instance)


class DummyExecuteResult:
    def __init__(self, value) -> None:  # noqa: ANN001
        self.value = value

    def scalar_one_or_none(self):  # noqa: ANN201
        return self.value


class DummyScalarListResult:
    def __init__(self, values) -> None:  # noqa: ANN001
        self.values = values

    def scalars(self):  # noqa: ANN201
        return self

    def all(self):  # noqa: ANN201
        return self.values


class DummyStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.saved: list[tuple] = []

    def delete(self, storage_path: str) -> None:
        self.deleted.append(storage_path)

    def save_bytes(self, tenant_id, brand_space_id, category, filename, content):  # noqa: ANN001
        self.saved.append((tenant_id, brand_space_id, category, filename, content))
        return SimpleNamespace(storage_path=f"{tenant_id}/global/{category}/{filename}", absolute_path=f"/tmp/{filename}")


def build_tenant(**overrides):
    payload = {
        "id": uuid4(),
        "name": "Acme",
        "slug": "acme",
        "contact_email": "team@acme.com",
        "contact_number": "+91 9000000000",
        "address": "Bengaluru",
        "logo_asset_path": None,
        "is_active": True,
        "metadata_json": {},
        "created_at": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def build_admin(**overrides):
    return SimpleNamespace(
        id=uuid4(),
        full_name="Admin User",
        email="admin@acme.com",
        phone_number="+91 9000000001",
        **overrides,
    )


async def test_update_tenant_persists_metadata_and_active_flag():
    session = DummySession()
    service = TenantService(session)
    tenant = build_tenant()
    admin = build_admin()
    service.get_tenant = AsyncMock(return_value=tenant)
    service._get_primary_tenant_admin = AsyncMock(return_value=admin)
    service.update_usage_limits = AsyncMock()
    service.users.get_by_email = AsyncMock(return_value=None)

    payload = TenantUpdateRequest(
        metadata_json={"usage_window": {"start_month": "January", "end_month": "December"}},
        is_active=False,
        admin_full_name="Updated Admin",
        admin_email="updated@acme.com",
        admin_phone_number="+91 9999999999",
    )

    updated = await service.update_tenant(tenant.id, payload)

    assert updated is tenant
    assert tenant.is_active is False
    assert tenant.metadata_json == {"usage_window": {"start_month": "January", "end_month": "December"}}
    assert admin.full_name == "Updated Admin"
    assert admin.email == "updated@acme.com"
    assert admin.phone_number == "+91 9999999999"
    assert session.commits == 1
    assert session.refreshed == [tenant]


async def test_delete_tenant_removes_logo_and_commits():
    session = DummySession()
    service = TenantService(session)
    tenant = build_tenant(logo_asset_path="tenant-1/global/tenant-assets/logo.png")
    storage = DummyStorage()
    service.get_tenant = AsyncMock(return_value=tenant)
    service.storage = storage
    session.execute.return_value = DummyScalarListResult([])

    await service.delete_tenant(tenant.id)

    assert storage.deleted == ["tenant-1/global/tenant-assets/logo.png"]
    delete_statements = [
        call.args[0]
        for call in session.execute.await_args_list
        if isinstance(call.args[0], Delete)
    ]
    assert any(statement.table.name == "users" for statement in delete_statements)
    assert delete_statements[-1].table.name == "tenants"
    assert session.commits == 1


async def test_upload_logo_replaces_existing_storage_path():
    session = DummySession()
    service = TenantService(session)
    tenant = build_tenant(logo_asset_path="tenant-1/global/tenant-assets/old-logo.png")
    storage = DummyStorage()
    service.get_tenant = AsyncMock(return_value=tenant)
    service.storage = storage

    payload = TenantLogoUploadRequest(
        filename="tenant-logo.png",
        mime_type="image/png",
        content_base64="data:image/png;base64,aGVsbG8=",
    )

    updated = await service.upload_logo(tenant.id, payload)

    assert updated is tenant
    assert storage.deleted == ["tenant-1/global/tenant-assets/old-logo.png"]
    assert storage.saved[0][2] == "tenant-assets"
    assert storage.saved[0][3] == "tenant-logo.png"
    assert storage.saved[0][4] == b"hello"
    assert tenant.logo_asset_path.endswith("/tenant-logo.png")
    assert session.commits == 1
    assert session.refreshed == [tenant]


async def test_get_tenant_summary_includes_primary_admin_and_last_activity():
    session = DummySession()
    service = TenantService(session)
    tenant = build_tenant(metadata_json={"usage_window": {"start_month": "2026-01", "end_month": "2026-12"}})
    admin = build_admin()
    recent_login = datetime.now(timezone.utc)
    service.get_tenant = AsyncMock(return_value=tenant)
    service.get_usage_summary = AsyncMock(
        return_value={
            "limits": {"max_users": 10, "max_brand_spaces": 5, "max_content_generations": 20, "max_image_generations": 10, "max_ocr_pages": 50},
            "consumption": {"users": 4, "brand_spaces": 2, "content_generations": 6, "image_generations": 3, "ocr_pages": 8},
        }
    )
    service.analytics.tenant_summary = AsyncMock(
        return_value={
            "total_users": 4,
            "number_of_brand_spaces": 2,
            "token_usage": {
                "input_tokens": 120,
                "output_tokens": 90,
                "total_tokens": 210,
                "monthly_token_usage": [
                    {"month": "2026-03", "input_tokens": 120, "output_tokens": 90, "total_tokens": 210}
                ],
            },
        }
    )
    service._get_primary_tenant_admin = AsyncMock(return_value=admin)
    session.execute.return_value = DummyExecuteResult(recent_login)

    summary = await service.get_tenant_summary(tenant.id)

    assert summary["tenant_admin_name"] == "Admin User"
    assert summary["tenant_admin_email"] == "admin@acme.com"
    assert summary["tenant_admin_phone_number"] == "+91 9000000001"
    assert summary["last_active_at"] == recent_login
    assert summary["brand_space_count"] == 2
    assert summary["usage_consumption"]["content_generations"] == 6
    assert summary["token_usage"]["total_tokens"] == 210
    assert summary["monthly_token_usage"][0]["month"] == "2026-03"


async def test_list_tenant_brand_space_summaries_collects_usage_metrics():
    session = DummySession()
    service = TenantService(session)
    tenant_id = uuid4()
    brand_id = uuid4()
    created_at = datetime.now(timezone.utc)
    recent_login = datetime.now(timezone.utc)
    service.brand_spaces.list_by_tenant = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=brand_id,
                tenant_id=tenant_id,
                name="Jiraaf",
                slug="jiraaf",
                lifecycle_state="active",
                created_at=created_at,
            )
        ]
    )
    session.scalar.side_effect = [12, 7, 18, recent_login]

    summaries = await service.list_tenant_brand_space_summaries(tenant_id)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["name"] == "Jiraaf"
    assert summary["content_generations"] == 12
    assert summary["visual_generations"] == 7
    assert summary["ocr_pages"] == 18
    assert summary["last_login_at"] == recent_login
    assert summary["last_active_at"] == recent_login


async def test_create_tenant_rejects_duplicate_slug():
    session = DummySession()
    service = TenantService(session)
    service.tenants.get_by_slug = AsyncMock(return_value=build_tenant(slug="jiraaf"))
    service.users.get_by_email = AsyncMock(return_value=None)

    payload = TenantCreateRequest(
        name="Jiraaf",
        slug="jiraaf",
        contact_email="team@jiraaf.com",
        contact_number="+91 9876543210",
        address="Bengaluru",
        admin_full_name="Jiraaf Admin",
        admin_email="admin@jiraaf.com",
        admin_phone_number="+91 9000000002",
        usage_limits=TenantUsageLimitUpdate(
            max_users=10,
            max_brand_spaces=5,
            max_content_generations=20,
            max_image_generations=10,
            max_ocr_pages=50,
        ),
        metadata_json={},
    )

    with pytest.raises(DuplicateResourceError, match="Tenant slug 'jiraaf' already exists"):
        await service.create_tenant(payload)

    assert session.commits == 0


async def test_create_tenant_user_rejects_duplicate_email():
    session = DummySession()
    service = TenantService(session)
    tenant_id = uuid4()
    service.users.get_by_email = AsyncMock(return_value=SimpleNamespace(id=uuid4(), email="member@jiraaf.com"))

    payload = TenantUserCreateRequest(
        full_name="Existing Member",
        email="member@jiraaf.com",
        phone_number="+91 9000000003",
        role_code="brand_user",
        brand_space_ids=[],
    )

    with pytest.raises(DuplicateResourceError, match="member@jiraaf.com"):
        await service.create_tenant_user(tenant_id, payload)

    assert session.commits == 0


async def test_create_tenant_user_returns_email_delivery_status():
    session = DummySession()
    service = TenantService(session)
    tenant_id = uuid4()
    role_id = uuid4()

    async def add_user(user):  # noqa: ANN001
        if user.id is None:
            user.id = uuid4()

    service.users.get_by_email = AsyncMock(return_value=None)
    service.users.add = AsyncMock(side_effect=add_user)
    service.roles.get_by_code = AsyncMock(return_value=SimpleNamespace(id=role_id))
    service.user_roles.add = AsyncMock()
    service.tokens.add = AsyncMock()
    service.brand_members.add = AsyncMock()
    service.usage.enforce = AsyncMock()
    service.usage.increment = AsyncMock()
    service.email.send_activation_email = Mock(
        return_value=EmailDeliveryResult(
            attempted=True,
            delivered=False,
            recipient_email="member@jiraaf.com",
            reason="SMTP authentication failed. Check the sender email password or app password.",
        )
    )

    payload = TenantUserCreateRequest(
        full_name="New Member",
        email="member@jiraaf.com",
        phone_number="+91 9000000004",
        role_code="brand_user",
        brand_space_ids=[],
    )

    user, delivery = await service.create_tenant_user(tenant_id, payload)

    assert user.email == "member@jiraaf.com"
    assert delivery.delivered is False
    assert delivery.recipient_email == "member@jiraaf.com"
    assert "SMTP authentication failed" in (delivery.reason or "")
    assert session.commits == 1
    assert session.refreshed == [user]


async def test_create_tenant_returns_email_delivery_status():
    session = DummySession()
    service = TenantService(session)
    tenant_id = uuid4()
    role_id = uuid4()

    async def add_tenant(tenant):  # noqa: ANN001
        tenant.id = tenant_id

    async def add_user(user):  # noqa: ANN001
        if user.id is None:
            user.id = uuid4()

    service.tenants.get_by_slug = AsyncMock(return_value=None)
    service.users.get_by_email = AsyncMock(return_value=None)
    service.tenants.add = AsyncMock(side_effect=add_tenant)
    service.users.add = AsyncMock(side_effect=add_user)
    service.roles.get_by_code = AsyncMock(return_value=SimpleNamespace(id=role_id))
    service.user_roles.add = AsyncMock()
    service.tokens.add = AsyncMock()
    service.usage_limits.add = AsyncMock()
    service.usage.increment = AsyncMock()
    service.email.send_activation_email = Mock(
        return_value=EmailDeliveryResult(
            attempted=True,
            delivered=False,
            recipient_email="admin@jiraaf.com",
            reason="SMTP authentication failed. Check the sender email password or app password.",
        )
    )

    payload = TenantCreateRequest(
        name="Jiraaf",
        slug="jiraaf-new",
        contact_email="team@jiraaf.com",
        contact_number="+91 9876543210",
        address="Bengaluru",
        admin_full_name="Jiraaf Admin",
        admin_email="admin@jiraaf.com",
        admin_phone_number="+91 9000000002",
        usage_limits=TenantUsageLimitUpdate(
            max_users=10,
            max_brand_spaces=5,
            max_content_generations=20,
            max_image_generations=10,
            max_ocr_pages=50,
        ),
        metadata_json={},
    )

    tenant, delivery = await service.create_tenant(payload)

    assert tenant.id == tenant_id
    assert delivery.delivered is False
    assert delivery.recipient_email == "admin@jiraaf.com"
    assert "SMTP authentication failed" in (delivery.reason or "")
    assert session.commits == 1
    assert session.refreshed == [tenant]
