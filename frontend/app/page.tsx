"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import LoaderFullscreen from "@/components/LoaderFullscreen";
import { useGetMe } from "@/hooks/useUser";

export default function ProtectedLayout() {
  const { data, isLoading } = useGetMe();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) {
      return;
    }

    router.replace(!data ? "/dashboard" : "/auth/login");
  }, [data, isLoading, router]);

  if (isLoading) {
    return <LoaderFullscreen />;
  }

  return null;
}
