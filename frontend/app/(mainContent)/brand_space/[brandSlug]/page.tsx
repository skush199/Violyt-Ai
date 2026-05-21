"use client";

import { useParams } from "next/navigation";
import WorkspaceChat from "@/components/chat/WorkspaceChat";

export default function BrandWorkspacePage() {
  const params = useParams<{ brandSlug: string }>();
  return <WorkspaceChat brandKey={params.brandSlug} />;
}
