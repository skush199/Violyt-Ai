import { API } from "@/lib/api/endpoints";
import { request } from "@/lib/api/request";
import type {
  AssetCategoryRoutingResponse,
  AssetProcessingStatusResponse,
  BrandAttachmentListResponse,
  BrandAttachmentResponse,
} from "@/lib/api/contracts";
import { fileToDataUrl, stripFileExtension } from "@/lib/file-utils";
import {
  createPersistedBrandUploadItem,
  emptyBrandFormState,
  type BrandFormState,
  type BrandUploadItem,
} from "@/types/brand-space.types";

export type UploadedBrandAssets = {
  logo: BrandAttachmentResponse | null;
  logos: BrandAttachmentResponse[];
  audienceInsights: BrandAttachmentResponse[];
  referenceCreatives: BrandAttachmentResponse[];
  moodBoards: BrandAttachmentResponse[];
  colorPaletteUploads: BrandAttachmentResponse[];
  fontStyleGuide: BrandAttachmentResponse[];
  positiveWordBankUploads: BrandAttachmentResponse[];
  replaceableWordUploads: BrandAttachmentResponse[];
  negativeWordBankUploads: BrandAttachmentResponse[];
  templateFiles: BrandAttachmentResponse[];
  otherDocuments: BrandAttachmentResponse[];
};

export const emptyUploadedBrandAssets: UploadedBrandAssets = {
  logo: null,
  logos: [],
  audienceInsights: [],
  referenceCreatives: [],
  moodBoards: [],
  colorPaletteUploads: [],
  fontStyleGuide: [],
  positiveWordBankUploads: [],
  replaceableWordUploads: [],
  negativeWordBankUploads: [],
  templateFiles: [],
  otherDocuments: [],
};

export const BRAND_SPACE_CREATE_DRAFT_STORAGE_KEY = "violyt.brand-space-create-draft.v1";

export type UploadProgressUpdate = {
  itemId: string;
  uploadedAssetId?: string;
  storagePath?: string;
  assetUrl?: string | null;
  lifecycleState?: string;
  channel?: string;
  mimeType?: string;
  pageCount?: number;
  processingError?: string | null;
  templateKind?: string;
  analysisJson?: Record<string, unknown>;
  fieldKey?: string;
  assetCategory?: string;
  validationState?: string;
  validationSummaryJson?: Record<string, unknown>;
  structuredDataJson?: Record<string, unknown>;
  normalizedDataJson?: Record<string, unknown>;
  processingStatus?: AssetProcessingStatusResponse;
  routing?: AssetCategoryRoutingResponse;
  isActive?: boolean;
};

export type UploadProgressCallback = (update: UploadProgressUpdate) => void;

type PersistedBrandSpaceDraft = {
  brandId?: string;
  lifecycleState?: string;
  form: BrandFormState;
  updatedAt: string;
};

type AttachmentFieldConfig = {
  key:
    | "logo"
    | "audience_insights"
    | "reference_creatives"
    | "mood_board"
    | "color_palette"
    | "font_guide"
    | "positive_word_bank"
    | "replaceable_word_bank"
    | "negative_word_bank"
    | "brand_knowledge_templates"
    | "brand_knowledge_other";
  getItems: (form: BrandFormState) => BrandUploadItem[];
  desiredCategory?: string;
  defaultTags?: string[];
};

