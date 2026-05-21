export type CreatedDateFilter = "all" | "last30" | "last90" | "thisYear";
export type RecentActivityStatus = "engaged" | "dormant";
export type RecentActivityFilter = "all" | RecentActivityStatus;
export type UserActivityStatus = RecentActivityStatus | "pending";
export type UserActivityFilter = "all" | UserActivityStatus;

const DAY_MS = 1000 * 60 * 60 * 24;

export const CREATED_DATE_FILTER_OPTIONS: ReadonlyArray<{ value: CreatedDateFilter; label: string }> = [
  { value: "all", label: "All dates" },
  { value: "last30", label: "Created last 30 days" },
  { value: "last90", label: "Created last 90 days" },
  { value: "thisYear", label: "Created this year" },
];

export const RECENT_ACTIVITY_FILTER_OPTIONS: ReadonlyArray<{ value: RecentActivityFilter; label: string }> = [
  { value: "all", label: "All activity" },
  { value: "engaged", label: "Engaged" },
  { value: "dormant", label: "Dormant" },
];

export const USER_ACTIVITY_FILTER_OPTIONS: ReadonlyArray<{ value: UserActivityFilter; label: string }> = [
  { value: "all", label: "All activity" },
  { value: "engaged", label: "Engaged" },
  { value: "dormant", label: "Dormant" },
  { value: "pending", label: "Pending activation" },
];

function parseDate(value?: string | null) {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function matchesCreatedDateFilter(value: string | null | undefined, filter: CreatedDateFilter) {
  if (filter === "all") {
    return true;
  }

  const parsed = parseDate(value);
  if (!parsed) {
    return false;
  }

  const now = new Date();
  if (filter === "thisYear") {
    return parsed.getFullYear() === now.getFullYear();
  }

  const dayWindow = filter === "last30" ? 30 : 90;
  const ageInMs = now.getTime() - parsed.getTime();
  return ageInMs >= 0 && ageInMs <= dayWindow * DAY_MS;
}

export function getRecentActivityStatus(value?: string | null): RecentActivityStatus {
  const parsed = parseDate(value);
  if (!parsed) {
    return "dormant";
  }

  const ageInMs = Date.now() - parsed.getTime();
  return ageInMs <= 30 * DAY_MS ? "engaged" : "dormant";
}

export function getUserActivityStatus(lastLoginAt?: string | null, isActivated?: boolean): UserActivityStatus {
  if (!isActivated) {
    return "pending";
  }

  if (!lastLoginAt) {
    return "engaged";
  }

  return getRecentActivityStatus(lastLoginAt);
}

export function formatRecentActivityStatus(status: RecentActivityStatus) {
  return status === "engaged" ? "Engaged" : "Dormant";
}

export function formatUserActivityStatus(status: UserActivityStatus) {
  if (status === "pending") {
    return "Pending Activation";
  }

  return formatRecentActivityStatus(status);
}
