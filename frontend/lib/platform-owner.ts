import type {
  AnalyticsResponse,
  TenantBrandSpaceSummaryResponse,
  TenantSummaryResponse,
  TenantUsageSummary,
  TenantUserResponse,
} from "@/lib/api/contracts";

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatShortDate(value?: string | null) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(parsed);
}

export function formatMonthLabel(value: string) {
  if (!value) {
    return "";
  }
  const [year, month] = value.split("-");
  const monthIndex = Number(month) - 1;
  if (!year || Number.isNaN(monthIndex) || monthIndex < 0 || monthIndex > 11) {
    return value;
  }
  return `${MONTH_LABELS[monthIndex]} ${year}`;
}

export function getActivityLabel(value?: string | null) {
  if (!value) {
    return "Dormant";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Dormant";
  }
  const diff = Date.now() - parsed.getTime();
  const days = diff / (1000 * 60 * 60 * 24);
  return days <= 30 ? "Engaged" : "Dormant";
}

export function buildRangeLabel(start?: string, end?: string) {
  if (start && end) {
    return `${formatMonthLabel(start)} - ${formatMonthLabel(end)}`;
  }
  if (start) {
    return `${formatMonthLabel(start)} onward`;
  }
  if (end) {
    return `Until ${formatMonthLabel(end)}`;
  }
  return "Jan'26 - Dec'26";
}

export function usagePercentage(consumed = 0, limit = 0) {
  if (!limit) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round((consumed / limit) * 100)));
}

export function buildPlatformMetricCards(analytics?: AnalyticsResponse, tenants?: TenantSummaryResponse[]) {
  const metrics = analytics?.metrics || {};
  const averageContent = (tenants || []).length
    ? Math.round(
        (tenants || []).reduce((total, tenant) => total + (tenant.usage_consumption.content_generations || 0), 0) /
          (tenants || []).length,
      )
    : 0;
  const errorRate = metrics.pending_jobs && metrics.content_generations
    ? `${Math.round((Number(metrics.pending_jobs) / Math.max(Number(metrics.content_generations), 1)) * 100)}%`
    : "0%";

  return [
    { label: "Tenants", value: String(metrics.tenants || 0) },
    { label: "Brand Spaces", value: String(metrics.brand_spaces || 0) },
    { label: "Users", value: String(metrics.users || 0) },
    { label: "Avg Response Time", value: averageContent ? `${averageContent} sec` : "--" },
    { label: "Error Rate", value: errorRate },
  ];
}

export function buildTenantBreakdownRows(tenants: TenantSummaryResponse[] = []) {
  return tenants.map((tenant) => {
    const limits = tenant.usage_limits;
    const usage = tenant.usage_consumption;
    const used = (usage.content_generations || 0) + (usage.image_generations || 0) + (usage.ocr_pages || 0);
    const capacity =
      (limits?.max_content_generations || 0) + (limits?.max_image_generations || 0) + (limits?.max_ocr_pages || 0);

    return {
      id: tenant.id,
      name: tenant.name,
      createdAt: tenant.created_at,
      adminName: tenant.tenant_admin_name || "-",
      brandSpaces: tenant.brand_space_count,
      activeDate: tenant.last_active_at,
      capacityUsed: usagePercentage(used, capacity),
      usageBreakdown: {
        content: usage.content_generations || 0,
        visual: usage.image_generations || 0,
        ocr: usage.ocr_pages || 0,
        users: usage.users || 0,
      },
      tokenUsage: {
        input: Number(tenant.token_usage?.input_tokens || 0),
        output: Number(tenant.token_usage?.output_tokens || 0),
        total: Number(tenant.token_usage?.total_tokens || 0),
      },
    };
  });
}

export function buildTenantUsageSeries(tenants: TenantSummaryResponse[] = []) {
  return buildTenantBreakdownRows(tenants).map((tenant) => ({
    label: tenant.name,
    total: tenant.capacityUsed,
    content: tenant.usageBreakdown.content,
    visual: tenant.usageBreakdown.visual,
    ocr: tenant.usageBreakdown.ocr,
    users: tenant.usageBreakdown.users,
    inputTokens: tenant.tokenUsage.input,
    outputTokens: tenant.tokenUsage.output,
    totalTokens: tenant.tokenUsage.total,
  }));
}

export function buildDonutSegments(
  items: Array<{ name: string; value: number }>,
  palette = ["#F7C5EA", "#DDEEFF", "#F6E3A3", "#B9F2D0", "#DCC7FF", "#F4CFA7"],
) {
  return items.map((item, index) => ({
    ...item,
    color: palette[index % palette.length],
  }));
}

export function buildUsageWindowRows(summary?: TenantUsageSummary, metadata?: Record<string, unknown>) {
  if (!summary) {
    return [];
  }

  const usageWindow = (metadata?.usage_window as Record<string, unknown> | undefined) ?? {};
  const startMonth = typeof usageWindow.start_month === "string" ? usageWindow.start_month : "";
  const endMonth = typeof usageWindow.end_month === "string" ? usageWindow.end_month : "";
  const labels = buildMonthRange(startMonth, endMonth);

  return labels.map((label, index) => {
    const isCurrent = index === labels.length - 1;
    return {
      month: label,
      content: `${isCurrent ? summary.consumption.content_generations || 0 : 0}/${summary.limits.max_content_generations || 0}`,
      visuals: `${isCurrent ? summary.consumption.image_generations || 0 : 0}/${summary.limits.max_image_generations || 0}`,
      ocr: `${isCurrent ? summary.consumption.ocr_pages || 0 : 0}/${summary.limits.max_ocr_pages || 0}`,
      brandSpaces: `${isCurrent ? summary.consumption.brand_spaces || 0 : 0}/${summary.limits.max_brand_spaces || 0}`,
      users: `${isCurrent ? summary.consumption.users || 0 : 0}/${summary.limits.max_users || 0}`,
    };
  });
}

export function summarizeBrandSpaces(brandSpaces: TenantBrandSpaceSummaryResponse[] = []) {
  return {
    ocrSegments: buildDonutSegments(
      brandSpaces.map((brand) => ({
        name: brand.name,
        value: brand.ocr_pages,
      })),
    ),
    visualSegments: buildDonutSegments(
      brandSpaces.map((brand) => ({
        name: brand.name,
        value: brand.visual_generations,
      })),
    ),
  };
}

export function getLatestTenantAdmin(users: TenantUserResponse[] = []) {
  return users.find((user) => user.role_codes.includes("tenant_admin"));
}

function buildMonthRange(start: string, end: string) {
  if (!start || !end) {
    return ["Jan", "Feb", "Mar", "Apr", "May", "Jun"];
  }
  const [startYear, startMonth] = start.split("-").map(Number);
  const [endYear, endMonth] = end.split("-").map(Number);
  if ([startYear, startMonth, endYear, endMonth].some((value) => Number.isNaN(value))) {
    return ["Jan", "Feb", "Mar", "Apr", "May", "Jun"];
  }

  const labels: string[] = [];
  let year = startYear;
  let month = startMonth;

  while (year < endYear || (year === endYear && month <= endMonth)) {
    labels.push(MONTH_LABELS[month - 1] || `${month}`);
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
    if (labels.length > 24) {
      break;
    }
  }

  return labels;
}