const ATTACHMENT_FIELDS: AttachmentFieldConfig[] = [
  {
    key: "logo",
    getItems: (form) => dedupeUploads(form.core.logos.length ? form.core.logos : form.core.logo ? [form.core.logo] : []),
    desiredCategory: "logo",
    defaultTags: ["Logo"],
  },
  {
    key: "audience_insights",
    getItems: (form) => form.targetAudience.audienceInsights,
    desiredCategory: "audience_insight",
  },
  {
    key: "reference_creatives",
    getItems: (form) => form.visualIdentity.referenceCreatives,
    desiredCategory: "reference_creative",
  },
  {
    key: "mood_board",
    getItems: (form) => form.visualIdentity.moodBoards,
    desiredCategory: "mood_board",
    defaultTags: ["Mood Board"],
  },
  {
    key: "color_palette",
    getItems: (form) => form.visualIdentity.colorPaletteUploads,
    desiredCategory: "color_palette",
    defaultTags: ["Color Palette"],
  },
  {
    key: "font_guide",
    getItems: (form) => form.visualIdentity.fontStyleGuide,
    desiredCategory: "typography_guide",
    defaultTags: ["Font Guide"],
  },
  {
    key: "positive_word_bank",
    getItems: (form) => form.brandRules.positiveWordBankUploads,
    desiredCategory: "positive_word_bank",
    defaultTags: ["Positive Word Bank"],
  },
  {
    key: "replaceable_word_bank",
    getItems: (form) => form.brandRules.replaceableWordUploads,
    desiredCategory: "replaceable_word_bank",
    defaultTags: ["Replaceable Words"],
  },
  {
    key: "negative_word_bank",
    getItems: (form) => form.brandRules.negativeWordBankUploads,
    desiredCategory: "negative_word_bank",
    defaultTags: ["Negative Word Bank"],
  },
  {
    key: "brand_knowledge_templates",
    getItems: (form) => form.brandKnowledge.templateFiles,
    desiredCategory: "template",
    defaultTags: ["Template", "Graphics"],
  },
  {
    key: "brand_knowledge_other",
    getItems: (form) => form.brandKnowledge.otherDocuments,
  },
];

function dedupeUploads(items: BrandUploadItem[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.id)) {
      return false;
    }
    seen.add(item.id);
    return true;
  });
}

function sleep(ms: number) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function normalizeLifecycleState(state?: string) {
  return (state || "").toLowerCase();
}

const TERMINAL_ATTACHMENT_STATES = new Set(["indexed", "complete", "ready", "deleted"]);

function shouldTrackUploadItem(item: BrandUploadItem) {
  if (!item.uploadedAssetId) {
    return false;
  }
  return !TERMINAL_ATTACHMENT_STATES.has(normalizeLifecycleState(item.lifecycleState));
}

function serializeUploadItem(item: BrandUploadItem | null): BrandUploadItem | null {
  if (!item || !item.uploadedAssetId) {
    return null;
  }
  return createPersistedBrandUploadItem({
    ...item,
    previewUrl: item.assetUrl || item.previewUrl,
  });
}

function serializeUploadList(items: BrandUploadItem[]) {
  return items
    .map((item) => serializeUploadItem(item))
    .filter((item): item is BrandUploadItem => Boolean(item));
}

export function serializeBrandSpaceDraftForm(form: BrandFormState): BrandFormState {
  const logoItems = dedupeUploads(form.core.logos.length ? form.core.logos : form.core.logo ? [form.core.logo] : []);
  return {
    ...form,
    core: {
      ...form.core,
      logo: serializeUploadItem(logoItems[0] || form.core.logo),
      logos: serializeUploadList(logoItems),
    },
    targetAudience: {
      ...form.targetAudience,
      audienceInsights: serializeUploadList(form.targetAudience.audienceInsights),
    },
    visualIdentity: {
      ...form.visualIdentity,
      referenceCreatives: serializeUploadList(form.visualIdentity.referenceCreatives),
      moodBoards: serializeUploadList(form.visualIdentity.moodBoards),
      colorPaletteUploads: serializeUploadList(form.visualIdentity.colorPaletteUploads),
      fontStyleGuide: serializeUploadList(form.visualIdentity.fontStyleGuide),
    },
    brandRules: {
      ...form.brandRules,
      positiveWordBankUploads: serializeUploadList(form.brandRules.positiveWordBankUploads),
      replaceableWordUploads: serializeUploadList(form.brandRules.replaceableWordUploads),
      negativeWordBankUploads: serializeUploadList(form.brandRules.negativeWordBankUploads),
    },
    brandKnowledge: {
      ...form.brandKnowledge,
      templateFiles: serializeUploadList(form.brandKnowledge.templateFiles),
      otherDocuments: serializeUploadList(form.brandKnowledge.otherDocuments),
    },
  };
}

