import type { BrandResponse } from "@/lib/api/contracts";

type RoutableBrand = Pick<BrandResponse, "id" | "slug">;

export function resolveBrandRouteKey(brand: RoutableBrand) {
  return brand.id || brand.slug;
}

export function resolveBrandByRouteKey<TBrand extends RoutableBrand>(
  brands: readonly TBrand[] | undefined,
  routeKey: string | undefined,
) {
  if (!brands?.length || !routeKey) {
    return undefined;
  }

  return brands.find((brand) => brand.id === routeKey) || brands.find((brand) => brand.slug === routeKey);
}

export function buildBrandWorkspaceHref(brand: RoutableBrand) {
  return `/brand_space/${resolveBrandRouteKey(brand)}`;
}

export function buildBrandEditHref(brand: RoutableBrand) {
  return `${buildBrandWorkspaceHref(brand)}/edit`;
}

export function buildBrandSharingHref(brand: RoutableBrand) {
  return `${buildBrandWorkspaceHref(brand)}/sharing`;
}
