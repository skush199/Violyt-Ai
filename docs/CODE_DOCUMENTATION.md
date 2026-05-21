# Code Documentation

## Architecture Overview

The codebase follows this runtime flow:

1. FastAPI receives a request in `app/api/routes/*`.
2. Route handlers resolve auth and DB dependencies from `app/core/dependencies.py` and `app/db/session.py`.
3. Route handlers delegate to service classes in `app/services/*`.
4. Services use repositories in `app/repositories/*` for persistence.
5. AI-aware services call the orchestration layer in `app/ai/*`.
6. Knowledge processing uses OCR plus vector indexing.
7. Final layout rendering is performed in backend code by `app/services/renderer.py`.
8. Background work is polled and executed by `app/workers/runner.py`.

## Entry and Core Files

### `main.py`

Purpose:

- creates the FastAPI app
- seeds RBAC on startup
- mounts `/storage`
- registers domain exception handlers
- attaches `/api/v1` routes

### `app/api/router.py`

Purpose:

- central route registration for all API modules

Registered groups:

- auth
- tenants
- brands
- knowledge
- content
- chat
- folders
- templates
- render
- review
- social
- analytics
- jobs

### `app/core/config.py`

Purpose:

- environment-backed settings container using `pydantic-settings`

Important setting groups:

- auth and token expiry
- social token encryption
- database URLs
- object storage and vector store paths
- OpenAI and Anthropic model settings
- provider routing defaults
- renderer defaults
- worker polling configuration

### `app/core/crypto.py`

Purpose:

- encrypts and decrypts sensitive social connector secrets using a Fernet key derived from config

### `app/core/dependencies.py`

Purpose:

- current-user resolution from bearer tokens
- role-based route guards
- Brand Space header parsing
- Super Admin brand-content access restriction

Important exports:

- `CurrentPrincipal`
- `get_current_principal()`
- `require_roles()`
- `get_brand_scope_header()`
- `forbid_super_admin_brand_access()`

### `app/core/studio.py`

Purpose:

- centralizes default studio-panel sizes and format/platform size overrides
- normalizes Studio Panel payloads across generation, chat, and render flows

### `app/core/security.py`

Purpose:

- password hashing
- password verification
- access token creation
- refresh token creation
- token decoding

### `app/core/exceptions.py`

Purpose:

- typed business exceptions for not found, lifecycle, guardrail, authorization, and usage-limit failures

### `app/db/base.py`

Purpose:

- SQLAlchemy declarative base

### `app/db/session.py`

Purpose:

- async engine and async session setup
- request-scoped DB dependency

## API Route Modules

### `app/api/routes/auth.py`

Purpose:

- login and activation endpoints
- current user identity lookup

Handlers:

- `login()`
- `activate()`
- `forgot_password()`
- `reset_password()`
- `me()`
- `profile()`
- `update_profile()`
- `change_password()`

### `app/api/routes/tenant.py`

Purpose:

- tenant creation
- tenant user administration
- usage limit updates

Handlers:

- `create_tenant()`
- `list_tenants()`
- `get_tenant()`
- `list_users()`
- `create_tenant_user()`
- `deactivate_user()`
- `update_usage_limits()`
- `get_usage_summary()`

### `app/api/routes/brand.py`

Purpose:

- Brand Space lifecycle and configuration APIs

Handlers:

- `create_brand()`
- `list_brands()`
- `get_brand()`
- `update_brand()`
- `upsert_section()`
- `finalize_brand()`
- `archive_brand()`
- `restore_brand()`
- `delete_brand()`
- `brand_overview()`

### `app/api/routes/knowledge.py`

Purpose:

- knowledge upload, reprocess, status, listing, and delete APIs

Handlers:

- `upload_knowledge()`
- `list_knowledge()`
- `knowledge_status()`
- `delete_knowledge()`
- `reprocess_knowledge()`

### `app/api/routes/content.py`

Purpose:

- content generation, rewrite, tone check, history, detail, export, and copy APIs

Handlers:

- `generate_content()`
- `rewrite_content()`
- `tone_check()`
- `content_history()`
- `content_detail()`
- `export_content()`
- `copy_content()`

### `app/api/routes/chat.py`

Purpose:

- chat session and message APIs built on top of content generation

Handlers:

- `create_chat_session()`
- `list_chat_sessions()`
- `list_chat_messages()`
- `send_chat_message()`

### `app/api/routes/folder.py`

Purpose:

- content folder CRUD and content move operations

Handlers:

- `create_folder()`
- `list_folders()`
- `rename_folder()`
- `delete_folder()`
- `move_content()`

