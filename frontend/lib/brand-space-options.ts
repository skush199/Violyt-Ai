// Source of truth for brand-space dropdown and multiselect values based on
// "Brand space creation fields (1) (1).docx" shared in the implementation review.
export const INDUSTRY_OPTIONS = [
  "Technology / SaaS",
  "Financial Services",
  "Healthcare",
  "Retail/E-commerce",
  "FMCG",
  "Education",
  "Real Estate",
  "Automotive",
  "Hospitality",
  "Media & Entertainment",
  "Manufacturing",
  "Energy",
  "Telecommunications",
  "Professional Services",
  "Government / Public Sector",
  "Nonprofit / NGO",
];

export const CORE_TONE_OPTIONS = [
  "Bold",
  "Premium",
  "Playful",
  "Authoritative",
  "Empathetic",
  "Inspirational",
  "Trust Worthy",
  "Polite",
  "Witty",
];

export const CONTENT_COMPLEXITY_OPTIONS = ["Basic", "Intermediate", "Advanced", "Expert"];

export const SENTENCE_LENGTH_OPTIONS = ["Short", "Medium", "Long", "Mixed"];

export const PERSPECTIVE_OPTIONS = ["First-person", "Third-person", "Brand-as-human"];

export const AUDIENCE_OPTIONS = [
  "Marketing Leaders",
  "Founders",
  "Investors",
  "Developers",
  "Consumers",
  "CXOs",
];

export const LOCATION_OPTIONS = ["Local", "Regional", "National", "Global", "Multi-region"];

export const EDUCATION_LEVEL_OPTIONS = [
  "High School or Below",
  "College / Diploma Educated",
  "University Graduate / Postgraduate Educated",
  "Highly Educated / Academic",
];

export const EMPLOYMENT_STATUS_OPTIONS = [
  "Student",
  "Early Career Professional",
  "Mid Career",
  "Professional",
  "Senior Professional",
  "Executive / Leadership",
  "Entrepreneur / Business Owner",
  "Freelancer / Independent Worker",
  "Homemaker",
  "Retired",
];

export const PROFESSIONAL_BACKGROUND_OPTIONS = [
  "Technology",
  "Business",
  "Finance",
  "Healthcare",
  "Education",
  "Creative",
  "Sales",
  "Operations",
  "Legal",
  "Entrepreneurship",
  "Skilled Trades",
  "Government",
  "Student",
  "General Audience",
];

export const HOUSEHOLD_SIZE_OPTIONS = [
  "Single Person Household",
  "Couple Household",
  "Small Family (3-4 Members)",
  "Large Family (5+ Members)",
  "Shared / Multi Generational Household",
];

export const LANGUAGE_PREFERENCE_OPTIONS = [
  "Local Language",
  "Local Language + English",
  "English Preferred",
  "Multilingual Audience",
];

export const INCOME_LEVEL_OPTIONS = [
  "Low Income",
  "Lower Middle Income",
  "Middle Income",
  "Upper Middle Income",
  "High Income",
];

export const DIGITAL_ACCESS_OPTIONS = [
  "Mobile Only",
  "Mobile First",
  "Mobile and Desktop",
  "Multi Device Power User",
];

export const BRAND_RULE_OPTIONS = [
  "Avoid emojis",
  "Avoid hype claims",
  "Avoid slang",
  "Avoid competitor comparison",
];

export const MARKET_MATURITY_OPTIONS = ["Emerging", "Growing", "Mature"];

export const BRAND_ARCHETYPE_OPTIONS = [
  "Hero",
  "Innovator",
  "Caregiver",
  "Explorer",
  "Creator",
  "Sage",
  "Rebel",
  "Entertainer",
  "Everyman",
  "Ruler",
  "Lover",
  "Magician",
];

export const BUYING_STAGE_OPTIONS = [
  "Awareness",
  "Consideration",
  "Decision",
  "Retention",
  "Advocacy",
];

export const COMPLIANCE_LEVEL_OPTIONS = ["Low", "Medium", "High"];

export function sanitizeOption(options: readonly string[], value?: string) {
  if (!value) {
    return "";
  }

  return options.includes(value) ? value : "";
}

export function sanitizeOptionArray(options: readonly string[], values?: string[]) {
  return (values || []).filter((value) => options.includes(value));
}