function hasDraftContent(form: BrandFormState) {
  const serialized = serializeBrandSpaceDraftForm(form);
  return JSON.stringify(serialized) !== JSON.stringify(serializeBrandSpaceDraftForm(emptyBrandFormState));
}

export function saveBrandSpaceDraft(value: {
  brandId?: string | null;
  lifecycleState?: string | null;
  form: BrandFormState;
}) {
  if (typeof window === "undefined") {
    return;
  }

  const payload: PersistedBrandSpaceDraft = {
    brandId: value.brandId || undefined,
    lifecycleState: value.lifecycleState || undefined,
    form: serializeBrandSpaceDraftForm(value.form),
    updatedAt: new Date().toISOString(),
  };

  if (!payload.brandId && !hasDraftContent(payload.form)) {
    window.localStorage.removeItem(BRAND_SPACE_CREATE_DRAFT_STORAGE_KEY);
    return;
  }

  window.localStorage.setItem(BRAND_SPACE_CREATE_DRAFT_STORAGE_KEY, JSON.stringify(payload));
}

export function loadBrandSpaceDraft(): PersistedBrandSpaceDraft | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(BRAND_SPACE_CREATE_DRAFT_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as PersistedBrandSpaceDraft;
    const restoredForm: BrandFormState = {
      ...structuredClone(emptyBrandFormState),
      ...parsed.form,
      core: {
        ...structuredClone(emptyBrandFormState.core),
        ...parsed.form.core,
      },
    };
    restoredForm.core.logos = dedupeUploads(
      restoredForm.core.logos.length
        ? restoredForm.core.logos
        : restoredForm.core.logo
          ? [restoredForm.core.logo]
          : [],
    );
    restoredForm.core.logo = restoredForm.core.logos[0] || restoredForm.core.logo || null;
    if (isUnknownFontName(restoredForm.visualIdentity.typography)) {
      restoredForm.visualIdentity.typography = "";
    }
    return {
      brandId: parsed.brandId,
      lifecycleState: parsed.lifecycleState,
      form: restoredForm,
      updatedAt: parsed.updatedAt,
    };
  } catch {
    window.localStorage.removeItem(BRAND_SPACE_CREATE_DRAFT_STORAGE_KEY);
    return null;
  }
}

export function clearBrandSpaceDraft() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(BRAND_SPACE_CREATE_DRAFT_STORAGE_KEY);
}

function notifyUploadProgress(onProgress: UploadProgressCallback | undefined, update: UploadProgressUpdate) {
  if (onProgress) {
    onProgress(update);
  }
}

function attachmentToUploadItem(asset: BrandAttachmentResponse): BrandUploadItem {
  return createPersistedBrandUploadItem({
    id: `existing-${asset.id}`,
    name: asset.original_filename || asset.name,
    tags: Array.isArray(asset.metadata_json?.tags) ? asset.metadata_json.tags.map((tag) => String(tag)) : [],
    previewUrl: asset.asset_url || undefined,
    uploadedAssetId: asset.id,
    storagePath: asset.storage_path,
    assetUrl: asset.asset_url || undefined,
    lifecycleState: asset.processing_status?.lifecycle_state || asset.lifecycle_state,
    channel: asset.channel,
    mimeType: asset.mime_type,
    pageCount: asset.page_count,
    processingError: asset.processing_error,
    kind: asset.field_key === "brand_knowledge_templates" ? "template" : "knowledge",
    templateKind:
      typeof asset.normalized_data_json?.template_kind === "string"
        ? String(asset.normalized_data_json.template_kind)
        : asset.asset_category === "template"
          ? "hybrid"
          : undefined,
    analysisJson:
      asset.field_key === "brand_knowledge_templates"
        ? ({
            status: asset.processing_status?.lifecycle_state || asset.lifecycle_state,
            ...asset.structured_data_json,
          } as Record<string, unknown>)
        : undefined,
    fieldKey: asset.field_key || undefined,
    assetCategory: asset.asset_category || undefined,
    validationState: asset.validation_result?.validation_state || asset.validation_state,
    validationSummaryJson: asset.validation_summary_json,
    structuredDataJson: asset.structured_data_json,
    normalizedDataJson: asset.normalized_data_json,
    processingStatus: asset.processing_status || undefined,
    routing: asset.routing || undefined,
    isActive: asset.is_active,
  });
}

