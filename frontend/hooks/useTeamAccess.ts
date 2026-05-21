import { useMemo } from "react";
import { useCreateTenantUser } from "@/hooks/tenantAdmins/useCreateTenant";
import { useGetTenantUser, useGetTenantUsers } from "@/hooks/tenantAdmins/useGetTenants";
import { useUpdateTenantUser } from "@/hooks/tenantAdmins/useUpdateTenant";
import { useGetMe } from "@/hooks/useUser";

export const useTenantUsers = () => {
  const { data: currentUser } = useGetMe();
  const tenantId = currentUser?.tenantId || "";
  const query = useGetTenantUsers(tenantId);
  const tenantUsers = useMemo(
    () => (query.data || []).filter((user) => !user.role_codes.includes("brand_user")),
    [query.data],
  );
  const brandUsers = useMemo(
    () => (query.data || []).filter((user) => user.role_codes.includes("brand_user")),
    [query.data],
  );
  return {
    tenantId,
    ...query,
    tenantUsers,
    brandUsers,
  };
};

export const useTenantUserDetail = (userId: string) => {
  const { data: currentUser } = useGetMe();
  const tenantId = currentUser?.tenantId || "";
  const query = useGetTenantUser(tenantId, userId);
  return {
    tenantId,
    ...query,
  };
};

export const useSaveTenantUser = (userId?: string) => {
  const { data: currentUser } = useGetMe();
  const tenantId = currentUser?.tenantId || "";
  const createMutation = useCreateTenantUser(tenantId);
  const updateMutation = useUpdateTenantUser(tenantId, userId || "");

  return userId
    ? {
        tenantId,
        ...updateMutation,
      }
    : {
        tenantId,
        ...createMutation,
      };
};
