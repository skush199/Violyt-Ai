"use client";

import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

type FilterOption<TValue extends string> = {
  value: TValue;
  label: string;
};

type TableFilterPopoverProps<TCreated extends string, TActivity extends string> = {
  createdLabel: string;
  createdValue: TCreated;
  createdOptions: ReadonlyArray<FilterOption<TCreated>>;
  onCreatedChange: (value: TCreated) => void;
  activityLabel: string;
  activityValue: TActivity;
  activityOptions: ReadonlyArray<FilterOption<TActivity>>;
  onActivityChange: (value: TActivity) => void;
  onClear: () => void;
  activeFilterCount?: number;
  buttonAriaLabel?: string;
  buttonClassName?: string;
};

export function TableFilterPopover<TCreated extends string, TActivity extends string>({
  createdLabel,
  createdValue,
  createdOptions,
  onCreatedChange,
  activityLabel,
  activityValue,
  activityOptions,
  onActivityChange,
  onClear,
  activeFilterCount = 0,
  buttonAriaLabel = "Open filters",
  buttonClassName,
}: TableFilterPopoverProps<TCreated, TActivity>) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className={cn("relative h-9 rounded-none border-none px-3", buttonClassName)}
          aria-label={buttonAriaLabel}
        >
          <Image src="/actions_icons/filter.svg" alt="" width={22} height={22} />
          {activeFilterCount > 0 ? (
            <span className="absolute -right-1 -top-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-white">
              {activeFilterCount}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[320px] rounded-[12px] border border-[#E5E7EB] bg-white p-4 shadow-[0_18px_48px_-20px_rgba(15,23,42,0.35)]">
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1">
              <p className="text-base font-semibold text-[#2F3342]">Filter records</p>
              <p className="text-sm text-[#6B7280]">Choose how you want to narrow the table.</p>
            </div>
            {activeFilterCount > 0 ? (
              <button
                type="button"
                onClick={onClear}
                className="text-xs font-semibold text-primary transition hover:text-primary/80"
              >
                Clear all
              </button>
            ) : null}
          </div>

          <FilterOptionGroup
            label={createdLabel}
            value={createdValue}
            options={createdOptions}
            onChange={onCreatedChange}
          />
          <FilterOptionGroup
            label={activityLabel}
            value={activityValue}
            options={activityOptions}
            onChange={onActivityChange}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}

function FilterOptionGroup<TValue extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: TValue;
  options: ReadonlyArray<FilterOption<TValue>>;
  onChange: (value: TValue) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[#6B7280]">{label}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange(option.value)}
              className={cn(
                "rounded-[10px] border px-3 py-2 text-sm font-medium transition",
                selected
                  ? "border-primary/25 bg-[#F5F6FB] text-[#2F3342]"
                  : "border-[#E5E7EB] bg-white text-[#6B7280] hover:bg-[#FAFAFD]",
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