function mergeAttachmentItems(
  currentItems: BrandUploadItem[],
  assets: BrandAttachmentResponse[],
) {
  const persistedItems = assets.map(attachmentToUploadItem);
  const unsavedItems = currentItems.filter((item) => {
    if (normalizeLifecycleState(item.lifecycleState) === "deleted") {
      return false;
    }
    if (item.uploadedAssetId) {
      return false;
    }
    return Boolean(item.file);
  });
  return [...persistedItems, ...unsavedItems];
}

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function isUnknownFontName(value: string) {
  return ["unknown", "unknown font", "unknown visual font", "font"].includes(value.trim().toLowerCase());
}

function extractedFontName(font: Record<string, unknown>) {
  const value = String(font.name || font.full_name || font.family || "").trim();
  return value && !isUnknownFontName(value) ? value : "";
}

function typographyTextFromAttachments(assets: BrandAttachmentResponse[]) {
  for (const asset of assets) {
    const structuredData = toRecord(asset.structured_data_json);
    const normalizedData = toRecord(asset.normalized_data_json);
    const directName = String(
      structuredData.detected_font_name || normalizedData.detected_font_name || "",
    ).trim();
    if (directName && !isUnknownFontName(directName)) {
      return directName;
    }

    const fontFamilies = Array.isArray(structuredData.font_families)
      ? structuredData.font_families
      : Array.isArray(normalizedData.font_families)
        ? normalizedData.font_families
        : [];
    const detectedName = fontFamilies.map(toRecord).map(extractedFontName).find(Boolean);
    if (detectedName) {
      return detectedName;
    }
  }
  return "";
}

function attachmentToProgressUpdate(itemId: string, asset: BrandAttachmentResponse): UploadProgressUpdate {
  return {
    itemId,
    uploadedAssetId: asset.id,
    storagePath: asset.storage_path,
    assetUrl: asset.asset_url,
    lifecycleState: asset.processing_status?.lifecycle_state || asset.lifecycle_state,
    channel: asset.channel,
    mimeType: asset.mime_type,
    pageCount: asset.page_count,
    processingError: asset.processing_error,
    templateKind:
      typeof asset.normalized_data_json?.template_kind === "string"
        ? String(asset.normalized_data_json.template_kind)
        : asset.asset_category === "template"
          ? "hybrid"
          : undefined,
    analysisJson:
      asset.field_key === "brand_knowledge_templates"
        ? ({
            status: asset.processing_status?.lifecycle_state || asset.lifecycle_state,
            ...asset.structured_data_json,
          } as Record<string, unknown>)
        : undefined,
    fieldKey: asset.field_key || undefined,
    assetCategory: asset.asset_category || undefined,
    validationState: asset.validation_result?.validation_state || asset.validation_state,
    validationSummaryJson: asset.validation_summary_json,
    structuredDataJson: asset.structured_data_json,
    normalizedDataJson: asset.normalized_data_json,
    processingStatus: asset.processing_status || undefined,
    routing: asset.routing || undefined,
    isActive: asset.is_active,
  };
}

