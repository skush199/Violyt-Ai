"use client";

import { createContext, useContext, useSyncExternalStore } from "react";

type NetworkContextType = {
  isOnline: boolean;
};

const networkContext = createContext<NetworkContextType>({
  isOnline: true,
});

function subscribe(callback: () => void) {
  window.addEventListener("online", callback);
  window.addEventListener("offline", callback);

  return () => {
    window.removeEventListener("online", callback);
    window.removeEventListener("offline", callback);
  };
}

function getSnapshot() {
  return window.navigator.onLine;
}

function getServerSnapshot() {
  return true;
}

export function NetworkProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const isOnline = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  return <networkContext.Provider value={{ isOnline }}>{children}</networkContext.Provider>;
}

export const useNetwork = () => {
  return useContext(networkContext);
};
