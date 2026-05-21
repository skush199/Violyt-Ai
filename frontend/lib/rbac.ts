
import { ROLE_MODULES } from "./module-access"
import { ROLE_PERMISSIONS } from "./permissions"
import { Role, Module, Action } from "@/types/rbac.types"

export interface User {
    id: string;
    role: Role;
    email: string;
    notificationsEnabled?: boolean;
    twoFactorEnabled?: boolean;
    tenantId?: string;
    brandSpaceIds?: string[];
}

export const canAccessModule = (
    user: User,
    module: Module
) => {
    return ROLE_MODULES[user?.role]?.includes(module)
}

export const canPerform = (
    user: User,
    module: Module,
    action: Action
) => {
    if (user.role === "PLATFORM_OWNER") return true;

    const modulePermissions = ROLE_PERMISSIONS[user.role]?.[module]
    return modulePermissions?.includes(action) ?? false;
}


export function canAccessBrand(
    user: User,
    brandId: string
) {
    if (user.role === "PLATFORM_OWNER") return true
    if (user.role === "TENANT_ADMIN") return true
    if (user.role === "TENANT_USER") return true

    // BRAND_USER
    return user.brandSpaceIds?.includes(brandId)
}
