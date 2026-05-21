import Image from "next/image";
import { Progress } from "./ui/progress";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { Button } from "./ui/button";
import { CalendarDays } from "lucide-react";
import { useId } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

export function ProgressRow({ label, value, icon }: { label: string; value: number; icon?: string; }) {
    return (
        <div className="space-y-2 border border-[#E4E7EC] p-4">
            <div className="flex items-center gap-4 text-sm">
                {icon && (
                    <div className="bg-[#EAE6F74D] p-3">
                        <Image src={icon} alt={`${label} icon`} width={16} height={16} className="w-auto h-auto" />
                    </div>
                )}
                <div className="flex flex-col gap-1">
                    <span className="text-[#666666] font-semibold">{label}</span>
                    <span className="text-xl font-semibold">{value}%</span>
                </div>
            </div>
            <Progress value={value} className="w-full mt-4" />
        </div>
    );
}


export function MiniMetric({
    label,
    value,
    helper,
    compact,
    progress,
    icon

}: {
    label: string;
    value: number;
    helper?: string;
    compact?: boolean;
    progress?: boolean;
    icon?: string;
}) {
    return (
        <div className="rounded-xs border border-[#E4E7EC] bg-white px-4 py-4">
            <div className="flex items-center justify-start gap-3 text-sm">
                {
                    icon && (
                        <div className="bg-[#EAE6F74D] p-3">
                            <Image src={icon} alt={`${label} icon`} width={16} height={16} className="w-auto h-auto mb-2" />
                        </div>
                    )
                }
                <div className="flex flex-col items-center justify-center">
                    <p className="text-base font-semibold text-[#666666]">{label}</p>
                    <div className="mt-1 flex items-end gap-2">
                        <p className="text-2xl font-semibold text-[#2F3342]">{value}</p>
                        {helper ? <p className="pb-1 text-xs text-[#6B7280]">/{helper}</p> : null}
                        {compact ? null : <span className="pb-1 text-xs text-[#6B7280]">%</span>}
                    </div>

                </div>
            </div>
            {progress && <Progress value={value} className="mt-2 h-2" />
            }
        </div>
    );
}


