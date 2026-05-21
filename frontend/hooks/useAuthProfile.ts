import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API } from "@/lib/api/endpoints";
import type { TwoFactorSetupResponse } from "@/lib/api/contracts";
import { request } from "@/lib/api/request";
import { clearTwoFactorTicket, setAuthTokens } from "@/lib/api/session";

export const useProfile = () =>
  useQuery({
    queryKey: ["auth", "profile"],
    queryFn: () => request(API.AUTH.PROFILE),
  });

export const useUpdateProfile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { full_name?: string; email?: string; phone_number?: string; notifications_enabled?: boolean }) =>
      request(API.AUTH.UPDATE_PROFILE, { data }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["auth", "profile"] });
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
};

export const useChangePassword = () =>
  useMutation({
    mutationFn: (data: { current_password: string; new_password: string }) => request(API.AUTH.CHANGE_PASSWORD, { data }),
  });

export const useDeleteProfile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => request(API.AUTH.DELETE_PROFILE),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["auth", "profile"] });
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
};

export const useTwoFactorStatus = () =>
  useQuery<TwoFactorSetupResponse>({
    queryKey: ["auth", "two-factor-status"],
    queryFn: () => request(API.AUTH.TWO_FACTOR_STATUS),
  });

export const useSetupTwoFactor = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => request(API.AUTH.TWO_FACTOR_SETUP),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["auth", "two-factor-status"] });
    },
  });
};

export const useEnableTwoFactor = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { code: string }) => request(API.AUTH.TWO_FACTOR_ENABLE, { data }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["auth", "two-factor-status"] });
      await queryClient.invalidateQueries({ queryKey: ["auth", "profile"] });
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
};

export const useDisableTwoFactor = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { code: string }) => request(API.AUTH.TWO_FACTOR_DISABLE, { data }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["auth", "two-factor-status"] });
      await queryClient.invalidateQueries({ queryKey: ["auth", "profile"] });
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
};

export const useVerifyTwoFactor = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { ticket: string; code: string }) => request(API.AUTH.TWO_FACTOR_VERIFY, { data }),
    onSuccess: async (tokens) => {
      setAuthTokens(tokens.access_token, tokens.refresh_token);
      clearTwoFactorTicket();
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      await queryClient.invalidateQueries({ queryKey: ["auth", "profile"] });
    },
  });
};
