export const isDev = process.env.NEXT_PUBLIC_ENV === "development";
export const isProd = process.env.NEXT_PUBLIC_ENV === "production";

function stripTrailingSlash(value: string) {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function stripApiPrefix(value: string) {
  return value.replace(/\/api\/v1\/?$/i, "");
}

const configuredApiValue =
  process.env.NEXT_PUBLIC_API_BASE_URI ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export const apiOrigin = stripTrailingSlash(stripApiPrefix(configuredApiValue));
export const apiBasePath = `${apiOrigin}/api/v1`;
