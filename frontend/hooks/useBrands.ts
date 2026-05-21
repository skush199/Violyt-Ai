import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ApiEndpoint } from "@/lib/api/endpoints";
import { API } from "@/lib/api/endpoints";
import { request } from "@/lib/api/request";

export const useBrands = (enabled = true) =>
  useQuery({
    queryKey: ["brands"],
    enabled,
    queryFn: () => request(API.BRANDS.LIST),
  });

export const useBrand = (brandId: string) =>
  useQuery({
    queryKey: ["brand", brandId],
    enabled: Boolean(brandId),
    queryFn: () => request(API.BRANDS.DETAIL, { pathParams: brandId }),
  });

export const useBrandOverview = (brandId: string) =>
  useQuery({
    queryKey: ["brand", brandId, "overview"],
    enabled: Boolean(brandId),
    queryFn: () => request(API.BRANDS.OVERVIEW, { pathParams: brandId }),
  });

export const useCreateBrand = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: unknown) => request(API.BRANDS.CREATE, { data }),
    onSuccess: async (brand) => {
      await queryClient.invalidateQueries({ queryKey: ["brands"] });
      await queryClient.invalidateQueries({ queryKey: ["brand", brand.id] });
    },
  });
};

export const useUpsertBrandSection = (brandId: string, sectionCode: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: unknown) =>
      request(API.BRANDS.UPSERT_SECTION, {
        pathParams: { brandId, sectionCode },
        data,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId] });
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId, "overview"] });
      await queryClient.invalidateQueries({ queryKey: ["brands"] });
    },
  });
};

export const useFinalizeBrand = (brandId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => request(API.BRANDS.PUBLISH, { pathParams: brandId }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId] });
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId, "overview"] });
      await queryClient.invalidateQueries({ queryKey: ["brands"] });
    },
  });
};

const useBrandLifecycleMutation = (
  brandId: string,
  endpoint: ApiEndpoint<void, unknown>,
) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => request(endpoint, { pathParams: brandId }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId] });
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId, "overview"] });
      await queryClient.invalidateQueries({ queryKey: ["brands"] });
    },
  });
};

export const usePublishBrand = (brandId: string) => useBrandLifecycleMutation(brandId, API.BRANDS.PUBLISH);

export const useUnpublishBrand = (brandId: string) => useBrandLifecycleMutation(brandId, API.BRANDS.UNPUBLISH);

export const useArchiveBrand = (brandId: string) => useBrandLifecycleMutation(brandId, API.BRANDS.ARCHIVE);

export const useRestoreBrand = (brandId: string) => useBrandLifecycleMutation(brandId, API.BRANDS.RESTORE);

export const useDeleteBrand = (brandId: string) => useBrandLifecycleMutation(brandId, API.BRANDS.DELETE);

const useDynamicBrandLifecycleMutation = (endpoint: ApiEndpoint<void, unknown>) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (brandId: string) => request(endpoint, { pathParams: brandId }),
    onSuccess: async (_response, brandId) => {
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId] });
      await queryClient.invalidateQueries({ queryKey: ["brand", brandId, "overview"] });
      await queryClient.invalidateQueries({ queryKey: ["brands"] });
    },
  });
};

export const usePublishBrandMutation = () => useDynamicBrandLifecycleMutation(API.BRANDS.PUBLISH);

export const useUnpublishBrandMutation = () => useDynamicBrandLifecycleMutation(API.BRANDS.UNPUBLISH);

export const useArchiveBrandMutation = () => useDynamicBrandLifecycleMutation(API.BRANDS.ARCHIVE);

export const useRestoreBrandMutation = () => useDynamicBrandLifecycleMutation(API.BRANDS.RESTORE);

export const useDeleteBrandMutation = () => useDynamicBrandLifecycleMutation(API.BRANDS.DELETE);