function buildExistingAttachment(
  item: BrandUploadItem,
  fieldKey: AttachmentFieldConfig["key"],
): BrandAttachmentResponse | null {
  if (!item.uploadedAssetId) {
    return null;
  }
  return {
    id: item.uploadedAssetId,
    tenant_id: "",
    brand_space_id: undefined,
    name: stripFileExtension(item.name),
    original_filename: item.name,
    mime_type: item.mimeType || "application/octet-stream",
    storage_path: item.storagePath || "",
    asset_url: item.assetUrl,
    lifecycle_state: item.lifecycleState || "indexed",
    channel: item.channel || "brand",
    field_key: fieldKey,
    asset_category: item.assetCategory || null,
    classification_confidence: undefined,
    page_count: item.pageCount || 0,
    is_active: item.isActive ?? true,
    metadata_json: { tags: item.tags || [] },
    structured_data_json: item.structuredDataJson || {},
    normalized_data_json: item.normalizedDataJson || {},
    processing_error: item.processingError,
    validation_state: item.validationState || "pending",
    validation_summary_json: item.validationSummaryJson || {},
    processing_status: item.processingStatus
      ? {
          field_key: fieldKey,
          lifecycle_state: String(item.processingStatus.lifecycle_state || item.lifecycleState || "indexed"),
          processor_name: typeof item.processingStatus.processor_name === "string" ? item.processingStatus.processor_name : null,
          progress_current: Number(item.processingStatus.progress_current || 0),
          progress_total: Number(item.processingStatus.progress_total || 0),
          status_message: typeof item.processingStatus.status_message === "string" ? item.processingStatus.status_message : null,
          raw_status_json: item.processingStatus.raw_status_json || {},
        }
      : null,
    validation_result: item.validationState
      ? {
          field_key: fieldKey,
          validation_state: item.validationState,
          warnings: Array.isArray(item.validationSummaryJson?.warnings)
            ? item.validationSummaryJson.warnings.map((warning) => String(warning))
            : [],
          exclusion_reason:
            typeof item.validationSummaryJson?.exclusion_reason === "string"
              ? item.validationSummaryJson.exclusion_reason
              : null,
          resolved_payload:
            item.validationSummaryJson && typeof item.validationSummaryJson === "object"
              ? item.validationSummaryJson
              : {},
          confidence:
            typeof item.validationSummaryJson?.confidence === "number"
              ? item.validationSummaryJson.confidence
              : null,
        }
      : null,
    routing: item.routing
      ? {
          requested_field_key: fieldKey,
          requested_category:
            typeof item.routing.requested_category === "string" ? item.routing.requested_category : null,
          routed_category:
            typeof item.routing.routed_category === "string"
              ? item.routing.routed_category
              : item.assetCategory || "brand",
          classifier: typeof item.routing.classifier === "string" ? item.routing.classifier : null,
          confidence: typeof item.routing.confidence === "number" ? item.routing.confidence : null,
          routing_reason: typeof item.routing.routing_reason === "string" ? item.routing.routing_reason : null,
          decision_json: item.routing.decision_json || {},
        }
      : null,
    reusable_assets: [],
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
  };
}

async function uploadAttachmentItem(
  brandId: string,
  field: AttachmentFieldConfig,
  item: BrandUploadItem,
  onProgress?: UploadProgressCallback,
) {
  const existing = buildExistingAttachment(item, field.key);
  if (existing) {
    notifyUploadProgress(onProgress, attachmentToProgressUpdate(item.id, existing));
    return existing;
  }
  if (!item.file) {
    return existing;
  }

  notifyUploadProgress(onProgress, {
    itemId: item.id,
    lifecycleState: "uploading",
    fieldKey: field.key,
    mimeType: item.mimeType,
  });

  const contentBase64 = await fileToDataUrl(item.file);
  const uploaded = await request(API.BRANDS.UPLOAD_ATTACHMENT, {
    pathParams: { brandId, fieldKey: field.key },
    data: {
      name: stripFileExtension(item.name),
      filename: item.file.name,
      mime_type: item.file.type || "application/octet-stream",
      content_base64: contentBase64,
      desired_category: field.desiredCategory,
      skip_processing: false,
      metadata: {
        tags: field.defaultTags || item.tags || [],
        uploaded_from: "brand_space_editor",
      },
    },
  });

  notifyUploadProgress(onProgress, attachmentToProgressUpdate(item.id, uploaded));
  return uploaded;
}

