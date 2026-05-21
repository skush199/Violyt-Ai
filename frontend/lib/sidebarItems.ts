// lib/sidebarItems.ts

import { Module } from "@/types/rbac.types"

export type SidebarItemProps = {
  id: number
  name: string
  href?: string
  icon: string
  module: Module // 🔥 ADD THIS
}

export const sidebarItems: SidebarItemProps[] = [
  {
    id: 1,
    name: "Dashboard",
    href: "/dashboard",
    icon: "/dashboard",
    module: "DASHBOARD",
  },
  {
    id: 2,
    name: "Tenant Management",
    href: "/tenants",
    icon: "/box",
    module: "TENANT_MANAGEMENT",
  },
  {
    id: 3,
    name: "Analytics",
    href: "/analytics",
    icon: "/analytics",
    module: "ANALYTICS",
  },
  {
    id: 4,
    name: "Brand Spaces",
    href: "/brand_space",
    icon: "/box",
    module: "BRAND_SPACE",
  },
  {
    id: 5,
    name: "User Management",
    href: "/user_management",
    icon: "/user_management",
    module: "USER_MANAGEMENT",
  },
  {
    id: 6,
    name: "Notification",
    // href: "/notifications",
    icon: "/notification",
    module: "NOTIFICATION",
  },
]
