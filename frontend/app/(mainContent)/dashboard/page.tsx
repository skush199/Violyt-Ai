"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import LoaderFullscreen from "@/components/LoaderFullscreen";
import BrandSpaces from "@/components/brandSpaces/BrandSpaces";
import PlatformOwnerDashboard from "@/components/platformOwner/PlatformOwnerDashboard";
import TenantAdminDashboard from "@/components/tenants/TenantAdminDashboard";
import { Button } from "@/components/ui/button";
import { PageHeading, SurfaceCard } from "@/components/common/DesignPrimitives";
import { usePlatformAnalytics } from "@/hooks/useContentWorkspace";
import { useRBAC } from "@/hooks/useRBAC";
import { useBrands } from "@/hooks/useBrands";
import { useGetTenants } from "@/hooks/tenantAdmins/useGetTenants";

export default function DashboardPage() {
  const router = useRouter();
  const { user } = useRBAC();
  const { data: platformAnalytics } = usePlatformAnalytics(user?.role === "PLATFORM_OWNER");
  const { data: tenants } = useGetTenants(user?.role === "PLATFORM_OWNER");
  const { data: brands } = useBrands(user?.role === "TENANT_ADMIN" || user?.role === "TENANT_USER" || user?.role === "BRAND_USER");

  useEffect(() => {
    if (user?.role === "BRAND_USER") {
      router.replace("/brand_space");
    }
  }, [router, user?.role]);

  if (!user) {
    return <LoaderFullscreen />;
  }

  if (user.role === "PLATFORM_OWNER") {
    return <PlatformOwnerDashboard analytics={platformAnalytics} tenants={tenants || []} />;
  }

  if (user.role === "BRAND_USER") {
    return <LoaderFullscreen />;
  }

  if (user.role === "TENANT_USER") {
    return (
      <div className="w-full">
        <TenantAdminDashboard />
      </div>
    );
  }

  if (user.role !== "TENANT_ADMIN") {
    return (
      <div className="w-full space-y-6 p-5">
        <PageHeading
          title="Workspace Overview"
          actions={
            <Button className="rounded-none bg-primary px-5 py-4 text-base hover:bg-primary/90" onClick={() => router.push("/brand_space")}>
              Open Brand Spaces
            </Button>
          }
        />
        <div className="grid gap-4 xl:grid-cols-[1.4fr_0.8fr]">
          <SurfaceCard className="space-y-4 p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-lg font-semibold text-slate-900">Assigned Brand Spaces</p>
                <p className="text-sm text-slate-500">Use these spaces to generate content, visuals, and share outputs for review.</p>
              </div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                {brands?.length || 0} assigned
              </span>
            </div>
            <BrandSpaces items={brands || []} />
          </SurfaceCard>

          <div className="space-y-4">
            <SurfaceCard className="space-y-3 p-5">
              <p className="text-lg font-semibold text-slate-900">Account Snapshot</p>
              <DetailRow label="Role" value={user.role} />
              <DetailRow label="Email" value={user.email} />
              <DetailRow label="Brand Access" value={String(brands?.length || 0)} />
            </SurfaceCard>
            <SurfaceCard className="space-y-3 p-5">
              <p className="text-lg font-semibold text-slate-900">Recommended Next Step</p>
              <p className="text-sm leading-6 text-slate-500">
                Open a brand space to continue creating campaign content, review outputs, and refine assets with the studio controls.
              </p>
              <Button variant="outline" className="w-full rounded-none" onClick={() => router.push("/brand_space")}>
                Go to workspace
              </Button>
            </SurfaceCard>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full">
      <TenantAdminDashboard />
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 pb-3 last:border-none last:pb-0">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm font-medium text-slate-800">{value}</span>
    </div>
  );
}