async function uploadAttachmentsForField(
  brandId: string,
  field: AttachmentFieldConfig,
  items: BrandUploadItem[],
  onProgress?: UploadProgressCallback,
) {
  const uploaded = await Promise.all(
    items.map(async (item) => {
      const asset = await uploadAttachmentItem(brandId, field, item, onProgress);
      return asset ? { itemId: item.id, asset } : null;
    }),
  );
  return uploaded.filter((item): item is { itemId: string; asset: BrandAttachmentResponse } => Boolean(item));
}

function mapUploadedAssets(
  uploads: Record<AttachmentFieldConfig["key"], BrandAttachmentResponse[]>,
): UploadedBrandAssets {
  const logos = uploads.logo || [];
  return {
    ...emptyUploadedBrandAssets,
    logo: logos[0] || null,
    logos,
    audienceInsights: uploads.audience_insights || [],
    referenceCreatives: uploads.reference_creatives || [],
    moodBoards: uploads.mood_board || [],
    colorPaletteUploads: uploads.color_palette || [],
    fontStyleGuide: uploads.font_guide || [],
    positiveWordBankUploads: uploads.positive_word_bank || [],
    replaceableWordUploads: uploads.replaceable_word_bank || [],
    negativeWordBankUploads: uploads.negative_word_bank || [],
    templateFiles: uploads.brand_knowledge_templates || [],
    otherDocuments: uploads.brand_knowledge_other || [],
  };
}

export async function uploadBrandSpaceAssets(
  brandId: string,
  form: BrandFormState,
  onProgress?: UploadProgressCallback,
): Promise<UploadedBrandAssets> {
  const entries = await Promise.all(
    ATTACHMENT_FIELDS.map(async (field) => {
      const uploads = await uploadAttachmentsForField(brandId, field, field.getItems(form), onProgress);
      return [field.key, uploads.map((entry) => entry.asset)] as const;
    }),
  );

  return mapUploadedAssets(
    Object.fromEntries(entries) as Record<AttachmentFieldConfig["key"], BrandAttachmentResponse[]>,
  );
}

export async function uploadFontStyleGuideAsset(
  brandId: string,
  item: BrandUploadItem,
  onProgress?: UploadProgressCallback,
) {
  const fontGuideField = ATTACHMENT_FIELDS.find((field) => field.key === "font_guide");
  if (!fontGuideField) {
    return null;
  }
  return uploadAttachmentItem(brandId, fontGuideField, item, onProgress);
}

function collectTrackedItems(form: BrandFormState) {
  return ATTACHMENT_FIELDS.flatMap((field) => field.getItems(form)).filter(shouldTrackUploadItem);
}

export async function syncBrandSpaceAssetStatuses(
  brandId: string,
  form: BrandFormState,
  onProgress?: UploadProgressCallback,
) {
  const trackedItems = collectTrackedItems(form);
  if (!trackedItems.length) {
    return;
  }

  const attachmentGroups = await request(API.BRANDS.ATTACHMENTS, {
    pathParams: brandId,
  });
  const assetsById = new Map<string, BrandAttachmentResponse>();
  attachmentGroups.forEach((group) => {
    group.assets.forEach((asset) => {
      assetsById.set(asset.id, asset);
    });
  });

  trackedItems.forEach((item) => {
    if (!item.uploadedAssetId) {
      return;
    }
    const asset = assetsById.get(item.uploadedAssetId);
    if (!asset) {
      return;
    }
    notifyUploadProgress(onProgress, attachmentToProgressUpdate(item.id, asset));
  });
}

export async function listBrandSpaceAttachments(brandId: string) {
  return request(API.BRANDS.ATTACHMENTS, {
    pathParams: brandId,
  });
}

