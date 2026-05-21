"use client";

import { useNetwork } from "@/context/network-provider";

const OfflineBanner = () => {
  const { isOnline } = useNetwork();

  if (isOnline) {
    return null;
  }

  return (
    <div className="fixed left-0 right-0 top-0 z-[99999] bg-red-600/70 py-2 text-center text-sm font-medium text-white">
      You are offline. Some features may not work.
    </div>
  );
};

export default OfflineBanner;
