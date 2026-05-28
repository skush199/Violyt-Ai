import type { Role } from "@/types/rbac.types";

export type UUID = string;

export type PlatformPreset = "instagram" | "linkedin" | "x" | "youtube_thumbnail";
export type StudioFormat = "static" | "carousel" | "pdf" | "infographic";
export type ExportFileType = "doc" | "pdf" | "png" | "jpg";

export interface TokenPairResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

export interface TwoFactorChallengeResponse {
  requires_two_factor: true;
  two_factor_ticket: string;
  delivery: "authenticator";
  email: string;
}

export type LoginResponse = TokenPairResponse | TwoFactorChallengeResponse;

export interface CurrentUserResponse {
  user_id: UUID;
  tenant_id?: UUID;
  email: string;
  full_name: string;
  role_codes: string[];
  assigned_brand_space_ids: UUID[];
  extra: Record<string, unknown>;
}

export interface UiUser {
  id: UUID;
  tenantId?: UUID;
  email: string;
  name: string;
  role: Role;
  roleCodes: string[];
  brandSpaceIds: UUID[];
  phone?: string;
  notificationsEnabled?: boolean;
  twoFactorEnabled?: boolean;
}

export interface TwoFactorSetupResponse {
  enabled: boolean;
  pending_setup: boolean;
  secret?: string | null;
  otpauth_url?: string | null;
  qr_code_url?: string | null;
}

export interface TenantUsageLimits {
  max_users: number;
  max_brand_spaces: number;
  max_content_generations: number;
  max_image_generations: number;
  max_ocr_pages: number;
}

export interface TenantSummaryResponse {
  id: UUID;
  name: string;
  slug: string;
  contact_email: string;
  contact_number?: string;
  address?: string;
  logo_asset_path?: string;
  is_active: boolean;
  total_users: number;
  brand_space_count: number;
  usage_limits?: TenantUsageLimits;
  usage_consumption: Record<string, number>;
  token_usage: Record<string, number>;
  monthly_token_usage: Array<{
    month: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  }>;
  metadata_json: Record<string, unknown>;
  created_at: string;
  tenant_admin_name?: string;
  tenant_admin_email?: string;
  tenant_admin_phone_number?: string;
  last_active_at?: string | null;
}

export interface TenantCreateResponse {
  id: UUID;
  name: string;
  slug: string;
  contact_email: string;
  contact_number?: string;
  address?: string;
  logo_asset_path?: string;
  is_active: boolean;
  metadata_json: Record<string, unknown>;
  created_at: string;
  activation_email: {
    attempted: boolean;
    delivered: boolean;
    recipient_email: string;
    reason?: string | null;
  };
}

export interface TenantCreateRequest {
  name: string;
  slug: string;
  contact_email: string;
  contact_number?: string;
  address?: string;
  admin_full_name: string;
  admin_email: string;
  admin_phone_number?: string;
  usage_limits: TenantUsageLimits;
  metadata_json?: Record<string, unknown>;
}

export type TenantUpdateRequest = Partial<TenantCreateRequest> & {
  metadata_json?: Record<string, unknown>;
  is_active?: boolean;
};

export interface TenantLogoUploadRequest {
  filename: string;
  mime_type: string;
  content_base64: string;
}

export interface TenantUserResponse {
  id: UUID;
  tenant_id?: UUID;
  email: string;
  full_name: string;
  phone_number?: string;
  is_active: boolean;
  is_activated: boolean;
  role_codes: string[];
  brand_space_ids: UUID[];
  created_at: string;
  last_login_at?: string | null;
  activation_email?: {
    attempted: boolean;
    delivered: boolean;
    recipient_email: string;
    reason?: string | null;
  };
}

export interface TenantBrandSpaceSummaryResponse {
  id: UUID;
  tenant_id: UUID;
  name: string;
  slug: string;
  lifecycle_state: string;
  created_at: string;
  last_active_at?: string | null;
  last_login_at?: string | null;
  content_generations: number;
  visual_generations: number;
  ocr_pages: number;
}

export interface TenantUserCreateRequest {
  full_name: string;
  email: string;
  phone_number?: string;
  role_code: string;
  brand_space_ids: UUID[];
}

export interface TenantUserUpdateRequest {
  full_name?: string;
  email?: string;
  phone_number?: string;
  role_code?: string;
  brand_space_ids?: UUID[];
  is_active?: boolean;
}

export interface TenantUsageSummary {
  tenant_id: UUID;
  limits: TenantUsageLimits;
  consumption: Record<string, number>;
}