export function mergeBrandAttachmentsIntoForm(
  form: BrandFormState,
  attachmentGroups: BrandAttachmentListResponse[],
): BrandFormState {
  const assetsByField = new Map<string, BrandAttachmentResponse[]>();
  attachmentGroups.forEach((group) => {
    assetsByField.set(group.field_key, group.assets || []);
  });

  const currentLogoItems = dedupeUploads(form.core.logos.length ? form.core.logos : form.core.logo ? [form.core.logo] : []);
  const logoItems = mergeAttachmentItems(currentLogoItems, assetsByField.get("logo") || []);
  const fontGuideAssets = assetsByField.get("font_guide") || [];
  const detectedTypography = typographyTextFromAttachments(fontGuideAssets);

  return {
    ...form,
    core: {
      ...form.core,
      logo: logoItems[0] || null,
      logos: logoItems,
    },
    targetAudience: {
      ...form.targetAudience,
      audienceInsights: mergeAttachmentItems(
        form.targetAudience.audienceInsights,
        assetsByField.get("audience_insights") || [],
      ),
    },
    visualIdentity: {
      ...form.visualIdentity,
      typography:
        !form.visualIdentity.typography || isUnknownFontName(form.visualIdentity.typography)
          ? detectedTypography || form.visualIdentity.typography
          : form.visualIdentity.typography,
      referenceCreatives: mergeAttachmentItems(
        form.visualIdentity.referenceCreatives,
        assetsByField.get("reference_creatives") || [],
      ),
      moodBoards: mergeAttachmentItems(form.visualIdentity.moodBoards, assetsByField.get("mood_board") || []),
      colorPaletteUploads: mergeAttachmentItems(
        form.visualIdentity.colorPaletteUploads,
        assetsByField.get("color_palette") || [],
      ),
      fontStyleGuide: mergeAttachmentItems(form.visualIdentity.fontStyleGuide, fontGuideAssets),
    },
    brandRules: {
      ...form.brandRules,
      positiveWordBankUploads: mergeAttachmentItems(
        form.brandRules.positiveWordBankUploads,
        assetsByField.get("positive_word_bank") || [],
      ),
      replaceableWordUploads: mergeAttachmentItems(
        form.brandRules.replaceableWordUploads,
        assetsByField.get("replaceable_word_bank") || [],
      ),
      negativeWordBankUploads: mergeAttachmentItems(
        form.brandRules.negativeWordBankUploads,
        assetsByField.get("negative_word_bank") || [],
      ),
    },
    brandKnowledge: {
      ...form.brandKnowledge,
      templateFiles: mergeAttachmentItems(
        form.brandKnowledge.templateFiles,
        assetsByField.get("brand_knowledge_templates") || [],
      ),
      otherDocuments: mergeAttachmentItems(
        form.brandKnowledge.otherDocuments,
        assetsByField.get("brand_knowledge_other") || [],
      ),
    },
  };
}

export async function waitForBrandAttachmentProcessing(
  brandId: string,
  assetId: string,
  onProgress?: UploadProgressCallback,
  itemId?: string,
  timeoutMs = 180000,
) {
  const deadline = Date.now() + timeoutMs;
  let latest = await request(API.BRANDS.ATTACHMENT_DETAIL, {
    pathParams: { brandId, assetId },
  });

  while (Date.now() < deadline) {
    const lifecycleState = normalizeLifecycleState(
      latest.processing_status?.lifecycle_state || latest.lifecycle_state,
    );
    if (["indexed", "complete", "ready", "failed", "deleted"].includes(lifecycleState)) {
      if (itemId) {
        notifyUploadProgress(onProgress, attachmentToProgressUpdate(itemId, latest));
      }
      return latest;
    }
    if (itemId) {
      notifyUploadProgress(onProgress, attachmentToProgressUpdate(itemId, latest));
    }
    await sleep(1500);
    latest = await request(API.BRANDS.ATTACHMENT_DETAIL, {
      pathParams: { brandId, assetId },
    });
  }

  if (itemId) {
    notifyUploadProgress(onProgress, attachmentToProgressUpdate(itemId, latest));
  }
  return latest;
}