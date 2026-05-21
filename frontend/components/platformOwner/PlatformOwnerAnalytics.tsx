"use client";

import { useMemo, useState } from "react";
import { DonutChart } from "@/components/common/DesignPrimitives";
import {
  DatePill,
  PlatformPageTitle,
  SectionCard,
  SimpleBarChart,
  ToolbarToggle,
} from "@/components/platformOwner/PlatformOwnerPrimitives";
import type { TenantSummaryResponse } from "@/lib/api/contracts";
import { buildRangeLabel, buildTenantBreakdownRows, buildTenantUsageSeries, formatShortDate } from "@/lib/platform-owner";

export default function PlatformOwnerAnalytics({ tenants }: { tenants: TenantSummaryResponse[] }) {
  const [metric, setMetric] = useState("content");
  const tenantRows = useMemo(() => buildTenantBreakdownRows(tenants), [tenants]);
  const usageSeries = useMemo(() => buildTenantUsageSeries(tenants).slice(0, 10), [tenants]);
  const dateLabel = useMemo(() => {
    const firstTenant = tenants[0];
    const usageWindow = firstTenant?.metadata_json?.usage_window as Record<string, unknown> | undefined;
    return buildRangeLabel(
      typeof usageWindow?.start_month === "string" ? usageWindow.start_month : undefined,
      typeof usageWindow?.end_month === "string" ? usageWindow.end_month : undefined,
    );
  }, [tenants]);

  const segments = useMemo(
    () =>
      usageSeries.map((item, index) => ({
        name: item.label,
        color: ["#F7C5EA", "#DDEEFF", "#F6E3A3", "#B9F2D0", "#DCC7FF", "#F4CFA7"][index % 6],
        value:
          metric === "content"
            ? item.content
            : metric === "visual"
              ? item.visual
              : metric === "ocr"
                ? item.ocr
                : item.users,
      })),
    [metric, usageSeries],
  );

  const barData = useMemo(
    () =>
      usageSeries.map((item) => ({
        label: item.label.slice(0, 3),
        primary:
          metric === "content"
            ? item.content
            : metric === "visual"
              ? item.visual
              : metric === "ocr"
                ? item.ocr
                : item.users,
        secondary: item.total,
      })),
    [metric, usageSeries],
  );

  return (
    <div className="w-full px-6 py-6">
      <div className="max-w-[1110px] space-y-6">
        <PlatformPageTitle title="Analytics" />

        <SectionCard
          title="Platform Usage by Tenant"
          toolbar={
            <div className="flex items-center gap-3">
              <ToolbarToggle
                items={[
                  { id: "content", label: "Content" },
                  { id: "visual", label: "Visual" },
                  { id: "ocr", label: "OCR" },
                  { id: "users", label: "User" },
                ]}
                active={metric}
                onChange={setMetric}
              />
              <DatePill label={dateLabel} />
            </div>
          }
        >
          <SimpleBarChart data={barData} />
        </SectionCard>

        <div className="grid gap-4 xl:grid-cols-2">
          <SectionCard title="Usage Split by Tenant" toolbar={<DatePill label={dateLabel} />}>
            <DonutChart segments={segments.length ? segments : [{ name: "No data", value: 1, color: "#DDEEFF" }]} />
          </SectionCard>
          <SectionCard title="Top Tenant Activity" toolbar={<DatePill label={dateLabel} />}>
            <div className="space-y-3">
              {tenantRows.slice(0, 6).map((tenant) => (
                <div key={tenant.id} className="flex items-center justify-between border-b border-[#F1F2F6] pb-3 text-sm text-[#4B5563] last:border-none last:pb-0">
                  <span>{tenant.name}</span>
                  <span>{formatShortDate(tenant.activeDate)}</span>
                </div>
              ))}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
