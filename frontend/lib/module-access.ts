import { Module, Role } from "@/types/rbac.types";


export const ROLE_MODULES: Record<Role, Module[]> = {
  PLATFORM_OWNER: ["DASHBOARD", "TENANT_MANAGEMENT", "ANALYTICS"],

  TENANT_ADMIN: [
    "DASHBOARD",
    "BRAND_SPACE",
    "USER_MANAGEMENT",
    "NOTIFICATION",
  ],

  TENANT_USER: [
    "DASHBOARD",
    "BRAND_SPACE",
    "NOTIFICATION",
  ],

  BRAND_USER: [
    "BRAND_SPACE",
    "NOTIFICATION",
  ],
}
