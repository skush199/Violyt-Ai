"use client";

import { Copy, Download, Facebook, Instagram, Linkedin, SendHorizontal, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from "@/components/ui/carousel";
import { PageHeading, SurfaceCard } from "@/components/common/DesignPrimitives";
import { resolveBrandByRouteKey } from "@/lib/brand-routing";
import { apiOrigin } from "@/lib/env";
import { useBrands } from "@/hooks/useBrands";
import { useAddReviewComment, useContentHistory, useCreateShareLink, useReviewDetail } from "@/hooks/useContentWorkspace";
import type { AssetReference } from "@/lib/api/contracts";
import { coerceGenerationDecision, formatGenerationMode, getGenerationDecisionReasons, getGenerationDecisionTemplate } from "@/lib/generation-decision";

type ShareReviewScreenProps = {
  brandKey?: string;
  reviewToken?: string;
  externalMode?: boolean;
};

type ModalMode = "none" | "share" | "save";

function resolveAssetUrl(storagePath?: string | null) {
  return storagePath ? `${apiOrigin}/storage/${storagePath}` : null;
}

function resolveAssetByExtension(storagePath: string | undefined, extension: string) {
  if (!storagePath) {
    return false;
  }
  return storagePath.toLowerCase().endsWith(extension);
}

function dedupeAssets(assets: AssetReference[]) {
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

export default function ShareReviewScreen({
  brandKey,
  reviewToken: reviewTokenProp,
  externalMode = false,
}: ShareReviewScreenProps) {
  const initialToken = reviewTokenProp || "";
  const [reviewToken, setReviewToken] = useState(initialToken);
  const [comment, setComment] = useState("");
  const [reviewerName, setReviewerName] = useState("");
  const [welcomeName, setWelcomeName] = useState("");
  const [modalMode, setModalMode] = useState<ModalMode>("none");
  const [copied, setCopied] = useState(false);

  const { data: brands } = useBrands(Boolean(brandKey) && !externalMode);
  const liveBrand = useMemo(
    () => resolveBrandByRouteKey(brands, brandKey),
    [brands, brandKey],
  );
  const brand = liveBrand;
  const brandId = liveBrand?.id || "";

  const { data: history } = useContentHistory(brandId);
  const latestContent = history?.[0];
  const createLink = useCreateShareLink(brandId);
  const review = useReviewDetail(reviewToken);
  const addComment = useAddReviewComment(reviewToken);

  const reviewContent = review.data?.content;
  const effectiveTitle = brand?.name || reviewContent?.title || "Violyt";
  const findDisplayAssets = (assets?: AssetReference[]) => {
    if (!assets?.length) {
      return [];
    }
    const exportImages = assets.filter(
      (asset) => asset.mime_type.startsWith("image/") && asset.asset_role === "render_export",
    );
    if (exportImages.length) {
      return dedupeAssets(exportImages);
    }
    const previewImages = assets.filter(
      (asset) => asset.mime_type.startsWith("image/") && asset.asset_role === "render_preview",
    );
    if (previewImages.length) {
      return dedupeAssets(previewImages);
    }
    return dedupeAssets(assets.filter((asset) => asset.mime_type.startsWith("image/")));
  };
  const reviewPreviewAssets = findDisplayAssets(reviewContent?.assets);
  const historyPreviewAssets = findDisplayAssets(latestContent?.assets);
  const previewAssets = reviewPreviewAssets.length ? reviewPreviewAssets : historyPreviewAssets;
  const generationDecision = coerceGenerationDecision(reviewContent?.generation_decision || latestContent?.generation_decision);
  const previewUrl = previewAssets[0]?.asset_url || resolveAssetUrl(previewAssets[0]?.storage_path);
  const candidateAssets = reviewContent?.assets || latestContent?.assets || [];
  const appOrigin = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
  const shareUrl = reviewToken ? `${appOrigin}/review/${reviewToken}` : "";

  const comments = (review.data?.comments || []).map((item) => ({
    id: item.id,
    author: item.external_author_name || "Reviewer",
    initials: (item.external_author_name || "R").slice(0, 1).toUpperCase(),
    color: "#52B2CF",
    content: item.body,
    timestamp: "Just now",
  }));

  const handleGenerateLink = () => {
    if (!latestContent) {
      return;
    }
    createLink.mutate(
      {
        content_version_id: latestContent.id,
        title: `${effectiveTitle} Review`,
        allow_external_comments: true,
      },
      {
        onSuccess: (response) => {
          setReviewToken(response.token);
          setModalMode("share");
        },
      },
    );
  };

  const handleComment = () => {
    if (!comment.trim() || !reviewToken) {
      return;
    }
    addComment.mutate(
      {
        body: comment,
        external_author_name: externalMode ? reviewerName || "Reviewer" : "Frontend Reviewer",
      },
      {
        onSuccess: () => setComment(""),
      },
    );
  };

  const handleCopyLink = async () => {
    if (!shareUrl) {
      return;
    }
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const exportCandidates = [
    { label: "PDF Standard", icon: Download, url: resolveAssetUrl(candidateAssets.find((asset) => resolveAssetByExtension(asset.storage_path, ".pdf"))?.storage_path) || previewUrl },
    { label: "JPG", icon: Download, url: resolveAssetUrl(candidateAssets.find((asset) => resolveAssetByExtension(asset.storage_path, ".jpg") || resolveAssetByExtension(asset.storage_path, ".jpeg"))?.storage_path) || previewUrl },
    { label: "PNG", icon: Download, url: resolveAssetUrl(candidateAssets.find((asset) => resolveAssetByExtension(asset.storage_path, ".png"))?.storage_path) || previewUrl },
  ];

  const openShareWindow = (url: string) => {
    window.open(url, "_blank", "noopener,noreferrer,width=720,height=720");
  };

  const handleSocialShare = async (network: "instagram" | "facebook" | "linkedin") => {
    if (!shareUrl && !previewUrl) {
      return;
    }
    const target = shareUrl || previewUrl || "";
    if (network === "instagram") {
      if (navigator.share && previewUrl) {
        await navigator.share({ title: effectiveTitle, text: `${effectiveTitle} review`, url: target });
        return;
      }
      await navigator.clipboard.writeText(target);
      openShareWindow("https://www.instagram.com/");
      return;
    }
    if (network === "facebook") {
      openShareWindow(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(target)}`);
      return;
    }
    openShareWindow(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(target)}`);
  };

  if (externalMode && !reviewerName) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white px-6">
        <div className="w-full max-w-md text-center">
          <div className="mx-auto mb-8 flex h-14 w-14 items-center justify-center rounded-xl bg-primary text-3xl font-bold text-white">V</div>
          <h1 className="font-dmSans text-5xl font-extrabold text-slate-900">Welcome to Violyt</h1>
          <p className="mt-3 text-slate-500">A reviewer has given you access.</p>
          <div className="mt-12 space-y-3 text-left">
            <label className="text-base font-medium text-slate-700">Your Name</label>
            <Input
              value={welcomeName}
              onChange={(event) => setWelcomeName(event.target.value)}
              placeholder="Enter your name"
              className="h-12 border-none bg-input-field shadow-none"
            />
          </div>
          <Button
            onClick={() => setReviewerName(welcomeName.trim())}
            disabled={!welcomeName.trim()}
            className="mt-8 h-12 w-full rounded-none bg-primary text-base hover:bg-primary/90"
          >
            Continue
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {!externalMode ? (
        <div className="border-b border-slate-200 px-6 py-4">
          <PageHeading
            title={effectiveTitle}
            actions={
              <div className="flex items-center gap-3">
                <Button
                  onClick={reviewToken ? () => setModalMode("share") : handleGenerateLink}
                  className="rounded-none bg-primary px-5 py-4 text-base hover:bg-primary/90"
                >
                  {createLink.isPending ? "Creating..." : reviewToken ? "Share" : "Generate Review Link"}
                </Button>
                {reviewToken ? (
                  <Button
                    variant="outline"
                    onClick={() => setModalMode("save")}
                    className="rounded-none border-slate-300 px-5 py-4 text-base"
                  >
                    Save As
                  </Button>
                ) : null}
              </div>
            }
          />
        </div>
      ) : (
        <div className="border-b border-slate-200 px-6 py-4">
          <div className="flex h-10 items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-sm font-bold text-white">V</div>
            <span className="text-2xl font-semibold text-primary">Violyt</span>
          </div>
        </div>
      )}

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-6">
        {!externalMode && reviewToken ? (
          <div className="text-sm text-slate-500">
            Review link: <span className="font-medium text-slate-700">{shareUrl}</span>
          </div>
        ) : null}

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
          <SurfaceCard className="p-5">
            {previewAssets.length ? (
              <div className="overflow-hidden rounded-xl border border-slate-100 bg-slate-50 p-4">
                {previewAssets.length === 1 ? (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img src={previewUrl || undefined} alt="Review preview" className="w-full object-cover" />
                ) : (
                  <Carousel opts={{ loop: false }} className="mx-10">
                    <CarouselContent>
                      {previewAssets.map((asset, index) => (
                        <CarouselItem key={asset.asset_id || asset.storage_path || asset.asset_url || index}>
                          <div className="space-y-3">
                            <div className="flex items-center justify-between">
                              <span className="rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-600">
                                Slide {index + 1} of {previewAssets.length}
                              </span>
                            </div>
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={asset.asset_url || resolveAssetUrl(asset.storage_path) || undefined}
                              alt={`Review slide ${index + 1}`}
                              className="w-full rounded-xl object-cover"
                            />
                          </div>
                        </CarouselItem>
                      ))}
                    </CarouselContent>
                    <CarouselPrevious className="left-1 top-1/2 -translate-y-1/2 bg-white" />
                    <CarouselNext className="right-1 top-1/2 -translate-y-1/2 bg-white" />
                  </Carousel>
                )}
              </div>
            ) : (
              <div className="rounded-xl border border-slate-100 bg-slate-50 p-10 text-slate-500">
                No preview available yet.
              </div>
            )}
            {generationDecision ? (
              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">
                    {formatGenerationMode(generationDecision.mode)}
                  </span>
                  {getGenerationDecisionTemplate(generationDecision) ? (
                    <span className="text-xs font-medium text-slate-500">
                      Template: {getGenerationDecisionTemplate(generationDecision)}
                    </span>
                  ) : null}
                </div>
                {getGenerationDecisionReasons(generationDecision).length ? (
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {getGenerationDecisionReasons(generationDecision)[0]}
                  </p>
                ) : null}
              </div>
            ) : null}
          </SurfaceCard>

          <SurfaceCard className="space-y-4 p-5">
            <p className="text-2xl font-semibold text-slate-800">Comment</p>
            <div className="space-y-4">
              {comments.map((item) => (
                <div key={item.id} className="border-b border-slate-100 pb-3 last:border-none last:pb-0">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <span className="mt-1 flex h-7 w-7 items-center justify-center rounded-full text-sm font-semibold text-white" style={{ backgroundColor: item.color }}>
                        {item.initials}
                      </span>
                      <div>
                        <p className="font-semibold text-slate-800">{item.author}</p>
                        <p className="mt-1 text-lg leading-7 text-slate-600">{item.content}</p>
                      </div>
                    </div>
                    <span className="text-sm text-slate-400">{item.timestamp}</span>
                  </div>
                </div>
              ))}
            </div>
            <Input
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="Add your comment"
              className="h-12 border-none bg-input-field shadow-none"
            />
          </SurfaceCard>
        </div>

        <SurfaceCard className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3 shadow-[0_18px_36px_-28px_rgba(60,47,143,0.45)]">
          <Input
            placeholder="Add your comment"
            className="h-14 border-none bg-transparent text-lg shadow-none focus-visible:ring-0"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
          <Button
            className="h-10 w-10 rounded-none bg-primary p-0 hover:bg-primary/90"
            onClick={handleComment}
            disabled={!comment.trim() || addComment.isPending || !reviewToken}
          >
            <SendHorizontal className="h-4 w-4" />
          </Button>
        </SurfaceCard>

        <div className="text-center text-sm text-slate-400">Violyt suggestions may need review. Verify accuracy before use.</div>
      </div>

      {modalMode !== "none" ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/25 px-4">
          <div className="w-full max-w-4xl rounded-[2rem] bg-white p-8 shadow-2xl">
            <div className="mb-6 flex justify-end">
              <button type="button" onClick={() => setModalMode("none")} className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-50 text-slate-700">
                <X className="h-6 w-6" />
              </button>
            </div>

            {modalMode === "share" ? (
              <div className="space-y-6">
                <h2 className="text-6xl font-semibold text-slate-900">Share</h2>
                {previewAssets.length ? (
                  <div className="overflow-hidden rounded-xl bg-slate-50 p-4">
                    {previewAssets.length === 1 ? (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img src={previewUrl || undefined} alt="Share preview" className="mx-auto max-h-[420px] w-auto object-contain" />
                    ) : (
                      <Carousel opts={{ loop: false }} className="mx-10">
                        <CarouselContent>
                          {previewAssets.map((asset, index) => (
                            <CarouselItem key={asset.asset_id || asset.storage_path || asset.asset_url || index}>
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={asset.asset_url || resolveAssetUrl(asset.storage_path) || undefined}
                                alt={`Share slide ${index + 1}`}
                                className="mx-auto max-h-[420px] w-auto rounded-xl object-contain"
                              />
                            </CarouselItem>
                          ))}
                        </CarouselContent>
                        <CarouselPrevious className="left-1 top-1/2 -translate-y-1/2 bg-white" />
                        <CarouselNext className="right-1 top-1/2 -translate-y-1/2 bg-white" />
                      </Carousel>
                    )}
                  </div>
                ) : null}
                <div className="flex justify-center">
                  <Button onClick={handleCopyLink} className="rounded-none bg-primary px-10 py-6 text-2xl hover:bg-primary/90">
                    <Copy className="mr-3 h-6 w-6" />
                    {copied ? "Copied" : "Copy Link"}
                  </Button>
                </div>
                <div className="border-t border-slate-200 pt-6 text-center">
                  <p className="text-4xl font-medium text-slate-900">Social Media</p>
                  <div className="mt-6 flex justify-center gap-6">
                    <button
                      type="button"
                      onClick={() => void handleSocialShare("instagram")}
                      className="flex h-14 w-14 items-center justify-center rounded-full border border-slate-200 text-primary"
                    >
                      <Instagram className="h-7 w-7" />
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleSocialShare("facebook")}
                      className="flex h-14 w-14 items-center justify-center rounded-full border border-slate-200 text-primary"
                    >
                      <Facebook className="h-7 w-7" />
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleSocialShare("linkedin")}
                      className="flex h-14 w-14 items-center justify-center rounded-full border border-slate-200 text-primary"
                    >
                      <Linkedin className="h-7 w-7" />
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-8">
                <h2 className="text-6xl font-semibold text-slate-900">Save as</h2>
                <div className="space-y-4 rounded-xl bg-white p-6 shadow-[0_18px_36px_-28px_rgba(60,47,143,0.45)]">
                  {exportCandidates.map((item) => (
                    <button
                      key={item.label}
                      type="button"
                      onClick={() => item.url && window.open(item.url, "_blank", "noopener,noreferrer")}
                      className="flex w-full items-center gap-4 border-b border-slate-100 py-6 text-left last:border-none"
                    >
                      <item.icon className="h-9 w-9 text-slate-700" />
                      <span className="text-5xl font-medium text-slate-700">{item.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
