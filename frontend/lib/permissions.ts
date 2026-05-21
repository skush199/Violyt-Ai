import { Role, Module, Action } from "@/types/rbac.types"

type PermissionMap = Record<
  Role,
  Partial<Record<Module, Action[]>>
>

export const ROLE_PERMISSIONS: PermissionMap = {
  PLATFORM_OWNER: {
    TENANT_MANAGEMENT: ["CREATE", "EDIT", "DELETE", "VIEW"],
  },

  TENANT_ADMIN: {
    USER_MANAGEMENT: ["CREATE", "EDIT", "DELETE", "VIEW"],
    BRAND_SPACE: ["CREATE", "EDIT", "DELETE", "VIEW"],
  },

  TENANT_USER: {
    BRAND_SPACE: ["VIEW"],
  },

  BRAND_USER: {
    BRAND_SPACE: ["VIEW"],
  },
}
