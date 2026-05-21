import { useMutation, useQueryClient } from "@tanstack/react-query";
import { API } from "@/lib/api/endpoints";
import { request } from "@/lib/api/request";

export const useUpdateTenantAdmin = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: unknown }) =>
      request(API.TENANTS.UPDATE, {
        pathParams: id,
        data,
      }),
    onSuccess: async (_, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["tenants"] });
      await queryClient.invalidateQueries({ queryKey: ["tenant", variables.id] });
      await queryClient.invalidateQueries({ queryKey: ["tenant", variables.id, "usage-summary"] });
      await queryClient.invalidateQueries({ queryKey: ["tenant", variables.id, "users"] });
    },
  });
};

export const useUploadTenantLogo = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: unknown }) =>
      request(API.TENANTS.UPLOAD_LOGO, {
        pathParams: id,
        data,
      }),
    onSuccess: async (_, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["tenants"] });
      await queryClient.invalidateQueries({ queryKey: ["tenant", variables.id] });
    },
  });
};

export const useUpdateTenantUser = (tenantId: string, userId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: unknown) =>
      request(API.TENANTS.UPDATE_USER, {
        pathParams: { tenantId, userId },
        data,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["tenant", tenantId, "users"] });
      await queryClient.invalidateQueries({ queryKey: ["tenant", tenantId, "user", userId] });
    },
  });
};
