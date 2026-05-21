# API Contracts

## Overview

This document describes the current contract surface for:

- frontend to backend
- backend to AI orchestration layer
- AI blueprint to backend renderer
- backend renderer to frontend-facing responses

Base API prefix:

- `/api/v1`

Primary contract sources in code:

- `app/api/routes/*.py`
- `app/schemas/*.py`
- `app/ai/contracts.py`
- `contracts/frontend-api.ts`

## Authentication and Authorization

Authentication uses bearer tokens returned by `/api/v1/auth/login` and `/api/v1/auth/activate`.

Protected routes expect:

```http
Authorization: Bearer <access_token>
```

Role rules implemented in backend:

- `SUPER_ADMIN`
  Can manage tenants and tenant users, but cannot access Brand Space content flows.
- `TENANT_ADMIN`
  Can manage tenant users, usage limits, and tenant-scoped brand resources.
- `TENANT_USER`
  Can work within tenant scope.
- `BRAND_USER`
  Is restricted to assigned Brand Spaces.
- external reviewers
  Use tokenized review links rather than tenant auth.

Some folder and template endpoints also use a Brand Space scope header:

```http
X-Brand-Space-Id: <brand_space_uuid>
```

## Common Payloads

### `StudioPanelSelection`

Used by content generation, chat, template apply, and rendering.

```json
{
  "format": "Static | Carousel | PDF | Infographic",
  "platform_preset": "Instagram | LinkedIn | X | YouTube Thumbnail",
  "file_type": "DOC | PDF | PNG | JPG",
  "size": {
    "width": 1080,
    "height": 1080
  }
}
```

### `AssetReference`

Returned for generated or rendered assets.

```json
{
  "asset_id": "uuid",
  "mime_type": "image/png",
  "storage_path": "tenant/brand/generated/file.png",
  "width": 1080,
  "height": 1080,
  "asset_role": "render_preview"
}
```

## Frontend to Backend Contracts

### Auth

#### `POST /api/v1/auth/login`

- Request: `LoginRequest`
- Response: `TokenPairResponse | TwoFactorChallengeResponse`

```json
{
  "email": "user@example.com",
  "password": "strong-password"
}
```

When 2FA is enabled for the user, the response is:

```json
{
  "requires_two_factor": true,
  "two_factor_ticket": "signed-challenge-ticket",
  "delivery": "authenticator",
  "email": "user@example.com"
}
```

#### `POST /api/v1/auth/activate`

- Request: `ActivationRequest`
- Response: `TokenPairResponse`

```json
{
  "token": "activation-token",
  "password": "new-password"
}
```

#### `POST /api/v1/auth/forgot-password`

- Request: `ForgotPasswordRequest`
- Response: `PasswordResetResponse`

#### `POST /api/v1/auth/reset-password`

- Request: `ResetPasswordRequest`
- Response: `TokenPairResponse`

#### `GET /api/v1/auth/me`

- Auth required
- Response: `CurrentUserResponse`

#### `GET /api/v1/auth/profile`

- Auth required
- Response: `CurrentUserResponse`

#### `PUT /api/v1/auth/profile`

- Auth required
- Request: `ProfileUpdateRequest`
- Response: `CurrentUserResponse`

Supports profile-field persistence for:

- `full_name`
- `email`
- `phone_number`
- `notifications_enabled`

#### `POST /api/v1/auth/change-password`

- Auth required
- Request: `ChangePasswordRequest`
- Response: `PasswordResetResponse`

#### `DELETE /api/v1/auth/profile`

- Auth required
- Response: `MessageResponse`

Soft-deactivates the authenticated account and is used by the profile deletion flow in the frontend.

#### `GET /api/v1/auth/2fa/status`

- Auth required
- Response: `TwoFactorSetupResponse`

#### `POST /api/v1/auth/2fa/setup`

- Auth required
- Response: `TwoFactorSetupResponse`

Returns:

- `secret`
- `otpauth_url`
- `qr_code_url`
- `pending_setup`

#### `POST /api/v1/auth/2fa/enable`

- Auth required
- Request: `{ "code": "123456" }`
- Response: `TwoFactorSetupResponse`

#### `POST /api/v1/auth/2fa/disable`

