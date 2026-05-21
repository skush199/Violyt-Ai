import { useMutation, useQueryClient } from "@tanstack/react-query";
import { API } from "@/lib/api/endpoints";
import { request } from "@/lib/api/request";

export const useCreateTenantAdmin = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: unknown) => request(API.TENANTS.CREATE, { data }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["tenants"] });
    },
  });
};

export const useCreateTenantUser = (tenantId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: unknown) =>
      request(API.TENANTS.CREATE_USER, {
        data,
        pathParams: tenantId,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["tenant", tenantId, "users"] });
    },
  });
};
