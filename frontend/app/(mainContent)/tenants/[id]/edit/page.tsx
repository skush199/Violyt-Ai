"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import TenantForm from "@/components/tenants/TenantForm";
import { useGetTenantData, useGetTenantUsageSummary, useGetTenantUsers } from "@/hooks/tenantAdmins/useGetTenants";
import { useUpdateTenantAdmin, useUploadTenantLogo } from "@/hooks/tenantAdmins/useUpdateTenant";
import { fileToDataUrl } from "@/lib/file-utils";
import { mapTenantFormToUpdateRequest, mapTenantSummaryToForm } from "@/lib/tenant-mappers";
import type { TenantFormData } from "@/types/tenant.types";
import { formatZodErrors, type FormErrors, tenantSchema } from "@/zod/tenantManagement";

export default function EditTenantPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const tenantId = params.id;
  const { data: tenant, isLoading } = useGetTenantData(tenantId);
  const { data: usage } = useGetTenantUsageSummary(tenantId);
  const { data: users } = useGetTenantUsers(tenantId);
  const { mutateAsync: updateTenant, isPending } = useUpdateTenantAdmin();
  const { mutateAsync: uploadTenantLogo, isPending: isUploadingLogo } = useUploadTenantLogo();

  const [errors, setErrors] = useState<FormErrors>({});
  const [activeTab, setActiveTab] = useState<"tenant" | "admin" | "usage">("tenant");
  const [form, setForm] = useState<TenantFormData | null>(null);
  const initialForm = useMemo(() => {
    if (!tenant) {
      return null;
    }
    const adminUser = users?.find((user) => user.role_codes.includes("tenant_admin"));
    return mapTenantSummaryToForm(tenant, usage, adminUser);
  }, [tenant, usage, users]);
  const resolvedForm = form ?? initialForm;

  function clearFieldError(section: keyof FormErrors, field: string) {
    setErrors((prev) => ({
      ...prev,
      [section]: {
        ...prev[section],
        [field]: undefined,
      },
    }));
  }

  const handleSubmit = async () => {
    if (!resolvedForm) {
      return;
    }
    const validation = tenantSchema.safeParse(resolvedForm);
    if (!validation.success) {
      const formattedErrors = formatZodErrors(validation.error);
      setErrors(formattedErrors);
      if (formattedErrors.tenant) setActiveTab("tenant");
      else if (formattedErrors.admin) setActiveTab("admin");
      else if (formattedErrors.usage) setActiveTab("usage");
      return;
    }
    await updateTenant({
      id: tenantId,
      data: mapTenantFormToUpdateRequest(validation.data),
    });
    if (validation.data.tenant.logo instanceof File) {
      const contentBase64 = await fileToDataUrl(validation.data.tenant.logo);
      await uploadTenantLogo({
        id: tenantId,
        data: {
          filename: validation.data.tenant.logo.name,
          mime_type: validation.data.tenant.logo.type || "application/octet-stream",
          content_base64: contentBase64,
        },
      });
    }
    router.push(`/tenants/${tenantId}`);
  };

  if (isLoading || !resolvedForm) {
    return <div className="p-5 text-sm text-slate-500">Loading tenant...</div>;
  }

  return (
    <div className="w-full px-6 py-6">
      <div className="max-w-[1110px] space-y-8">
        <div className="flex items-start justify-between gap-4">
          <h1 className="font-dmSans text-[44px] font-bold leading-none tracking-[-0.03em] text-primary">Edit Tenant</h1>
          <Button
            onClick={handleSubmit}
            disabled={isPending || isUploadingLogo}
            className="h-12 rounded-[2px] bg-[#B8B8BD] px-7 text-base font-semibold text-white hover:bg-[#A8A8AE]"
          >
            {isPending || isUploadingLogo ? "Saving..." : "Save"}
          </Button>
        </div>
        <TenantForm
          form={resolvedForm}
          setForm={(updater) =>
            setForm((prev) => {
              const base = prev ?? resolvedForm;
              return typeof updater === "function" ? updater(base) : updater;
            })
          }
          tab={activeTab}
          setTab={setActiveTab}
          errors={errors}
          clearFieldError={clearFieldError}
        />
      </div>
    </div>
  );
}
