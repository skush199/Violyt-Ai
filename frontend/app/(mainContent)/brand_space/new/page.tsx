"use client";

import { useSearchParams } from "next/navigation";
import BrandSpaceEditor from "@/components/brandSpaces/BrandSpaceEditor";

export default function NewBrandSpace() {
  const searchParams = useSearchParams();
  const skipDraftHydration = searchParams.get("fresh") === "1";

  return <BrandSpaceEditor mode="create" skipDraftHydration={skipDraftHydration} />;
}