### `app/api/routes/template.py`

Purpose:

- template upload, analysis metadata access, metadata update, apply, and delete

Handlers:

- `upload_template()`
- `list_templates()`
- `template_detail()`
- `update_metadata()`
- `apply_template()`
- `recommend_templates()`
- `delete_template()`

### `app/api/routes/render.py`

Purpose:

- explicit layout, preview, export, and render status APIs

Handlers:

- `render_layout()`
- `render_preview()`
- `render_export()`
- `render_status()`

### `app/api/routes/review.py`

Purpose:

- share links, review read access, review comments, and review status changes

Handlers:

- `create_share_link()`
- `get_review()`
- `add_comment()`
- `update_review_status()`

### `app/api/routes/social.py`

Purpose:

- social connector registration, publish request dispatch, and disconnect

Handlers:

- `list_social_connections()`
- `connect_social()`
- `publish_social()`
- `disconnect_social()`

### `app/api/routes/analytics.py`

Purpose:

- tenant analytics
- brand analytics
- usage summary

Handlers:

- `platform_analytics()`
- `tenant_analytics()`
- `brand_analytics()`
- `usage_summary()`

### `app/api/routes/jobs.py`

Purpose:

- list tenant jobs
- inspect a single job state

Handlers:

- `list_jobs()`
- `job_status()`

## Service Modules

### `app/services/auth.py`

Purpose:

- auth workflow orchestration

Methods:

- `login()`
  Validates credentials, updates last login, returns token pair.
- `activate()`
  Validates activation token, sets password, marks user activated, returns token pair.
- `forgot_password()`
  Issues a password-reset token for active users.
- `reset_password()`
  Resets the password through the token flow.
- `update_profile()`
  Updates profile fields for the current user.
- `change_password()`
  Changes password using the authenticated user flow.
- `build_current_user_response()`
  Builds `CurrentUserResponse` using role codes and brand assignments.

### `app/services/tenant.py`

Purpose:

- tenant and tenant-user business logic

Methods:

- `create_tenant()`
  Creates tenant, admin user, activation token, and usage-limit row.
- `create_tenant_user()`
  Adds a tenant-scoped user and assigns role and Brand Space scope.
- `list_users()`
  Returns tenant users.
- `list_tenants()`
  Returns all tenants for super-admin use.
- `get_tenant()`
  Loads a single tenant by id.
- `get_usage_summary()`
  Returns limits and consumption for one tenant.
- `get_tenant_summary()`
  Builds a UAT-friendly tenant summary with counts and usage state.
- `build_user_summary()`
  Enriches user records with role codes and Brand Space assignments.
- `deactivate_user()`
  Soft-disables a tenant user.
- `update_usage_limits()`
  Updates tenant capacity controls.

### `app/services/brand.py`

Purpose:

- Brand Space lifecycle, configuration persistence, and brand-context refresh

Methods:

- `create_brand()`
  Creates a draft Brand Space and seed configuration sections.
- `refresh_context()`
  Rebuilds the resolved brand context from current sections, personas, guardrails, and objectives.
- `upsert_section()`
  Version-writes a section and refreshes brand context.
- `update_brand()`
  Updates high-level Brand Space fields.
- `finalize_brand()`
  Marks the brand finalized and active for future generation workflows.
- `archive_brand()`
  Moves the brand to archived state.
- `restore_brand()`
  Restores an archived brand to active state.
- `delete_brand()`
  Soft-deletes the Brand Space.
- `list_brands()`
  Applies tenant and brand-user scoping.
- `require_active()`
  Enforces active lifecycle state.

### `app/services/knowledge.py`

Purpose:

- knowledge file ingestion and vector indexing

Methods:

- `upload()`
  Saves bytes to object storage, creates asset row, and enqueues a knowledge-processing job.
- `process_asset()`
  Runs OCR or document extraction, updates page counts, indexes text, and updates usage consumption.
- `list()`
  Lists brand knowledge assets.
- `delete()`
  Removes embeddings, marks asset deleted, and deletes the stored file.
- `reprocess()`
  Re-runs processing for an existing asset.

### `app/services/content.py`

Purpose:

- content generation, rewrite, tone scoring, history, and export orchestration

Methods:

- `_get_or_create_session()`
  Creates or reuses a `ContentSession`.
- `_gather_context()`
  Loads brand, section, persona, and objective context.
- `generate()`
  Enforces usage limits, resolves template recommendations, retrieves knowledge, calls the AI orchestrator, saves version history, stores generated assets, and updates usage counters.