- Auth required
- Request: `{ "code": "123456" }`
- Response: `TwoFactorSetupResponse`

#### `POST /api/v1/auth/2fa/verify`

- Public by challenge ticket
- Request: `{ "ticket": "signed-challenge-ticket", "code": "123456" }`
- Response: `TokenPairResponse`

### Tenants

#### `POST /api/v1/tenants`

- Role: `SUPER_ADMIN`
- Request: `TenantCreateRequest`
- Response: `TenantResponse`

Important nested field:

```json
{
  "usage_limits": {
    "max_users": 10,
    "max_brand_spaces": 5,
    "max_content_generations": 1000,
    "max_image_generations": 200,
    "max_ocr_pages": 500
  },
  "metadata_json": {
    "usage_window": {
      "start_month": "January",
      "end_month": "December"
    },
    "messaging": {
      "max_messages": 5000
    }
  }
}
```

`metadata_json` is now used by the UI to persist design-driven tenant settings that do not belong in the hard usage-limit columns, such as capacity-window labels and message allowances.

#### `GET /api/v1/tenants`

- Role: `SUPER_ADMIN`
- Response: `TenantSummaryResponse[]`

Provides super-admin visibility into tenant counts, usage limits, and current usage consumption.

#### `GET /api/v1/tenants/{tenant_id}`

- Role: `SUPER_ADMIN` or `TENANT_ADMIN`
- Response: `TenantSummaryResponse`

The tenant summary now includes:

- `logo_asset_path`
- `metadata_json`
- `created_at`
- `token_usage`
- `monthly_token_usage`

#### `POST /api/v1/tenants/{tenant_id}/logo`

- Role: `SUPER_ADMIN` or `TENANT_ADMIN`
- Request: `TenantLogoUploadRequest`
- Response: `TenantSummaryResponse`

```json
{
  "filename": "tenant-logo.png",
  "mime_type": "image/png",
  "content_base64": "data:image/png;base64,..."
}
```

This endpoint persists the tenant logo into local object storage and updates `logo_asset_path` so the platform-owner tenant-management screens can render real branding.

#### `GET /api/v1/tenants/{tenant_id}/users`

- Role: `SUPER_ADMIN` or `TENANT_ADMIN`
- Response: `TenantUserResponse[]`

#### `POST /api/v1/tenants/{tenant_id}/users`

- Role: `SUPER_ADMIN` or `TENANT_ADMIN`
- Request: `TenantUserCreateRequest`
- Response: `TenantUserResponse`

#### `POST /api/v1/tenants/{tenant_id}/users/{user_id}/deactivate`

- Role: `SUPER_ADMIN` or `TENANT_ADMIN`
- Response: `MessageResponse`

#### `PUT /api/v1/tenants/{tenant_id}/usage-limits`

- Role: `SUPER_ADMIN` or `TENANT_ADMIN`
- Request: `TenantUsageLimitUpdate`
- Response: `MessageResponse`

#### `GET /api/v1/tenants/{tenant_id}/usage-summary`

- Role: `SUPER_ADMIN` or `TENANT_ADMIN`
- Response: `TenantUsageSummary`

### Brand Spaces

#### `POST /api/v1/brands`

- Auth required
- Request: `BrandCreateRequest`
- Response: `BrandResponse`

This initializes the brand using the first-step payloads:

- `identity`
- `foundations`
- `voice_tone`

#### `GET /api/v1/brands`

- Auth required
- Response: `BrandResponse[]`

#### `GET /api/v1/brands/{brand_id}`

- Auth required
- Response: `BrandResponse`

#### `PUT /api/v1/brands/{brand_id}`

- Auth required
- Request: `BrandUpdateRequest`
- Response: `BrandResponse`

#### `PUT /api/v1/brands/{brand_id}/sections/{section_code}`

- Auth required
- Request: `BrandSectionUpsertRequest`
- Response: `BrandResponse`

Used for the sectioned Brand Space setup flow. The section payload is stored versioned and only future generations use updated brand configuration.

#### `POST /api/v1/brands/{brand_id}/finalize`

- Auth required
- Request: `BrandFinalizeRequest`
- Response: `BrandResponse`

