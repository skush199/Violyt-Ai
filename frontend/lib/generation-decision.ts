import type { GenerationDecision, TemplateRecommendationResponse } from "@/lib/api/contracts";

function asObject(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

export function coerceGenerationDecision(value: unknown): GenerationDecision | null {
  const record = asObject(value);
  if (!record) {
    return null;
  }
  return record as GenerationDecision;
}

export function formatGenerationMode(mode: unknown) {
  if (typeof mode !== "string" || !mode.trim()) {
    return "Auto Layout";
  }
  switch (mode) {
    case "exact_template":
      return "Exact Template";
    case "adapted_template":
      return "Adapted Template";
    case "synthesized_layout":
      return "Synthesized Layout";
    default:
      return mode
        .split("_")
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");
  }
}

export function formatRecommendationMatchType(matchType: unknown) {
  if (typeof matchType !== "string" || !matchType.trim()) {
    return "Suggested";
  }
  switch (matchType) {
    case "exact_template":
      return "Exact Match";
    case "adapted_template":
      return "Adaptable";
    case "reference_only":
      return "Reference";
    default:
      return formatGenerationMode(matchType);
  }
}

export function getGenerationDecisionTemplate(decision: GenerationDecision | null) {
  if (!decision) {
    return null;
  }
  if (typeof decision.template_name === "string" && decision.template_name.trim()) {
    return decision.template_name;
  }
  if (typeof decision.template_id === "string" && decision.template_id.trim()) {
    return decision.template_id;
  }
  return null;
}

export function getGenerationDecisionTemplatePreview(decision: GenerationDecision | null) {
  if (!decision) {
    return null;
  }
  if (typeof decision.template_preview_asset_url === "string" && decision.template_preview_asset_url.trim()) {
    return decision.template_preview_asset_url;
  }
  const recommendations = Array.isArray(decision.template_recommendations) ? decision.template_recommendations : [];
  const matched =
    recommendations.find((item) => item.template_id === decision.template_id) ||
    recommendations.find((item) => item.name === decision.template_name) ||
    recommendations[0];
  return matched?.asset_url || null;
}

export function getGenerationDecisionConfidence(decision: GenerationDecision | null) {
  if (!decision) {
    return null;
  }
  if (typeof decision.template_decision_confidence === "number") {
    return `${Math.round(decision.template_decision_confidence * 100)}% confidence`;
  }
  const recommendations = Array.isArray(decision.template_recommendations) ? decision.template_recommendations : [];
  const matched =
    recommendations.find((item) => item.template_id === decision.template_id) ||
    recommendations.find((item) => item.name === decision.template_name) ||
    recommendations[0];
  if (typeof matched?.decision_confidence === "number") {
    return `${Math.round(matched.decision_confidence * 100)}% confidence`;
  }
  const templateScore = decision.score_breakdown?.template_score;
  if (typeof templateScore === "number") {
    return `${Math.round(Math.max(0, Math.min(templateScore / 15, 1)) * 100)}% confidence`;
  }
  return null;
}

export function getGenerationDecisionReasons(decision: GenerationDecision | null) {
  if (!decision) {
    return [];
  }
  if (Array.isArray(decision.rationale)) {
    return decision.rationale.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
  }
  if (typeof decision.rationale === "string" && decision.rationale.trim()) {
    return [decision.rationale];
  }
  return [];
}

export function getRecommendationConfidence(recommendation: TemplateRecommendationResponse) {
  if (typeof recommendation.decision_confidence === "number") {
    return `${Math.round(recommendation.decision_confidence * 100)}% confidence`;
  }
  return `${Math.round(recommendation.score * 100)} score`;
}

export function getRecommendationDisplayName(recommendation: TemplateRecommendationResponse) {
  if (typeof recommendation.display_name === "string" && recommendation.display_name.trim()) {
    return recommendation.display_name;
  }
  return recommendation.name;
}

export function getRecommendationSelectionReason(recommendation: TemplateRecommendationResponse) {
  if (typeof recommendation.selection_reason === "string" && recommendation.selection_reason.trim()) {
    return recommendation.selection_reason;
  }
  if (recommendation.is_primary_adaptation) {
    return "Best Adaptation";
  }
  switch (recommendation.format_family) {
    case "carousel":
      return "Carousel Match";
    case "infographic":
      return "Infographic Match";
    case "static":
      return "Static Match";
    default:
      return "Suggested Match";
  }
}
