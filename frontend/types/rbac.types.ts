// types/rbac.types.ts

export type Role =
  | "PLATFORM_OWNER"
  | "TENANT_ADMIN"
  | "TENANT_USER"
  | "BRAND_USER"

export type Module =
  | "DASHBOARD"
  | "TENANT_MANAGEMENT"
  | "ANALYTICS"
  | "BRAND_SPACE"
  | "USER_MANAGEMENT"
  | "NOTIFICATION"

export type Action =
  | "VIEW"
  | "CREATE"
  | "EDIT"
  | "DELETE"
