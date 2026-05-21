import { useMutation, useQueryClient } from "@tanstack/react-query";
import { clearAuthTokens } from "@/lib/api/session";

export const useLogout = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => true,
    onSuccess: () => {
      clearAuthTokens();
      queryClient.clear();
      window.location.href = "/auth/login";
    },
  });
};
