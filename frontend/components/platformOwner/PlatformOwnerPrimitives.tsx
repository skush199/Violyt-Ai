"use client";

import type { ReactNode } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Button } from "../ui/button";

export function PlatformPageTitle({
    title,
    action,
    children,
}: {
    title: string;
    action?: ReactNode;
    children?: ReactNode;
}) {
    return (
        <div className="space-y-6">
            <div className="flex items-start justify-between gap-4">
                <h1 className="font-dmSans text-[32px] font-bold leading-none  text-primary">{title}</h1>
                {action}
            </div>
            {children}
        </div>
    );
}

export function PlatformTabSwitcher({
    tabs,
    active,
    onChange,
}: {
    tabs: Array<{ id: string; label: string }>;
    active: string;
    onChange: (tab: string) => void;
}) {
    return (
        <div className="flex flex-wrap items-center gap-3">
            {tabs.map((tab) => (
                <Button
                    key={tab.id}
                    type="button"
                    onClick={() => onChange(tab.id)}
                    className={cn(
                        "h-12 min-w-[92px] rounded-[10px] border border-[#D4D8E5] bg-white px-5 text-[15px] font-medium text-[#2F3342] transition",
                        active === tab.id ? "bg-[#CDCDCD]/22 shadow-[inset_0_0_0_1px_rgba(60,47,143,0.14)]" : "hover:bg-[#FAFAFD]",
                    )}
                >
                    {tab.label}
                </Button>
            ))}
        </div>
    );
}

export function DatePill({ label }: { label: string }) {
    return (
        <div className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-[#D5D8E8] bg-white px-3 text-sm font-medium text-[#6B7280]">
            <CalendarDays className="h-3.5 w-3.5" />
            <span>{label}</span>
        </div>
    );
}

export function SectionCard({
    title,
    description,
    toolbar,
    children,
    className,
}: {
    title: string;
    description?: string;
    toolbar?: ReactNode;
    children: ReactNode;
    className?: string;
}) {
    return (
        <div className={cn("rounded-[2px] border border-[#ECEEF5] bg-white p-6 shadow-[0_10px_24px_-22px_rgba(15,23,42,0.45)]", className)}>
            <div className="mb-5 flex flex-col items-start justify-between">
                <div className="w-full flex items-center justify-between">
                    <h2 className="text-xl font-semibold text-[#4B5563]">{title}</h2>
                    {toolbar}
                </div>
                <p className="text-sm text-[#6B7280]">{description}</p>

            </div>
            {children}
        </div>
    );
}

export function MetricTile({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-[2px] border border-[#ECEEF5] bg-white px-5 py-4 shadow-[0_10px_24px_-22px_rgba(15,23,42,0.45)]">
            <p className="text-sm text-[#6B7280]">{label}</p>
            <p className="mt-3 text-[32px] font-semibold leading-none text-[#2F3342]">{value}</p>
        </div>
    );
}

export function ToolbarToggle({
    items,
    active,
    onChange,
}: {
    items: Array<{ id: string; label: string }>;
    active: string;
    onChange: (value: string) => void;
}) {
    return (
        <div className="inline-flex items-center gap-2 rounded-md">
            {items.map((item) => (
                <Button
                variant={"ghost"}
                    key={item.id}
                    type="button"
                    onClick={() => onChange(item.id)}
                    className={cn(
                        "h-10 rounded-none border border-[#D0D5DD] px-4 text-sm font-medium text-[#6B7280]",
                        active === item.id && "bg-[#85829940] text-[#2F3342]",
                    )}
                >
                    {item.label}
                </Button>
            ))}
        </div>
    );
}

export function SimpleBarChart({
    data,
    tone = "double",
    height = 180,
}: {
    data: Array<{ label: string; primary: number; secondary?: number }>;
    tone?: "double" | "stack";
    height?: number;
}) {
    const max = Math.max(...data.flatMap((item) => [item.primary, item.secondary || 0, 1]));

    return (
        <div className="space-y-4">
            <div className="flex h-[180px] items-end gap-5">
                {data.map((item) => {
                    const primaryHeight = `${Math.max(10, (item.primary / max) * height)}px`;
                    const secondaryHeight = `${Math.max(6, ((item.secondary || 0) / max) * height)}px`;
                    return (
                        <div key={item.label} className="flex flex-1 flex-col items-center gap-2">
                            <div className="flex h-full items-end gap-1">
                                <span className="w-2 rounded-sm bg-[#A3A6B3]" style={{ height: primaryHeight }} />
                                {tone === "double" ? (
                                    <span className="w-2 rounded-sm bg-[#3D414E]" style={{ height: secondaryHeight }} />
                                ) : (
                                    <span className="w-2 rounded-sm bg-[#DADCE6]" style={{ height: secondaryHeight }} />
                                )}
                            </div>
                            <span className="text-[11px] text-[#6B7280]">{item.label}</span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export function SearchField({
    value,
    onChange,
    placeholder = "Search",
}: {
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
}) {
    return (
        <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#A1A1AA]" />
            <Input
                value={value}
                onChange={(event) => onChange(event.target.value)}
                placeholder={placeholder}
                className="h-10 w-[210px] rounded-none border-[#E5E7EB] bg-white pl-9"
            />
        </div>
    );
}

export function Pager({
    page,
    totalPages,
    onPrevious,
    onNext,
}: {
    page: number;
    totalPages: number;
    onPrevious?: () => void;
    onNext?: () => void;
}) {
    const canGoBack = page > 1;
    const canGoForward = page < Math.max(totalPages, 1);
    return (
        <div className="flex items-center gap-5 text-sm text-[#2F3342]">
            <button type="button" onClick={onPrevious} disabled={!canGoBack} className={cn(!canGoBack && "cursor-not-allowed text-[#C7CBD8]")}>
                <ChevronLeft className="h-4 w-4" />
            </button>
            <span>Page {page} of {Math.max(totalPages, 1)}</span>
            <button type="button" onClick={onNext} disabled={!canGoForward} className={cn(!canGoForward && "cursor-not-allowed text-[#C7CBD8]")}>
                <ChevronRight className="h-4 w-4" />
            </button>
        </div>
    );
}