- `rewrite()`
  Produces a new version from an existing content version plus rewrite instruction.
- `tone_check()`
  Runs tone scoring outside a full generate call.
- `history()`
  Returns content history for a Brand Space.
- `detail()`
  Loads a single content version.
- `export()`
  Converts a content version plus blueprint into renderer output, with template metadata, template background, logo asset resolution, and render-asset persistence.
- `copy()`
  Returns lightweight copy-ready text.

### `app/services/chat.py`

Purpose:

- chat-session lifecycle and message persistence

Methods:

- `create_session()`
  Creates an active chat session bound to a Brand Space and studio panel selection.
- `list_sessions()`
  Returns chat sessions for a Brand Space.
- `get_session()`
  Loads and scope-checks a chat session.
- `list_messages()`
  Returns ordered chat messages for a session.
- `send_message()`
  Persists the user message, calls `ContentService.generate()`, stores the assistant message, and updates conversation context.
- `build_assistant_message_text()`
  Builds readable assistant text from structured output.
- `build_citations()`
  Converts explainability retrieval channels into simple citation references.

### `app/services/folder.py`

Purpose:

- organization layer for generated content

Methods:

- `create()`
- `rename()`
- `delete()`
- `move_content()`
- `list()`

### `app/services/template.py`

Purpose:

- template asset persistence and metadata management

Methods:

- `upload()`
  Saves template bytes and queues analysis.
- `analyze()`
  Produces template analysis metadata using OpenAI Vision when configured and a deterministic heuristic fallback otherwise.
- `list()`
- `detail()`
- `update_metadata()`
- `delete()`
- `recommend()`
  Scores templates against prompt keywords, platform support, export support, and kind compatibility.

### `app/services/renderer.py`

Purpose:

- deterministic backend rendering

Methods:

- `_font()`
  Chooses configured font or falls back to default font.
- `_draw_text_block()`
  Fits text into bounded zones by progressively reducing font size, truncating safely, and aligning text.
- `_build_page_payloads()`
  Splits long-form body text into multi-page output payloads for carousel, PDF, and infographic-style flows.
- `_save_image_asset()`
  Persists rendered images to object storage.
- `_image_to_pdf_bytes()`
  Converts a rendered image to PDF bytes.
- `_document_export()`
  Produces a DOCX export with image and text.
- `render()`
  Builds preview and export assets from blueprint, structured text, image assets, optional template backgrounds, and logo assets.

### `app/services/review.py`

Purpose:

- share-link generation and external review flows

Methods:

- `create_link()`
- `get_by_token()`
- `add_comment()`
- `update_status()`

External review enforcement includes:

- share-link scoped content resolution
- allow/disallow external comments
- explicit review status validation

### `app/services/social.py`

Purpose:

- social connector persistence and publish placeholder logic

Methods:

- `connect()`
- `list_connections()`
- `disconnect()`
- `publish()`

Social connector notes:

- credentials are stored encrypted
- publish currently prepares validated dispatch payloads and media selection
- live provider posting is still a downstream integration step

### `app/services/analytics.py`

Purpose:

- analytics aggregation over content, jobs, and usage

Methods:

- `tenant_summary()`
- `brand_summary()`
- `platform_summary()`

### `app/services/jobs.py`

Purpose:

- job creation and state transitions

Methods:

- `create()`
- `set_status()`
- `list_for_tenant()`
- `get()`

### `app/services/usage.py`

Purpose:

- usage-limit enforcement and consumption tracking

Methods:

- `enforce()`
  Blocks over-limit actions before work starts.
- `increment()`
  Records successful consumption.
- `summary()`
  Returns tenant consumption snapshot.

### `app/services/bootstrap.py`

Purpose:

- seeds roles, permissions, and role-permission mappings on startup

## AI Modules

### `app/ai/contracts.py`

Purpose:

- strongly typed internal contracts between backend, AI orchestration, and renderer

Key models:

- `AIOrchestrationRequest`
- `StructuredTextPayload`
- `BlueprintZone`
- `BlueprintPayload`
- `GeneratedImageAsset`
- `AIOrchestrationResponse`
- `RendererInput`
- `RendererResponse`

### `app/ai/orchestrator.py`

Purpose:

- top-level AI orchestration entry point

Method:

- `generate()`
  Validates prompt guardrails, selects providers, produces research summary, composes prompts, generates structured text, scores tone, builds blueprint, optionally creates image assets, and returns explainability metadata.

### `app/ai/brand_intelligence.py`

Purpose:

- converts database entities into AI-ready context dictionaries

Methods:

- `build_context()`
- `persona_to_dict()`
- `guardrail_to_dict()`
- `objective_to_dict()`

### `app/ai/prompt_intelligence.py`

Purpose:

- converts backend context into LLM-ready prompts

Methods:

- `compose_generation_envelope()`
- `compose_rewrite_envelope()`
- `_knowledge_to_sections()`

The generation envelope now includes:

- platform-specific prompt guidance
- reference asset context
- deterministic conflict-resolution instructions

### `app/ai/guardrails.py`

Purpose:

- prompt and output safety checks against brand guardrails

Methods:

- `validate_prompt()`
- `validate_output()`

### `app/ai/tone_intelligence.py`

Purpose:

- tone consistency scoring and rewrite-suggestion generation

Method:

- `evaluate()`

Tone scoring now uses:

- LLM-assisted structured scoring when the configured text provider is available
- deterministic heuristic fallback when provider access is unavailable

### `app/ai/template_vision.py`

Purpose:

- analyzes uploaded template images with OpenAI Vision when configured
- falls back to deterministic metadata when provider access is unavailable

### `app/ai/blueprint.py`

Purpose:

- deterministic blueprint planning for backend rendering

Method:

- `build()`
  Generates layout type, zones, text blocks, image zones, CTA placement, and overflow strategy from studio panel plus content.

### `app/ai/rag/ocr.py`

Purpose:

- wraps the existing OCR logic from `ocr_processor.py`

Method:

- `extract()`

### `app/ai/rag/retrieval.py`

Purpose:

- brand-scoped indexing and retrieval service over the vector store

Methods:

- `index_asset()`
- `delete_asset()`
- `search()`

### `app/ai/providers/base.py`

Purpose:

- provider interfaces

Exports:

- `PromptEnvelope`
- `TextGenerationProvider`
- `ImageGenerationBackend`

### `app/ai/providers/router.py`

Purpose:

- config-driven provider selection for research, text generation, and image generation

Methods:

- `get_text_provider()`
- `get_image_provider()`

### `app/ai/providers/openai_provider.py`

Purpose:

- OpenAI-backed text and image providers

Classes and methods:

- `OpenAITextProvider.generate_structured_json()`
- `OpenAITextProvider.generate_text()`
- `OpenAIImageProvider.generate()`

### `app/ai/providers/anthropic_provider.py`

Purpose:

- Anthropic-backed text provider for research or generation flows

Methods:

- `generate_structured_json()`
- `generate_text()`

### `app/ai/providers/image_generation.py`

Purpose:

- mock or deterministic image generation fallback

Method:

- `generate()`

### `app/ai/providers/llm.py`

Purpose:

- compatibility export module for legacy imports

## Repository Modules

Repositories encapsulate scoped reads and writes so services do not directly embed query logic.

### `app/repositories/base.py`

Purpose:

- base repository utilities for create, fetch, and list operations

### `app/repositories/tenant.py`

Purpose:

- tenant, user, role, activation-token, and usage-limit persistence

### `app/repositories/brand.py`

Purpose:

- Brand Space, section, persona, guardrail, objective, and member persistence

### `app/repositories/knowledge.py`

Purpose:

- knowledge assets, templates, and template metadata persistence

### `app/repositories/content.py`

Purpose:

- sessions, chat messages, content history, generated assets, and folders persistence

### `app/repositories/collaboration.py`

Purpose:

- review links, review comments, analytics snapshots, usage consumption, and jobs persistence

## Model Modules

### `app/models/tenant.py`

Entities:

- `Tenant`
- `User`
- `Role`
- `Permission`
- `RolePermission`
- `UserRole`
- `ActivationToken`

### `app/models/brand.py`

Entities:

- `BrandSpace`
- `BrandConfigurationSection`
- `Persona`
- `Guardrail`
- `Objective`
- `BrandSpaceMember`

### `app/models/knowledge.py`

Entities:

- `KnowledgeAsset`
- `Template`
- `TemplateMetadata`

### `app/models/content.py`

Entities:

- `ContentSession`
- `ChatMessage`
- `ContentFolder`
- `ContentVersion`
- `GeneratedAsset`

### `app/models/collaboration.py`

Entities:

- `ReviewLink`
- `ReviewComment`
- `SocialConnection`
- `AnalyticsSnapshot`
- `UsageLimit`
- `UsageConsumption`
- `JobRecord`

### `app/models/mixins.py`

Purpose:

- common SQLAlchemy mixins for UUIDs, timestamps, tenant scope, Brand Space scope, and soft-delete state

## Schema Modules

### `app/schemas/common.py`

Shared contracts:

