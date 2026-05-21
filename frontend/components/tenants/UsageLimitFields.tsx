"use client";

import { CalendarDays } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { TenantFormData } from "@/types/tenant.types";
import type { FormErrors } from "@/zod/tenantManagement";

interface UsageLimitFieldsProps {
  form: TenantFormData["usage"];
  setForm: (usage: TenantFormData["usage"]) => void;
  errors: FormErrors["usage"];
  clearError: (field: string) => void;
}

export default function UsageLimitFields({ form, setForm, errors, clearError }: UsageLimitFieldsProps) {
  return (
    <div className="max-w-[458px] space-y-6">
      <div className="space-y-3">
        <Label htmlFor="startMonth" className="text-base font-medium leading-6 text-[#2F3342]">
          Configure Monthly Limits
        </Label>
        <MonthField
          id="startMonth"
          value={form.startMonth}
          placeholder="Select start month"
          onChange={(value) => {
            setForm({ ...form, startMonth: value });
            clearError("startMonth");
          }}
        />
        <div className="flex items-start gap-3 py-1">
          <Checkbox
            id="renewsCredits"
            checked={form.renewsCredits}
            onCheckedChange={(checked) => setForm({ ...form, renewsCredits: checked === true })}
            className="mt-1"
          />
          <Label htmlFor="renewsCredits" className="text-sm font-medium leading-6 text-[#6B7280]">
            Automatically renews credits for the next month
          </Label>
        </div>
        <MonthField
          id="endMonth"
          value={form.endMonth}
          placeholder="Select end month"
          onChange={(value) => {
            setForm({ ...form, endMonth: value });
            clearError("endMonth");
          }}
        />
        {errors?.endMonth ? <p className="text-sm text-red-500">{errors.endMonth}</p> : null}
      </div>

      <UsageField
        id="content-generations"
        label="Content Generations"
        placeholder="Add limit for AI content generation requests"
        value={form.maxContentGenerations}
        error={errors?.maxContentGenerations}
        onChange={(value) => {
          setForm({ ...form, maxContentGenerations: value });
          clearError("maxContentGenerations");
        }}
      />

      <UsageField
        id="visual-generations"
        label="Visual Generations"
        placeholder="Add limit for AI image generations"
        value={form.maxVisualGenerations}
        error={errors?.maxVisualGenerations}
        onChange={(value) => {
          setForm({ ...form, maxVisualGenerations: value });
          clearError("maxVisualGenerations");
        }}
      />

      <UsageField
        id="ocr-pages"
        label="OCR Pages"
        placeholder="Add limit for OCR pages"
        value={form.maxOcrPages}
        error={errors?.maxOcrPages}
        onChange={(value) => {
          setForm({ ...form, maxOcrPages: value });
          clearError("maxOcrPages");
        }}
      />

      <UsageField
        id="users"
        label="Users"
        placeholder="Add limit for number of users"
        value={form.maxUsers}
        error={errors?.maxUsers}
        onChange={(value) => {
          setForm({ ...form, maxUsers: value });
          clearError("maxUsers");
        }}
      />

      <UsageField
        id="brand-spaces"
        label="Brand Space Limit"
        placeholder="Add limit for number of brand spaces"
        value={form.maxBrandSpaces}
        error={errors?.maxBrandSpaces}
        onChange={(value) => {
          setForm({ ...form, maxBrandSpaces: value });
          clearError("maxBrandSpaces");
        }}
      />
    </div>
  );
}

function MonthField({
  id,
  value,
  placeholder,
  onChange,
}: {
  id: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="relative">
      <Input
        id={id}
        type="month"
        value={value}
        placeholder={placeholder}
        className="h-12 rounded-[10px] border-none bg-input-field px-4 pr-11 text-sm text-[#2F3342] placeholder:text-[#A7A7A7] focus-visible:ring-2 focus-visible:ring-primary/20"
        onChange={(event) => onChange(event.target.value)}
      />
      <CalendarDays className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#7A7A7A]" />
    </div>
  );
}

function UsageField({
  id,
  label,
  placeholder,
  value,
  error,
  onChange,
}: {
  id: string;
  label: string;
  placeholder: string;
  value: string;
  error?: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-2.5">
      <Label htmlFor={id} className="text-base font-medium leading-6 text-[#2F3342]">
        {label}
      </Label>
      <Input
        id={id}
        type="number"
        min="0"
        value={value}
        placeholder={placeholder}
        className="h-[54px] rounded-[10px] border-none bg-input-field px-4 text-sm text-[#2F3342] placeholder:text-[#A7A7A7] focus-visible:ring-2 focus-visible:ring-primary/20"
        onChange={(event) => onChange(event.target.value)}
      />
      {error ? <p className="text-sm text-red-500">{error}</p> : null}
    </div>
  );
}
