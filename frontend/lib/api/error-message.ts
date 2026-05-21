import { isAxiosError } from "axios";

type ErrorRecord = Record<string, unknown>;

function isRecord(value: unknown): value is ErrorRecord {
  return typeof value === "object" && value !== null;
}

function getValidationLocation(loc: unknown) {
  if (!Array.isArray(loc)) {
    return null;
  }

  const path = loc
    .map((segment) => (typeof segment === "string" || typeof segment === "number" ? String(segment) : ""))
    .filter((segment) => segment && segment !== "body" && segment !== "query" && segment !== "path");

  return path.length ? path.join(".") : null;
}

function getValidationMessage(value: ErrorRecord) {
  const message = typeof value.msg === "string" && value.msg.trim() ? value.msg.trim() : null;
  if (!message) {
    return null;
  }

  const location = getValidationLocation(value.loc);
  return location ? `${location}: ${message}` : message;
}

function extractMessage(value: unknown): string | null {
  if (typeof value === "string") {
    return value.trim() || null;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  if (Array.isArray(value)) {
    const messages = value
      .map(extractMessage)
      .filter((message): message is string => Boolean(message));

    return messages.length ? Array.from(new Set(messages)).join(" ") : null;
  }

  if (!isRecord(value)) {
    return null;
  }

  const validationMessage = getValidationMessage(value);
  if (validationMessage) {
    return validationMessage;
  }

  const candidateKeys = ["detail", "message", "error", "errors"];
  for (const key of candidateKeys) {
    const message = extractMessage(value[key]);
    if (message) {
      return message;
    }
  }

  const nestedMessages = Object.values(value)
    .map(extractMessage)
    .filter((message): message is string => Boolean(message));

  return nestedMessages.length ? Array.from(new Set(nestedMessages)).join(" ") : null;
}

export function getApiErrorMessage(error: unknown, fallback: string) {
  if (isAxiosError(error)) {
    const responseMessage = extractMessage(error.response?.data);
    if (responseMessage) {
      return responseMessage;
    }

    const axiosMessage = extractMessage(error.message);
    if (axiosMessage) {
      return axiosMessage;
    }
  }

  return extractMessage(error) || fallback;
}
