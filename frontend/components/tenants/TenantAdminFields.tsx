"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { TenantFormData } from "@/types/tenant.types";
import type { FormErrors } from "@/zod/tenantManagement";

interface TenantAdminFieldsProps {
  form: TenantFormData["admin"];
  setForm: (admin: TenantFormData["admin"]) => void;
  errors: FormErrors["admin"];
  clearError: (field: string) => void;
}

export default function TenantAdminFields({ form, setForm, errors, clearError }: TenantAdminFieldsProps) {
  return (
    <div className="max-w-[458px] space-y-6">
      <Field
        id="admin-name"
        label="Full Name"
        value={form.name}
        placeholder="Enter full name"
        error={errors?.name}
        onChange={(value) => {
          setForm({ ...form, name: value });
          clearError("name");
        }}
      />

      <Field
        id="admin-email"
        label="Email Address"
        value={form.email}
        placeholder="Enter email address"
        error={errors?.email}
        onChange={(value) => {
          setForm({ ...form, email: value });
          clearError("email");
        }}
      />

      <Field
        id="admin-phone"
        label="Contact Number"
        value={form.phone || ""}
        placeholder="Enter contact number"
        error={errors?.phone}
        onChange={(value) => {
          setForm({ ...form, phone: value });
          clearError("phone");
        }}
      />
    </div>
  );
}

function Field({
  id,
  label,
  value,
  placeholder,
  error,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  placeholder: string;
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
        value={value}
        placeholder={placeholder}
        className="h-12 rounded-[10px] border-none bg-input-field px-4 text-sm text-[#2F3342] placeholder:text-[#A7A7A7] focus-visible:ring-2 focus-visible:ring-primary/20"
        onChange={(event) => onChange(event.target.value)}
      />
      {error ? <p className="text-sm text-red-500">{error}</p> : null}
    </div>
  );
}
