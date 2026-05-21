"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import BrandSpaces from "@/components/brandSpaces/BrandSpaces";
import {
  MetricTile,
  PlatformPageTitle,
  PlatformTabSwitcher,
  SectionCard,
} from "@/components/platformOwner/PlatformOwnerPrimitives";
import { toast } from "@/components/ui/use-toast";
import { useArchiveBrandMutation, useBrands, useDeleteBrandMutation, usePublishBrandMutation, useRestoreBrandMutation, useUnpublishBrandMutation } from "@/hooks/useBrands";
import { useRBAC } from "@/hooks/useRBAC";
import type { BrandResponse } from "@/lib/api/contracts";
import { clearBrandSpaceDraft } from "@/lib/brand-space-persistence";
import Image from "next/image";

function getBrandId(item: BrandResponse | { id: string }) {
  return item.id;
}

export default function BrandSpacePage() {
  const router = useRouter();
  const { user, can } = useRBAC();
  const { data: brands, isLoading } = useBrands();
  const publishBrand = usePublishBrandMutation();
  const unpublishBrand = useUnpublishBrandMutation();
  const archiveBrand = useArchiveBrandMutation();
  const restoreBrand = useRestoreBrandMutation();
  const deleteBrand = useDeleteBrandMutation();
  const isAdmin = user?.role === "TENANT_ADMIN";
  const [activeTab, setActiveTab] = useState<"brand_spaces" | "archive">("brand_spaces");

  const liveActiveSpaces = useMemo(
    () => (brands || []).filter((brand) => brand.lifecycle_state !== "archived" && brand.lifecycle_state !== "deleted"),
    [brands],
  );
  const liveArchivedSpaces = useMemo(
    () => (brands || []).filter((brand) => brand.lifecycle_state === "archived"),
    [brands],
  );
  const activeSpaces = liveActiveSpaces;
  const archivedSpaces = liveArchivedSpaces;
  const visibleSpaces = activeTab === "brand_spaces" ? activeSpaces : archivedSpaces;

  const runBrandAction = async (
    action: () => Promise<unknown>,
    successMessage: string,
    failureMessage: string,
  ) => {
    try {
      await action();
      toast({
        title: successMessage,
      });
    } catch (error) {
      const description = error instanceof Error ? error.message : failureMessage;
      toast({
        title: failureMessage,
        description,
        variant: "destructive",
      });
    }
  };

  return (
    <div className="w-full px-5 py-5">
      <div className="mx-auto max-w-278 space-y-6">
        <PlatformPageTitle
          title="Brand Spaces"
          action={
            <div className="flex gap-2">
              {isAdmin && (
                <Button
                  onClick={() => router.push("/brand_space/usage")}
                  variant="outline"
                  className="h-12 rounded-none border border-primary bg-white px-5 text-[15px] font-semibold text-primary hover:bg-[#F7F7FB]"
                >
                  <span>Edit Usage</span>
                </Button>
              )}
              {can("BRAND_SPACE", "CREATE") && (
                <Button
                  onClick={() => {
                    clearBrandSpaceDraft();
                    router.push("/brand_space/new?fresh=1");
                  }}
                  className="flex h-12 items-center justify-center gap-2 rounded-none border-0 bg-primary/72 px-5 text-[15px] font-semibold hover:bg-primary/90"
                >
                  <Image src="/actions_icons/add.svg" alt="plus icon" width={16} height={16} />
                  <span>New Brand Space</span>
                </Button>
              )}
            </div>
          }
        >
          <PlatformTabSwitcher
            tabs={[
              { id: "brand_spaces", label: "Your Space" },
              { id: "archive", label: "Archive" },
            ]}
            active={activeTab}
            onChange={(tab) => setActiveTab(tab as "brand_spaces" | "archive")}
          />
        </PlatformPageTitle>

        <div className="grid gap-4 md:grid-cols-3">
          <MetricTile label="Active Spaces" value={String(activeSpaces.length)} />
          <MetricTile label="Archived Spaces" value={String(archivedSpaces.length)} />
          <MetricTile label="Workspace Access" value={user?.role === "BRAND_USER" ? "Assigned" : "Managed"} />
        </div>

        <SectionCard title={activeTab === "brand_spaces" ? "Your Brand Spaces" : "Archived Brand Spaces"}>
          {isLoading ? (
            <div className="py-10 text-sm text-slate-500">Loading brand spaces...</div>
          ) : (
            <BrandSpaces
              items={visibleSpaces}
              onPublish={(item) => {
                void runBrandAction(
                  () => publishBrand.mutateAsync(getBrandId(item)),
                  "Brand Space activated",
                  "Unable to activate this Brand Space right now.",
                );
              }}
              onUnpublish={(item) => {
                void runBrandAction(
                  () => unpublishBrand.mutateAsync(getBrandId(item)),
                  "Brand Space moved to draft",
                  "Unable to move this Brand Space to draft right now.",
                );
              }}
              onArchive={(item) => {
                void runBrandAction(
                  () => archiveBrand.mutateAsync(getBrandId(item)),
                  "Brand Space archived",
                  "Unable to archive this Brand Space right now.",
                );
              }}
              onRestore={(item) => {
                void runBrandAction(
                  () => restoreBrand.mutateAsync(getBrandId(item)),
                  "Brand Space restored",
                  "Unable to restore this Brand Space right now.",
                );
              }}
              onDelete={(item) => {
                if (!window.confirm(`Delete "${item.name}"? This will remove it from your Brand Space list.`)) {
                  return;
                }
                void runBrandAction(
                  () => deleteBrand.mutateAsync(getBrandId(item)),
                  "Brand Space deleted",
                  "Unable to delete this Brand Space right now.",
                );
              }}
            />
          )}
        </SectionCard>
      </div>
    </div>
  );
}
