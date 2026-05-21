import type { TenantSummaryResponse } from "@/lib/api/contracts";
import { apiOrigin } from "@/lib/env";

export function resolveTenantLogoUrl(tenant?: Pick<TenantSummaryResponse, "logo_asset_path"> | null) {
  if (!tenant?.logo_asset_path) {
    return null;
  }
  return `${apiOrigin}/storage/${tenant.logo_asset_path}`;
}
