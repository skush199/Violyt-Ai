import axios from "axios";
import { clearAuthTokens, getAccessToken, getRefreshToken, setAuthTokens } from "@/lib/api/session";
import { apiOrigin } from "@/lib/env";

export const apiClient = axios.create({
  baseURL: apiOrigin,
  withCredentials: false,
});

let refreshRequest: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }
  if (!refreshRequest) {
    refreshRequest = axios
      .post(`${apiOrigin}/api/v1/auth/refresh`, { refresh_token: refreshToken }, { withCredentials: false })
      .then((response) => {
        const payload = response.data as { access_token: string; refresh_token: string };
        if (!payload?.access_token) {
          return null;
        }
        setAuthTokens(payload.access_token, payload.refresh_token);
        return payload.access_token;
      })
      .catch(() => {
        clearAuthTokens();
        return null;
      })
      .finally(() => {
        refreshRequest = null;
      });
  }
  return refreshRequest;
}

apiClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error?.config as ((typeof error)["config"] & { _retry?: boolean }) | undefined;
    if (
      error?.response?.status === 401
      && originalRequest
      && !originalRequest._retry
      && !String(originalRequest.url || "").includes("/api/v1/auth/refresh")
    ) {
      originalRequest._retry = true;
      const nextAccessToken = await refreshAccessToken();
      if (nextAccessToken) {
        originalRequest.headers = originalRequest.headers ?? {};
        originalRequest.headers.Authorization = `Bearer ${nextAccessToken}`;
        return apiClient(originalRequest);
      }
    }
    if (error?.response?.status === 401) {
      clearAuthTokens();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/auth/")) {
        window.location.href = "/auth/login";
      }
    }
    return Promise.reject(error);
  },
);
