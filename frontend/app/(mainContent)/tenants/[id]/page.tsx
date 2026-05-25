"use client";

import { useMemo, useState } from "react";
import { CalendarDays, Trash2 } from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { toast } from "@/components/ui/use-toast";
import {
    DatePill,
    PlatformPageTitle,
    PlatformTabSwitcher,
    SectionCard,
    ToolbarToggle,
} from "@/components/platformOwner/PlatformOwnerPrimitives";
import { useGetTenantBrandSpaces, useGetTenantData, useGetTenantUsageSummary, useGetTenantUsers } from "@/hooks/tenantAdmins/useGetTenants";
import { useDeleteTenantAdmin, useUpdateTenantAdmin } from "@/hooks/tenantAdmins/useUpdateTenant";
import {
    buildRangeLabel,
    buildUsageWindowRows,
    formatShortDate,
    getActivityLabel,
    summarizeBrandSpaces,
    usagePercentage,
} from "@/lib/platform-owner";
import Image from "next/image";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { buildMonthYearOptions, formatCompactMonthLabel, GradientDonutChart, MiniMetric, MonthWindowPopoverButton, normalizeMonthWindow, parseMonthValue, parseUsageValue, ProgressRow } from "@/components/Premitives";

export default function TenantDetailsPage() {
    const params = useParams<{ id: string }>();
    const router = useRouter();
    const searchParams = useSearchParams();
    const tenantId = params.id;
    const { data: tenant, isLoading } = useGetTenantData(tenantId);
    const { data: users } = useGetTenantUsers(tenantId);
    const { data: usage } = useGetTenantUsageSummary(tenantId);
    const { data: brandSpaces } = useGetTenantBrandSpaces(tenantId);
    const { mutate: updateTenant, isPending: isUpdatingTenant } = useUpdateTenantAdmin();
    const { mutateAsync: deleteTenant, isPending: isDeletingTenant } = useDeleteTenantAdmin();
    const [tab, setTab] = useState("tenant");
    const [provider, setProvider] = useState("openai");
    const [selectedUsageMonth, setSelectedUsageMonth] = useState("");
    const [usageLimitStartMonth, setUsageLimitStartMonth] = useState("");
    const [usageLimitEndMonth, setUsageLimitEndMonth] = useState("");
    const [ocrStartMonth, setOcrStartMonth] = useState("");
    const [ocrEndMonth, setOcrEndMonth] = useState("");
    const [generationStartMonth, setGenerationStartMonth] = useState("");
    const [generationEndMonth, setGenerationEndMonth] = useState("");
    const [brandUsageStartMonth, setBrandUsageStartMonth] = useState("");
    const [brandUsageEndMonth, setBrandUsageEndMonth] = useState("");

    const usageWindow = useMemo(
        () => (tenant?.metadata_json?.usage_window as Record<string, unknown> | undefined) ?? {},
        [tenant?.metadata_json?.usage_window],
    );
    const usageMonthOptions = useMemo(
        () =>
            buildMonthYearOptions(
                typeof usageWindow.start_month === "string" ? usageWindow.start_month : undefined,
                typeof usageWindow.end_month === "string" ? usageWindow.end_month : undefined,
            ),
        [usageWindow.end_month, usageWindow.start_month],
    );
    const dateLabel = useMemo(
        () =>
            buildRangeLabel(
                typeof usageWindow.start_month === "string" ? usageWindow.start_month : undefined,
                typeof usageWindow.end_month === "string" ? usageWindow.end_month : undefined,
            ),
        [usageWindow],
    );
    const totalCapacity = usage
        ? usagePercentage(
            (usage.consumption.content_generations || 0) +
            (usage.consumption.image_generations || 0) +
            (usage.consumption.ocr_pages || 0),
            usage.limits.max_content_generations + usage.limits.max_image_generations + usage.limits.max_ocr_pages,
        )
        : 0;
    const usageRows = useMemo(() => buildUsageWindowRows(usage, tenant?.metadata_json), [tenant?.metadata_json, usage]);
    const brandCharts = useMemo(() => summarizeBrandSpaces(brandSpaces || []), [brandSpaces]);
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
    const resolvedUsageLimitStartMonth = usageLimitRows.some((row) => row.monthValue === usageLimitStartMonth)
        ? usageLimitStartMonth
        : usageLimitMinMonth;
    const resolvedUsageLimitEndMonth = usageLimitRows.some((row) => row.monthValue === usageLimitEndMonth)
        ? usageLimitEndMonth
        : usageLimitMaxMonth;
    const normalizedUsageLimitRange = useMemo(
        () => normalizeMonthWindow(resolvedUsageLimitStartMonth, resolvedUsageLimitEndMonth),
        [resolvedUsageLimitEndMonth, resolvedUsageLimitStartMonth],
    );
    const filteredUsageRows = useMemo(() => {
        if (!usageLimitRows.length) return usageLimitRows;
        if (!normalizedUsageLimitRange.start || !normalizedUsageLimitRange.end) {
            return usageLimitRows;
        }

        return usageLimitRows.filter((row) =>
            row.monthValue >= normalizedUsageLimitRange.start && row.monthValue <= normalizedUsageLimitRange.end,
        );
    }, [normalizedUsageLimitRange.end, normalizedUsageLimitRange.start, usageLimitRows]);
    const usageLimitDateLabel = useMemo(() => {
        if (!normalizedUsageLimitRange.start || !normalizedUsageLimitRange.end) {
            return "Select month window";
        }

        return `${formatCompactMonthLabel(normalizedUsageLimitRange.start)} - ${formatCompactMonthLabel(normalizedUsageLimitRange.end)}`;
    }, [normalizedUsageLimitRange.end, normalizedUsageLimitRange.start]);
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
    const llmMonthlyUsage = useMemo(
        () => resolveTenantProviderMonthlyUsage(tenant, provider),
        [provider, tenant],
    );
    const llmWindowData = useMemo(() => {
        const usageByMonth = new Map(llmMonthlyUsage.map((item) => [item.month, item]));
        return filteredUsageRows.map((row) => {
            const monthUsage = usageByMonth.get(row.monthValue);
            return {
                month: row.monthValue,
                label: row.monthLabel,
                inputTokens: monthUsage?.input_tokens || 0,
                outputTokens: monthUsage?.output_tokens || 0,
            };
        });
    }, [filteredUsageRows, llmMonthlyUsage]);

    const llmTotals = useMemo(
        () =>
            llmWindowData.reduce(
                (totals, item) => ({
                    inputTokens: totals.inputTokens + item.inputTokens,
                    outputTokens: totals.outputTokens + item.outputTokens,
                }),
                { inputTokens: 0, outputTokens: 0 },
            ),
        [llmWindowData],
    );
    const ocrWindowData = useMemo(
        () =>
            filteredOcrRows.map((row) => ({
                month: row.monthValue,
                label: row.monthLabel,
                ocrPages: parseUsageValue(row.ocr).used,
            })),
        [filteredOcrRows],
    );
    const totalOcrPages = useMemo(
        () => ocrWindowData.reduce((total, item) => total + item.ocrPages, 0),
        [ocrWindowData],
    );
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
    const generationTotals = useMemo(
        () =>
            generationWindowData.reduce(
                (totals, item) => ({
                    visuals: totals.visuals + item.visuals,
                    content: totals.content + item.content,
                    total: totals.total + item.visuals + item.content,
                }),
                { visuals: 0, content: 0, total: 0 },
            ),
        [generationWindowData],
    );
    const brandOcrTotal = useMemo(
        () => filteredBrandUsageRows.reduce((sum, row) => sum + parseUsageValue(row.ocr).used, 0),
        [filteredBrandUsageRows],
    );
    const brandVisualTotal = useMemo(
        () => filteredBrandUsageRows.reduce((sum, row) => sum + parseUsageValue(row.visuals).used, 0),
        [filteredBrandUsageRows],
    );
    const brandOcrSegments = useMemo(
        () => scaleSegmentsToTotal(brandCharts.ocrSegments, brandOcrTotal),
        [brandCharts.ocrSegments, brandOcrTotal],
    );
    const brandVisualSegments = useMemo(
        () => scaleSegmentsToTotal(brandCharts.visualSegments, brandVisualTotal),
        [brandCharts.visualSegments, brandVisualTotal],
    );
    const creationFeedback = useMemo(() => {
        if (searchParams.get("created") !== "1") {
            return null;
        }
        const email = searchParams.get("email") || tenant?.tenant_admin_email || "the tenant admin";
        const status = searchParams.get("emailStatus");
        const reason = searchParams.get("emailReason");
        if (status === "sent") {
            return {
                tone: "success" as const,
                title: "Tenant created successfully",
                description: `Activation email sent to ${email}.`,
            };
        }
        return {
            tone: "warning" as const,
            title: "Tenant created, but activation email was not sent",
            description: reason ? `${email}: ${reason}` : `${email}: Email delivery could not be completed.`,
        };
    }, [searchParams, tenant?.tenant_admin_email]);
    const resolvedUsageMonth = usageMonthOptions.some((option) => option.value === selectedUsageMonth)
        ? selectedUsageMonth
        : usageMonthOptions[usageMonthOptions.length - 1]?.value || "";
    const selectedUsageOption =
        usageMonthOptions.find((option) => option.value === resolvedUsageMonth) ?? usageMonthOptions[usageMonthOptions.length - 1] ?? null;
    const resetUsageLimitWindow = () => {
        setUsageLimitStartMonth(usageLimitMinMonth);
        setUsageLimitEndMonth(usageLimitMaxMonth);
    };
    const resetBrandUsageWindow = () => {
        setBrandUsageStartMonth(usageLimitMinMonth);
        setBrandUsageEndMonth(usageLimitMaxMonth);
    };
    const resetOcrWindow = () => {
        setOcrStartMonth(usageLimitMinMonth);
        setOcrEndMonth(usageLimitMaxMonth);
    };
    const resetGenerationWindow = () => {
        setGenerationStartMonth(usageLimitMinMonth);
        setGenerationEndMonth(usageLimitMaxMonth);
    };
    const selectedUsageMetrics = (() => {
        const fallbackMetrics = {
            totalCapacity,
            contentPercent: usagePercentage(usage?.consumption.content_generations || 0, usage?.limits.max_content_generations || 0),
            visualsPercent: usagePercentage(usage?.consumption.image_generations || 0, usage?.limits.max_image_generations || 0),
            ocrPercent: usagePercentage(usage?.consumption.ocr_pages || 0, usage?.limits.max_ocr_pages || 0),
            brandSpacesUsed: usage?.consumption.brand_spaces || 0,
            brandSpacesLimit: usage?.limits.max_brand_spaces || 0,
            usersUsed: usage?.consumption.users || 0,
            usersLimit: usage?.limits.max_users || 0,
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

    const handleDeleteTenant = async () => {
        if (!tenant) {
            return;
        }

        if (!window.confirm(`Delete "${tenant.name}"? This will permanently remove the tenant and related data.`)) {
            return;
        }

        try {
            await deleteTenant(tenantId);
            toast({ title: "Tenant deleted" });
            router.push("/tenants");
        } catch (error) {
            toast({
                title: "Unable to delete this tenant right now.",
                description: error instanceof Error ? error.message : "Please try again.",
                variant: "destructive",
            });
        }
    };

    if (isLoading || !tenant) {
        return <div className="p-5 text-sm text-slate-500">Loading tenant details...</div>;
    }

    return (
        <div className="w-full space-y-6 px-5 py-5">
            <PlatformPageTitle
                title={tenant.name}
                action={
                    <div className="flex items-center gap-3">
                        <Button
                            onClick={() => router.push(`/tenants/${tenantId}/edit`)}
                            className="rounded-none bg-primary/72 px-5 py-5 text-base hover:bg-primary/90"
                        >
                            {/* <PencilLine className="mr-2 h-4 w-4" /> */}
                            <Image src={"/actions_icons/edit.svg"} alt="Edit" width={16} height={16} />
                            Edit
                        </Button>
                        <Button
                            variant="outline"
                            className="rounded-none border-[#D5D8E8] bg-[#D4D4D8] px-5 py-5 text-base text-white hover:bg-[#BFBFC6]"
                            disabled={isUpdatingTenant}
                            onClick={() =>
                                updateTenant({
                                    id: tenantId,
                                    data: {
                                        is_active: !tenant.is_active,
                                    },
                                })
                            }
                        >
                            <Image src={"/actions_icons/deactivate_user.svg"} alt="Edit" width={16} height={16} className="w-auto h-auto" />

                            {tenant.is_active ? "Deactivate" : "Reactivate"}
                        </Button>
                        <Button
                            variant="outline"
                            className="rounded-none border-[#FFB4AA] bg-[#FF6D5E] px-5 py-5 text-base text-white hover:bg-[#F35F50] hover:text-white"
                            disabled={isDeletingTenant}
                            onClick={handleDeleteTenant}
                        >
                            <Trash2 className="h-4 w-4" />
                            Delete
                        </Button>
                    </div>
                }
            >
                <PlatformTabSwitcher
                    tabs={[
                        { id: "tenant", label: "Tenant" },
                        { id: "brandSpaces", label: "Brand Spaces" },
                    ]}
                    active={tab}
                    onChange={setTab}
                />
            </PlatformPageTitle>

            {tab === "tenant" ? (
                <div className="space-y-4">
                    {creationFeedback ? (
                        <Alert
                            className={
                                creationFeedback.tone === "success"
                                    ? "border-[#CFE6D6] bg-[#F4FBF6] text-[#1F6B38]"
                                    : "border-[#F1D9A7] bg-[#FFF8EA] text-[#8A5A00]"
                            }
                        >
                            <AlertTitle className="text-inherit">{creationFeedback.title}</AlertTitle>
                            <AlertDescription className="text-inherit/90">
                                <div className="flex flex-wrap items-center justify-between gap-3">
                                    <p>{creationFeedback.description}</p>
                                    <Button
                                        type="button"
                                        variant="outline"
                                        className="h-9 rounded-[10px] border-current/25 bg-transparent px-3 text-current hover:bg-white/70"
                                        onClick={() => router.replace(`/tenants/${tenantId}`)}
                                    >
                                        Dismiss
                                    </Button>
                                </div>
                            </AlertDescription>
                        </Alert>
                    ) : null}

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

                    <SectionCard title="Usage Limit" toolbar={
                        <MonthWindowPopoverButton
                            label={usageLimitDateLabel}
                            startMonth={resolvedUsageLimitStartMonth}
                            endMonth={resolvedUsageLimitEndMonth}
                            minMonth={usageLimitMinMonth}
                            maxMonth={usageLimitMaxMonth}
                            onStartChange={setUsageLimitStartMonth}
                            onEndChange={setUsageLimitEndMonth}
                            onReset={resetUsageLimitWindow}
                        />
                    }>
                        <div className="overflow-x-auto">
                            <table className="min-w-full text-left text-sm">
                                <thead className="border-b border-[#ECEEF5] text-[#6B7280]">
                                    <tr>
                                        <th className="pb-3 font-medium">Month</th>
                                        <th className="pb-3 font-medium">Content Generations</th>
                                        <th className="pb-3 font-medium">Visuals</th>
                                        <th className="pb-3 font-medium">OCR Pages</th>
                                        <th className="pb-3 font-medium">Brand Spaces</th>
                                        <th className="pb-3 font-medium">Users</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredUsageRows.map((row) => (
                                        <tr key={row.month} className="border-b border-[#F1F2F6] text-[#4B5563]">
                                            <td className="py-3">{row.monthLabel}</td>
                                            <td className="py-3">{row.content}</td>
                                            <td className="py-3">{row.visuals}</td>
                                            <td className="py-3">{row.ocr}</td>
                                            <td className="py-3">{row.brandSpaces}</td>
                                            <td className="py-3">{row.users}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </SectionCard>

                    <SectionCard title="Tenant Admin">
                        <div className="grid gap-3 text-sm text-[#4B5563]">
                            <InfoPair label="Name" value={tenant.tenant_admin_name || "-"} />
                            <InfoPair label="Email" value={tenant.tenant_admin_email || "-"} />
                            <InfoPair label="Contact Number" value={tenant.tenant_admin_phone_number || "-"} />
                        </div>
                    </SectionCard>

                    <SectionCard title="Tenant Users">
                        <div className="overflow-x-auto">
                            <table className="min-w-full text-left text-base">
                                <thead className="border-b border-[#ECEEF5]">
                                    <tr>
                                        <th className="pb-3 font-medium">Name</th>
                                        <th className="pb-3 font-medium">Date Created</th>
                                        <th className="pb-3 font-medium">Status</th>
                                        <th className="pb-3 font-medium">Active (Last 30 Days)</th>
                                        <th className="pb-3 font-medium">Last Login</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(users || []).map((user) => (
                                        <tr key={user.id} className="border-b border-[#F1F2F6] text-[#4B5563]">
                                            <td className="py-3">{user.full_name}</td>
                                            <td className="py-3">{formatShortDate(user.created_at)}</td>
                                            <td className="py-3">{user.is_active ? "Active" : "Inactive"}</td>
                                            <td className="py-3">{getActivityLabel(user.last_login_at)}</td>
                                            <td className="py-3">{formatShortDate(user.last_login_at)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </SectionCard>

                    <SectionCard
                        title="LLM Tokens"
                        toolbar={
                            <div className="flex items-center gap-3">
                                <MonthWindowPopoverButton
                                    label={usageLimitDateLabel}
                                    startMonth={resolvedUsageLimitStartMonth}
                                    endMonth={resolvedUsageLimitEndMonth}
                                    minMonth={usageLimitMinMonth}
                                    maxMonth={usageLimitMaxMonth}
                                    onStartChange={setUsageLimitStartMonth}
                                    onEndChange={setUsageLimitEndMonth}
                                    onReset={resetUsageLimitWindow}
                                />
                            </div>
                        }
                    >
                        <div className="w-full flex items-center justify-center">
                        <ToolbarToggle
                            items={[
                                { id: "openai", label: "OpenAI" },
                                { id: "anthropic", label: "Anthropic" },
                            ]}
                            active={provider}
                            onChange={setProvider}
                        />
                        </div>
                        <TokenUsageChart
                            data={llmWindowData}
                            inputTotal={llmTotals.inputTokens}
                            outputTotal={llmTotals.outputTokens}
                        />
                    </SectionCard>

                    <div className="grid gap-4 xl:grid-cols-2">
                        <SectionCard
                            title={`Total OCR Pages: ${formatCount(totalOcrPages)}`}
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
                            title={`Total Generations: ${formatCount(generationTotals.total)}`}
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
                                <div className="space-y-1 text-sm text-[#4B5563]">
                                    <div className="flex items-center gap-2">
                                        <span className="inline-block h-4 w-4 bg-[#A9A9A9]" />
                                        <span>Visuals: {formatCount(generationTotals.visuals)}</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="inline-block h-4 w-4 bg-[#595959]" />
                                        <span>Content: {formatCount(generationTotals.content)}</span>
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
                </div>
            ) : (
                <div className="space-y-5">
                    <SectionCard title="Brand Spaces">
                        <div className="overflow-x-auto">
                            <table className="min-w-full text-left text-sm">
                                <thead className="border-b border-[#ECEEF5] text-[#6B7280]">
                                    <tr>
                                        <th className="pb-3 font-medium">Name</th>
                                        <th className="pb-3 font-medium">Date Created</th>
                                        <th className="pb-3 font-medium">Status</th>
                                        <th className="pb-3 font-medium">Active (Last 30 Days)</th>
                                        <th className="pb-3 font-medium">Last Login</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(brandSpaces || []).map((brand) => (
                                        <tr key={brand.id} className="border-b border-[#F1F2F6] text-[#4B5563]">
                                            <td className="py-3">{brand.name}</td>
                                            <td className="py-3">{formatShortDate(brand.created_at)}</td>
                                            <td className="py-3">{brand.lifecycle_state === "active" ? "Active" : "Inactive"}</td>
                                            <td className="py-3">{getActivityLabel(brand.last_active_at)}</td>
                                            <td className="py-3">{formatShortDate(brand.last_login_at)}</td>
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
                            <GradientDonutChart
                                chartId="tenant-brand-ocr"
                                segments={brandOcrSegments}
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
                            <GradientDonutChart
                                chartId="tenant-brand-ai"
                                segments={brandVisualSegments}
                                emptyMessage="No brand AI usage is available for the selected window."
                            />
                        </SectionCard>
                    </div>

                    <SectionCard title="Usage Overview" toolbar={<DatePill label={dateLabel} />}>
                        <div className="overflow-x-auto">
                            <table className="min-w-full text-left text-sm">
                                <thead className="border-b border-[#ECEEF5] text-[#6B7280]">
                                    <tr>
                                        <th className="pb-3 font-medium">Brand</th>
                                        <th className="pb-3 font-medium">Content Generations</th>
                                        <th className="pb-3 font-medium">Visuals</th>
                                        <th className="pb-3 font-medium">OCR Pages</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(brandSpaces || []).map((brand) => (
                                        <tr key={brand.id} className="border-b border-[#F1F2F6] text-[#4B5563]">
                                            <td className="py-3">{brand.name}</td>
                                            <td className="py-3">{brand.content_generations}</td>
                                            <td className="py-3">{brand.visual_generations}</td>
                                            <td className="py-3">{brand.ocr_pages}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </SectionCard>
                </div>
            )}
        </div>
    );
}




function scaleSegmentsToTotal(
    segments: Array<{ name: string; value: number; color: string }>,
    totalValue: number,
) {
    if (!segments.length || totalValue <= 0) {
        return [] as Array<{ name: string; value: number; color: string }>;
    }

    const weightedSegments = segments.filter((segment) => segment.value > 0);
    const weightTotal = weightedSegments.reduce((sum, segment) => sum + segment.value, 0);
    if (!weightTotal) {
        return [] as Array<{ name: string; value: number; color: string }>;
    }

    return weightedSegments.map((segment) => ({
        name: segment.name,
        color: segment.color,
        value: (totalValue * segment.value) / weightTotal,
    }));
}

function TokenUsageChart({
    data,
    inputTotal,
    outputTotal,
}: {
    data: Array<{ month: string; label: string; inputTokens: number; outputTokens: number }>;
    inputTotal: number;
    outputTotal: number;
}) {
    const chartData = data.map((item) => ({
        ...item,
        axisLabel: formatMonthAxisLabel(item.month, data.length),
    }));

    return (
        <div className="space-y-5">
            <div className="space-y-1 text-sm text-[#4B5563]">
                <div className="flex items-center gap-2">
                    <span className="inline-block h-4 w-4 bg-[#B7B7B7]" />
                    <span>Input Tokens: {formatCount(inputTotal)}</span>
                </div>
                <div className="flex items-center gap-2">
                    <span className="inline-block h-4 w-4 bg-[#4B4B4B]" />
                    <span>Output Tokens: {formatCount(outputTotal)}</span>
                </div>
            </div>

            {chartData.length ? (
                <div className="h-[280px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData} barCategoryGap="44%" margin={{ top: 8, bottom: 8 }}>
                            <CartesianGrid vertical={false} stroke="#E4E7EC" strokeDasharray="3 3" />
                            <XAxis
                                dataKey="axisLabel"
                                axisLine={false}
                                tickLine={false}
                                interval={0}
                                minTickGap={0}
                                tickMargin={10}
                                padding={{ left: 8, right: 8 }}
                                tick={{ fill: "#4B5563", fontSize: 12 }}
                            />
                            <YAxis hide />
                            <Tooltip
                                cursor={{ fill: "rgba(245, 246, 251, 0.7)" }}
                                content={<TokenUsageTooltip />}
                            />
                            <Bar dataKey="inputTokens" fill="#979797" radius={[2, 2, 0, 0]} maxBarSize={14} />
                            <Bar dataKey="outputTokens" fill="#555555" radius={[2, 2, 0, 0]} maxBarSize={14} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            ) : (
                <div className="rounded-[8px] border border-[#E4E7EC] px-4 py-10 text-center text-sm text-[#6B7280]">
                    No token data is available for the selected window.
                </div>
            )}
        </div>
    );
}

function TokenUsageTooltip({
    active,
    payload,
    label,
}: {
    active?: boolean;
    payload?: Array<{ dataKey?: string; value?: number }>;
    label?: string;
}) {
    if (!active || !payload?.length) {
        return null;
    }

    const inputValue = payload.find((item) => item.dataKey === "inputTokens")?.value || 0;
    const outputValue = payload.find((item) => item.dataKey === "outputTokens")?.value || 0;

    return (
        <div className="rounded-[8px] border border-[#E4E7EC] bg-white px-3 py-2 text-sm shadow-[0_18px_48px_-20px_rgba(15,23,42,0.25)]">
            <p className="mb-2 font-medium text-[#2F3342]">{label}</p>
            <div className="space-y-1 text-[#4B5563]">
                <div className="flex items-center gap-2">
                    <span className="inline-block h-4 w-4 bg-[#B7B7B7]" />
                    <span>{formatCount(inputValue)}</span>
                </div>
                <div className="flex items-center gap-2">
                    <span className="inline-block h-4 w-4 bg-[#4B4B4B]" />
                    <span>{formatCount(outputValue)}</span>
                </div>
            </div>
        </div>
    );
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

function resolveTenantProviderMonthlyUsage(tenant: unknown, provider: string) {
    const providerKey = provider.toLowerCase();
    const tenantRecord = isRecord(tenant) ? tenant : null;
    if (!tenantRecord) {
        return [] as Array<{ month: string; input_tokens: number; output_tokens: number }>;
    }

    const metadata = isRecord(tenantRecord.metadata_json) ? tenantRecord.metadata_json : {};
    const providerCandidates = [
        getNestedValue(metadata, ["llm_token_usage", "providers", providerKey, "monthly_token_usage"]),
        getNestedValue(metadata, ["llm_token_usage", providerKey, "monthly_token_usage"]),
        getNestedValue(metadata, ["provider_token_usage", providerKey, "monthly_token_usage"]),
        getNestedValue(metadata, ["token_usage", "providers", providerKey, "monthly_token_usage"]),
        getNestedValue(metadata, ["token_usage", providerKey, "monthly_token_usage"]),
        getNestedValue(tenantRecord, ["llm_token_usage", "providers", providerKey, "monthly_token_usage"]),
        getNestedValue(tenantRecord, ["token_usage", "providers", providerKey, "monthly_token_usage"]),
    ];

    for (const candidate of providerCandidates) {
        const normalized = normalizeTokenUsageCollection(candidate);
        if (normalized.length) {
            return normalized;
        }
    }

    const providerScopedMonthlyUsage = normalizeTokenUsageCollection(tenantRecord.monthly_token_usage, providerKey, true);
    if (providerScopedMonthlyUsage.length) {
        return providerScopedMonthlyUsage;
    }

    return normalizeTokenUsageCollection(tenantRecord.monthly_token_usage);
}

function normalizeTokenUsageCollection(value: unknown, providerKey?: string, requireProviderMatch = false) {
    if (Array.isArray(value)) {
        return collapseMonthlyUsage(
            value.flatMap((entry) => normalizeTokenUsageEntry(entry, providerKey, requireProviderMatch)),
        );
    }

    if (!isRecord(value)) {
        return [] as Array<{ month: string; input_tokens: number; output_tokens: number }>;
    }

    if (typeof value.month === "string") {
        return collapseMonthlyUsage(normalizeTokenUsageEntry(value, providerKey, requireProviderMatch));
    }

    return collapseMonthlyUsage(
        Object.entries(value).flatMap(([month, entry]) => {
            if (!isRecord(entry)) {
                return [];
            }

            return [{
                month,
                input_tokens: getTokenMetric(entry, "input_tokens"),
                output_tokens: getTokenMetric(entry, "output_tokens"),
            }];
        }),
    );
}

function normalizeTokenUsageEntry(entry: unknown, providerKey?: string, requireProviderMatch = false) {
    if (!isRecord(entry) || typeof entry.month !== "string") {
        return [] as Array<{ month: string; input_tokens: number; output_tokens: number }>;
    }

    const providerLabel = getProviderLabel(entry);
    if (requireProviderMatch && providerLabel && providerLabel !== providerKey) {
        return [];
    }

    if (hasTokenMetrics(entry) && (!requireProviderMatch || !providerLabel || providerLabel === providerKey)) {
        return [{
            month: entry.month,
            input_tokens: getTokenMetric(entry, "input_tokens"),
            output_tokens: getTokenMetric(entry, "output_tokens"),
        }];
    }

    if (!providerKey) {
        return [];
    }

    const providerUsage = resolveProviderMetrics(entry, providerKey);
    if (!providerUsage) {
        return [];
    }

    return [{
        month: entry.month,
        input_tokens: getTokenMetric(providerUsage, "input_tokens"),
        output_tokens: getTokenMetric(providerUsage, "output_tokens"),
    }];
}

function collapseMonthlyUsage(items: Array<{ month: string; input_tokens: number; output_tokens: number }>) {
    const monthMap = new Map<string, { month: string; input_tokens: number; output_tokens: number }>();

    items.forEach((item) => {
        if (!item.month) {
            return;
        }

        const current = monthMap.get(item.month) || { month: item.month, input_tokens: 0, output_tokens: 0 };
        monthMap.set(item.month, {
            month: item.month,
            input_tokens: current.input_tokens + item.input_tokens,
            output_tokens: current.output_tokens + item.output_tokens,
        });
    });

    return Array.from(monthMap.values()).sort((left, right) => left.month.localeCompare(right.month));
}

function resolveProviderMetrics(entry: Record<string, unknown>, providerKey: string) {
    const directCandidate = entry[providerKey];
    if (isRecord(directCandidate)) {
        return directCandidate;
    }

    const providersCandidate = entry.providers;
    if (isRecord(providersCandidate)) {
        const providerEntry = providersCandidate[providerKey];
        if (isRecord(providerEntry)) {
            return providerEntry;
        }
    }

    const providerUsageCandidate = entry.provider_usage;
    if (isRecord(providerUsageCandidate)) {
        const providerEntry = providerUsageCandidate[providerKey];
        if (isRecord(providerEntry)) {
            return providerEntry;
        }
    }

    return null;
}

function getProviderLabel(entry: Record<string, unknown>) {
    if (typeof entry.provider === "string") {
        return entry.provider.toLowerCase();
    }

    if (typeof entry.model_provider === "string") {
        return entry.model_provider.toLowerCase();
    }

    return "";
}

function hasTokenMetrics(value: Record<string, unknown>) {
    return "input_tokens" in value || "output_tokens" in value;
}

function getTokenMetric(value: Record<string, unknown>, key: "input_tokens" | "output_tokens") {
    const metric = value[key];
    return typeof metric === "number" && Number.isFinite(metric) ? metric : 0;
}

function getNestedValue(source: unknown, path: string[]) {
    let current = source;

    for (const key of path) {
        if (!isRecord(current)) {
            return undefined;
        }

        current = current[key];
    }

    return current;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

function formatMonthAxisLabel(month: string, totalMonths: number) {
    const parsed = parseMonthValue(month);
    if (!parsed) {
        return month;
    }

    const shortMonth = parsed.toLocaleString("en-IN", { month: "short" });
    return totalMonths <= 6 ? `${shortMonth}'${String(parsed.getFullYear()).slice(-2)}` : shortMonth;
}

function formatCount(value: number) {
    return new Intl.NumberFormat("en-US").format(value);
}



function InfoPair({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex  items-center justify-start border-b border-[#F1F2F6] pb-3 last:border-none last:pb-0">
            <p className="text-base text-[#666666]">{label} : </p>
            <p className="ml-2 text-base text-black"> {value}</p>
        </div>
    );
}
