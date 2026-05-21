"use client";

import { CalendarDays } from "lucide-react";
import { PlatformPageTitle, SectionCard } from "@/components/platformOwner/PlatformOwnerPrimitives";
import { useBrands } from "@/hooks/useBrands";
import { useTenantAnalytics } from "@/hooks/useContentWorkspace";
import { useGetMe } from "@/hooks/useUser";
import { useGetTenantData, useGetTenantUsageSummary } from "@/hooks/tenantAdmins/useGetTenants";
import {
    buildMonthYearOptions,
    formatCompactMonthLabel,
    MiniMetric,
    MonthWindowPopoverButton,
    normalizeMonthWindow,
    parseUsageValue,
    ProgressRow,
} from "../Premitives";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Button } from "../ui/button";
import { useId, useMemo, useState } from "react";
import { buildUsageWindowRows, usagePercentage } from "@/lib/platform-owner";
import { CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

function toPercent(value?: number, max?: number) {
    if (!max || max <= 0) {
        return 0;
    }
    return Math.min(100, Math.round(((value || 0) / max) * 100));
}

const chartPalette = ["#f6c5e6", "#c7d7ff", "#fbe29c", "#c6f0d3", "#d9d0ff", "#ffd6ae"];

function formatDateLabel(value?: string) {
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

function formatLifecycleLabel(value: string) {
    if (value === "active") {
        return "Engaged";
    }
    return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatMonthAxisLabel(month: string, totalMonths: number) {
    const [year, monthValue] = month.split("-").map(Number);
    if (Number.isNaN(year) || Number.isNaN(monthValue) || monthValue < 1 || monthValue > 12) {
        return month;
    }

    const parsed = new Date(year, monthValue - 1, 1);
    const shortMonth = parsed.toLocaleString("en-IN", { month: "short" });
    return totalMonths <= 6 ? `${shortMonth}'${String(parsed.getFullYear()).slice(-2)}` : shortMonth;
}

function formatCount(value: number) {
    return new Intl.NumberFormat("en-US").format(value);
}

type UsageTrendSeries = {
    dataKey: string;
    label: string;
    color: string;
};

type UsageTrendPoint = {
    month: string;
    label: string;
    [key: string]: string | number;
};

function UsageTrendChart({
    data,
    series,
    emptyMessage,
}: {
    data: UsageTrendPoint[];
    series: UsageTrendSeries[];
    emptyMessage: string;
}) {
    const chartData = data.map((item) => ({
        ...item,
        axisLabel: formatMonthAxisLabel(item.month, data.length),
    }));

    return chartData.length ? (
        <div className="h-[260px] w-full">
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 12, right: 8, left: 8, bottom: 8 }}>
                    <CartesianGrid vertical={false} stroke="#EEF1F6" />
                    <XAxis
                        dataKey="axisLabel"
                        axisLine={false}
                        tickLine={false}
                        interval={0}
                        minTickGap={0}
                        tickMargin={10}
                        padding={{ left: 8, right: 8 }}
                        tick={{ fill: "#475467", fontSize: 12 }}
                    />
                    <YAxis hide />
                    <Tooltip
                        cursor={{ stroke: "#D0D5DD", strokeDasharray: "4 4" }}
                        content={<UsageTrendTooltip series={series} />}
                    />
                    {series.map((item) => (
                        <Line
                            key={item.dataKey}
                            type="monotone"
                            dataKey={item.dataKey}
                            stroke={item.color}
                            strokeWidth={2.25}
                            dot={false}
                            activeDot={{ r: 4, fill: item.color, stroke: "#FFFFFF", strokeWidth: 2 }}
                            connectNulls
                        />
                    ))}
                </LineChart>
            </ResponsiveContainer>
        </div>
    ) : (
        <div className="rounded-[8px] border border-[#E4E7EC] px-4 py-10 text-center text-sm text-[#6B7280]">
            {emptyMessage}
        </div>
    );
}

function UsageTrendTooltip({
    active,
    payload,
    label,
    series,
}: {
    active?: boolean;
    payload?: Array<{ dataKey?: string; value?: number; payload?: { label?: string } }>;
    label?: string;
    series: UsageTrendSeries[];
}) {
    if (!active || !payload?.length) {
        return null;
    }

    const tooltipLabel = payload[0]?.payload?.label || label;

    return (
        <div className="rounded-[8px] border border-[#E4E7EC] bg-white px-3 py-2 text-sm shadow-[0_18px_48px_-20px_rgba(15,23,42,0.25)]">
            <p className="mb-2 font-medium text-[#2F3342]">{tooltipLabel}</p>
            <div className="space-y-1 text-[#4B5563]">
                {series.map((item) => {
                    const seriesValue = payload.find((entry) => entry.dataKey === item.dataKey)?.value || 0;
                    return (
                        <div key={item.dataKey} className="flex items-center gap-2">
                            <span className="inline-block h-4 w-4" style={{ backgroundColor: item.color }} />
                            <span>
                                {item.label}: {formatCount(seriesValue)}
                            </span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

type BrandUsageSlice = {
    id: string;
    name: string;
    value: number;
    percentage: number;
    color: string;
};

function buildBrandUsageSlices(
    brands: Array<{ id: string; name: string }>,
    targets: Record<string, number>,
    totalValue: number,
) {
    if (!brands.length || totalValue <= 0) {
        return [] as BrandUsageSlice[];
    }

    const evenWeight = brands.length ? 100 / brands.length : 0;
    const weightedBrands = brands.map((brand, index) => ({
        id: brand.id,
        name: brand.name,
        color: chartPalette[index % chartPalette.length],
        weight: typeof targets[brand.id] === "number" && targets[brand.id] > 0 ? targets[brand.id] : evenWeight,
    }));
    const totalWeight = weightedBrands.reduce((sum, brand) => sum + brand.weight, 0);
    if (!totalWeight) {
        return [] as BrandUsageSlice[];
    }

    return weightedBrands.map((brand) => {
        const percentage = (brand.weight / totalWeight) * 100;
        return {
            id: brand.id,
            name: brand.name,
            color: brand.color,
            percentage,
            value: (totalValue * percentage) / 100,
        };
    });
}

function hexToRgba(hex: string, alpha: number) {
    const normalized = hex.replace("#", "");
    const safeHex = normalized.length === 3
        ? normalized.split("").map((char) => `${char}${char}`).join("")
        : normalized.padEnd(6, "0").slice(0, 6);
    const red = parseInt(safeHex.slice(0, 2), 16);
    const green = parseInt(safeHex.slice(2, 4), 16);
    const blue = parseInt(safeHex.slice(4, 6), 16);

    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function BrandUsagePieChart({
    chartId,
    data,
    emptyMessage,
}: {
    chartId: string;
    data: BrandUsageSlice[];
    emptyMessage: string;
}) {
    const gradientPrefix = useId().replace(/:/g, "");
    const totalValue = data.reduce((sum, item) => sum + item.value, 0);

    if (!data.length || totalValue <= 0) {
        return (
            <div className="rounded-[8px] border border-[#E4E7EC] px-4 py-10 text-center text-sm text-[#6B7280]">
                {emptyMessage}
            </div>
        );
    }

    return (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_210px] lg:items-center">
            <div className="h-[260px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <defs>
                            {data.map((item) => {
                                const gradientId = `${gradientPrefix}-${chartId}-${item.id}`;
                                return (
                                    <linearGradient key={gradientId} id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
                                        <stop offset="0%" stopColor={hexToRgba(item.color, 0.96)} />
                                        <stop offset="100%" stopColor={hexToRgba(item.color, 0.72)} />
                                    </linearGradient>
                                );
                            })}
                        </defs>
                        <Tooltip content={<BrandUsagePieTooltip />} />
                        <Pie
                            data={data}
                            dataKey="value"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            innerRadius="42%"
                            outerRadius="76%"
                            paddingAngle={1.5}
                            cornerRadius={3}
                            stroke="none"
                            isAnimationActive={false}
                        >
                            {data.map((item) => {
                                const gradientId = `${gradientPrefix}-${chartId}-${item.id}`;
                                return <Cell key={item.id} fill={`url(#${gradientId})`} />;
                            })}
                        </Pie>
                    </PieChart>
                </ResponsiveContainer>
            </div>
            <div className="max-h-[220px] space-y-3 overflow-y-auto pr-2">
                {data.map((item) => (
                    <div key={item.id} className="flex items-center gap-3 text-sm text-[#4B5563]">
                        <span
                            className="h-4 w-4 shrink-0 rounded-[2px]"
                            style={{ background: `linear-gradient(135deg, ${hexToRgba(item.color, 0.96)} 0%, ${hexToRgba(item.color, 0.72)} 100%)` }}
                        />
                        <span className="truncate">{item.name}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}

function BrandUsagePieTooltip({
    active,
    payload,
}: {
    active?: boolean;
    payload?: Array<{ payload?: BrandUsageSlice }>;
}) {
    const item = payload?.[0]?.payload;
    if (!active || !item) {
        return null;
    }

    return (
        <div className="rounded-[8px] border border-[#E4E7EC] bg-white px-4 py-3 text-sm shadow-[0_18px_48px_-20px_rgba(15,23,42,0.25)]">
            <div className="flex items-center gap-2 text-[#4B5563]">
                <span
                    className="inline-block h-4 w-4 rounded-[2px]"
                    style={{ background: `linear-gradient(135deg, ${hexToRgba(item.color, 0.96)} 0%, ${hexToRgba(item.color, 0.72)} 100%)` }}
                />
                <span>{item.name} {Math.round(item.percentage)}%</span>
            </div>
        </div>
    );
}

export default function TenantAdminDashboard() {
    const { data: analytics } = useTenantAnalytics();
    const { data: currentUser } = useGetMe();
    const { data: tenant } = useGetTenantData(currentUser?.tenantId ?? "");
    const { data: usageSummary } = useGetTenantUsageSummary(currentUser?.tenantId ?? "");
    const { data: brands } = useBrands();

    const [selectedUsageMonth, setSelectedUsageMonth] = useState("");
    const [ocrStartMonth, setOcrStartMonth] = useState("");
    const [ocrEndMonth, setOcrEndMonth] = useState("");
    const [generationStartMonth, setGenerationStartMonth] = useState("");
    const [generationEndMonth, setGenerationEndMonth] = useState("");
    const [brandUsageStartMonth, setBrandUsageStartMonth] = useState("");
    const [brandUsageEndMonth, setBrandUsageEndMonth] = useState("");


    const metrics = (analytics?.metrics || {}) as Record<string, unknown>;
    const contentGenerationCount = Number(metrics.content_generations || 0);
    const templateCount = Number(metrics.templates || 0);
    const knowledgeAssetCount = Number(metrics.knowledge_assets || 0);
    const totalCapacity = Math.round(
        [
            toPercent(usageSummary?.consumption.content_generations, usageSummary?.limits.max_content_generations),
            toPercent(usageSummary?.consumption.image_generations, usageSummary?.limits.max_image_generations),
            toPercent(usageSummary?.consumption.ocr_pages, usageSummary?.limits.max_ocr_pages),
            toPercent(usageSummary?.consumption.users, usageSummary?.limits.max_users),
            toPercent(usageSummary?.consumption.brand_spaces, usageSummary?.limits.max_brand_spaces),
        ].reduce((sum, current) => sum + current, 0) / 5,
    );
    const liveTargets = useMemo(
        () => (tenant?.metadata_json?.brand_usage_targets as Record<string, number> | undefined) ?? {},
        [tenant?.metadata_json?.brand_usage_targets],
    );
    const liveActiveBrands = useMemo(
        () => (brands || []).filter((brand) => brand.lifecycle_state !== "archived" && brand.lifecycle_state !== "deleted"),
        [brands],
    );
    const brandRows = liveActiveBrands.map((brand) => ({
        name: brand.name,
        createdAt: formatDateLabel(brand.created_at),
        createdBy: currentUser?.name || "Tenant Admin",
        activeLast30Days: formatLifecycleLabel(brand.lifecycle_state),
        lastUsed: formatDateLabel(brand.updated_at),
    }));

    const usageRows = useMemo(() => buildUsageWindowRows(usageSummary, tenant?.metadata_json), [tenant?.metadata_json, usageSummary]);
    const usageWindow = useMemo(
        () => (tenant?.metadata_json?.usage_window as Record<string, unknown> | undefined) ?? {},
        [tenant?.metadata_json?.usage_window],
    );
    const liveUsageRows = liveActiveBrands.map((brand) => {
        const percentage =
            typeof liveTargets[brand.id] === "number"
                ? liveTargets[brand.id] / 100
                : 1 / Math.max(liveActiveBrands.length || 1, 1);
        return {
            brand: brand.name,
            contentGenerations: Math.round(contentGenerationCount * percentage),
            visuals: Math.round(templateCount * percentage),
            ocrPages: Math.round(knowledgeAssetCount * percentage),
        };
    });

    const usageMonthOptions = useMemo(
        () =>
            buildMonthYearOptions(
                typeof usageWindow.start_month === "string" ? usageWindow.start_month : undefined,
                typeof usageWindow.end_month === "string" ? usageWindow.end_month : undefined,
            ),
        [usageWindow.end_month, usageWindow.start_month],
    );

     const resolvedUsageMonth = usageMonthOptions.some((option) => option.value === selectedUsageMonth)
        ? selectedUsageMonth
        : usageMonthOptions[usageMonthOptions.length - 1]?.value || "";

    const selectedUsageOption =
        usageMonthOptions.find((option) => option.value === resolvedUsageMonth) ?? usageMonthOptions[usageMonthOptions.length - 1] ?? null;

    const usageLimitRows = useMemo(
        () =>
            usageRows.map((row, index) => ({
                ...row,
                monthValue: usageMonthOptions[index]?.value || "",
                monthLabel: usageMonthOptions[index]?.label || row.month,
            })),
        [usageMonthOptions, usageRows],
    );
    const usageLimitMinMonth = usageLimitRows[0]?.monthValue || "";
    const usageLimitMaxMonth = usageLimitRows[usageLimitRows.length - 1]?.monthValue || "";
    const resolvedOcrStartMonth = usageLimitRows.some((row) => row.monthValue === ocrStartMonth)
        ? ocrStartMonth
        : usageLimitMinMonth;
    const resolvedOcrEndMonth = usageLimitRows.some((row) => row.monthValue === ocrEndMonth)
        ? ocrEndMonth
        : usageLimitMaxMonth;
    const normalizedOcrRange = useMemo(
        () => normalizeMonthWindow(resolvedOcrStartMonth, resolvedOcrEndMonth),
        [resolvedOcrEndMonth, resolvedOcrStartMonth],
    );
    const filteredOcrRows = useMemo(() => {
        if (!usageLimitRows.length) return usageLimitRows;
        if (!normalizedOcrRange.start || !normalizedOcrRange.end) {
            return usageLimitRows;
        }

        return usageLimitRows.filter((row) =>
            row.monthValue >= normalizedOcrRange.start && row.monthValue <= normalizedOcrRange.end,
        );
    }, [normalizedOcrRange.end, normalizedOcrRange.start, usageLimitRows]);
    const ocrDateLabel = useMemo(() => {
        if (!normalizedOcrRange.start || !normalizedOcrRange.end) {
            return "Select month window";
        }

        return `${formatCompactMonthLabel(normalizedOcrRange.start)} - ${formatCompactMonthLabel(normalizedOcrRange.end)}`;
    }, [normalizedOcrRange.end, normalizedOcrRange.start]);
    const ocrWindowData = useMemo(
        () =>
            filteredOcrRows.map((row) => ({
                month: row.monthValue,
                label: row.monthLabel,
                ocrPages: parseUsageValue(row.ocr).used,
            })),
        [filteredOcrRows],
    );
    const resolvedGenerationStartMonth = usageLimitRows.some((row) => row.monthValue === generationStartMonth)
        ? generationStartMonth
        : usageLimitMinMonth;
    const resolvedGenerationEndMonth = usageLimitRows.some((row) => row.monthValue === generationEndMonth)
        ? generationEndMonth
        : usageLimitMaxMonth;
    const normalizedGenerationRange = useMemo(
        () => normalizeMonthWindow(resolvedGenerationStartMonth, resolvedGenerationEndMonth),
        [resolvedGenerationEndMonth, resolvedGenerationStartMonth],
    );
    const filteredGenerationRows = useMemo(() => {
        if (!usageLimitRows.length) return usageLimitRows;
        if (!normalizedGenerationRange.start || !normalizedGenerationRange.end) {
            return usageLimitRows;
        }

        return usageLimitRows.filter((row) =>
            row.monthValue >= normalizedGenerationRange.start && row.monthValue <= normalizedGenerationRange.end,
        );
    }, [normalizedGenerationRange.end, normalizedGenerationRange.start, usageLimitRows]);
    const generationDateLabel = useMemo(() => {
        if (!normalizedGenerationRange.start || !normalizedGenerationRange.end) {
            return "Select month window";
        }

        return `${formatCompactMonthLabel(normalizedGenerationRange.start)} - ${formatCompactMonthLabel(normalizedGenerationRange.end)}`;
    }, [normalizedGenerationRange.end, normalizedGenerationRange.start]);
    const generationWindowData = useMemo(
        () =>
            filteredGenerationRows.map((row) => {
                const contentMetric = parseUsageValue(row.content);
                const visualsMetric = parseUsageValue(row.visuals);
                return {
                    month: row.monthValue,
                    label: row.monthLabel,
                    visuals: visualsMetric.used,
                    content: contentMetric.used,
                };
            }),
        [filteredGenerationRows],
    );
    const resolvedBrandUsageStartMonth = usageLimitRows.some((row) => row.monthValue === brandUsageStartMonth)
        ? brandUsageStartMonth
        : usageLimitMinMonth;
    const resolvedBrandUsageEndMonth = usageLimitRows.some((row) => row.monthValue === brandUsageEndMonth)
        ? brandUsageEndMonth
        : usageLimitMaxMonth;
    const normalizedBrandUsageRange = useMemo(
        () => normalizeMonthWindow(resolvedBrandUsageStartMonth, resolvedBrandUsageEndMonth),
        [resolvedBrandUsageEndMonth, resolvedBrandUsageStartMonth],
    );
    const filteredBrandUsageRows = useMemo(() => {
        if (!usageLimitRows.length) return usageLimitRows;
        if (!normalizedBrandUsageRange.start || !normalizedBrandUsageRange.end) {
            return usageLimitRows;
        }

        return usageLimitRows.filter((row) =>
            row.monthValue >= normalizedBrandUsageRange.start && row.monthValue <= normalizedBrandUsageRange.end,
        );
    }, [normalizedBrandUsageRange.end, normalizedBrandUsageRange.start, usageLimitRows]);
    const brandUsageDateLabel = useMemo(() => {
        if (!normalizedBrandUsageRange.start || !normalizedBrandUsageRange.end) {
            return "Select month window";
        }

        return `${formatCompactMonthLabel(normalizedBrandUsageRange.start)} - ${formatCompactMonthLabel(normalizedBrandUsageRange.end)}`;
    }, [normalizedBrandUsageRange.end, normalizedBrandUsageRange.start]);
    const brandOcrTotal = useMemo(
        () => filteredBrandUsageRows.reduce((sum, row) => sum + parseUsageValue(row.ocr).used, 0),
        [filteredBrandUsageRows],
    );
    const brandAiTotal = useMemo(
        () =>
            filteredBrandUsageRows.reduce((sum, row) => {
                const contentMetric = parseUsageValue(row.content);
                const visualsMetric = parseUsageValue(row.visuals);
                return sum + contentMetric.used + visualsMetric.used;
            }, 0),
        [filteredBrandUsageRows],
    );
    const brandUsageBrands = useMemo(
        () => liveActiveBrands.map((brand) => ({ id: brand.id, name: brand.name })),
        [liveActiveBrands],
    );
    const brandOcrSlices = useMemo(
        () => buildBrandUsageSlices(brandUsageBrands, liveTargets, brandOcrTotal),
        [brandOcrTotal, brandUsageBrands, liveTargets],
    );
    const brandAiSlices = useMemo(
        () => buildBrandUsageSlices(brandUsageBrands, liveTargets, brandAiTotal),
        [brandAiTotal, brandUsageBrands, liveTargets],
    );

    const resetOcrWindow = () => {
        setOcrStartMonth(usageLimitMinMonth);
        setOcrEndMonth(usageLimitMaxMonth);
    };
    const resetGenerationWindow = () => {
        setGenerationStartMonth(usageLimitMinMonth);
        setGenerationEndMonth(usageLimitMaxMonth);
    };
    const resetBrandUsageWindow = () => {
        setBrandUsageStartMonth(usageLimitMinMonth);
        setBrandUsageEndMonth(usageLimitMaxMonth);
    };

    const selectedUsageMetrics = (() => {
        const fallbackMetrics = {
            totalCapacity,
            contentPercent: usagePercentage(usageSummary?.consumption.content_generations || 0, usageSummary?.limits.max_content_generations || 0),
            visualsPercent: usagePercentage(usageSummary?.consumption.image_generations || 0, usageSummary?.limits.max_image_generations || 0),
            ocrPercent: usagePercentage(usageSummary?.consumption.ocr_pages || 0, usageSummary?.limits.max_ocr_pages || 0),
            brandSpacesUsed: usageSummary?.consumption.brand_spaces || 0,
            brandSpacesLimit: usageSummary?.limits.max_brand_spaces || 0,
            usersUsed: usageSummary?.consumption.users || 0,
            usersLimit: usageSummary?.limits.max_users || 0,
        };

        const selectedIndex = usageMonthOptions.findIndex((option) => option.value === resolvedUsageMonth);
        const selectedRow = selectedIndex >= 0 ? usageRows[selectedIndex] : null;
        if (!selectedRow) {
            return fallbackMetrics;
        }

        const contentMetric = parseUsageValue(selectedRow.content);
        const visualsMetric = parseUsageValue(selectedRow.visuals);
        const ocrMetric = parseUsageValue(selectedRow.ocr);
        const brandSpacesMetric = parseUsageValue(selectedRow.brandSpaces);
        const usersMetric = parseUsageValue(selectedRow.users);

        return {
            totalCapacity: usagePercentage(
                contentMetric.used + visualsMetric.used + ocrMetric.used,
                contentMetric.limit + visualsMetric.limit + ocrMetric.limit,
            ),
            contentPercent: usagePercentage(contentMetric.used, contentMetric.limit),
            visualsPercent: usagePercentage(visualsMetric.used, visualsMetric.limit),
            ocrPercent: usagePercentage(ocrMetric.used, ocrMetric.limit),
            brandSpacesUsed: brandSpacesMetric.used,
            brandSpacesLimit: brandSpacesMetric.limit,
            usersUsed: usersMetric.used,
            usersLimit: usersMetric.limit,
        };
    })();

    return (
        <div className="w-full px-5 py-5">
            <div className="mx-auto max-w-6xl space-y-6">
                <PlatformPageTitle title="Dashboard" ></PlatformPageTitle>
                <SectionCard title="Monthly Usage"
                    toolbar={
                        <Popover>
                            <PopoverTrigger asChild>
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="h-10 rounded-xs border-[#D5D8E8] bg-white px-3 text-sm font-medium text-[#4B5563] shadow-none hover:bg-[#FAFAFD]"
                                >
                                    <CalendarDays className="mr-2 h-4 w-4 text-[#4B5563]" />
                                    {selectedUsageOption?.label || "Select month"}
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent align="end" className="w-45 rounded-[10px] border border-[#D5D8E8] bg-white p-2 shadow-[0_18px_48px_-20px_rgba(15,23,42,0.35)]">
                                <div className="space-y-1">
                                    {usageMonthOptions.map((option) => {
                                        const isActive = option.value === resolvedUsageMonth;
                                        return (
                                            <button
                                                key={option.value}
                                                type="button"
                                                onClick={() => setSelectedUsageMonth(option.value)}
                                                className={`w-full rounded-[8px] px-3 py-2 text-left text-sm font-medium transition ${isActive
                                                    ? "bg-[#F5F6FB] text-[#2F3342]"
                                                    : "text-[#6B7280] hover:bg-[#FAFAFD]"
                                                    }`}
                                            >
                                                {option.label}
                                            </button>
                                        );
                                    })}
                                </div>
                            </PopoverContent>
                        </Popover>
                    }
                >
                    <div className="space-y-4">
                        <ProgressRow label="Total Capacity" value={selectedUsageMetrics.totalCapacity} icon="/tenants/capacity.svg" />
                        <div className="grid gap-4 md:grid-cols-3">
                            <MiniMetric label="Content" progress={true} value={selectedUsageMetrics.contentPercent} icon="/tenants/content.svg" />
                            <MiniMetric label="Visuals" progress={true} value={selectedUsageMetrics.visualsPercent} icon="/tenants/visuals.svg" />
                            <MiniMetric label="OCR Pages" progress={true} value={selectedUsageMetrics.ocrPercent} icon="/tenants/ocr_pages.svg" />
                        </div>
                    </div>

                </SectionCard>
                <div className="grid gap-4 md:grid-cols-2">
                    <MiniMetric label="Brand Spaces" value={selectedUsageMetrics.brandSpacesUsed} helper={`${selectedUsageMetrics.brandSpacesLimit}`} compact icon="/tenants/brand_spaces.svg" />
                    <MiniMetric label="Users" value={selectedUsageMetrics.usersUsed} helper={`${selectedUsageMetrics.usersLimit}`} compact icon="/tenants/users.svg" />
                </div>

                <div className="grid gap-4 xl:grid-cols-2">
                    <SectionCard
                        title="Total OCR Pages"
                        toolbar={
                            <MonthWindowPopoverButton
                                label={ocrDateLabel}
                                startMonth={resolvedOcrStartMonth}
                                endMonth={resolvedOcrEndMonth}
                                minMonth={usageLimitMinMonth}
                                maxMonth={usageLimitMaxMonth}
                                onStartChange={setOcrStartMonth}
                                onEndChange={setOcrEndMonth}
                                onReset={resetOcrWindow}
                            />
                        }
                    >
                        <UsageTrendChart
                            data={ocrWindowData}
                            series={[{ dataKey: "ocrPages", label: "OCR Pages", color: "#7E7E7E" }]}
                            emptyMessage="No OCR usage is available for the selected window."
                        />
                    </SectionCard>

                    <SectionCard
                        title="Total Generations"
                        toolbar={
                            <MonthWindowPopoverButton
                                label={generationDateLabel}
                                startMonth={resolvedGenerationStartMonth}
                                endMonth={resolvedGenerationEndMonth}
                                minMonth={usageLimitMinMonth}
                                maxMonth={usageLimitMaxMonth}
                                onStartChange={setGenerationStartMonth}
                                onEndChange={setGenerationEndMonth}
                                onReset={resetGenerationWindow}
                            />
                        }
                    >
                        <div className="space-y-5">
                            <div className="space-y-2 text-xs text-slate-500">
                                <div className="flex items-center gap-2">
                                    <span className="inline-block h-4 w-4 bg-[#A9A9A9]" />
                                    <span>Visuals</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="inline-block h-4 w-4 bg-[#595959]" />
                                    <span>Content</span>
                                </div>
                            </div>
                            <UsageTrendChart
                                data={generationWindowData}
                                series={[
                                    { dataKey: "visuals", label: "Visuals", color: "#A9A9A9" },
                                    { dataKey: "content", label: "Content", color: "#595959" },
                                ]}
                                emptyMessage="No generation usage is available for the selected window."
                            />
                        </div>
                    </SectionCard>
                </div>

                <SectionCard title="Brand Spaces" >
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-left text-sm">
                            <thead className="bg-slate-50 text-slate-500">
                                <tr>
                                    <th className="px-5 py-3 font-medium">Name</th>
                                    <th className="px-5 py-3 font-medium">Date Created</th>
                                    <th className="px-5 py-3 font-medium">Created By</th>
                                    <th className="px-5 py-3 font-medium">Active (Last 30 Days)</th>
                                    <th className="px-5 py-3 font-medium">Last Used</th>
                                </tr>
                            </thead>
                            <tbody>
                                {brandRows.map((brand) => (
                                    <tr key={brand.name} className="border-t border-slate-100 text-slate-600">
                                        <td className="px-5 py-3">{brand.name}</td>
                                        <td className="px-5 py-3">{brand.createdAt}</td>
                                        <td className="px-5 py-3">{brand.createdBy}</td>
                                        <td className="px-5 py-3">{brand.activeLast30Days}</td>
                                        <td className="px-5 py-3">{brand.lastUsed}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </SectionCard>

                <div className="grid gap-4 xl:grid-cols-2">
                    <SectionCard
                        title="Brand OCR Usage"
                        toolbar={
                            <MonthWindowPopoverButton
                                label={brandUsageDateLabel}
                                startMonth={resolvedBrandUsageStartMonth}
                                endMonth={resolvedBrandUsageEndMonth}
                                minMonth={usageLimitMinMonth}
                                maxMonth={usageLimitMaxMonth}
                                onStartChange={setBrandUsageStartMonth}
                                onEndChange={setBrandUsageEndMonth}
                                onReset={resetBrandUsageWindow}
                            />
                        }
                    >
                        <BrandUsagePieChart
                            chartId="brand-ocr"
                            data={brandOcrSlices}
                            emptyMessage="No brand OCR usage is available for the selected window."
                        />
                    </SectionCard>

                    <SectionCard
                        title="Brand AI Usage"
                        toolbar={
                            <MonthWindowPopoverButton
                                label={brandUsageDateLabel}
                                startMonth={resolvedBrandUsageStartMonth}
                                endMonth={resolvedBrandUsageEndMonth}
                                minMonth={usageLimitMinMonth}
                                maxMonth={usageLimitMaxMonth}
                                onStartChange={setBrandUsageStartMonth}
                                onEndChange={setBrandUsageEndMonth}
                                onReset={resetBrandUsageWindow}
                            />
                        }
                    >
                        <BrandUsagePieChart
                            chartId="brand-ai"
                            data={brandAiSlices}
                            emptyMessage="No brand AI usage is available for the selected window."
                        />
                    </SectionCard>
                </div>

                <SectionCard title="Usage Overview">
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-left text-sm">
                            <thead className="bg-slate-50 text-slate-500">
                                <tr>
                                    <th className="px-5 py-3 font-medium">Brand</th>
                                    <th className="px-5 py-3 font-medium">Content Generations</th>
                                    <th className="px-5 py-3 font-medium">Visuals</th>
                                    <th className="px-5 py-3 font-medium">OCR Pages</th>
                                </tr>
                            </thead>
                            <tbody>
                                {liveUsageRows.map((row) => (
                                    <tr key={row.brand} className="border-t border-slate-100 text-slate-600">
                                        <td className="px-5 py-3">{row.brand}</td>
                                        <td className="px-5 py-3">{row.contentGenerations}</td>
                                        <td className="px-5 py-3">{row.visuals}</td>
                                        <td className="px-5 py-3">{row.ocrPages}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </SectionCard>
            </div>
        </div>
    );
}
