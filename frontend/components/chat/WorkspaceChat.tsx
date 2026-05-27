"use client";

import Link from "next/link";
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import {
  BadgePlus,
  Loader2,
  Megaphone,
  Paperclip,
  PencilLine,
  Plus,
  RefreshCw,
  SendHorizontal,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from "@/components/ui/carousel";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PageHeading, SurfaceCard, UsageRing } from "@/components/common/DesignPrimitives";
import type {
  AssetReference,
  ChatAssistantStructuredPayload,
  GenerationDecision,
  KnowledgeAssetResponse,
  StudioPanelSelection,
  TemplateRecommendationResponse,
} from "@/lib/api/contracts";
import { buildBrandEditHref, buildBrandSharingHref, resolveBrandByRouteKey } from "@/lib/brand-routing";
import { useBrands } from "@/hooks/useBrands";
import {
  useChatMessages,
  useChatSessions,
  useCreateChatSession,
  useKnowledgeAssets,
  useSendChatMessage,
  useTemplateRecommendations,
  useToneCheck,
  useUploadKnowledgeAsset,
} from "@/hooks/useContentWorkspace";
import { fileToDataUrl, stripFileExtension } from "@/lib/file-utils";
import {
  coerceGenerationDecision,
  formatGenerationMode,
  getGenerationDecisionConfidence,
  getGenerationDecisionReasons,
  getGenerationDecisionTemplate,
  getGenerationDecisionTemplatePreview,
  getRecommendationConfidence,
  getRecommendationDisplayName,
  getRecommendationSelectionReason,
} from "@/lib/generation-decision";

type WorkspaceChatProps = { brandKey: string };
type ActionMode = "none" | "idea" | "social" | "repurpose" | "alignment";
type Platform = "instagram" | "linkedin" | "x" | "youtube_thumbnail";
type FormatMode = "static" | "carousel" | "infographic" | "video";
type FileType = "doc" | "pdf" | "jpg" | "png";

const actionOptions = [
  { id: "idea", label: "Generate Campaign Idea", icon: Sparkles },
  { id: "social", label: "Create Social Media Post", icon: Megaphone },
  { id: "repurpose", label: "Repurpose Content", icon: RefreshCw },
  { id: "alignment", label: "Check Brand Alignment", icon: Wand2 },
] as const;

const platformOptions: Platform[] = ["instagram", "linkedin", "x", "youtube_thumbnail"];
const platformLabels: Record<Platform, string> = {
  instagram: "Instagram",
  linkedin: "LinkedIn",
  x: "X",
  youtube_thumbnail: "YouTube",
};
const fileTypeOptions: FileType[] = ["doc", "pdf", "jpg", "png"];
const campaignGoalOptions = ["Brand awareness", "Engagement", "Lead generation", "Investor education", "Thought leadership"];
const sizeOptionsByPlatform: Record<Platform, Array<{ label: string; width: number; height: number }>> = {
  instagram: [{ label: "1:1", width: 1080, height: 1080 }, { label: "9:16", width: 1080, height: 1920 }],
  linkedin: [{ label: "4:5", width: 1080, height: 1350 }, { label: "16:9", width: 1200, height: 675 }],
  x: [{ label: "1:1", width: 1080, height: 1080 }, { label: "16:9", width: 1600, height: 900 }],
  youtube_thumbnail: [{ label: "16:9", width: 1280, height: 720 }],
};

const MAX_COMPOSER_HEIGHT = 220;
const GENERATION_PROGRESS_MESSAGES = [
  {
    eyebrow: "Now",
    title: "Reading your brief",
    body: "Lining it up with the brand voice, platform, and format you picked.",
  },
  {
    eyebrow: "Did you know?",
    title: "Violyt can reuse brand-safe assets",
    body: "Uploaded logos, references, and validated brand rules all help keep outputs more consistent.",
  },
  {
    eyebrow: "Now",
    title: "Shaping the message",
    body: "Balancing the hook, body copy, CTA, and visual direction for this creative.",
  },
  {
    eyebrow: "Did you know?",
    title: "One brief can drive multiple formats",
    body: "The same intent can be adapted into static posts, carousels, infographics, and more.",
  },
  {
    eyebrow: "Now",
    title: "Building the visual direction",
    body: "Bringing together layout, imagery, brand color balance, and the strongest available logo path.",
  },
  {
    eyebrow: "Did you know?",
    title: "Brand knowledge keeps getting smarter",
    body: "Templates, docs, and uploaded references help future generations stay closer to your brand.",
  },
  {
    eyebrow: "Now",
    title: "Polishing the final creative",
    body: "Checking the finishing details so we can show the cleanest version possible.",
  },
] as const;

function formatGenerationStatusLine(entry: (typeof GENERATION_PROGRESS_MESSAGES)[number]) {
  if (entry.eyebrow.toLowerCase().includes("did you know")) {
    return `${entry.eyebrow} ${entry.body}`;
  }
  return entry.title;
}

function useDebouncedValue<T>(value: T, delayMs: number) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedValue(value), delayMs);
    return () => window.clearTimeout(timeout);
  }, [delayMs, value]);

  return debouncedValue;
}

function resizeComposer(node: HTMLTextAreaElement | null) {
  if (!node) {
    return;
  }
  node.style.height = "0px";
  const nextHeight = Math.min(node.scrollHeight, MAX_COMPOSER_HEIGHT);
  node.style.height = `${Math.max(nextHeight, 44)}px`;
  node.style.overflowY = node.scrollHeight > MAX_COMPOSER_HEIGHT ? "auto" : "hidden";
}