export interface BrandResponse {
  id: UUID;
  tenant_id: UUID;
  name: string;
  slug: string;
  description: string;
  lifecycle_state: string;
  is_finalized: boolean;
  resolved_brand_context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AssetProcessingStatusResponse {
  field_key: string;
  lifecycle_state: string;
  processor_name?: string | null;
  progress_current: number;
  progress_total: number;
  status_message?: string | null;
  raw_status_json: Record<string, unknown>;
}

export interface AssetValidationResultResponse {
  field_key: string;
  validation_state: string;
  trust_level?: string | null;
  warnings: string[];
  exclusion_reason?: string | null;
  resolved_payload: Record<string, unknown>;
  confidence?: number | null;
}

export interface AssetCategoryRoutingResponse {
  requested_field_key: string;
  requested_category?: string | null;
  routed_category: string;
  classifier?: string | null;
  confidence?: number | null;
  routing_reason?: string | null;
  decision_json: Record<string, unknown>;
}

export interface ReusableBrandAssetResponse {
  id: UUID;
  knowledge_asset_id: UUID;
  asset_kind: string;
  review_class?: string | null;
  review_status?: string | null;
  review_reason?: string | null;
  label?: string | null;
  mime_type: string;
  storage_path: string;
  asset_url?: string | null;
  width?: number | null;
  height?: number | null;
  confidence?: number | null;
  is_active: boolean;
  source_metadata_json: Record<string, unknown>;
  normalized_metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface BrandAttachmentResponse {
  id: UUID;
  tenant_id: UUID;
  brand_space_id?: UUID | null;
  name: string;
  original_filename: string;
  mime_type: string;
  storage_path: string;
  asset_url?: string | null;
  lifecycle_state: string;
  channel: string;
  field_key?: string | null;
  asset_category?: string | null;
  classification_confidence?: number | null;
  page_count: number;
  is_active: boolean;
  metadata_json: Record<string, unknown>;
  structured_data_json: Record<string, unknown>;
  normalized_data_json: Record<string, unknown>;
  processing_error?: string | null;
  validation_state: string;
  validation_summary_json: Record<string, unknown>;
  processing_status?: AssetProcessingStatusResponse | null;
  validation_result?: AssetValidationResultResponse | null;
  routing?: AssetCategoryRoutingResponse | null;
  reusable_assets: ReusableBrandAssetResponse[];
  created_at: string;
  updated_at: string;
}

export interface BrandAttachmentListResponse {
  field_key: string;
  assets: BrandAttachmentResponse[];
}

export interface DataConflictResponse {
  id: UUID;
  conflict_type: string;
  severity: string;
  field_keys: string[];
  knowledge_asset_ids: string[];
  details_json: Record<string, unknown>;
  resolution_status: string;
  resolved_payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ResolvedBrandContextResponse {
  brand_space_id: UUID;
  snapshot_id?: UUID | null;
  snapshot_kind: string;
  status: string;
  warnings: string[];
  excluded_asset_ids: string[];
  context_json: Record<string, unknown>;
}

export interface ValidationSummaryResponse {
  brand_space_id: UUID;
  warnings: string[];
  conflicts: DataConflictResponse[];
  excluded_assets: string[];
  validation_results: AssetValidationResultResponse[];
  latest_snapshot?: ResolvedBrandContextResponse | null;
}

export interface BrandOverviewResponse {
  brand: BrandResponse;
  sections: Array<{ section_code: string; payload: Record<string, unknown>; version?: number }>;
  personas: Array<Record<string, unknown>>;
  guardrails: Array<Record<string, unknown>>;
  objectives: Array<Record<string, unknown>>;
}

export interface KnowledgeAssetResponse {
  id: UUID;
  brand_space_id?: UUID;
  name: string;
  original_filename: string;
  mime_type: string;
  storage_path: string;
  asset_url?: string;
  lifecycle_state: string;
  channel: string;
  field_key?: string | null;
  asset_category?: string | null;
  page_count: number;
  metadata_json: Record<string, unknown>;
  structured_data_json: Record<string, unknown>;
  normalized_data_json: Record<string, unknown>;
  validation_state: string;
  validation_summary_json: Record<string, unknown>;
  is_active: boolean;
  processing_error?: string | null;
}

export interface TemplateResponse {
  id: UUID;
  name: string;
  description?: string | null;
  kind: string;
  storage_path: string;
  asset_url?: string | null;
  source_knowledge_asset_id?: UUID | null;
  origin_field_key?: string | null;
  tags: string[];
  analysis_json: Record<string, unknown>;
  matcher_features_json: Record<string, unknown>;
}

export interface TemplateRecommendationResponse {
  template_id: UUID;
  name: string;
  display_name?: string | null;
  asset_url?: string | null;
  score: number;
  match_type: string;
  decision_confidence?: number | null;
  format_family?: string | null;
  is_primary_adaptation?: boolean;
  selection_reason?: string | null;
  recommendation_group_key?: string | null;
  reasons: string[];
  score_breakdown: Record<string, unknown>;
  adaptation_plan: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface TemplateRecommendRequest {
  prompt: string;
  studio_panel: StudioPanelSelection;
  limit?: number;
}

export interface GenerationDecision {
  mode?: string;
  template_id?: UUID | null;
  template_name?: string | null;
  template_preview_asset_url?: string | null;
  template_decision_confidence?: number | null;
  template_recommendations?: TemplateRecommendationResponse[];
  rationale?: string[] | string;
  score_breakdown?: Record<string, unknown>;
  adaptation_plan?: Record<string, unknown>;
  brand_rule_hints?: string[];
  asset_strategy?: Record<string, unknown>;
  review_flags?: string[];
}

export interface StudioPanelSelection {
  format: StudioFormat;
  platform_preset: PlatformPreset;
  file_type: ExportFileType;
  size?: { width: number; height: number };
}

export interface StructuredTextPayload {
  headline: string;
  body: string;
  cta: string;
  hashtags: string[];
  metadata: Record<string, unknown>;
}

export interface AssetReference {
  asset_id: UUID;
  mime_type: string;
  storage_path: string;
  asset_url?: string | null;
  width?: number;
  height?: number;
  asset_role: string;
}

export interface ContentVersionResponse {
  id: UUID;
  session_id: UUID;
  parent_version_id?: UUID;
  lifecycle_state: string;
  content_type: string;
  title?: string;
  prompt: string;
  studio_panel: StudioPanelSelection;
  generated_payload: StructuredTextPayload;
  blueprint_payload: Record<string, unknown>;
  explainability_metadata: Record<string, unknown>;
  generation_decision: GenerationDecision;
  tone_score?: number;
  tone_feedback: Record<string, unknown>;
  assets: AssetReference[];
}

export interface ContentGenerateRequest {
  prompt: string;
  session_id?: UUID;
  persona_id?: UUID;
  objective_id?: UUID;
  template_id?: UUID;
  studio_panel: StudioPanelSelection;
  generate_image: boolean;
  reference_asset_ids: UUID[];
}

export interface ToneEvaluationResponse {
  score: number;
  matched_signals: string[];
  deviations: string[];
  rewrite_suggestions: string[];
}

export interface ChatSessionResponse {
  id: UUID;
  brand_space_id?: UUID;
  title?: string;
  session_kind: string;
  studio_panel: StudioPanelSelection;
  conversational_context: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChatMessageResponse {
  id: UUID;
  session_id: UUID;
  user_id?: UUID;
  content_version_id?: UUID;
  role: "user" | "assistant";
  message_text: string;
  structured_payload: ChatAssistantStructuredPayload | Record<string, unknown>;
  citations: Array<Record<string, unknown>>;
  created_at: string;
}

export interface BrandScoringPayload {
  overall_score: number;
  score_breakdown: {
    on_brand: number;
    prompt_adherence: number;
    relevance: number;
  };
  weighting?: Record<string, number>;
  summary?: string[];
  developer_explanation?: Record<string, unknown>;
}

export interface ChatAssistantStructuredPayload {
  content_version_id?: UUID;
  generated_payload?: StructuredTextPayload;
  blueprint_payload?: Record<string, unknown>;
  tone_feedback?: Record<string, unknown>;
  generation_decision?: GenerationDecision;
  assets?: AssetReference[];
  preview_asset?: AssetReference;
  export_assets?: AssetReference[];
  renderer_metadata?: Record<string, unknown>;
  image_generation_requested?: boolean;
  image_generation_status?: string;
  image_asset_count?: number;
  brand_scoring?: BrandScoringPayload;
}

export interface ChatSendResponse {
  user_message: ChatMessageResponse;
  assistant_message: ChatMessageResponse;
}

export interface ChatSessionCreateRequest {
  title?: string;
  studio_panel: StudioPanelSelection;
}

export interface ChatMessageCreateRequest {
  message: string;
  studio_panel: StudioPanelSelection;
  persona_id?: UUID;
  objective_id?: UUID;
  template_id?: UUID;
  reference_asset_ids?: UUID[];
  generate_image: boolean;
}

export interface ReviewLinkResponse {
  id: UUID;
  token: string;
  status: string;
  allow_external_comments: boolean;
}

export interface ReviewDetailResponse {
  link: ReviewLinkResponse;
  content?: {
    id: UUID;
    title?: string;
    generated_payload: StructuredTextPayload;
    blueprint_payload: Record<string, unknown>;
    generation_decision?: GenerationDecision;
    assets: AssetReference[];
  };
  comments: Array<{
    id: UUID;
    body: string;
    external_author_name?: string;
    author_user_id?: UUID;
  }>;
}

export interface RenderResponse {
  content_version_id: UUID;
  preview_asset?: AssetReference;
  export_assets: AssetReference[];
  renderer_metadata: Record<string, unknown>;
}

export interface AnalyticsResponse {
  scope: string;
  tenant_id?: UUID;
  brand_space_id?: UUID;
  metrics: Record<string, unknown>;
}