#### `POST /api/v1/brands/{brand_id}/archive`

- Auth required
- Response: `BrandResponse`

#### `POST /api/v1/brands/{brand_id}/restore`

- Auth required
- Response: `BrandResponse`

#### `DELETE /api/v1/brands/{brand_id}`

- Auth required
- Response: `MessageResponse`

#### `GET /api/v1/brands/{brand_id}/overview`

- Auth required
- Response: `BrandOverviewResponse`

Includes:

- brand snapshot
- current configuration sections
- personas
- guardrails
- objectives

### Knowledge

#### `POST /api/v1/knowledge/upload`

- Auth required
- Request: `KnowledgeUploadRequest`
- Response: `KnowledgeAssetResponse`

```json
{
  "name": "Brand Strategy",
  "filename": "strategy.pdf",
  "mime_type": "application/pdf",
  "content_base64": "<base64>",
  "channel": "brand",
  "metadata": {}
}
```

#### `GET /api/v1/knowledge/list`

- Auth required
- Query/brand scope driven by current user
- Response: `KnowledgeAssetResponse[]`

#### `GET /api/v1/knowledge/{knowledge_id}/status`

- Auth required
- Response: `KnowledgeAssetResponse`

#### `DELETE /api/v1/knowledge/{knowledge_id}`

- Auth required
- Response: `KnowledgeAssetResponse`

Delete also removes indexed embeddings for that asset source.

#### `POST /api/v1/knowledge/{knowledge_id}/reprocess`

- Auth required
- Response: `KnowledgeAssetResponse`

### Content

#### `POST /api/v1/content/generate`

- Auth required
- Brand Space must be `Active`
- Request: `ContentGenerateRequest`
- Response: `ContentVersionResponse`

Important fields:

- `prompt`
- `session_id`
- `persona_id`
- `objective_id`
- `template_id`
- `studio_panel`
- `generate_image`
- `reference_asset_ids`

Response contains:

- generated structured text
- blueprint JSON
- explainability metadata
- tone score
- generated assets
- optional auto-selected template guidance when no template is explicitly chosen

#### `POST /api/v1/content/rewrite`

- Auth required
- Request: `ContentRewriteRequest`
- Response: `ContentVersionResponse`

Creates a new version and does not overwrite history.

#### `POST /api/v1/content/tone-check`

- Auth required
- Request: `ToneCheckRequest`
- Response: `ToneEvaluationResponse`

#### `GET /api/v1/content/history`

- Auth required
- Response: `ContentVersionResponse[]`

#### `GET /api/v1/content/{content_id}`

- Auth required
- Response: `ContentVersionResponse`

#### `POST /api/v1/content/export`

- Auth required
- Request: `ContentExportRequest`
- Response: `RenderResponse`

Supports optional export-time overrides for:

- `studio_panel`
- `blueprint_payload`
- `template_id`

#### `POST /api/v1/content/copy`

- Auth required
- Request: `ContentCopyRequest`
- Response: simplified copy payload

### Chat

The chat module is session-based and uses the same content generation backend under the hood.

#### `POST /api/v1/chat/sessions`

- Auth required
- Request: `ChatSessionCreateRequest`
- Response: `ChatSessionResponse`

#### `GET /api/v1/chat/sessions`

- Auth required
- Response: `ChatSessionResponse[]`

#### `GET /api/v1/chat/sessions/{session_id}/messages`

- Auth required
- Response: `ChatMessageResponse[]`

#### `POST /api/v1/chat/sessions/{session_id}/messages`

- Auth required
- Request: `ChatMessageCreateRequest`
- Response: `ChatSendResponse`

Chat history is persisted through:

- `sessions`
- `chat_messages`
- linked `content_history` versions

### Folders

Folder APIs use `X-Brand-Space-Id`.

#### `POST /api/v1/folders`

- Auth required
- Header: `X-Brand-Space-Id`
- Request: `FolderCreateRequest`
- Response: `{ id, name, description }`

#### `GET /api/v1/folders`

- Auth required
- Header: `X-Brand-Space-Id`
- Response: `list[dict]`

#### `PUT /api/v1/folders/{folder_id}`

- Auth required
- Request: `FolderRenameRequest`
- Response: `{ id, name }`

