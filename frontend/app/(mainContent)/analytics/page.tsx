"use client";

import LoaderFullscreen from "@/components/LoaderFullscreen";
import PlatformOwnerAnalytics from "@/components/platformOwner/PlatformOwnerAnalytics";
import { MetricTile, PlatformPageTitle, SectionCard } from "@/components/platformOwner/PlatformOwnerPrimitives";
import { useTenantAnalytics } from "@/hooks/useContentWorkspace";
import { useRBAC } from "@/hooks/useRBAC";
import { useGetTenants } from "@/hooks/tenantAdmins/useGetTenants";

export default function AnalyticsPage() {
  const { user } = useRBAC();
  const isPlatformOwner = user?.role === "PLATFORM_OWNER";
  const isTenantAdmin = user?.role === "TENANT_ADMIN";
  const { data: tenants, isLoading: isTenantListLoading } = useGetTenants(isPlatformOwner);
  const { data: tenantAnalytics, isLoading: isTenantLoading } = useTenantAnalytics(isTenantAdmin);

  if (!user || (isPlatformOwner && isTenantListLoading) || (isTenantAdmin && isTenantLoading)) {
    return <LoaderFullscreen />;
  }

  if (isPlatformOwner) {
    return <PlatformOwnerAnalytics tenants={tenants || []} />;
  }

  if (!isTenantAdmin) {
    return (
      <div className="w-full px-5 py-5">
        <div className="mx-auto max-w-[1110px] space-y-6">
          <PlatformPageTitle title="Analytics" />
          <SectionCard title="Analytics">
            <p className="text-sm text-slate-500">Analytics is only available for platform owners and tenant admins.</p>
          </SectionCard>
        </div>
      </div>
    );
  }

  const metrics = tenantAnalytics?.metrics || {};
  const usage = (metrics.usage as Record<string, number> | undefined) || {};
  const tokenUsage = (metrics.token_usage as Record<string, number> | undefined) || {};
  const summaryTiles = [
    { label: "Brand Spaces", value: metrics.number_of_brand_spaces },
    { label: "Users", value: metrics.total_users },
    { label: "Content Generations", value: metrics.content_generations },
    { label: "Knowledge Assets", value: metrics.knowledge_assets },
    { label: "Templates", value: metrics.templates },
    { label: "Chat Sessions", value: metrics.chat_sessions },
    { label: "Pending Jobs", value: metrics.pending_jobs },
    { label: "OCR Pages Used", value: usage.ocr_pages },
    { label: "Image Generations", value: usage.image_generations },
    { label: "Input Tokens", value: tokenUsage.input_tokens },
    { label: "Output Tokens", value: tokenUsage.output_tokens },
    { label: "Total Tokens", value: tokenUsage.total_tokens },
  ].filter((item) => item.value !== undefined);

  return (
    <div className="w-full px-5 py-5">
      <div className="mx-auto max-w-[1110px] space-y-6">
        <PlatformPageTitle title="Analytics" />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {summaryTiles.length ? (
            summaryTiles.map((item) => (
              <MetricTile
                key={item.label}
                label={item.label}
                value={String(item.value ?? 0)}
              />
            ))
          ) : (
            <SectionCard title="Analytics">
              <p className="text-sm text-slate-500">No analytics are available yet for this role.</p>
            </SectionCard>
          )}
        </div>
      </div>
    </div>
  );
}
