import type { BrandResponse } from "@/lib/api/contracts";
import { apiOrigin } from "@/lib/env";

type AnyBrand = BrandResponse & {
  logo?: string | null;
};

export function resolveBrandLogoUrl(brand: AnyBrand): string | null {
  if ("logo" in brand && typeof brand.logo === "string" && brand.logo) {
    return brand.logo;
  }

  if (!("resolved_brand_context" in brand)) {
    return null;
  }

  const identity = (brand.resolved_brand_context as Record<string, unknown>)?.identity as
    | Record<string, unknown>
    | undefined;

  const directUrl = identity?.logo_asset_url;
  if (typeof directUrl === "string" && directUrl) {
    return directUrl;
  }

  const storagePath = identity?.logo_asset_path;
  if (typeof storagePath === "string" && storagePath) {
    return `${apiOrigin}/storage/${storagePath}`;
  }

  return null;
}
