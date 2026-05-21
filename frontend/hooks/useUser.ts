import { useQuery } from "@tanstack/react-query";
import { API } from "@/lib/api/endpoints";
import type { CurrentUserResponse, UiUser } from "@/lib/api/contracts";
import { request } from "@/lib/api/request";
import { getAccessToken } from "@/lib/api/session";

function normalizeRole(roleCodes: string[]): UiUser["role"] {
  if (roleCodes.includes("super_admin")) {
    return "PLATFORM_OWNER";
  }
  if (roleCodes.includes("tenant_admin")) {
    return "TENANT_ADMIN";
  }
  if (roleCodes.includes("tenant_user")) {
    return "TENANT_USER";
  }
  return "BRAND_USER";
}

function normalizeUser(payload: CurrentUserResponse): UiUser {
  return {
    id: payload.user_id,
    tenantId: payload.tenant_id,
    email: payload.email,
    name: payload.full_name,
    role: normalizeRole(payload.role_codes),
    roleCodes: payload.role_codes,
    brandSpaceIds: payload.assigned_brand_space_ids,
    phone: typeof payload.extra?.phone_number === "string" ? payload.extra.phone_number : undefined,
    notificationsEnabled:
      typeof payload.extra?.notifications_enabled === "boolean" ? payload.extra.notifications_enabled : true,
    twoFactorEnabled:
      typeof payload.extra?.two_factor_enabled === "boolean" ? payload.extra.two_factor_enabled : false,
  };
}

export const useGetMe = () => {
  return useQuery<UiUser | null>({
    queryKey: ["me"],
    queryFn: async () => {
      if (!getAccessToken()) {
        return null;
      }
      const response = await request(API.USER.GET_ME);
      return normalizeUser(response);
    },
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
};
