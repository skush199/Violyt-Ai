"use client";

import { useMemo } from "react";
import { useParams } from "next/navigation";
import BrandSpaceEditor from "@/components/brandSpaces/BrandSpaceEditor";
import { useBrandOverview, useBrands } from "@/hooks/useBrands";
import { mapBrandOverviewToForm } from "@/lib/brand-mappers";
import { resolveBrandByRouteKey } from "@/lib/brand-routing";

export default function EditBrandSpacePage() {
  const params = useParams<{ brandSlug: string }>();
  const { data: brands, isLoading: isBrandsLoading } = useBrands();
  const brand = useMemo(
    () => resolveBrandByRouteKey(brands, params.brandSlug),
    [brands, params.brandSlug],
  );
  const { data: overview, isLoading: isOverviewLoading } = useBrandOverview(brand?.id || "");

  const initialForm = useMemo(
    () => (overview ? mapBrandOverviewToForm(overview) : undefined),
    [overview],
  );

  if (isBrandsLoading || isOverviewLoading || !brand || !overview || !initialForm) {
    return <div className="w-full px-6 py-10 text-sm text-slate-500">Loading Brand Space...</div>;
  }

  return (
    <BrandSpaceEditor
      mode="edit"
      brandId={brand.id}
      initialForm={initialForm}
      initialLifecycleState={overview.brand.lifecycle_state}
    />
  );
}
