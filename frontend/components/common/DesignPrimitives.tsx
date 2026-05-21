"use client";

import { cn } from "@/lib/utils";
import { ReactNode } from "react";

type PageHeadingProps = {
  title: string;
  actions?: ReactNode;
  subtitle?: string;
};

export function PageHeading({ title, actions, subtitle }: PageHeadingProps) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div className="space-y-1">
        <h1 className="font-dmSans text-3xl font-bold tracking-tight text-primary">
          {title}
        </h1>
        {subtitle ? <p className="text-sm text-slate-500">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
    </div>
  );
}

export function SurfaceCard({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("border border-slate-200 bg-white shadow-[0_8px_24px_-16px_rgba(60,47,143,0.2)]", className)}>
      {children}
    </div>
  );
}

export function MetricBar({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint?: string;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{label}</span>
        {hint ? <span>{hint}</span> : null}
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${Math.max(0, Math.min(value, 100))}%` }}
        />
      </div>
      <p className="text-lg font-semibold text-slate-800">{value}%</p>
    </div>
  );
}

export function Sparkline({
  values,
  height = 96,
}: {
  values: number[];
  height?: number;
}) {
  const width = 320;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const normalized = values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * width;
    const y = height - (((value - min) / Math.max(max - min, 1)) * (height - 16) + 8);
    return `${x},${y}`;
  });

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-28 w-full">
      <polyline
        fill="none"
        stroke="#C9CBD6"
        strokeWidth="2"
        points={`0,${height - 8} ${width},${height - 8}`}
      />
      <polyline
        fill="none"
        stroke="#2F3342"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={normalized.join(" ")}
      />
    </svg>
  );
}

export function DonutChart({
  segments,
}: {
  segments: { color: string; value: number; name: string }[];
}) {
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  const safeTotal = total || 1;
  const chartSegments = segments.map((segment, index) => {
    const priorValue = segments.slice(0, index).reduce((sum, item) => sum + item.value, 0);
    return {
      ...segment,
      dash: (segment.value / safeTotal) * 100,
      offset: (priorValue / safeTotal) * 100,
    };
  });

  return (
    <div className="flex items-center gap-6">
      <svg viewBox="0 0 42 42" className="h-32 w-32 -rotate-90">
        <circle cx="21" cy="21" r="15.915" fill="transparent" stroke="#EEF0F6" strokeWidth="6" />
        {chartSegments.map((segment) => {
          return (
            <circle
              key={segment.name}
              cx="21"
              cy="21"
              r="15.915"
              fill="transparent"
              stroke={segment.color}
              strokeWidth="6"
              strokeDasharray={`${segment.dash} ${100 - segment.dash}`}
              strokeDashoffset={-segment.offset}
            />
          );
        })}
      </svg>

      <div className="space-y-2 text-sm text-slate-500">
        {segments.map((segment) => (
          <div key={segment.name} className="flex items-center gap-2">
            <span
              className="inline-block h-3 w-3 rounded-full"
              style={{ backgroundColor: segment.color }}
            />
            <span>{segment.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function UsageRing({
  value,
  label,
}: {
  value: number;
  label?: string;
}) {
  const circumference = 2 * Math.PI * 16;
  const progress = circumference - (value / 100) * circumference;

  return (
    <div className="flex items-center gap-2 text-xs text-slate-500">
      <svg viewBox="0 0 42 42" className="h-11 w-11 -rotate-90">
        <circle cx="21" cy="21" r="16" fill="transparent" stroke="#DADCE6" strokeWidth="6" />
        <circle
          cx="21"
          cy="21"
          r="16"
          fill="transparent"
          stroke="#3C2F8F"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={progress}
        />
      </svg>
      {label ? <span>{label}</span> : null}
    </div>
  );
}

export function StatusChip({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning";
}) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2.5 py-1 text-xs font-medium",
        tone === "neutral" && "bg-slate-100 text-slate-600",
        tone === "success" && "bg-emerald-50 text-emerald-700",
        tone === "warning" && "bg-amber-50 text-amber-700",
      )}
    >
      {children}
    </span>
  );
}
