const ACCESS_TOKEN_KEY = "violyt.access_token";
const REFRESH_TOKEN_KEY = "violyt.refresh_token";
const TWO_FACTOR_TICKET_KEY = "violyt.two_factor_ticket";
const TWO_FACTOR_EMAIL_KEY = "violyt.two_factor_email";

function canUseStorage() {
  return typeof window !== "undefined";
}

export function getAccessToken() {
  if (!canUseStorage()) {
    return null;
  }
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken() {
  if (!canUseStorage()) {
    return null;
  }
  return window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setAuthTokens(accessToken: string, refreshToken?: string) {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (refreshToken) {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
  clearTwoFactorTicket();
}

export function setAccessToken(accessToken: string) {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
}

export function clearAuthTokens() {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function setTwoFactorTicket(ticket: string, email?: string) {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.setItem(TWO_FACTOR_TICKET_KEY, ticket);
  if (email) {
    window.localStorage.setItem(TWO_FACTOR_EMAIL_KEY, email);
  }
}

export function getTwoFactorTicket() {
  if (!canUseStorage()) {
    return null;
  }
  return window.localStorage.getItem(TWO_FACTOR_TICKET_KEY);
}

export function getTwoFactorEmail() {
  if (!canUseStorage()) {
    return null;
  }
  return window.localStorage.getItem(TWO_FACTOR_EMAIL_KEY);
}

export function clearTwoFactorTicket() {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.removeItem(TWO_FACTOR_TICKET_KEY);
  window.localStorage.removeItem(TWO_FACTOR_EMAIL_KEY);
}
