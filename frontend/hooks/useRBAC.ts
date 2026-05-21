import { useGetMe } from "./useUser";
import { ROLE_MODULES } from "@/lib/module-access";
import { ROLE_PERMISSIONS } from "@/lib/permissions";
import type { Action, Module } from "@/types/rbac.types";

export function useRBAC() {
  const { data: user } = useGetMe();

  function canAccessModule(module: Module) {
    if (!user) return false;
    return ROLE_MODULES[user.role]?.includes(module);
  }

  function can(module: Module, action: Action) {
    if (!user) return false;
    if (user.role === "PLATFORM_OWNER") return true;

    return ROLE_PERMISSIONS[user.role]?.[module]?.includes(action) ?? false;
  }

  return {
    user,
    can,
    canAccessModule,
  };
}
