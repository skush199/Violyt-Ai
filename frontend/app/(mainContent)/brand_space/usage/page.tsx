"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { StyledInput } from "@/components/brandSpaces/tabs/FormFields";
import {
  MetricTile,
  PlatformPageTitle,
  SectionCard,
} from "@/components/platformOwner/PlatformOwnerPrimitives";
import { useBrands } from "@/hooks/useBrands";
import { useGetMe } from "@/hooks/useUser";
import { useGetTenantData } from "@/hooks/tenantAdmins/useGetTenants";
import { useUpdateTenantAdmin } from "@/hooks/tenantAdmins/useUpdateTenant";

type UsageRow = {
  id: string;
  name: string;
  value: number;
};

export default function BrandUsageAllocationPage() {
  const { data: currentUser } = useGetMe();
  const tenantId = currentUser?.tenantId ?? "";
  const { data: tenant } = useGetTenantData(tenantId);
  const { data: brands } = useBrands();
  const updateTenant = useUpdateTenantAdmin();

  const initialRows = useMemo<UsageRow[]>(() => {
    const configuredTargets = (tenant?.metadata_json?.brand_usage_targets as Record<string, number> | undefined) ?? {};
    const activeBrands = (brands || []).filter((brand) => brand.lifecycle_state !== "archived" && brand.lifecycle_state !== "deleted");
    if (!activeBrands.length) {
      return [];
    }
    const evenSplit = Math.floor(100 / activeBrands.length);
    return activeBrands.map((brand, index) => ({
      id: brand.id,
      name: brand.name,
      value:
        typeof configuredTargets[brand.id] === "number"
          ? configuredTargets[brand.id]
          : index === activeBrands.length - 1
            ? 100 - evenSplit * (activeBrands.length - 1)
            : evenSplit,
    }));
  }, [brands, tenant?.metadata_json?.brand_usage_targets]);

  const [rows, setRows] = useState<UsageRow[]>(initialRows);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    setRows(initialRows);
  }, [initialRows]);

  const total = rows.reduce((sum, row) => sum + row.value, 0);

  return (
    <div className="w-full px-5 py-5">
      <div className="mx-auto max-w-[1110px] space-y-6">
        <PlatformPageTitle
          title="Edit Capacity Usage"
          action={
            <Button
              className="h-12 rounded-[10px] bg-primary px-6 text-[15px] font-medium hover:bg-primary/90"
              onClick={() => {
                if (!tenantId || !tenant) {
                  setError("Tenant context is missing.");
                  return;
                }
                if (total !== 100) {
                  setError("Brand usage allocation must total exactly 100% before saving.");
                  return;
                }
                setError(null);
                updateTenant.mutate(
                  {
                    id: tenantId,
                    data: {
                      metadata_json: {
                        ...(tenant.metadata_json || {}),
                        brand_usage_targets: Object.fromEntries(rows.map((row) => [row.id, row.value])),
                      },
                    },
                  },
                  {
                    onSuccess: () => setFeedback("Usage allocation saved successfully."),
                    onError: () => setError("Unable to save usage allocation right now."),
                  },
                );
              }}
            >
              {updateTenant.isPending ? "Saving..." : "Save"}
            </Button>
          }
        />

        <div className="grid gap-4 md:grid-cols-3">
          <MetricTile label="Assigned Brands" value={String(rows.length)} />
          <MetricTile label="Current Total" value={`${total}%`} />
          <MetricTile label="Status" value={total === 100 ? "Balanced" : "Needs review"} />
        </div>

        <SectionCard title="Usage Overview">
          <div className="space-y-1">
            <p className="text-sm text-[#6B7280]">
              This does not restrict usage. It helps track usage and triggers alerts as the limit approaches.
            </p>
            {feedback ? <p className="text-sm text-emerald-600">{feedback}</p> : null}
            {error ? <p className="text-sm text-red-500">{error}</p> : null}
          </div>

          <div className="max-w-[720px] overflow-hidden rounded-[2px] border border-[#ECEEF5] bg-[#FAFBFF]">
            <div className="grid grid-cols-[1.2fr_1fr] bg-[#F5F6FB] text-sm font-medium text-[#4B5563]">
              <div className="border-r border-white px-4 py-3">Brand</div>
              <div className="px-4 py-3">Usage</div>
            </div>
            <div className="divide-y divide-slate-100 bg-white">
              {rows.map((row) => (
                <div key={row.id} className="grid grid-cols-[1.2fr_1fr]">
                  <div className="border-r border-slate-100 px-4 py-4 text-sm font-medium text-[#2F3342]">{row.name}</div>
                  <div className="px-4 py-2">
                    <StyledInput
                      type="number"
                      min={0}
                      max={100}
                      value={String(row.value)}
                      onChange={(event) => {
                        const nextValue = Math.max(0, Math.min(100, Number(event.target.value || 0)));
                        setRows((current) => current.map((item) => (item.id === row.id ? { ...item, value: nextValue } : item)));
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <p className="text-sm text-[#6B7280]">Current total allocation: {total}%</p>
        </SectionCard>
      </div>
    </div>
  );
}