function dedupeImageAssets(assets: AssetReference[]) {
  const seen = new Set<string>();
  return assets.filter((asset) => {
    const key = asset.asset_url || asset.storage_path || asset.asset_id;
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function resolveGeneratedImageAssets(payload: ChatAssistantStructuredPayload | Record<string, unknown> | undefined) {
  if (!payload || Array.isArray(payload)) {
    return [];
  }
  const typedPayload = payload as ChatAssistantStructuredPayload;
  const exportImages = (typedPayload.export_assets || []).filter(
    (asset) => asset.mime_type.startsWith("image/") && Boolean(asset.asset_url),
  );
  if (exportImages.length) {
    return dedupeImageAssets(exportImages);
  }
  if (typedPayload.preview_asset?.asset_url && typedPayload.preview_asset.mime_type.startsWith("image/")) {
    return [typedPayload.preview_asset];
  }
  return dedupeImageAssets(
    (typedPayload.assets || []).filter((asset) =>
      asset.mime_type.startsWith("image/") &&
      Boolean(asset.asset_url) &&
      ["render_export", "render_preview", "ai_image"].includes(asset.asset_role),
    ),
  );
}

function resolveGenerationDecision(payload: ChatAssistantStructuredPayload | Record<string, unknown> | undefined) {
  if (!payload || Array.isArray(payload)) {
    return null;
  }
  const typedPayload = payload as ChatAssistantStructuredPayload;
  const rendererMetadata =
    typedPayload.renderer_metadata && typeof typedPayload.renderer_metadata === "object"
      ? (typedPayload.renderer_metadata as Record<string, unknown>)
      : null;
  return coerceGenerationDecision(typedPayload.generation_decision || rendererMetadata?.layout_decision);
}

function assetPreviewLabel(asset: KnowledgeAssetResponse) {
  return asset.name || asset.original_filename;
}

function getTemplatePreviewUrl(recommendation: TemplateRecommendationResponse) {
  const metadata =
    recommendation.metadata && typeof recommendation.metadata === "object"
      ? (recommendation.metadata as Record<string, unknown>)
      : {};
  const candidates = [
    recommendation.asset_url,
    metadata.asset_url,
    metadata.preview_asset_url,
    metadata.template_preview_asset_url,
    metadata.preview_url,
    metadata.thumbnail_url,
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate;
    }
  }
  return undefined;
}

function ActionButton({
  selected,
  onClick,
  icon: Icon,
  label,
}: {
  selected: boolean;
  onClick: () => void;
  icon: typeof Sparkles;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm shadow-[0_16px_36px_-30px_rgba(15,23,42,0.35)] ${
        selected ? "border-primary/20 bg-primary/8 text-primary" : "border-slate-200 bg-white text-slate-700"
      }`}
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </button>
  );
}

function TemplateRecommendationRail({
  recommendations,
  isLoading,
  selectedTemplateId,
  onSelect,
}: {
  recommendations: TemplateRecommendationResponse[];
  isLoading: boolean;
  selectedTemplateId: string;
  onSelect: (templateId: string) => void;
}) {
  const [previewTemplate, setPreviewTemplate] = useState<TemplateRecommendationResponse | null>(null);
  const [brokenPreviewIds, setBrokenPreviewIds] = useState<Record<string, boolean>>({});

  if (!recommendations.length && !isLoading) {
    return null;
  }

  return (
    <div className="space-y-2 rounded-[24px] border border-[#E8EBF4] bg-white/90 px-3 py-3 shadow-[0_16px_36px_-30px_rgba(15,23,42,0.35)]">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-slate-800">Template Direction</p>
        {isLoading ? (
          <span className="inline-flex items-center gap-2 text-xs font-medium text-primary">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Matching templates
          </span>
        ) : null}
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        <button
          type="button"
          onClick={() => onSelect("")}
          className={`flex min-w-[164px] items-center gap-3 rounded-[18px] border px-3 py-2.5 text-left transition ${
            !selectedTemplateId
              ? "border-primary bg-primary/8 text-primary shadow-[0_16px_36px_-30px_rgba(60,47,143,0.55)]"
              : "border-slate-200 bg-white text-slate-700 hover:border-primary/30"
          }`}
        >
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[14px] border border-dashed border-current/25 bg-white/80">
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em]">Auto</span>
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <p className="line-clamp-2 text-[12px] font-semibold leading-4 text-current">Let Violyt choose</p>
            <p className="text-[10px] font-medium text-slate-500">
              {!selectedTemplateId ? "Currently active" : "Switch to auto"}
            </p>
          </div>
        </button>
        {recommendations.map((recommendation) => {
          const selected = recommendation.template_id === selectedTemplateId;
          const previewUrl = brokenPreviewIds[recommendation.template_id]
            ? undefined
            : getTemplatePreviewUrl(recommendation);
          const displayName = getRecommendationDisplayName(recommendation);
          const selectionReason = getRecommendationSelectionReason(recommendation);
          const formatFamilyLabel =
            typeof recommendation.format_family === "string" && recommendation.format_family.trim()
              ? recommendation.format_family.charAt(0).toUpperCase() + recommendation.format_family.slice(1)
              : null;
          return (
            <div
              key={recommendation.template_id}
              className={`flex min-w-[172px] items-center gap-2 rounded-[18px] border px-2.5 py-2.5 ${
                selected
                  ? "border-primary bg-primary/8 shadow-[0_16px_36px_-30px_rgba(60,47,143,0.55)]"
                  : "border-slate-200 bg-white"
              }`}
            >
              <button
                type="button"
                onClick={() => previewUrl && setPreviewTemplate(recommendation)}
                disabled={!previewUrl}
                className={`flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-[14px] border ${
                  previewUrl
                    ? "border-slate-200 bg-slate-50 hover:border-primary/30"
                    : "border-dashed border-slate-200 bg-slate-50 text-slate-400"
                }`}
              >
                {previewUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={previewUrl}
                    alt={recommendation.name}
                    loading="lazy"
                    onError={() =>
                      setBrokenPreviewIds((current) => ({
                        ...current,
                        [recommendation.template_id]: true,
                      }))}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <span className="px-1 text-center text-[9px] font-medium">No preview</span>
                )}
              </button>
              <div className="min-w-0 flex-1 space-y-1">
                <p className="line-clamp-2 text-[11px] font-semibold leading-4 text-slate-800">{displayName}</p>
                {/*
                  {formatRecommendationMatchType(recommendation.match_type)} · {getRecommendationConfidence(recommendation)}
                */}
                <div className="flex flex-wrap items-center gap-1">
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${
                      recommendation.is_primary_adaptation
                        ? "bg-primary/10 text-primary"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {selectionReason}
                  </span>
                  {formatFamilyLabel ? (
                    <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-semibold text-slate-600">
                      {formatFamilyLabel}
                    </span>
                  ) : null}
                </div>
                <p className="text-[10px] font-medium text-slate-500">{getRecommendationConfidence(recommendation)}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => onSelect(selected ? "" : recommendation.template_id)}
                  className={`rounded-full border px-2.5 py-1.5 text-[11px] font-medium ${
                    selected
                      ? "border-primary bg-primary text-white"
                      : "border-slate-200 bg-white text-slate-700"
                  }`}
                >
                  {selected ? "Pinned" : "Use"}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <Dialog open={Boolean(previewTemplate)} onOpenChange={(open) => !open && setPreviewTemplate(null)}>
        <DialogContent className="max-w-3xl border-none bg-white p-0">
          <DialogHeader className="px-6 pb-0 pt-6">
            <DialogTitle>{previewTemplate?.name || "Template preview"}</DialogTitle>
          </DialogHeader>
          <div className="px-6 pb-6 pt-4">
            {previewTemplate && getTemplatePreviewUrl(previewTemplate) ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={getTemplatePreviewUrl(previewTemplate)}
                alt={previewTemplate.name}
                className="max-h-[72vh] w-full rounded-[20px] object-contain"
              />
            ) : (
              <div className="flex min-h-[320px] items-center justify-center rounded-[20px] border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
                Preview unavailable
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function GenerationPreviewPlaceholder({
  width,
  height,
}: {
  width?: number;
  height?: number;
}) {
  const safeWidth = Math.max(width || 1080, 1);
  const safeHeight = Math.max(height || 1080, 1);
  const aspectRatio = `${safeWidth} / ${safeHeight}`;
  return (
    <div className="overflow-hidden rounded-[24px] border border-[#E8EBF4] bg-white">
      <div
        className="relative w-full overflow-hidden"
        style={{ aspectRatio }}
      >
        <div className="absolute inset-0 bg-[linear-gradient(135deg,#F8FAFF_0%,#FFFFFF_48%,#F4F7FD_100%)]" />
        <div className="absolute -left-10 top-8 h-40 w-40 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute -right-8 bottom-8 h-44 w-44 rounded-full bg-emerald-400/15 blur-3xl" />
        <div className="absolute inset-0 animate-pulse">
          <div className="absolute left-[8%] top-[10%] h-[14%] w-[52%] rounded-[26px] bg-white/80 shadow-[0_20px_50px_-34px_rgba(15,23,42,0.3)]" />
          <div className="absolute left-[8%] top-[28%] h-[10%] w-[38%] rounded-[22px] bg-slate-100/90" />
          <div className="absolute right-[8%] top-[18%] h-[36%] w-[32%] rounded-[28px] bg-primary/10" />
          <div className="absolute left-[8%] bottom-[18%] h-[11%] w-[58%] rounded-[24px] bg-emerald-400/15" />
          <div className="absolute right-[8%] bottom-[14%] h-[16%] w-[22%] rounded-[28px] bg-white/80 shadow-[0_20px_50px_-34px_rgba(15,23,42,0.3)]" />
        </div>
        <div className="absolute inset-y-0 left-0 w-full animate-pulse bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.38),transparent)]" />
      </div>
    </div>
  );
}

function GenerationDecisionCard({ decision }: { decision: GenerationDecision | null }) {
  const templateLabel = getGenerationDecisionTemplate(decision);
  const templatePreview = getGenerationDecisionTemplatePreview(decision);
  const templateConfidence = getGenerationDecisionConfidence(decision);
  const reasons = getGenerationDecisionReasons(decision);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  if (!decision?.mode && !templateLabel && !reasons.length) {
    return null;
  }

  return (
    <div className="mt-3 rounded-[18px] border border-slate-200 bg-slate-50/90 px-4 py-3 text-sm text-slate-700">
      <div className="flex flex-wrap items-start gap-3">
        <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">
          {formatGenerationMode(decision?.mode)}
        </span>
        {templateLabel ? (
          <div className="flex items-start gap-3">
            {templatePreview ? (
              <button
                type="button"
                onClick={() => setIsPreviewOpen(true)}
                className="overflow-hidden rounded-[12px] border border-slate-200 bg-white"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={templatePreview} alt={templateLabel} className="h-8 w-8 object-cover" />
              </button>
            ) : null}
            <div className="min-w-0">
              <p className="line-clamp-2 text-xs font-medium text-slate-600">{templateLabel}</p>
              {templateConfidence ? <p className="mt-1 text-[11px] text-slate-500">{templateConfidence}</p> : null}
            </div>
          </div>
        ) : null}
      </div>
      {reasons.length ? <p className="mt-2 leading-6 text-slate-600">{reasons[0]}</p> : null}
      <Dialog open={isPreviewOpen} onOpenChange={setIsPreviewOpen}>
        <DialogContent className="max-w-3xl border-none bg-white p-0">
          <DialogHeader className="px-6 pb-0 pt-6">
            <DialogTitle>{templateLabel || "Template preview"}</DialogTitle>
          </DialogHeader>
          <div className="px-6 pb-6 pt-4">
            {templatePreview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={templatePreview} alt={templateLabel || "Template preview"} className="max-h-[72vh] w-full rounded-[20px] object-contain" />
            ) : (
              <div className="flex min-h-[320px] items-center justify-center rounded-[20px] border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
                Preview unavailable
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function StudioPanel({
  platform,
  setPlatform,
  format,
  setFormat,
  fileType,
  setFileType,
  sizeLabel,
  setSizeLabel,
  campaignGoal,
  setCampaignGoal,
  className,
}: {
  platform: Platform;
  setPlatform: (value: Platform) => void;
  format: FormatMode;
  setFormat: (value: FormatMode) => void;
  fileType: FileType;
  setFileType: (value: FileType) => void;
  sizeLabel: string;
  setSizeLabel: (value: string) => void;
  campaignGoal: string;
  setCampaignGoal: (value: string) => void;
  className?: string;
}) {
  const sizeOptions = sizeOptionsByPlatform[platform];

  return (
    <aside className={`w-full overflow-hidden space-y-5 rounded-[28px] border border-white/70 bg-white/90 px-4 py-5 shadow-[0_28px_72px_-42px_rgba(15,23,42,0.42)] xl:max-w-[320px] ${className || ""}`}>
      <div className="flex items-center justify-between">
        <h3 className="text-[1.45rem] font-semibold text-slate-900">Studio</h3>
        <BadgePlus className="h-4 w-4 text-slate-400" />
      </div>

      <div className="space-y-3">
        <p className="text-lg font-medium text-slate-900">Format</p>
        <div className="grid grid-cols-2 gap-2">
          {[
            { value: "static", label: "Static", enabled: true },
            { value: "carousel", label: "Carousel", enabled: true },
            { value: "infographic", label: "Infographic", enabled: true },
            { value: "video", label: "Video", enabled: false },
          ].map((option) => (
            <button
              key={option.value}
              type="button"
              disabled={!option.enabled}
              onClick={() => option.enabled && setFormat(option.value as FormatMode)}
              className={`min-w-0 rounded-xl border px-3 py-2.5 text-left text-sm font-medium ${
                format === option.value
                  ? "border-primary bg-primary/8 text-primary"
                  : option.enabled
                    ? "border-slate-200 bg-slate-50 text-slate-500"
                    : "cursor-not-allowed border-slate-100 bg-slate-50/70 text-slate-300"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        <p className="text-lg font-medium text-slate-900">Platform</p>
        <div className="grid grid-cols-2 gap-2">
          {platformOptions.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                setPlatform(option);
                setSizeLabel(sizeOptionsByPlatform[option][0].label);
              }}
              className={`min-w-0 rounded-xl border px-3 py-2.5 text-center text-sm font-medium ${
                platform === option ? "border-primary bg-primary/8 text-primary" : "border-slate-200 bg-slate-50 text-slate-500"
              }`}
            >
              <span className="block truncate">{platformLabels[option]}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        <p className="text-lg font-medium text-slate-900">Size</p>
        <div className="grid grid-cols-2 gap-2">
          {sizeOptions.map((option) => (
            <button
              key={option.label}
              type="button"
              onClick={() => setSizeLabel(option.label)}
              className={`rounded-xl border px-3 py-2.5 text-center text-sm font-medium ${
                sizeLabel === option.label ? "border-primary bg-primary/8 text-primary" : "border-slate-200 bg-slate-50 text-slate-500"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        <p className="text-lg font-medium text-slate-900">File Type</p>
        <div className="grid grid-cols-2 gap-2">
          {fileTypeOptions.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setFileType(option)}
              className={`rounded-xl border px-3 py-2.5 text-center text-sm font-semibold uppercase ${
                fileType === option ? "border-primary bg-primary/8 text-primary" : "border-slate-200 bg-slate-50 text-slate-500"
              }`}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        <p className="text-lg font-medium text-slate-900">Campaign Goal</p>
        <select
          className="h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm text-slate-700 outline-none"
          value={campaignGoal}
          onChange={(event) => setCampaignGoal(event.target.value)}
        >
          <option value="">Select</option>
          {campaignGoalOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>
    </aside>
  );
}

export default function WorkspaceChat({ brandKey }: WorkspaceChatProps) {
  const { data: brands, isLoading: isBrandsLoading } = useBrands();
  const brand = useMemo(() => resolveBrandByRouteKey(brands, brandKey), [brands, brandKey]);
  const brandId = brand?.id || "";

  const { data: sessions } = useChatSessions(brandId);
  const createSession = useCreateChatSession(brandId);
  const { data: knowledgeAssets } = useKnowledgeAssets(brandId);
  const uploadKnowledgeAsset = useUploadKnowledgeAsset(brandId);
  const [activeSessionId, setActiveSessionId] = useState("");
  const resolvedActiveSessionId = activeSessionId || sessions?.[0]?.id || "";
  const { data: messages } = useChatMessages(brandId, resolvedActiveSessionId);
  const sendMessage = useSendChatMessage(brandId);
  const toneCheck = useToneCheck(brandId);

  const [selectedAction, setSelectedAction] = useState<ActionMode>("none");
  const [workspacePrompt, setWorkspacePrompt] = useState("");
  const [campaignFocus, setCampaignFocus] = useState("");
  const [campaignAudience, setCampaignAudience] = useState("");
  const [campaignObjective, setCampaignObjective] = useState("");
  const [socialGoal, setSocialGoal] = useState("");
  const [repurposeSource, setRepurposeSource] = useState("");
  const [repurposeTarget, setRepurposeTarget] = useState("");
  const [alignmentContent, setAlignmentContent] = useState("");
  const [composerDraft, setComposerDraft] = useState("");
  const [studioPlatform, setStudioPlatform] = useState<Platform>("instagram");
  const [studioFormat, setStudioFormat] = useState<FormatMode>("static");
  const [studioFileType, setStudioFileType] = useState<FileType>("png");
  const [studioSizeLabel, setStudioSizeLabel] = useState("1:1");
  const [campaignGoal, setCampaignGoal] = useState("");
  const [attachedAssets, setAttachedAssets] = useState<KnowledgeAssetResponse[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [selectedTemplateName, setSelectedTemplateName] = useState("");
  const [attachmentError, setAttachmentError] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const attachmentInputRef = useRef<HTMLInputElement | null>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const promptTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  const sizeOption = useMemo(
    () => sizeOptionsByPlatform[studioPlatform].find((entry) => entry.label === studioSizeLabel) || sizeOptionsByPlatform[studioPlatform][0],
    [studioPlatform, studioSizeLabel],
  );
  const studioPanel = useMemo<StudioPanelSelection>(
    () => ({
      format: studioFormat === "video" ? "static" : studioFormat,
      platform_preset: studioPlatform,
      file_type: studioFileType,
      size: { width: sizeOption.width, height: sizeOption.height },
    }),
    [sizeOption.height, sizeOption.width, studioFileType, studioFormat, studioPlatform],
  );
  const brandLifecycle = brand?.lifecycle_state || "draft";
  const canGenerateInWorkspace = brandLifecycle === "active";
  const isGeneratingMessage = createSession.isPending || sendMessage.isPending;
  const recommendationPrompt = useMemo(() => {
    if (selectedAction === "idea") {
      return [campaignFocus, campaignAudience, campaignObjective || campaignGoal, workspacePrompt]
        .map((item) => item.trim())
        .filter(Boolean)
        .join("\n");
    }
    if (selectedAction === "social") {
      return [workspacePrompt, socialGoal || campaignGoal].map((item) => item.trim()).filter(Boolean).join("\n");
    }
    if (selectedAction === "repurpose") {
      return [repurposeSource, repurposeTarget, workspacePrompt].map((item) => item.trim()).filter(Boolean).join("\n");
    }
    if (selectedAction === "alignment") {
      return alignmentContent.trim();
    }
    return composerDraft.trim() || workspacePrompt.trim();
  }, [
    alignmentContent,
    campaignAudience,
    campaignFocus,
    campaignGoal,
    campaignObjective,
    composerDraft,
    repurposeSource,
    repurposeTarget,
    selectedAction,
    socialGoal,
    workspacePrompt,
  ]);
  const debouncedRecommendationPrompt = useDebouncedValue(recommendationPrompt, 400);
  const { data: templateRecommendations = [], isFetching: isFetchingTemplateRecommendations } = useTemplateRecommendations(
    brandId,
    debouncedRecommendationPrompt,
    studioPanel,
    3,
    canGenerateInWorkspace &&
      !isGeneratingMessage &&
      debouncedRecommendationPrompt.trim().length >= 12,
  );
  const selectedTemplate = useMemo(
    () => templateRecommendations.find((item) => item.template_id === selectedTemplateId) || null,
    [selectedTemplateId, templateRecommendations],
  );
  const selectedTemplateLabel = selectedTemplate?.name || selectedTemplateName;
  const recentKnowledgeAssets = (knowledgeAssets || []).filter(
    (asset) => !attachedAssets.some((selected) => selected.id === asset.id),
  ).slice(0, 4);
  const hasConversation = Boolean((messages || []).length);
  const [generationProgressIndex, setGenerationProgressIndex] = useState(0);
  const activeGenerationMessage = isGeneratingMessage
    ? GENERATION_PROGRESS_MESSAGES[generationProgressIndex] || GENERATION_PROGRESS_MESSAGES[0]
    : GENERATION_PROGRESS_MESSAGES[0];
  const activeGenerationStatusLine = formatGenerationStatusLine(activeGenerationMessage);

  useEffect(() => {
    if (!isGeneratingMessage) {
      return;
    }

    const startedAt = Date.now();
    const updateProgress = () => {
      const elapsedMs = Date.now() - startedAt;
      const nextIndex = Math.floor(elapsedMs / 3000) % GENERATION_PROGRESS_MESSAGES.length;
      setGenerationProgressIndex(nextIndex);
    };

    updateProgress();
    const interval = window.setInterval(updateProgress, 900);
    return () => window.clearInterval(interval);
  }, [isGeneratingMessage]);

  const handleTemplateSelection = (templateId: string) => {
    setSelectedTemplateId(templateId);
    if (!templateId) {
      setSelectedTemplateName("");
      return;
    }
    const matchedTemplate = templateRecommendations.find((item) => item.template_id === templateId);
    if (matchedTemplate?.name) {
      setSelectedTemplateName(matchedTemplate.name);
    }
  };

  useEffect(() => {
    resizeComposer(composerTextareaRef.current);
  }, [composerDraft]);

  useEffect(() => {
    resizeComposer(promptTextareaRef.current);
  }, [workspacePrompt]);

  if (isBrandsLoading) {
    return <div className="p-5 text-sm text-slate-500">Loading workspace...</div>;
  }

  if (!brand) {
    return <div className="p-5 text-sm text-slate-500">Brand Space not found.</div>;
  }

  const extractApiError = (error: unknown, fallback: string) => {
    if (axios.isAxiosError(error)) {
      return String(error.response?.data?.detail || error.response?.data?.message || error.message || fallback);
    }
    if (error instanceof Error) {
      return error.message;
    }
    return fallback;
  };

  const ensureSession = async () => {
    if (!canGenerateInWorkspace) {
      throw new Error("This Brand Space is still in draft. Activate it before generating content or images.");
    }
    if (resolvedActiveSessionId) {
      return resolvedActiveSessionId;
    }
    const session = await createSession.mutateAsync({
      title: workspacePrompt || `${brand.name} Workspace`,
      studio_panel: studioPanel,
    });
    setActiveSessionId(session.id);
    return session.id;
  };

  const dispatchGeneration = async (message: string) => {
    if (!message.trim()) {
      setWorkspaceError("Enter a prompt before sending.");
      return;
    }
    try {
      setWorkspaceError("");
      setGenerationProgressIndex(0);
      const sessionId = await ensureSession();
      await sendMessage.mutateAsync({
        sessionId,
        data: {
          message,
          studio_panel: studioPanel,
          generate_image: studioFormat !== "video",
          template_id: selectedTemplateId || undefined,
          reference_asset_ids: attachedAssets.map((asset) => asset.id),
        },
      });
      setSelectedAction("none");
      setComposerDraft("");
      setWorkspacePrompt((current) => (current.trim() === message.trim() ? "" : current));
      setAttachedAssets([]);
      setAttachmentError("");
    } catch (error) {
      setWorkspaceError(extractApiError(error, "Unable to start the workspace session right now."));
    }
  };

  const handleReferenceUpload = async (files: FileList | null) => {
    if (!files?.length) {
      return;
    }
    try {
      setAttachmentError("");
      const uploaded = await Promise.all(
        Array.from(files).map(async (file) =>
          uploadKnowledgeAsset.mutateAsync({
            name: stripFileExtension(file.name),
            filename: file.name,
            mime_type: file.type || "application/octet-stream",
            content_base64: await fileToDataUrl(file),
            channel: "chat_reference",
            skip_processing: false,
            metadata: {
              asset_role: "chat_reference",
              section: "workspace_chat",
              tags: ["Chat Reference"],
            },
          }),
        ),
      );
      setAttachedAssets((current) => [...current, ...uploaded]);
    } catch {
      setAttachmentError("Unable to upload reference assets right now.");
    }
  };

  const toggleReferenceAsset = (asset: KnowledgeAssetResponse) => {
    setAttachedAssets((current) =>
      current.some((item) => item.id === asset.id)
        ? current.filter((item) => item.id !== asset.id)
        : [...current, asset],
    );
  };

  const handleActionGenerate = async () => {
    if (selectedAction === "idea") {
      await dispatchGeneration(
        `Generate campaign ideas.\nCampaign focus: ${campaignFocus}\nTarget audience: ${campaignAudience}\nCampaign objective: ${campaignObjective || campaignGoal}\nPlatform: ${studioPlatform}\nAdditional context: ${workspacePrompt}`,
      );
      return;
    }
    if (selectedAction === "social") {
      await dispatchGeneration(
        `Create a ${studioPlatform} social media post.\nGoal: ${socialGoal || campaignGoal}\nTopic: ${workspacePrompt}\nCampaign focus: ${campaignFocus}`,
      );
      return;
    }
    if (selectedAction === "repurpose") {
      await dispatchGeneration(
        `Repurpose the following content.\nSource content: ${repurposeSource}\nTarget outcome: ${repurposeTarget}\nPlatform: ${studioPlatform}\nAdditional context: ${workspacePrompt}`,
      );
      return;
    }
    if (alignmentContent.trim()) {
      await toneCheck.mutateAsync({ content: alignmentContent });
    }
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void dispatchGeneration(composerDraft);
    }
  };

  const handlePromptKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void dispatchGeneration(workspacePrompt);
    }
  };

  return (
    <div className="min-h-screen bg-[#F6F7FB]">
      <input
        ref={attachmentInputRef}
        type="file"
        className="hidden"
        multiple
        onChange={(event) => void handleReferenceUpload(event.target.files)}
      />
      <div className="border-b border-slate-200/80 bg-white/90 px-6 py-4 backdrop-blur">
        <PageHeading
          title={brand.name}
          actions={
            <>
              <Link href={buildBrandEditHref(brand)}>
                <Button variant="outline" className="h-11 rounded-[12px] border-[#D8DDEA] bg-white px-4 text-sm font-semibold text-[#2F3342] hover:bg-[#F7F7FB]">
                  <PencilLine className="mr-2 h-4 w-4" />
                  Edit Brand Space
                </Button>
              </Link>
              <UsageRing value={32} label={`${brand.name} Usage Pending: 32%`} />
            </>
          }
        />
      </div>

      <div className="grid min-h-[calc(100vh-96px)] gap-6 px-6 py-6">
        <div>
          {!canGenerateInWorkspace ? (
            <div className="mx-auto mb-6 max-w-4xl rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              This Brand Space is currently <span className="font-medium capitalize">{brandLifecycle}</span>. Finish activation before generating content or images in the workspace.
            </div>
          ) : null}
          {workspaceError ? (
            <div className="mx-auto mb-6 max-w-4xl rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {workspaceError}
            </div>
          ) : null}
          {hasConversation ? (
            <div className="mx-auto flex h-full max-w-6xl flex-col">
              <div className="grid flex-1 gap-6 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-end">
                <SurfaceCard className="flex flex-col rounded-[32px] border border-white/70 bg-white/90 px-4 py-4 shadow-[0_28px_72px_-42px_rgba(15,23,42,0.42)]">
                  <div className="space-y-4 px-2">
                    {(messages || []).map((message) => {
                      const previewAssets = message.role === "assistant" ? resolveGeneratedImageAssets(message.structured_payload) : [];
                      const previewUrl = previewAssets[0]?.asset_url || undefined;
                      const generationDecision = message.role === "assistant" ? resolveGenerationDecision(message.structured_payload) : null;
                      const imageStatus =
                        message.role === "assistant" &&
                        !previewUrl &&
                        (message.structured_payload as ChatAssistantStructuredPayload)?.image_generation_requested
                          ? (message.structured_payload as ChatAssistantStructuredPayload).image_generation_status
                          : null;
                      return (
                        <div key={message.id} className={`max-w-[86%] ${message.role === "user" ? "ml-auto" : "mr-auto"}`}>
                          <div className={`rounded-[24px] px-5 py-4 text-[1.05rem] leading-7 shadow-[0_16px_36px_-30px_rgba(15,23,42,0.35)] ${
                            message.role === "user"
                              ? "bg-[#F2F4FA] text-slate-800"
                              : "border border-[#ECEFFA] bg-white text-slate-800"
                          }`}>
                            <p className="whitespace-pre-wrap">{message.message_text}</p>
                          </div>
                          {message.role === "assistant" ? <GenerationDecisionCard decision={generationDecision} /> : null}
                          {previewAssets.length ? (
                            <div className="mt-4 overflow-hidden rounded-[24px] border border-slate-200 bg-white">
                              {previewAssets.length === 1 && previewUrl ? (
                                /* eslint-disable-next-line @next/next/no-img-element */
                                <img src={previewUrl} alt="Generated image" className="w-full object-cover" />
                              ) : (
                                <div className="px-5 py-5">
                                  <Carousel opts={{ loop: false }} className="mx-10">
                                    <CarouselContent>
                                      {previewAssets.map((asset, index) => {
                                        const assetUrl = asset.asset_url || undefined;
                                        if (!assetUrl) {
                                          return null;
                                        }
                                        return (
                                          <CarouselItem key={asset.asset_id || asset.storage_path || asset.asset_url || index}>
                                            <div className="space-y-3">
                                              <div className="flex items-center justify-between">
                                                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                                                  Slide {index + 1} of {previewAssets.length}
                                                </span>
                                              </div>
                                              {/* eslint-disable-next-line @next/next/no-img-element */}
                                              <img
                                                src={assetUrl}
                                                alt={`Generated slide ${index + 1}`}
                                                className="w-full rounded-[20px] object-cover"
                                              />
                                            </div>
                                          </CarouselItem>
                                        );
                                      })}
                                    </CarouselContent>
                                    <CarouselPrevious className="left-1 top-1/2 -translate-y-1/2 bg-white" />
                                    <CarouselNext className="right-1 top-1/2 -translate-y-1/2 bg-white" />
                                  </Carousel>
                                </div>
                              )}
                            </div>
                          ) : null}
                          {imageStatus === "not_generated" ? <p className="mt-3 text-sm text-slate-500">Image generation was requested, but no generated image asset was returned for this message.</p> : null}
                        </div>
                      );
                    })}
                    {isGeneratingMessage ? (
                      <div className="mr-auto max-w-[86%]">
                        <div className="rounded-[24px] border border-[#ECEFFA] bg-white px-5 py-4 text-slate-800 shadow-[0_16px_36px_-30px_rgba(15,23,42,0.35)]">
                          <div className="space-y-4">
                            <GenerationPreviewPlaceholder
                              width={studioPanel.size?.width ?? 1080}
                              height={studioPanel.size?.height ?? 1080}
                            />
                            <div className="flex items-center gap-3">
                              <Loader2 className="h-4 w-4 animate-spin text-primary" />
                              <p className="min-w-0 text-sm font-medium text-slate-700">
                                <span className="block truncate">{activeGenerationStatusLine}</span>
                              </p>
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </div>

                  <div className="mt-auto px-2 pt-8">
                    {!isGeneratingMessage ? (
                      <div className="mb-4 flex items-center gap-2 text-sm font-medium text-primary">
                        <BadgePlus className="h-4 w-4" />
                        <span>Applying brand intelligence...</span>
                      </div>
                    ) : null}
                    {attachedAssets.length ? (
                      <div className="mb-3 flex flex-wrap gap-2">
                        {attachedAssets.map((asset) => (
                          <button
                            key={asset.id}
                            type="button"
                            onClick={() => toggleReferenceAsset(asset)}
                            className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-xs text-primary"
                          >
                            <Paperclip className="h-3 w-3" />
                            <span>{assetPreviewLabel(asset)}</span>
                            <X className="h-3 w-3" />
                          </button>
                        ))}
                      </div>
                    ) : null}
                    <div className="mb-3">
                      <TemplateRecommendationRail
                        recommendations={templateRecommendations}
                        isLoading={isFetchingTemplateRecommendations}
                        selectedTemplateId={selectedTemplateId}
                        onSelect={handleTemplateSelection}
                      />
                    </div>
                    {selectedTemplateLabel ? (
                      <p className="mb-3 text-xs text-slate-500">
                        Pinned template: <span className="font-medium text-slate-700">{selectedTemplateLabel}</span>. We&apos;ll follow this visual direction unless auto mode is safer.
                      </p>
                    ) : null}
                    {attachmentError ? <p className="mb-2 text-sm text-red-500">{attachmentError}</p> : null}
                    <SurfaceCard className="flex items-center gap-3 rounded-[24px] border border-[#E8EBF4] bg-[#FBFBFE] px-3 py-3 shadow-none">
                      <button
                        type="button"
                        onClick={() => attachmentInputRef.current?.click()}
                        disabled={!canGenerateInWorkspace || isGeneratingMessage}
                        className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-400 disabled:cursor-not-allowed"
                      >
                        <Plus className="h-4 w-4" />
                      </button>
                      <Textarea
                        ref={composerTextareaRef}
                        value={composerDraft}
                        onChange={(event) => setComposerDraft(event.target.value)}
                        onKeyDown={handleComposerKeyDown}
                        placeholder="What do you want to create today?"
                        className="min-h-11 max-h-[220px] flex-1 resize-none overflow-y-hidden border-none bg-transparent px-0 py-2 text-lg leading-7 shadow-none outline-none focus-visible:ring-0"
                      />
                      <button
                        type="button"
                        onClick={() => void dispatchGeneration(composerDraft)}
                        disabled={!canGenerateInWorkspace || isGeneratingMessage || !composerDraft.trim()}
                        className="flex h-11 min-w-11 items-center justify-center rounded-2xl bg-primary px-3 text-white disabled:cursor-not-allowed disabled:bg-slate-200"
                      >
                        {isGeneratingMessage ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizontal className="h-4 w-4" />}
                      </button>
                    </SurfaceCard>
                  </div>
                </SurfaceCard>
                <StudioPanel
                  platform={studioPlatform}
                  setPlatform={setStudioPlatform}
                  format={studioFormat}
                  setFormat={setStudioFormat}
                  fileType={studioFileType}
                  setFileType={setStudioFileType}
                  sizeLabel={studioSizeLabel}
                  setSizeLabel={setStudioSizeLabel}
                  campaignGoal={campaignGoal}
                  setCampaignGoal={setCampaignGoal}
                  className="xl:sticky xl:bottom-6 xl:self-end xl:max-w-none"
                />
              </div>
            </div>
          ) : (
            <div className="mx-auto flex max-w-6xl flex-col items-center space-y-6 pt-10">
              <div className="flex items-center gap-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-[20px] bg-primary text-3xl font-bold text-white shadow-[0_16px_40px_-24px_rgba(60,47,143,0.85)]">
                  V
                </div>
                <h2 className="font-dmSans text-5xl font-bold tracking-tight text-slate-900">Greeting message</h2>
              </div>

              <div className="grid w-full gap-4 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-end">
                <SurfaceCard className="rounded-[32px] border border-white/70 bg-white/90 px-6 py-6 shadow-[0_28px_72px_-42px_rgba(15,23,42,0.42)]">
                  <Textarea
                    ref={promptTextareaRef}
                    placeholder="What do you want to create today?"
                    className="min-h-28 max-h-[220px] resize-none overflow-y-hidden border-none bg-transparent p-0 text-xl text-[#6A6E8B] shadow-none focus-visible:ring-0"
                    value={workspacePrompt}
                    onChange={(event) => setWorkspacePrompt(event.target.value)}
                    onKeyDown={handlePromptKeyDown}
                  />
                  <div className="mt-4 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => attachmentInputRef.current?.click()}
                      disabled={!canGenerateInWorkspace || isGeneratingMessage}
                      className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-400 disabled:cursor-not-allowed"
                    >
                      <Plus className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => void dispatchGeneration(workspacePrompt)}
                      disabled={!canGenerateInWorkspace || isGeneratingMessage || !workspacePrompt.trim()}
                      className="flex h-11 min-w-11 items-center justify-center rounded-2xl bg-primary px-3 text-white disabled:cursor-not-allowed disabled:bg-slate-200"
                    >
                      {isGeneratingMessage ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizontal className="h-4 w-4" />}
                    </button>
                  </div>
                </SurfaceCard>
                <StudioPanel
                  platform={studioPlatform}
                  setPlatform={setStudioPlatform}
                  format={studioFormat}
                  setFormat={setStudioFormat}
                  fileType={studioFileType}
                  setFileType={setStudioFileType}
                  sizeLabel={studioSizeLabel}
                  setSizeLabel={setStudioSizeLabel}
                  campaignGoal={campaignGoal}
                  setCampaignGoal={setCampaignGoal}
                  className="xl:sticky xl:bottom-6 xl:self-end xl:max-w-none"
                />
              </div>
              {attachedAssets.length ? (
                <div className="flex w-full flex-wrap justify-center gap-2">
                  {attachedAssets.map((asset) => (
                    <button
                      key={asset.id}
                      type="button"
                      onClick={() => toggleReferenceAsset(asset)}
                      className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-xs text-primary"
                    >
                      <Paperclip className="h-3 w-3" />
                      <span>{assetPreviewLabel(asset)}</span>
                      <X className="h-3 w-3" />
                    </button>
                  ))}
                </div>
              ) : null}
              {recentKnowledgeAssets.length ? (
                <div className="flex w-full flex-wrap justify-center gap-2">
                  {recentKnowledgeAssets.map((asset) => (
                    <button
                      key={asset.id}
                      type="button"
                      onClick={() => toggleReferenceAsset(asset)}
                      className="inline-flex items-center gap-2 border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600"
                    >
                      <Paperclip className="h-3.5 w-3.5" />
                      <span>{assetPreviewLabel(asset)}</span>
                    </button>
                  ))}
                </div>
              ) : null}
              <div className="w-full">
                <TemplateRecommendationRail
                  recommendations={templateRecommendations}
                  isLoading={isFetchingTemplateRecommendations}
                  selectedTemplateId={selectedTemplateId}
                  onSelect={handleTemplateSelection}
                />
              </div>
              {selectedTemplateLabel ? (
                <p className="text-sm text-slate-500">
                  Pinned template: <span className="font-medium text-slate-700">{selectedTemplateLabel}</span>. Clear it any time to go back to auto selection.
                </p>
              ) : null}

              <div className="flex flex-wrap justify-center gap-3">
                {actionOptions.map((action) => (
                  <ActionButton
                    key={action.id}
                    selected={selectedAction === action.id}
                    onClick={() => setSelectedAction((current) => (current === action.id ? "none" : action.id))}
                    icon={action.icon}
                    label={action.label}
                  />
                ))}
                <Link href={buildBrandSharingHref(brand)} className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 shadow-[0_16px_40px_-32px_rgba(15,23,42,0.35)]">
                  <BadgePlus className="h-4 w-4" />
                  <span>Open Review</span>
                </Link>
              </div>

              {selectedAction !== "none" ? (
                <SurfaceCard className="w-full rounded-[28px] border border-white/70 bg-white/90 px-6 py-5 shadow-[0_28px_72px_-44px_rgba(15,23,42,0.4)]">
                  <div className="mb-6 flex items-center gap-2 text-base font-medium text-slate-700">
                    {selectedAction === "idea" ? <Sparkles className="h-4 w-4" /> : null}
                    {selectedAction === "social" ? <Megaphone className="h-4 w-4" /> : null}
                    {selectedAction === "repurpose" ? <RefreshCw className="h-4 w-4" /> : null}
                    {selectedAction === "alignment" ? <Wand2 className="h-4 w-4" /> : null}
                    <span>
                      {selectedAction === "idea" && "Generate Campaign Idea"}
                      {selectedAction === "social" && "Create Social Media Post"}
                      {selectedAction === "repurpose" && "Repurpose Content"}
                      {selectedAction === "alignment" && "Check Brand Alignment"}
                    </span>
                  </div>

                  <div className="grid gap-5 md:max-w-md">
                    {selectedAction === "idea" ? (
                      <>
                        <label className="space-y-2">
                          <span className="text-base font-medium text-slate-700">Campaign focus</span>
                          <Input placeholder="What product, service, or initiative is this campaign for" className="h-12 border-none bg-input-field shadow-none" value={campaignFocus} onChange={(event) => setCampaignFocus(event.target.value)} />
                        </label>
                        <label className="space-y-2">
                          <span className="text-base font-medium text-slate-700">Target Audience</span>
                          <Input placeholder="Select target audience" className="h-12 border-none bg-input-field shadow-none" value={campaignAudience} onChange={(event) => setCampaignAudience(event.target.value)} />
                        </label>
                        <label className="space-y-2">
                          <span className="text-base font-medium text-slate-700">Campaign Objective</span>
                          <Input placeholder="What outcome should this campaign aim to achieve" className="h-12 border-none bg-input-field shadow-none" value={campaignObjective} onChange={(event) => setCampaignObjective(event.target.value)} />
                        </label>
                      </>
                    ) : null}

                    {selectedAction === "social" ? (
                      <label className="space-y-2">
                        <span className="text-base font-medium text-slate-700">Goal</span>
                        <Input placeholder="What is the goal of this post" className="h-12 border-none bg-input-field shadow-none" value={socialGoal} onChange={(event) => setSocialGoal(event.target.value)} />
                      </label>
                    ) : null}

                    {selectedAction === "repurpose" ? (
                      <>
                        <label className="space-y-2">
                          <span className="text-base font-medium text-slate-700">Source Content</span>
                          <Input placeholder="Paste the content you would like to repurpose" className="h-12 border-none bg-input-field shadow-none" value={repurposeSource} onChange={(event) => setRepurposeSource(event.target.value)} />
                        </label>
                        <label className="space-y-2">
                          <span className="text-base font-medium text-slate-700">Target</span>
                          <Input placeholder="Specify what the repurposed content should aim to achieve" className="h-12 border-none bg-input-field shadow-none" value={repurposeTarget} onChange={(event) => setRepurposeTarget(event.target.value)} />
                        </label>
                      </>
                    ) : null}

                    {selectedAction === "alignment" ? (
                      <label className="space-y-2">
                        <span className="text-base font-medium text-slate-700">Content</span>
                        <Textarea placeholder="Paste the content you want to evaluate for brand alignment" className="min-h-28 border-none bg-input-field shadow-none" value={alignmentContent} onChange={(event) => setAlignmentContent(event.target.value)} />
                      </label>
                    ) : null}

                    <label className="space-y-2">
                      <span className="text-base font-medium text-slate-700">Platform</span>
                      <select
                        className="h-12 w-full rounded-xl border-none bg-input-field px-4 text-sm text-slate-700 outline-none"
                        value={studioPlatform}
                        onChange={(event) => {
                          const value = event.target.value as Platform;
                          setStudioPlatform(value);
                          setStudioSizeLabel(sizeOptionsByPlatform[value][0].label);
                        }}
                      >
                        {platformOptions.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <div className="mt-8 flex justify-end">
                    <Button
                      className="rounded-none bg-primary px-8 py-4 text-base hover:bg-primary/90"
                      onClick={handleActionGenerate}
                      disabled={!canGenerateInWorkspace || isGeneratingMessage}
                    >
                      {selectedAction === "alignment" ? (toneCheck.isPending ? "Checking..." : "Generate") : isGeneratingMessage ? "Generating..." : "Generate"}
                    </Button>
                  </div>

                  {toneCheck.data && selectedAction === "alignment" ? (
                    <div className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-700">
                      <p className="font-semibold">Tone Score: {toneCheck.data.score}</p>
                      <p className="mt-2">Deviations: {toneCheck.data.deviations.join(", ") || "None"}</p>
                    </div>
                  ) : null}
                </SurfaceCard>
              ) : null}

              <p className="pt-12 text-center text-sm text-slate-400">Violyt suggestions may need review. Verify accuracy before use.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
