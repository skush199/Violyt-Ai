import { useQuery } from "@tanstack/react-query";
import { API } from "@/lib/api/endpoints";
import { request } from "@/lib/api/request";

export const useGetTenants = (enabled = true) =>
  useQuery({
    queryKey: ["tenants"],
    enabled,
    queryFn: () => request(API.TENANTS.LIST),
  });

export const useGetTenantData = (id: string) =>
  useQuery({
    queryKey: ["tenant", id],
    enabled: Boolean(id),
    queryFn: () => request(API.TENANTS.DETAIL, { pathParams: id }),
  });

export const useGetTenantUsers = (tenantId: string) =>
  useQuery({
    queryKey: ["tenant", tenantId, "users"],
    enabled: Boolean(tenantId),
    queryFn: () => request(API.TENANTS.USERS, { pathParams: tenantId }),
  });

export const useGetTenantBrandSpaces = (tenantId: string) =>
  useQuery({
    queryKey: ["tenant", tenantId, "brand-spaces"],
    enabled: Boolean(tenantId),
    queryFn: () => request(API.TENANTS.BRAND_SPACES, { pathParams: tenantId }),
  });

export const useGetTenantUsageSummary = (tenantId: string) =>
  useQuery({
    queryKey: ["tenant", tenantId, "usage-summary"],
    enabled: Boolean(tenantId),
    queryFn: () => request(API.TENANTS.USAGE_SUMMARY, { pathParams: tenantId }),
  });

export const useGetTenantUser = (tenantId: string, userId: string) =>
  useQuery({
    queryKey: ["tenant", tenantId, "user", userId],
    enabled: Boolean(tenantId && userId),
    queryFn: () =>
      request(API.TENANTS.USER_DETAIL, {
        pathParams: { tenantId, userId },
      }),
  });
