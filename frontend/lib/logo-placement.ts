export const LOGO_PLACEMENT_OPTIONS = [
  "top-right",
  "top-left",
  "bottom-right",
  "bottom-left",
  "top-center",
  "bottom-center",
  "center",
] as const;

export type LogoPlacementOption = (typeof LOGO_PLACEMENT_OPTIONS)[number];

const LOGO_PLACEMENT_SET = new Set<string>(LOGO_PLACEMENT_OPTIONS);

export function isLogoPlacementOption(value: unknown): value is LogoPlacementOption {
  return typeof value === "string" && LOGO_PLACEMENT_SET.has(value);
}

export function normalizeLogoPlacementPolicy(
  allowedInput: unknown,
  defaultInput: unknown,
): { allowedLogoPlacements: LogoPlacementOption[]; defaultLogoPlacement: LogoPlacementOption | "" } {
  const allowedLogoPlacements: LogoPlacementOption[] = [];
  if (Array.isArray(allowedInput)) {
    for (const item of allowedInput) {
      if (isLogoPlacementOption(item) && !allowedLogoPlacements.includes(item)) {
        allowedLogoPlacements.push(item);
      }
    }
  }

  const defaultLogoPlacement =
    isLogoPlacementOption(defaultInput) && allowedLogoPlacements.includes(defaultInput) ? defaultInput : allowedLogoPlacements[0] || "";

  return { allowedLogoPlacements, defaultLogoPlacement };
}
