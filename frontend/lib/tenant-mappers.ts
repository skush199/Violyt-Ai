import type {
  TenantCreateRequest,
  TenantSummaryResponse,
  TenantUpdateRequest,
  TenantUsageSummary,
  TenantUserResponse,
} from "@/lib/api/contracts";
import type { TenantFormData } from "@/types/tenant.types";

function joinAddress(form: TenantFormData["tenant"]) {
  return [form.address1, form.address2, form.city, form.state, form.zip, form.country]
    .filter(Boolean)
    .join(", ");
}

function splitAddress(address?: string) {
  const parts = (address || "").split(",").map((part) => part.trim());
  return {
    address1: parts[0] || "",
    address2: parts[1] || "",
    city: parts[2] || "",
    state: parts[3] || "",
    zip: parts[4] || "",
    country: parts[5] || "",
  };
}

function buildTenantMetadata(form: TenantFormData) {
  return {
    address: {
      line_1: form.tenant.address1,
      line_2: form.tenant.address2 || "",
      city: form.tenant.city,
      state: form.tenant.state,
      zip: form.tenant.zip,
      country: form.tenant.country,
    },
    usage_window: {
      start_month: form.usage.startMonth,
      end_month: form.usage.endMonth,
      renews_credits: form.usage.renewsCredits,
    },
  };
}

export function mapTenantFormToCreateRequest(form: TenantFormData): TenantCreateRequest {
  return {
    name: form.tenant.name,
    slug: form.tenant.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""),
    contact_email: form.tenant.email,
    contact_number: form.tenant.phone,
    address: joinAddress(form.tenant),
    admin_full_name: form.admin.name,
    admin_email: form.admin.email,
    admin_phone_number: form.admin.phone,
    metadata_json: buildTenantMetadata(form),
    usage_limits: {
      max_users: Number(form.usage.maxUsers || 0),
      max_brand_spaces: Number(form.usage.maxBrandSpaces || 0),
      max_content_generations: Number(form.usage.maxContentGenerations || 0),
      max_image_generations: Number(form.usage.maxVisualGenerations || 0),
      max_ocr_pages: Number(form.usage.maxOcrPages || 0),
    },
  };
}

export function mapTenantFormToUpdateRequest(form: TenantFormData): TenantUpdateRequest {
  return {
    ...mapTenantFormToCreateRequest(form),
  };
}

export function mapTenantSummaryToForm(
  summary: TenantSummaryResponse,
  usage?: TenantUsageSummary,
  adminUser?: TenantUserResponse,
): TenantFormData {
  const addressMetadata = (summary.metadata_json?.address as Record<string, unknown> | undefined) ?? {};
  const address = Object.keys(addressMetadata).length
    ? {
        address1: typeof addressMetadata.line_1 === "string" ? addressMetadata.line_1 : "",
        address2: typeof addressMetadata.line_2 === "string" ? addressMetadata.line_2 : "",
        city: typeof addressMetadata.city === "string" ? addressMetadata.city : "",
        state: typeof addressMetadata.state === "string" ? addressMetadata.state : "",
        zip: typeof addressMetadata.zip === "string" ? addressMetadata.zip : "",
        country: typeof addressMetadata.country === "string" ? addressMetadata.country : "",
      }
    : splitAddress(summary.address);
  const usageLimits = usage?.limits || summary.usage_limits;
  const usageWindow = (summary.metadata_json?.usage_window as Record<string, unknown> | undefined) ?? {};
  return {
    tenant: {
      name: summary.name,
      email: summary.contact_email,
      phone: summary.contact_number || "",
      logo: summary.logo_asset_path || "",
      ...address,
    },
    admin: {
      name: adminUser?.full_name || "",
      email: adminUser?.email || "",
      phone: adminUser?.phone_number || "",
    },
    usage: {
      startMonth: typeof usageWindow.start_month === "string" ? usageWindow.start_month : "",
      endMonth: typeof usageWindow.end_month === "string" ? usageWindow.end_month : "",
      renewsCredits: usageWindow.renews_credits !== false,
      maxContentGenerations: String(usageLimits?.max_content_generations || ""),
      maxVisualGenerations: String(usageLimits?.max_image_generations || ""),
      maxOcrPages: String(usageLimits?.max_ocr_pages || ""),
      maxUsers: String(usageLimits?.max_users || ""),
      maxBrandSpaces: String(usageLimits?.max_brand_spaces || ""),
    },
  };
}
