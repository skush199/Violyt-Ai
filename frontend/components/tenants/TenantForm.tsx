"use client";

import type { TenantFormData } from "@/types/tenant.types";
import TenantFields from "./TenantFields";
import TenantAdminFields from "./TenantAdminFields";
import UsageLimitFields from "./UsageLimitFields";
import type { FormErrors } from "@/zod/tenantManagement";
import { PlatformTabSwitcher } from "@/components/platformOwner/PlatformOwnerPrimitives";

interface Props {
  form: TenantFormData;
  setForm: React.Dispatch<React.SetStateAction<TenantFormData>>;
  errors: FormErrors;
  tab: "tenant" | "admin" | "usage";
  setTab: (tab: "tenant" | "admin" | "usage") => void;
  clearFieldError: (section: keyof FormErrors, field: string) => void;
}

export default function TenantForm({ form, setForm, errors, clearFieldError, tab, setTab }: Props) {
  return (
    <div className="max-w-[1110px] space-y-8">
      <PlatformTabSwitcher
        tabs={[
          { id: "tenant", label: "Tenant" },
          { id: "admin", label: "Tenant Admin" },
          { id: "usage", label: "Usage Limit" },
        ]}
        active={tab}
        onChange={(value) => setTab(value as "tenant" | "admin" | "usage")}
      />

      {tab === "tenant" ? (
        <TenantFields
          form={form.tenant}
          setForm={(data) => setForm((prev) => ({ ...prev, tenant: data }))}
          errors={errors.tenant}
          clearError={(field) => clearFieldError("tenant", field)}
        />
      ) : null}

      {tab === "admin" ? (
        <TenantAdminFields
          form={form.admin}
          setForm={(data) => setForm((prev) => ({ ...prev, admin: data }))}
          errors={errors.admin}
          clearError={(field) => clearFieldError("admin", field)}
        />
      ) : null}

      {tab === "usage" ? (
        <UsageLimitFields
          form={form.usage}
          setForm={(data) => setForm((prev) => ({ ...prev, usage: data }))}
          errors={errors.usage}
          clearError={(field) => clearFieldError("usage", field)}
        />
      ) : null}
    </div>
  );
}
