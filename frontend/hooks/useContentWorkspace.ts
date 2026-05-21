import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API } from "@/lib/api/endpoints";
import { request } from "@/lib/api/request";
import type { StudioPanelSelection } from "@/lib/api/contracts";

function brandHeaders(brandId: string) {
  return {
    "X-Brand-Space-Id": brandId,
  };
}

export const useContentHistory = (brandId: string) =>
  useQuery({
    queryKey: ["brand", brandId, "content-history"],
    enabled: Boolean(brandId),
    queryFn: () =>
      request(API.CONTENT.HISTORY, {
        headers: brandHeaders(brandId),
      }),
  });

export const useGenerateContent = (brandId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: unknown) =>
      request(API.CONTENT.GENERATE, {
        data,
        headers: brandHeaders(brandId),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId, "content-history"] });
    },
  });
};

export const useExportContent = (brandId: string) =>
  useMutation({
    mutationFn: (data: unknown) =>
      request(API.CONTENT.EXPORT, {
        data,
        headers: brandHeaders(brandId),
      }),
  });

export const useTemplateRecommendations = (
  brandId: string,
  prompt: string,
  studioPanel: StudioPanelSelection,
  limit = 3,
  enabled = true,
) =>
  useQuery({
    queryKey: ["brand", brandId, "template-recommendations", prompt, studioPanel, limit],
    enabled: enabled && Boolean(brandId) && Boolean(prompt.trim()),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: () =>
      request(API.TEMPLATES.RECOMMEND, {
        data: {
          prompt,
          studio_panel: studioPanel,
          limit,
        },
        headers: brandHeaders(brandId),
      }),
  });

export const useToneCheck = (brandId: string) =>
  useMutation({
    mutationFn: (data: unknown) =>
      request(API.CONTENT.TONE_CHECK, {
        data,
        headers: brandHeaders(brandId),
      }),
  });

export const useCreateChatSession = (brandId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: unknown) =>
      request(API.CHAT.CREATE_SESSION, {
        data,
        headers: brandHeaders(brandId),
      }),
    onSuccess: async (session) => {
      queryClient.setQueryData(["brand", brandId, "chat-sessions"], (current: Array<{ id: string }> | undefined) => {
        if (!current) {
          return [session];
        }
        const next = current.filter((item) => item.id !== session.id);
        return [session, ...next];
      });
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId, "chat-sessions"] });
    },
  });
};

export const useChatSessions = (brandId: string) =>
  useQuery({
    queryKey: ["brand", brandId, "chat-sessions"],
    enabled: Boolean(brandId),
    queryFn: () =>
      request(API.CHAT.LIST_SESSIONS, {
        headers: brandHeaders(brandId),
      }),
  });

export const useChatMessages = (brandId: string, sessionId: string) =>
  useQuery({
    queryKey: ["brand", brandId, "chat-session", sessionId, "messages"],
    enabled: Boolean(brandId && sessionId),
    queryFn: () =>
      request(API.CHAT.LIST_MESSAGES, {
        pathParams: sessionId,
        headers: brandHeaders(brandId),
      }),
  });

export const useSendChatMessage = (brandId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, data }: { sessionId: string; data: unknown }) =>
      request(API.CHAT.SEND_MESSAGE, {
        pathParams: sessionId,
        data,
        headers: brandHeaders(brandId),
      }),
    onSuccess: async (response, variables) => {
      queryClient.setQueryData(
        ["brand", brandId, "chat-session", variables.sessionId, "messages"],
        (current: Array<{ id: string }> | undefined) => {
          const items = current || [];
          const seen = new Set(items.map((item) => item.id));
          const appended = [response.user_message, response.assistant_message].filter((item) => !seen.has(item.id));
          return [...items, ...appended];
        },
      );
      await queryClient.invalidateQueries({
        queryKey: ["brand", brandId, "chat-session", variables.sessionId, "messages"],
      });
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId, "content-history"] });
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId, "chat-sessions"] });
    },
  });
};

export const useCreateShareLink = (brandId: string) =>
  useMutation({
    mutationFn: (data: unknown) =>
      request(API.REVIEW.CREATE_LINK, {
        data,
        headers: brandHeaders(brandId),
      }),
  });

export const useReviewDetail = (token: string) =>
  useQuery({
    queryKey: ["review", token],
    enabled: Boolean(token),
    queryFn: () => request(API.REVIEW.DETAIL, { pathParams: token }),
  });

export const useAddReviewComment = (token: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: unknown) =>
      request(API.REVIEW.ADD_COMMENT, {
        pathParams: token,
        data,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["review", token] });
    },
  });
};

export const useTenantAnalytics = (enabled = true) =>
  useQuery({
    queryKey: ["analytics", "tenant"],
    enabled,
    queryFn: () => request(API.ANALYTICS.TENANT),
  });

export const usePlatformAnalytics = (enabled = true) =>
  useQuery({
    queryKey: ["analytics", "platform"],
    enabled,
    queryFn: () => request(API.ANALYTICS.PLATFORM),
  });

export const useKnowledgeAssets = (brandId: string) =>
  useQuery({
    queryKey: ["brand", brandId, "knowledge-assets"],
    enabled: Boolean(brandId),
    queryFn: () =>
      request(API.KNOWLEDGE.LIST, {
        headers: brandHeaders(brandId),
      }),
  });

export const useUploadKnowledgeAsset = (brandId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: unknown) =>
      request(API.KNOWLEDGE.UPLOAD, {
        data,
        headers: brandHeaders(brandId),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId, "knowledge-assets"] });
    },
  });
};