#### `DELETE /api/v1/folders/{folder_id}`

- Auth required
- Response: `MessageResponse`

#### `POST /api/v1/folders/move`

- Auth required
- Request: `FolderMoveRequest`
- Response: `MessageResponse`

### Templates

Template APIs use `X-Brand-Space-Id` where brand scope matters.

#### `POST /api/v1/templates/upload`

- Auth required
- Header: `X-Brand-Space-Id`
- Request: `TemplateUploadRequest`
- Response: `TemplateResponse`

#### `GET /api/v1/templates/list`

- Auth required
- Header: `X-Brand-Space-Id`
- Response: `TemplateResponse[]`

#### `GET /api/v1/templates/{template_id}`

- Auth required
- Response: `{ template, metadata }`

#### `PUT /api/v1/templates/{template_id}/metadata`

- Auth required
- Request: `TemplateMetadataUpsertRequest`
- Response: zone metadata `dict`

#### `POST /api/v1/templates/apply`

- Auth required
- Request: `TemplateApplyRequest`
- Response: `{ template, metadata, prompt, studio_panel }`

#### `POST /api/v1/templates/recommend`

- Auth required
- Request: `TemplateRecommendRequest`
- Response: `TemplateRecommendationResponse[]`

Recommendation scoring considers:

- prompt keyword overlap
- supported platforms
- supported export formats
- template kind compatibility

#### `DELETE /api/v1/templates/{template_id}`

- Auth required
- Response: `MessageResponse`

### Rendering

#### `POST /api/v1/render/layout`

- Auth required
- Request: `RenderLayoutRequest`
- Response: `dict`

Supports optional blueprint overrides and template-aware zone resolution before preview/export.

#### `POST /api/v1/render/preview`

- Auth required
- Request: `RenderPreviewRequest`
- Response: `RenderResponse`

#### `POST /api/v1/render/export`

- Auth required
- Request: `RenderExportRequest`
- Response: `RenderResponse`

Supports:

- blueprint override
- template override
- multi-page export assets for carousel/PDF/infographic flows

#### `GET /api/v1/render/{content_id}/status`

- Auth required
- Response: `dict`

### Review and Sharing

#### `POST /api/v1/review/share-link`

- Auth required
- Request: `ShareLinkCreateRequest`
- Response: `ReviewLinkResponse`

#### `GET /api/v1/review/{token}`

- Public by token
- Response: `dict`

Response includes:

- review link metadata
- content payload being reviewed
- available content/render assets
- comments

#### `POST /api/v1/review/{token}/comment`

- Public by token
- Request: `ReviewCommentCreateRequest`
- Response: `ReviewCommentResponse`

#### `POST /api/v1/review/{token}/status`

- Public by token
- Request: `ReviewStatusUpdateRequest`
- Response: `ReviewLinkResponse`

### Social

#### `POST /api/v1/social/connect`

- Auth required
- Header: `X-Brand-Space-Id`
- Request: `SocialConnectRequest`
- Response: `SocialConnectionResponse`

#### `GET /api/v1/social/list`

- Auth required
- Header: `X-Brand-Space-Id`
- Response: `SocialConnectionResponse[]`

#### `POST /api/v1/social/publish`

- Auth required
- Header: `X-Brand-Space-Id`
- Request: `SocialPublishRequest`
- Response: `dict`

#### `POST /api/v1/social/disconnect`

- Auth required
- Header: `X-Brand-Space-Id`
- Request: `SocialConnectRequest`
- Response: `MessageResponse`

### Analytics

#### `GET /api/v1/analytics/platform`

- Role: `SUPER_ADMIN`
- Response: `AnalyticsResponse`

#### `GET /api/v1/analytics/tenant`

- Auth required
- Role-gated for tenant scope
- Response: `AnalyticsResponse`

#### `GET /api/v1/analytics/brand/{brand_id}`

- Auth required
- Response: `AnalyticsResponse`

#### `GET /api/v1/analytics/usage-summary`

- Auth required
- Response: `AnalyticsResponse`

Analytics metrics now also carry persisted token telemetry derived from generated content history:

```json
{
  "token_usage": {
    "input_tokens": 1200,
    "output_tokens": 850,
    "total_tokens": 2050,
    "monthly_token_usage": [
      {
        "month": "2026-03",
        "input_tokens": 400,
        "output_tokens": 250,
        "total_tokens": 650
      }
    ]
  }
}
```

### Jobs

#### `GET /api/v1/jobs/list`

- Auth required
- Response: `JobResponse[]`

#### `GET /api/v1/jobs/{job_id}/status`

- Auth required
- Response: `JobResponse`

## Backend to AI Orchestration Contract

Defined in `app/ai/contracts.py`.

### `AIOrchestrationRequest`

```json
{
  "tenant_id": "uuid",
  "brand_space_id": "uuid",
  "user_id": "uuid",
  "prompt": "Create launch copy for LinkedIn",
  "studio_panel": {},
  "conversation_context": {},
  "resolved_brand_context": {},
  "persona_context": {},
  "objective_context": {},
  "retrieved_knowledge": {
    "brand": [],
    "strategy": [],
    "metadata": [],
    "campaign_history": []
  },
  "template_context": {},
  "reference_assets": [],
  "resolution_policy": {},
  "generate_image": true
}
```

### `AIOrchestrationResponse`

```json
{
  "text": {
    "headline": "string",
    "body": "string",
    "cta": "string",
    "hashtags": ["string"],
    "metadata": {}
  },
  "blueprint": {},
  "image_assets": [],
  "explainability": {},
  "tone_analysis": {}
}
```

## AI Blueprint to Backend Renderer Contract

### `BlueprintPayload`

```json
{
  "layout_type": "single-panel",
  "zones": [
    {
      "zone_id": "headline-zone",
      "role": "headline",
      "x": 64,
      "y": 80,
      "width": 952,
      "height": 180,
      "max_lines": 3
    }
  ],
  "hierarchy": ["headline", "body", "cta"],
  "text_blocks": [
    {
      "role": "headline",
      "text": "Campaign headline"
    }
  ],
  "image_zones": [
    {
      "zone_id": "hero-image"
    }
  ],
  "logo_rules": {},
  "cta_placement": {},
  "platform_preset": "instagram",
  "export_format": "png",
  "overflow_strategy": {}
}
```

## Backend to Renderer Contract

### `RendererInput`

The backend sends:

- content version id
- studio panel selection
- blueprint payload
- structured text payload
- optional template metadata
- optional template asset path
- optional logo path
- generated image assets
- brand visual rules

## Renderer to Backend Contract

### `RendererResponse`

```json
{
  "preview_asset": {
    "asset_id": "uuid",
    "mime_type": "image/png",
    "storage_path": "tenant/brand/generated/preview.png",
    "width": 1080,
    "height": 1080,
    "asset_role": "render_preview"
  },
  "export_assets": [],
  "renderer_metadata": {
    "deterministic": true,
    "overflow_strategy": {},
    "page_count": 1,
    "render_manifest": {
      "zones_used": [],
      "text_blocks_used": [],
      "template_zone_map": {},
      "image_asset_paths": []
    }
  }
}
```

Notes:

- `preview_asset` is always the first-page render asset.
- `export_assets` can contain multiple files for carousel, infographic, or multi-page PDF/image flows.
- `renderer_metadata.render_manifest` is persisted so frontend and UAT can inspect which template zones, image assets, and text blocks were used.

## Error Contract

Business exceptions are normalized by FastAPI exception handlers in `main.py`.

Typical error response:

```json
{
  "detail": "Brand Space must be Active for generation"
}
```

Common status codes:

- `400` business rule or lifecycle failure
- `401` invalid or inactive auth
- `403` forbidden role or brand access
- `404` scoped resource not found

## Notes for Frontend Developers

- Always pass `studio_panel` for generation, rewrite, chat, template apply, and rendering.
- Treat `generated_payload`, `blueprint_payload`, and `explainability_metadata` as first-class response fields.
- Use `assets` and renderer export payloads rather than assuming base64 image returns.
- `renderer_metadata.page_count` and `export_assets` should drive carousel/PDF/infographic preview behavior.
- Review endpoints are token-based and can be used outside tenant auth flows.
- OpenAPI is available at `/docs`, but this file is the developer-oriented contract summary.
