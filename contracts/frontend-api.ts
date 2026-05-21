export type UUID = string;

export type StudioFormat = "static" | "carousel" | "pdf" | "infographic";
export type PlatformPreset = "instagram" | "linkedin" | "x" | "youtube_thumbnail";
export type ExportFileType = "doc" | "pdf" | "png" | "jpg";
export type BrandLifecycle = "draft" | "active" | "archived" | "deleted";
export type ContentLifecycle = "generated" | "edited" | "organized" | "shared" | "archived";
export type AssetLifecycle = "uploaded" | "processing" | "indexed" | "failed" | "deleted";
export type ReviewStatus = "pending" | "approved" | "needs_changes";
export type JobStatus = "queued" | "processing" | "succeeded" | "failed" | "cancelled";
export type KnowledgeChannel = "brand" | "strategy" | "metadata" | "template" | "campaign_history";

export interface StudioPanelSelection {
  format: StudioFormat;
  platform_preset: PlatformPreset;
  file_type: ExportFileType;
  size?: { width: number; height: number };
}

export interface AssetReference {
  asset_id: UUID;
  mime_type: string;
  storage_path: string;
  width?: number;
  height?: number;
  asset_role: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface ActivationRequest {
  token: string;
  password: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  password: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface ProfileUpdateRequest {
  full_name?: string;
  phone_number?: string;
}

export interface TokenPairResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

export interface PasswordResetResponse {
  message: string;
  reset_token?: string;
}

export interface CurrentUserResponse {
  user_id: UUID;
  tenant_id?: UUID;
  email: string;
  full_name: string;
  role_codes: string[];
  assigned_brand_space_ids: UUID[];
  extra: Record<string, unknown>;
}

export interface TenantUsageLimits {
  max_users: number;
  max_brand_spaces: number;
  max_content_generations: number;
  max_image_generations: number;
  max_ocr_pages: number;
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
}

export interface TenantResponse {
  id: UUID;
  name: string;
  slug: string;
  contact_email: string;
  contact_number?: string;
  address?: string;
  is_active?: boolean;
}

export interface TenantSummaryResponse extends TenantResponse {
  total_users: number;
  brand_space_count: number;
  usage_limits?: TenantUsageLimits;
  usage_consumption: Record<string, number>;
}

export interface TenantUserCreateRequest {
  full_name: string;
  email: string;
  phone_number?: string;
  role_code: string;
  brand_space_ids?: UUID[];
}

export interface TenantUserResponse {
  id: UUID;
  tenant_id?: UUID;
  email: string;
  full_name: string;
  phone_number?: string;
  is_active: boolean;
  is_activated: boolean;
  role_codes?: string[];
  brand_space_ids?: UUID[];
}

export interface TenantUsageSummary {
  tenant_id: UUID;
  limits: TenantUsageLimits;
  consumption: Record<string, number>;
}

export interface BrandCreateRequest {
  identity: {
    brand_name: string;
    brand_description: string;
    industry_category?: string;
    sub_industry?: string;
    target_geography: Record<string, string>;
    audience_type?: string;
    key_differentiators: string[];
    logo_asset_id?: UUID;
    website_url?: string;
    social_profiles: Record<string, string>;
  };
  foundations?: Record<string, unknown>;
  voice_tone?: Record<string, unknown>;
}

export interface BrandSectionUpsertRequest {
  section_code: string;
  payload: Record<string, unknown>;
  completion_percent: number;
}

export interface BrandUpdateRequest {
  description?: string;
  overview_snapshot?: Record<string, unknown>;
}

export interface BrandResponse {
  id: UUID;
  tenant_id: UUID;
  name: string;
  slug: string;
  description: string;
  lifecycle_state: BrandLifecycle;
  is_finalized: boolean;
  resolved_brand_context: Record<string, unknown>;
}

export interface BrandOverviewResponse {
  brand: BrandResponse;
  sections: Array<Record<string, unknown>>;
  personas: Array<Record<string, unknown>>;
  guardrails: Array<Record<string, unknown>>;
  objectives: Array<Record<string, unknown>>;
}

export interface KnowledgeUploadRequest {
  name: string;
  filename: string;
  mime_type: string;
  content_base64: string;
  channel: KnowledgeChannel;
  metadata: Record<string, unknown>;
}

export interface KnowledgeAssetResponse {
  id: UUID;
  name: string;
  original_filename: string;
  mime_type: string;
  storage_path: string;
  lifecycle_state: AssetLifecycle;
  channel: KnowledgeChannel;
  page_count: number;
  metadata_json: Record<string, unknown>;
  extracted_text?: string;
  extracted_summary?: string;
  processing_error?: string;
  last_indexed_at?: string;
}

export interface StructuredTextPayload {
  headline: string;
  body: string;
  cta: string;
  hashtags: string[];
  metadata: Record<string, unknown>;
}

export interface BlueprintPayload {
  layout_type: string;
  zones: Array<{
    zone_id: string;
    role: string;
    x: number;
    y: number;
    width: number;
    height: number;
    max_lines?: number;
  }>;
  hierarchy: string[];
  text_blocks: Array<Record<string, unknown>>;
  image_zones: Array<Record<string, unknown>>;
  logo_rules: Record<string, unknown>;
  cta_placement: Record<string, unknown>;
  platform_preset: PlatformPreset;
  export_format: ExportFileType;
  overflow_strategy: Record<string, unknown>;
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

export interface ContentRewriteRequest {
  content_version_id: UUID;
  rewrite_instruction: string;
  studio_panel: StudioPanelSelection;
}

export interface ToneCheckRequest {
  content: string;
  persona_id?: UUID;
}

export interface ToneEvaluationResponse {
  score: number;
  matched_signals: string[];
  deviations: string[];
  rewrite_suggestions: string[];
}

export interface ContentVersionResponse {
  id: UUID;
  session_id: UUID;
  parent_version_id?: UUID;
  lifecycle_state: ContentLifecycle;
  content_type: string;
  title?: string;
  prompt: string;
  studio_panel: StudioPanelSelection;
  generated_payload: StructuredTextPayload;
  blueprint_payload: BlueprintPayload;
  explainability_metadata: Record<string, unknown>;
  tone_score?: number;
  tone_feedback: Record<string, unknown>;
  assets: AssetReference[];
}

export interface ContentExportRequest {
  content_version_id: UUID;
  export_format: ExportFileType;
  studio_panel?: Partial<StudioPanelSelection>;
  blueprint_payload?: BlueprintPayload;
  template_id?: UUID;
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

export interface ChatSessionResponse {
  id: UUID;
  brand_space_id?: UUID;
  title?: string;
  session_kind: "chat";
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
  structured_payload: Record<string, unknown>;
  citations: Array<Record<string, unknown>>;
  created_at: string;
}

export interface ChatSendResponse {
  user_message: ChatMessageResponse;
  assistant_message: ChatMessageResponse;
}

export interface FolderCreateRequest {
  name: string;
  description?: string;
}

export interface FolderRenameRequest {
  name: string;
}

export interface FolderMoveRequest {
  content_version_id: UUID;
  folder_id: UUID;
}

export interface TemplateUploadRequest {
  name: string;
  description?: string;
  kind?: string;
  filename: string;
  mime_type: string;
  content_base64: string;
  tags: string[];
}

export interface TemplateResponse {
  id: UUID;
  name: string;
  description?: string;
  kind: string;
  tags: string[];
  analysis_json: Record<string, unknown>;
}

export interface TemplateMetadataUpsertRequest {
  zone_map: Record<string, unknown>;
  sizing_rules: Record<string, unknown>;
  platform_rules: Record<string, unknown>;
  editable_fields: string[];
  export_rules: Record<string, unknown>;
}

export interface TemplateDetailResponse {
  template: TemplateResponse;
  metadata: Record<string, unknown>;
}

export interface TemplateApplyRequest {
  template_id: UUID;
  prompt: string;
  studio_panel: StudioPanelSelection;
}

export interface TemplateRecommendRequest {
  prompt: string;
  studio_panel: StudioPanelSelection;
  limit?: number;
}

export interface TemplateRecommendationResponse {
  template_id: UUID;
  name: string;
  score: number;
  reasons: string[];
  metadata: Record<string, unknown>;
}

export interface RenderLayoutRequest {
  content_version_id: UUID;
  blueprint_payload?: BlueprintPayload;
  studio_panel: StudioPanelSelection;
  template_id?: UUID;
}

export interface RenderPreviewRequest {
  content_version_id: UUID;
  blueprint_payload?: BlueprintPayload;
  studio_panel: StudioPanelSelection;
  template_id?: UUID;
}

export interface RenderExportRequest {
  content_version_id: UUID;
  studio_panel: StudioPanelSelection;
  export_format: ExportFileType;
  blueprint_payload?: BlueprintPayload;
  template_id?: UUID;
}

export interface RenderResponse {
  content_version_id: UUID;
  preview_asset?: AssetReference;
  export_assets: AssetReference[];
  renderer_metadata: Record<string, unknown>;
}

export interface ShareLinkCreateRequest {
  content_version_id: UUID;
  title?: string;
  allow_external_comments: boolean;
}

export interface ReviewCommentCreateRequest {
  body: string;
  external_author_name?: string;
}

export interface ReviewLinkResponse {
  id: UUID;
  token: string;
  status: ReviewStatus;
  allow_external_comments: boolean;
}

export interface ReviewDetailResponse {
  link: ReviewLinkResponse;
  content?: {
    id: UUID;
    title?: string;
    generated_payload: StructuredTextPayload;
    blueprint_payload: BlueprintPayload;
    assets: AssetReference[];
  };
  comments: Array<{
    id: UUID;
    body: string;
    external_author_name?: string;
    author_user_id?: UUID;
  }>;
}

export interface SocialConnectRequest {
  platform: "linkedin" | "instagram" | "x";
  account_name?: string;
  account_identifier?: string;
  access_token?: string;
  refresh_token?: string;
  scopes: string[];
}

export interface SocialConnectionResponse {
  id: UUID;
  platform: string;
  account_name?: string;
  account_identifier?: string;
  is_connected: boolean;
}

export interface SocialPublishRequest {
  content_version_id: UUID;
  platform: "linkedin" | "instagram" | "x";
  caption_override?: string;
  media_asset_ids: UUID[];
  publish_now: boolean;
}

export interface AnalyticsResponse {
  scope: string;
  tenant_id?: UUID;
  brand_space_id?: UUID;
  metrics: Record<string, unknown>;
}

export interface JobResponse {
  id: UUID;
  brand_space_id?: UUID;
  content_version_id?: UUID;
  knowledge_asset_id?: UUID;
  job_type: string;
  status: JobStatus;
  payload: Record<string, unknown>;
  result_payload: Record<string, unknown>;
  error_message?: string;
  retry_count: number;
  max_retries: number;
  created_at: string;
  updated_at: string;
}
