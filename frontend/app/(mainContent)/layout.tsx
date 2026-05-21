"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import LoaderFullscreen from "@/components/LoaderFullscreen";
import { useGetMe } from "@/hooks/useUser";

export default function ContentLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const router = useRouter();
  const { data: user, isLoading } = useGetMe();

  useEffect(() => {
    if (isLoading) {
      return;
    }
    if (!user) {
      router.replace("/auth/login");
    }
  }, [isLoading, router, user]);

  if (isLoading || !user) {
    return <LoaderFullscreen />;
  }

  return (
    <div className="flex min-h-screen w-full gap-2 bg-white p-2">
      <Sidebar />
      <div className="relative min-h-[calc(100vh-16px)] flex-1 overflow-y-auto">{children}</div>
    </div>
  );
}