export function MonthWindowPopoverButton({
    label,
    startMonth,
    endMonth,
    minMonth,
    maxMonth,
    onStartChange,
    onEndChange,
    onReset,
}: {
    label: string;
    startMonth: string;
    endMonth: string;
    minMonth: string;
    maxMonth: string;
    onStartChange: (value: string) => void;
    onEndChange: (value: string) => void;
    onReset: () => void;
}) {
    return (
        <Popover>
            <PopoverTrigger asChild>
                <Button
                    type="button"
                    variant="outline"
                    className="h-10 rounded-[2px] border-[#D5D8E8] bg-white px-3 text-sm font-medium text-[#4B5563] shadow-none hover:bg-[#FAFAFD]"
                >
                    <CalendarDays className="mr-2 h-4 w-4 text-[#4B5563]" />
                    {label}
                </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-[320px] rounded-[10px] border border-[#D5D8E8] bg-white p-4 shadow-[0_18px_48px_-20px_rgba(15,23,42,0.35)]">
                <div className="space-y-4">
                    <div className="space-y-1">
                        <p className="text-sm font-semibold text-[#2F3342]">Usage window</p>
                        <p className="text-xs text-[#6B7280]">Choose the month range to display in the chart and table.</p>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                        <label className="space-y-2">
                            <span className="text-xs font-medium text-[#666666]">Start Month</span>
                            <input
                                type="month"
                                value={startMonth}
                                min={minMonth || undefined}
                                max={maxMonth || undefined}
                                onChange={(event) => onStartChange(event.target.value)}
                                className="h-10 w-full rounded-[8px] border border-[#D5D8E8] bg-white px-3 text-sm text-[#2F3342] outline-none focus:border-primary/40"
                            />
                        </label>
                        <label className="space-y-2">
                            <span className="text-xs font-medium text-[#666666]">End Month</span>
                            <input
                                type="month"
                                value={endMonth}
                                min={minMonth || undefined}
                                max={maxMonth || undefined}
                                onChange={(event) => onEndChange(event.target.value)}
                                className="h-10 w-full rounded-[8px] border border-[#D5D8E8] bg-white px-3 text-sm text-[#2F3342] outline-none focus:border-primary/40"
                            />
                        </label>
                    </div>
                    <div className="flex items-center justify-between border-t border-[#E4E7EC] pt-3">
                        <p className="text-xs font-medium text-[#6B7280]">{label}</p>
                        <button
                            type="button"
                            onClick={onReset}
                            className="text-xs font-semibold text-primary transition hover:text-primary/80"
                        >
                            Reset window
                        </button>
                    </div>
                </div>
            </PopoverContent>
        </Popover>
    );
}

export function buildMonthYearOptions(startMonth?: string, endMonth?: string) {
    const end = parseMonthValue(endMonth) ?? startOfMonth(new Date());
    const start = parseMonthValue(startMonth) ?? new Date(end.getFullYear(), end.getMonth() - 5, 1);

    const safeStart = start.getTime() <= end.getTime() ? start : end;
    const safeEnd = start.getTime() <= end.getTime() ? end : start;
    const options: Array<{ value: string; label: string }> = [];
    const cursor = new Date(safeStart.getFullYear(), safeStart.getMonth(), 1);

    while (cursor.getTime() <= safeEnd.getTime() && options.length < 24) {
        const year = cursor.getFullYear();
        const month = cursor.getMonth();
        options.push({
            value: `${year}-${String(month + 1).padStart(2, "0")}`,
            label: `${cursor.toLocaleString("en-IN", { month: "short" })}'${String(year).slice(-2)}`,
        });
        cursor.setMonth(cursor.getMonth() + 1);
    }

    return options;
}

export function parseMonthValue(value?: string) {
    if (!value) {
        return null;
    }

    const [year, month] = value.split("-").map(Number);
    if (Number.isNaN(year) || Number.isNaN(month) || month < 1 || month > 12) {
        return null;
    }

    return new Date(year, month - 1, 1);
}

export function startOfMonth(value: Date) {
    return new Date(value.getFullYear(), value.getMonth(), 1);
}

export function parseUsageValue(value: string) {
    const [usedRaw, limitRaw] = value.split("/");
    const used = Number(usedRaw);
    const limit = Number(limitRaw);

    return {
        used: Number.isFinite(used) ? used : 0,
        limit: Number.isFinite(limit) ? limit : 0,
    };
}

export function normalizeMonthWindow(startMonth?: string, endMonth?: string) {
    if (!startMonth && !endMonth) {
        return { start: "", end: "" };
    }

    const start = startMonth || endMonth || "";
    const end = endMonth || startMonth || "";

    if (!start || !end) {
        return { start, end };
    }

    return start <= end ? { start, end } : { start: end, end: start };
}

export function formatCompactMonthLabel(value: string) {
    const parsed = parseMonthValue(value);
    if (!parsed) {
        return value;
    }

    return `${parsed.toLocaleString("en-IN", { month: "short" })}'${String(parsed.getFullYear()).slice(-2)}`;
}

export type GradientDonutSegment = {
    name: string;
    value: number;
    color: string;
};

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

export function GradientDonutChart({
    chartId,
    segments,
    emptyMessage,
}: {
    chartId: string;
    segments: GradientDonutSegment[];
    emptyMessage: string;
}) {
    const gradientPrefix = useId().replace(/:/g, "");
    const totalValue = segments.reduce((sum, item) => sum + item.value, 0);
    const chartData = segments.map((item) => ({
        ...item,
        percentage: totalValue ? Math.round((item.value / totalValue) * 100) : 0,
    }));

    if (!chartData.length || totalValue <= 0) {
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
                            {chartData.map((item, index) => {
                                const gradientId = `${gradientPrefix}-${chartId}-${index}`;
                                return (
                                    <linearGradient key={gradientId} id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
                                        <stop offset="0%" stopColor={hexToRgba(item.color, 0.96)} />
                                        <stop offset="100%" stopColor={hexToRgba(item.color, 0.72)} />
                                    </linearGradient>
                                );
                            })}
                        </defs>
                        <Tooltip content={<GradientDonutTooltip />} />
                        <Pie
                            data={chartData}
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
                            {chartData.map((item, index) => {
                                const gradientId = `${gradientPrefix}-${chartId}-${index}`;
                                return <Cell key={`${item.name}-${index}`} fill={`url(#${gradientId})`} />;
                            })}
                        </Pie>
                    </PieChart>
                </ResponsiveContainer>
            </div>
            <div className="max-h-[220px] space-y-3 overflow-y-auto pr-2">
                {chartData.map((item, index) => (
                    <div key={`${item.name}-${index}`} className="flex items-center gap-3 text-sm text-[#4B5563]">
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

function GradientDonutTooltip({
    active,
    payload,
}: {
    active?: boolean;
    payload?: Array<{ payload?: GradientDonutSegment & { percentage?: number } }>;
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
                <span>{item.name} {item.percentage || 0}%</span>
            </div>
        </div>
    );
}
