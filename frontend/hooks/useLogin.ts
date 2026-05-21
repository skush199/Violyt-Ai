import { useMutation, useQueryClient } from "@tanstack/react-query";
import { API } from "@/lib/api/endpoints";
import { request } from "@/lib/api/request";
import { setAuthTokens, setTwoFactorTicket } from "@/lib/api/session";

export const useLogin = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { email: string; password: string }) => request(API.AUTH.LOGIN, { data }),
    onSuccess: async (response) => {
      if ("access_token" in response) {
        setAuthTokens(response.access_token, response.refresh_token);
        await queryClient.invalidateQueries({ queryKey: ["me"] });
        return;
      }
      if ("two_factor_ticket" in response) {
        setTwoFactorTicket(response.two_factor_ticket, response.email);
      }
    },
  });
};