- `APIModel`
- `MessageResponse`
- `PaginatedResponse`
- `AuditMetadata`
- `StudioPanelSelection`
- `AssetReference`

### `app/schemas/auth.py`

Contracts:

- `LoginRequest`
- `ActivationRequest`
- `TokenPairResponse`
- `CurrentUserResponse`

### `app/schemas/tenant.py`

Contracts:

- `TenantUsageLimitUpdate`
- `TenantCreateRequest`
- `TenantResponse`
- `TenantSummaryResponse`
- `TenantUserCreateRequest`
- `TenantUserResponse`
- `TenantUsageSummary`

### `app/schemas/brand.py`

Contracts:

- identity, foundations, voice, persona, guardrail, objective, visual identity, and prompt-intelligence payloads
- `BrandSectionUpsertRequest`
- `BrandCreateRequest`
- `BrandUpdateRequest`
- `BrandFinalizeRequest`
- `BrandResponse`
- `BrandOverviewResponse`

### `app/schemas/knowledge.py`

Contracts:

- `KnowledgeUploadRequest`
- `KnowledgeAssetResponse`
- `KnowledgeReprocessRequest`

### `app/schemas/content.py`

Contracts:

- `ContentGenerateRequest`
- `ContentRewriteRequest`
- `ToneCheckRequest`
- `ContentExportRequest`
- `ContentCopyRequest`
- `ToneEvaluationResponse`
- `ContentVersionResponse`

### `app/schemas/chat.py`

Contracts:

- `ChatSessionCreateRequest`
- `ChatMessageCreateRequest`
- `ChatSessionResponse`
- `ChatMessageResponse`
- `ChatSendResponse`

### `app/schemas/folder.py`

Contracts:

- `FolderCreateRequest`
- `FolderRenameRequest`
- `FolderMoveRequest`

### `app/schemas/template.py`

Contracts:

- `TemplateUploadRequest`
- `TemplateMetadataUpsertRequest`
- `TemplateApplyRequest`
- `TemplateResponse`

### `app/schemas/render.py`

Contracts:

- `RenderLayoutRequest`
- `RenderPreviewRequest`
- `RenderExportRequest`
- `RenderResponse`

### `app/schemas/review.py`

Contracts:

- `ShareLinkCreateRequest`
- `ReviewCommentCreateRequest`
- `ReviewCommentResponse`
- `ReviewStatusUpdateRequest`
- `ReviewLinkResponse`
- `ReviewDetailContent`
- `ReviewDetailResponse`

### `app/schemas/social.py`

Contracts:

- `SocialConnectRequest`
- `SocialPublishRequest`
- `SocialConnectionResponse`

### `app/schemas/analytics.py`

Contracts:

- `AnalyticsResponse`

### `app/schemas/job.py`

Contracts:

- `JobResponse`

## Integration and Utility Modules

### `app/integrations/object_storage.py`

Purpose:

- local filesystem object storage adapter

Methods:

- `build_relative_path()`
- `save_bytes()`
- `read_bytes()`
- `delete()`
- `absolute_path()`

### `app/integrations/vector_store.py`

Purpose:

- FAISS-backed vector index with OpenAI embeddings or deterministic hash fallback

Key classes:

- `SearchResult`
- `HashEmbeddings`
- `FaissVectorStoreProvider`

Important methods:

- `upsert_documents()`
- `delete_source()`
- `search()`
- `namespace()`

### `app/utils/files.py`

Purpose:

- file helper utilities such as base64 decoding and safe parent-path creation

## Worker and Script Modules

### `app/workers/runner.py`

Purpose:

- simple polling worker loop for queued jobs

Functions:

- `handle_job()`
  Dispatches knowledge processing or template analysis and applies retry-aware failure handling.
- `run_worker_loop()`
  Polls queued jobs and executes them sequentially.

### `scripts/run_worker.py`

Purpose:

- launches the async worker loop

### `scripts/seed_rbac.py`

Purpose:

- helper script entry for role and permission seeding if needed outside app startup

## Database Migration

### `alembic/versions/0001_initial_schema.py`

Purpose:

- creates the initial multi-tenant schema including tenants, roles, Brand Spaces, knowledge assets, content history, review data, analytics, usage, and jobs

## How to Extend Safely

- Add a schema first when changing an external contract.
- Add or update a repository if new persistence patterns are needed.
- Keep business rules in services, not routes.
- Keep AI provider details behind `app/ai/providers/*`.
- Keep renderer logic backend-owned and deterministic.
- Preserve lifecycle and usage-limit checks whenever you add new content-producing actions.
