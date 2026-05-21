"use client";

import { isAxiosError } from "axios";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import TenantForm from "@/components/tenants/TenantForm";
import { useCreateTenantAdmin } from "@/hooks/tenantAdmins/useCreateTenant";
import { useUploadTenantLogo } from "@/hooks/tenantAdmins/useUpdateTenant";
import { fileToDataUrl } from "@/lib/file-utils";
import { mapTenantFormToCreateRequest } from "@/lib/tenant-mappers";
import type { TenantFormData } from "@/types/tenant.types";
import { formatZodErrors, type FormErrors, tenantSchema } from "@/zod/tenantManagement";

const emptyForm: TenantFormData = {
  tenant: {
    name: "",
    email: "",
    phone: "",
    address1: "",
    address2: "",
    city: "",
    state: "",
    zip: "",
    country: "",
    logo: "",
  },
  admin: {
    name: "",
    email: "",
    phone: "",
  },
  usage: {
    startMonth: "",
    endMonth: "",
    renewsCredits: true,
    maxContentGenerations: "",
    maxVisualGenerations: "",
    maxOcrPages: "",
    maxUsers: "",
    maxBrandSpaces: "",
  },
};

export default function CreateTenantPage() {
  const router = useRouter();
  const { mutateAsync: createTenant, isPending } = useCreateTenantAdmin();
  const { mutateAsync: uploadTenantLogo, isPending: isUploadingLogo } = useUploadTenantLogo();
  const [errors, setErrors] = useState<FormErrors>({});
  const [activeTab, setActiveTab] = useState<"tenant" | "admin" | "usage">("tenant");
  const [form, setForm] = useState<TenantFormData>(emptyForm);
  const [submissionFeedback, setSubmissionFeedback] = useState<{ title: string; description: string } | null>(null);

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
    setSubmissionFeedback(null);
    const validation = tenantSchema.safeParse(form);
    if (!validation.success) {
      const formattedErrors = formatZodErrors(validation.error);
      setErrors(formattedErrors);
      if (formattedErrors.tenant) setActiveTab("tenant");
      else if (formattedErrors.admin) setActiveTab("admin");
      else if (formattedErrors.usage) setActiveTab("usage");
      return;
    }

    const payload = mapTenantFormToCreateRequest(validation.data);
    try {
      const tenant = await createTenant(payload);
      if (validation.data.tenant.logo instanceof File) {
        const contentBase64 = await fileToDataUrl(validation.data.tenant.logo);
        await uploadTenantLogo({
          id: tenant.id,
          data: {
            filename: validation.data.tenant.logo.name,
            mime_type: validation.data.tenant.logo.type || "application/octet-stream",
            content_base64: contentBase64,
          },
        });
      }
      const params = new URLSearchParams({
        created: "1",
        email: tenant.activation_email?.recipient_email || validation.data.admin.email,
        emailStatus: tenant.activation_email?.delivered
          ? "sent"
          : tenant.activation_email?.attempted
            ? "failed"
            : "skipped",
      });
      if (tenant.activation_email?.reason) {
        params.set("emailReason", tenant.activation_email.reason);
      }
      router.push(`/tenants/${tenant.id}?${params.toString()}`);
    } catch (error) {
      const detail =
        isAxiosError(error) && typeof error.response?.data?.detail === "string"
          ? error.response.data.detail
          : "We could not create the tenant right now.";
      setSubmissionFeedback({
        title: "Tenant creation failed",
        description: detail,
      });
    }
  };

  return (
    <div className="w-full px-6 py-6">
      <div className="max-w-[1110px] space-y-8">
        <div className="flex items-start justify-between gap-4">
          <h1 className="font-dmSans text-[44px] font-bold leading-none tracking-[-0.03em] text-primary">Create Tenant</h1>
          <Button
            onClick={handleSubmit}
            disabled={isPending || isUploadingLogo}
            className="h-12 rounded-[2px] bg-primary/72 px-7 text-base font-semibold text-white hover:bg-primary/90"
          >
            {isPending || isUploadingLogo ? "Creating..." : "Create"}
          </Button>
        </div>
        {submissionFeedback ? (
          <Alert variant="destructive">
            <AlertTitle>{submissionFeedback.title}</AlertTitle>
            <AlertDescription>{submissionFeedback.description}</AlertDescription>
          </Alert>
        ) : null}
        <TenantForm
          form={form}
          setForm={setForm}
          tab={activeTab}
          setTab={setActiveTab}
          errors={errors}
          clearFieldError={clearFieldError}
        />
      </div>
    </div>
  );
}
