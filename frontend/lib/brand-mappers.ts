import { apiOrigin } from "@/lib/env";
import type { BrandAttachmentResponse, BrandOverviewResponse } from "@/lib/api/contracts";
import {
  AUDIENCE_OPTIONS,
  BRAND_ARCHETYPE_OPTIONS,
  BRAND_RULE_OPTIONS,
  BUYING_STAGE_OPTIONS,
  COMPLIANCE_LEVEL_OPTIONS,
  CONTENT_COMPLEXITY_OPTIONS,
  CORE_TONE_OPTIONS,
  DIGITAL_ACCESS_OPTIONS,
  EDUCATION_LEVEL_OPTIONS,
  EMPLOYMENT_STATUS_OPTIONS,
  HOUSEHOLD_SIZE_OPTIONS,
  INDUSTRY_OPTIONS,
  INCOME_LEVEL_OPTIONS,
  LANGUAGE_PREFERENCE_OPTIONS,
  LOCATION_OPTIONS,
  MARKET_MATURITY_OPTIONS,
  PERSPECTIVE_OPTIONS,
  PROFESSIONAL_BACKGROUND_OPTIONS,
  SENTENCE_LENGTH_OPTIONS,
  sanitizeOption,
  sanitizeOptionArray,
} from "@/lib/brand-space-options";
import { createPersistedBrandUploadItem, emptyBrandFormState, type BrandFormState } from "@/types/brand-space.types";
import type { UploadedBrandAssets } from "@/lib/brand-space-persistence";

type AttachmentLike = Pick<
  BrandAttachmentResponse,
  | "id"
  | "name"
  | "channel"
  | "asset_url"
  | "storage_path"
  | "lifecycle_state"
  | "asset_category"
  | "metadata_json"
  | "normalized_data_json"
> & {
  field_key?: string | null;
};

function splitList(value?: string) {
  return (value || "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toTextarea(value: unknown) {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item).trim())
      .filter(Boolean)
      .join("\n");
  }
  return typeof value === "string" ? value : "";
}

function toRecord(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function isUnknownFontName(value: string) {
  return ["unknown", "unknown font", "unknown visual font", "font"].includes(value.trim().toLowerCase());
}

function cleanTypographyValue(value: unknown) {
  const text = String(value || "").trim();
  return text && !isUnknownFontName(text) ? text : "";
}

function resolveAssetUrl(value: unknown) {
  if (typeof value === "string" && value) {
    return value;
  }
  return undefined;
}

function resolveStorageUrl(storagePath?: string) {
  return storagePath ? `${apiOrigin}/storage/${storagePath}` : undefined;
}

function createKnowledgeItemFromDescriptor(
  descriptor: Record<string, unknown> | undefined,
  fallbackName: string,
  fallbackChannel: string,
  fallbackTags?: string[],
) {
  if (!descriptor) {
    return null;
  }
  const uploadedAssetId = typeof descriptor.id === "string" ? descriptor.id : undefined;
  if (!uploadedAssetId) {
    return null;
  }
  const storagePath = typeof descriptor.storage_path === "string" ? descriptor.storage_path : undefined;
  const assetUrl = resolveAssetUrl(descriptor.url) || resolveStorageUrl(storagePath);
  return createPersistedBrandUploadItem({
    id: `existing-${uploadedAssetId}`,
    name: typeof descriptor.name === "string" && descriptor.name ? descriptor.name : fallbackName,
    uploadedAssetId,
    storagePath,
    assetUrl,
    lifecycleState:
      typeof descriptor.lifecycle_state === "string" && descriptor.lifecycle_state
        ? descriptor.lifecycle_state
        : "indexed",
    channel:
      typeof descriptor.channel === "string" && descriptor.channel
        ? descriptor.channel
        : fallbackChannel,
    mimeType: typeof descriptor.mime_type === "string" ? descriptor.mime_type : undefined,
    pageCount: typeof descriptor.page_count === "number" ? descriptor.page_count : undefined,
    processingError: typeof descriptor.processing_error === "string" ? descriptor.processing_error : undefined,
    tags: fallbackTags,
    kind: "knowledge",
  });
}

function createKnowledgeItems(
  descriptors: unknown,
  fallbackChannel: string,
  fallbackTags?: string[],
) {
  if (!Array.isArray(descriptors)) {
    return [];
  }
  return descriptors
    .map((descriptor, index) =>
      createKnowledgeItemFromDescriptor(
        toRecord(descriptor),
        `Uploaded file ${index + 1}`,
        fallbackChannel,
        fallbackTags,
      ),
    )
    .filter((item): item is NonNullable<typeof item> => Boolean(item));
}

function createTemplateItems(descriptors: unknown) {
  if (!Array.isArray(descriptors)) {
    return [];
  }
  return descriptors
    .map((descriptor, index) => {
      const record = toRecord(descriptor);
      const uploadedAssetId = typeof record.id === "string" ? record.id : undefined;
      if (!uploadedAssetId) {
        return null;
      }
      const storagePath = typeof record.storage_path === "string" ? record.storage_path : undefined;
      return createPersistedBrandUploadItem({
        id: `template-${uploadedAssetId}`,
        name: typeof record.name === "string" && record.name ? record.name : `Template ${index + 1}`,
        uploadedAssetId,
        storagePath,
        assetUrl: resolveAssetUrl(record.url) || resolveStorageUrl(storagePath),
        lifecycleState:
          typeof toRecord(record.analysis_json).status === "string"
            ? String(toRecord(record.analysis_json).status)
            : "indexed",
        tags: Array.isArray(record.tags) ? record.tags.map((item) => String(item)) : [],
        kind: "template",
        templateKind: typeof record.kind === "string" ? record.kind : "hybrid",
        analysisJson: toRecord(record.analysis_json),
      });
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item));
}

export function mapBrandOverviewToForm(overview: BrandOverviewResponse): BrandFormState {
  const form: BrandFormState = structuredClone(emptyBrandFormState);
  const sectionMap = Object.fromEntries(
    overview.sections.map((section) => [section.section_code, section.payload || {}]),
  ) as Record<string, Record<string, unknown>>;

  const identity = toRecord(sectionMap.identity);
  const foundations = toRecord(sectionMap.foundations);
  const voiceTone = toRecord(sectionMap.voice_tone);
  const personasSection = toRecord(sectionMap.personas);
  const guardrails = toRecord(sectionMap.guardrails);
  const objectives = toRecord(sectionMap.objectives);
  const visualIdentity = toRecord(sectionMap.visual_identity);
  const logoPlacement = toRecord(visualIdentity.logo_placement);
  const knowledge = toRecord(sectionMap.knowledge);
  const promptIntelligence = toRecord(sectionMap.prompt_intelligence);

  const primaryPersona =
    Array.isArray(personasSection.personas) && personasSection.personas.length
      ? toRecord(
          personasSection.personas.find((item) => toRecord(item).is_default) || personasSection.personas[0],
        )
      : toRecord(overview.personas.find((item) => Boolean(item.is_default)) || overview.personas[0]);
  const personaPsychographics = toRecord(primaryPersona.psychographics);
  const personaDemographics = toRecord(primaryPersona.demographics);
  const personaContentBehavior = toRecord(primaryPersona.content_behavior);
  const industryContext = toRecord(foundations.industry_context);
  const colorPalette = toRecord(visualIdentity.brand_color_palette);
  const typography = toRecord(visualIdentity.typography);
  const socialProfiles = toRecord(identity.social_profiles);

  form.core = {
    logo: null,
    logos: [],
    name: String(identity.brand_name || overview.brand.name || ""),
    description: String(identity.brand_description || overview.brand.description || ""),
    industryCategory: String(identity.industry_category || ""),
    differentiators: toTextarea(identity.key_differentiators),
  };

  const primaryLogo =
    createKnowledgeItemFromDescriptor(
        {
          id: identity.logo_asset_id,
          name: `${overview.brand.name} Logo`,
          storage_path: identity.logo_asset_path,
          url: identity.logo_asset_url,
          lifecycle_state: "indexed",
          channel: "brand_asset",
        },
        `${overview.brand.name} Logo`,
        "brand_asset",
        ["Logo"],
      ) || null;
  const uploadedLogos = createKnowledgeItems(identity.logo_assets, "brand_asset", ["Logo"]);
  form.core.logos = uploadedLogos.length ? uploadedLogos : primaryLogo ? [primaryLogo] : [];
  form.core.logo = form.core.logos[0] || primaryLogo;

  form.voiceTone = {
    coreToneAttributes: Array.isArray(voiceTone.tone_attributes)
      ? voiceTone.tone_attributes.map((item) => String(item))
      : [],
    primaryEmotion: String(voiceTone.primary_emotion || ""),
    secondaryEmotion: String(voiceTone.secondary_emotion || ""),
    avoidedEmotion: String(voiceTone.avoided_emotion || ""),
    contentComplexity: String(voiceTone.content_complexity || ""),
    sentenceLength: String(voiceTone.sentence_length || ""),
    perspective: String(voiceTone.perspective || ""),
  };

  form.targetAudience = {
    selectedAudiences: Array.isArray(personaContentBehavior.selected_audiences)
      ? personaContentBehavior.selected_audiences.map((item) => String(item))
      : Array.isArray(identity.audience_type)
        ? identity.audience_type.map((item) => String(item))
        : identity.audience_type
          ? [String(identity.audience_type)]
          : [],
    goals: toTextarea(primaryPersona.audience_goals || personaPsychographics.goals),
    motivations: toTextarea(primaryPersona.motivations || personaPsychographics.motivations),
    fearsAndPainPoints: toTextarea(primaryPersona.fears_and_pain_points || personaPsychographics.fears_and_pain_points),
    objections: toTextarea(primaryPersona.objections),
    contentConsumptionBehavior: toTextarea(
      personaPsychographics.content_consumption_behavior || personaContentBehavior.preferred_channels,
    ),
    audienceInsights: createKnowledgeItems(personaContentBehavior.audience_insights, "audience_insights"),
    ageRange: String(personaDemographics.age_range || ""),
    gender: String(personaDemographics.gender || ""),
    location: String(personaDemographics.region || toRecord(identity.target_geography).country || ""),
    educationLevel: String(personaDemographics.education_level || ""),
    employmentStatus: String(personaDemographics.employment_status || ""),
    professionalBackground: String(personaDemographics.professional_background || ""),
    householdSize: String(personaDemographics.household_size || ""),
    languagePreference: String(primaryPersona.language_preference || personaDemographics.language_preference || ""),
    incomeLevel: String(personaDemographics.income_level || ""),
    familyStatusOrLifeStage: String(personaDemographics.family_status_or_life_stage || ""),
    socioEconomicSegment: String(personaDemographics.socio_economic_segment || ""),
    digitalAccess: String(personaDemographics.digital_access || ""),
  };

  form.visualIdentity = {
    brandMood: String(visualIdentity.brand_mood || ""),
    visualStyle: String(visualIdentity.visual_style || ""),
    allowedLogoPlacements: Array.isArray(logoPlacement.allowed_positions)
      ? logoPlacement.allowed_positions.map((item) => String(item))
      : [],
    defaultLogoPlacement: String(logoPlacement.default_position || ""),
    referenceCreatives: createKnowledgeItems(visualIdentity.reference_creatives, "reference_creative"),
    moodBoards: createKnowledgeItems(visualIdentity.mood_boards, "mood_board", ["Mood Board"]),
    primaryColor: String(colorPalette.primary || ""),
    secondaryColor: String(colorPalette.secondary || ""),
    additionalColors:
      Array.isArray(colorPalette.additional) && colorPalette.additional.length
        ? colorPalette.additional.map((item) => ({
            name: String(toRecord(item).name || ""),
            hex: String(toRecord(item).hex || ""),
          }))
        : [{ name: "", hex: "" }],
    colorPaletteUploads: createKnowledgeItems(visualIdentity.color_palette_uploads, "visual_identity", ["Color Palette"]),
    typography: cleanTypographyValue(typography.primary_style),
    fontStyleGuide: createKnowledgeItems(visualIdentity.font_style_guides, "visual_identity", ["Font Guide"]),
  };
  if (
    overview.brand.name.trim().toLowerCase() === "jiraaf" &&
    !form.visualIdentity.allowedLogoPlacements.length &&
    !form.visualIdentity.defaultLogoPlacement
  ) {
    form.visualIdentity.allowedLogoPlacements = ["top-right"];
    form.visualIdentity.defaultLogoPlacement = "top-right";
  }

  form.brandRules = {
    selectedRules: Array.isArray(guardrails.custom_rules) ? guardrails.custom_rules.map((item) => String(item)) : [],
    positiveWordBank: toTextarea(guardrails.positive_word_bank),
    positiveWordBankUploads: createKnowledgeItems(toRecord(guardrails.word_bank_assets).positive, "guardrail_support", ["Positive Word Bank"]),
    replaceableWords: toTextarea(guardrails.replaceable_words),
    replaceableWordUploads: createKnowledgeItems(toRecord(guardrails.word_bank_assets).replaceable, "guardrail_support", ["Replaceable Words"]),
    negativeWordBank: toTextarea(guardrails.negative_word_bank),
    negativeWordBankUploads: createKnowledgeItems(toRecord(guardrails.word_bank_assets).negative, "guardrail_support", ["Negative Word Bank"]),
    whatToDo: toTextarea(guardrails.dos),
    whatNotToDo: toTextarea(guardrails.donts),
    restrictedTopics: toTextarea(guardrails.restricted_topics),
    restrictedClaims: toTextarea(guardrails.restricted_claims),
    blockedWordsPhrases: toTextarea(guardrails.blocked_words),
  };

  form.brandKnowledge = {
    templateFiles: createTemplateItems(knowledge.template_files || toRecord(promptIntelligence.platform_rules).recommended_templates),
    otherDocuments: createKnowledgeItems(knowledge.other_documents, "brand"),
  };

  const defaultObjective =
    Array.isArray(objectives.objectives) && objectives.objectives.length
      ? toRecord(
          objectives.objectives.find((item) => toRecord(item).is_default) || objectives.objectives[0],
        )
      : toRecord(overview.objectives.find((item) => Boolean(item.is_default)) || overview.objectives[0]);
  const objectiveConfig = toRecord(defaultObjective.configuration);

  form.additional = {
    brandMission: String(foundations.brand_mission || ""),
    brandVision: String(foundations.brand_vision || ""),
    brandPromise: String(foundations.brand_promise || ""),
    marketPositioning: String(foundations.market_positioning || ""),
    roleOfDigitalPlatforms: String(foundations.role_of_digital_platforms || ""),
    socialMediaChallenges: toTextarea(foundations.social_media_challenges),
    businessProblemOrOpportunity: String(foundations.business_problem_or_opportunity || objectiveConfig.business_problem_or_opportunity || ""),
    perceptionChallenge: String(foundations.perception_challenge || objectiveConfig.perception_challenge || ""),
    humanInsight: String(foundations.human_insight || objectiveConfig.human_insight || ""),
    brandAdvantage: String(foundations.brand_advantage || defaultObjective.name || ""),
    strategy: String(industryContext.strategy || defaultObjective.description || ""),
    marketMaturity: String(industryContext.market_maturity || objectiveConfig.market_maturity || ""),
    brandArchetype: String(industryContext.brand_archetype || objectiveConfig.brand_archetype || ""),
    buyingStage: String(industryContext.buying_stage || objectiveConfig.buying_stage || ""),
    complianceLevel: String(industryContext.compliance_level || objectiveConfig.compliance_level || ""),
    competitorBrandName: String(industryContext.competitor_brand_name || knowledge.competitor_brand_name || ""),
    websiteUrl: String(identity.website_url || knowledge.website || ""),
    linkedin: String(socialProfiles.linkedin || toRecord(knowledge.social_profiles).linkedin || ""),
    instagram: String(socialProfiles.instagram || toRecord(knowledge.social_profiles).instagram || ""),
    x: String(socialProfiles.x || toRecord(knowledge.social_profiles).x || ""),
  };

  return form;
}

function assetIds(items: Array<{ id: string }>) {
  return items.map((item) => item.id);
}

function assetDescriptors(items: AttachmentLike[]) {
  return items.map((item) => ({
    id: item.id,
    name: item.name,
    channel: item.channel,
    url: item.asset_url,
    storage_path: item.storage_path,
    lifecycle_state: item.lifecycle_state,
    asset_category: item.asset_category,
    field_key: item.field_key || undefined,
  }));
}

function templateDescriptors(items: AttachmentLike[]) {
  return items.map((item) => ({
    id: item.id,
    name: item.name,
    kind:
      typeof item.normalized_data_json?.template_kind === "string"
        ? String(item.normalized_data_json.template_kind)
        : item.asset_category === "template"
          ? "hybrid"
          : "hybrid",
    tags: Array.isArray(item.metadata_json?.tags) ? item.metadata_json.tags.map((tag) => String(tag)) : [],
    url: item.asset_url,
    storage_path: item.storage_path,
    lifecycle_state: item.lifecycle_state,
  }));
}

function toneIntensity(attributes: string[]) {
  return Object.fromEntries(attributes.map((attribute) => [attribute, 8]));
}

function normalizeBrandSelections(form: BrandFormState) {
  return {
    industryCategory: sanitizeOption(INDUSTRY_OPTIONS, form.core.industryCategory),
    coreToneAttributes: sanitizeOptionArray(CORE_TONE_OPTIONS, form.voiceTone.coreToneAttributes),
    contentComplexity: sanitizeOption(CONTENT_COMPLEXITY_OPTIONS, form.voiceTone.contentComplexity),
    sentenceLength: sanitizeOption(SENTENCE_LENGTH_OPTIONS, form.voiceTone.sentenceLength),
    perspective: sanitizeOption(PERSPECTIVE_OPTIONS, form.voiceTone.perspective),
    selectedAudiences: sanitizeOptionArray(AUDIENCE_OPTIONS, form.targetAudience.selectedAudiences),
    location: sanitizeOption(LOCATION_OPTIONS, form.targetAudience.location),
    educationLevel: sanitizeOption(EDUCATION_LEVEL_OPTIONS, form.targetAudience.educationLevel),
    employmentStatus: sanitizeOption(EMPLOYMENT_STATUS_OPTIONS, form.targetAudience.employmentStatus),
    professionalBackground: sanitizeOption(
      PROFESSIONAL_BACKGROUND_OPTIONS,
      form.targetAudience.professionalBackground,
    ),
    householdSize: sanitizeOption(HOUSEHOLD_SIZE_OPTIONS, form.targetAudience.householdSize),
    languagePreference: sanitizeOption(
      LANGUAGE_PREFERENCE_OPTIONS,
      form.targetAudience.languagePreference,
    ),
    incomeLevel: sanitizeOption(INCOME_LEVEL_OPTIONS, form.targetAudience.incomeLevel),
    digitalAccess: sanitizeOption(DIGITAL_ACCESS_OPTIONS, form.targetAudience.digitalAccess),
    selectedRules: sanitizeOptionArray(BRAND_RULE_OPTIONS, form.brandRules.selectedRules),
    marketMaturity: sanitizeOption(MARKET_MATURITY_OPTIONS, form.additional.marketMaturity),
    brandArchetype: sanitizeOption(BRAND_ARCHETYPE_OPTIONS, form.additional.brandArchetype),
    buyingStage: sanitizeOption(BUYING_STAGE_OPTIONS, form.additional.buyingStage),
    complianceLevel: sanitizeOption(COMPLIANCE_LEVEL_OPTIONS, form.additional.complianceLevel),
  };
}

export function mapBrandFormToCreateRequest(form: BrandFormState, uploads?: UploadedBrandAssets) {
  const normalized = normalizeBrandSelections(form);
  const logoAssets = uploads?.logos?.length ? uploads.logos : uploads?.logo ? [uploads.logo] : [];

  return {
    identity: {
      brand_name: form.core.name || "",
      brand_description: form.core.description || "",
      industry_category: normalized.industryCategory || undefined,
      target_geography: {
        country: normalized.location || "",
      },
      audience_type: normalized.selectedAudiences[0] || undefined,
      key_differentiators: splitList(form.core.differentiators),
      logo_asset_id: logoAssets[0]?.id,
      logo_asset_ids: assetIds(logoAssets),
      website_url: form.additional.websiteUrl || undefined,
      social_profiles: {
        linkedin: form.additional.linkedin || undefined,
        instagram: form.additional.instagram || undefined,
        x: form.additional.x || undefined,
      },
    },
    foundations: {
      brand_mission: form.additional.brandMission || undefined,
      brand_vision: form.additional.brandVision || undefined,
      brand_promise: form.additional.brandPromise || undefined,
    },
    voice_tone: {
      tone_attributes: normalized.coreToneAttributes,
      tone_intensity: toneIntensity(normalized.coreToneAttributes),
      primary_emotion: form.voiceTone.primaryEmotion || "confident",
      secondary_emotion: form.voiceTone.secondaryEmotion || undefined,
      avoided_emotion: form.voiceTone.avoidedEmotion || undefined,
      content_complexity: normalized.contentComplexity || undefined,
      sentence_length: normalized.sentenceLength || undefined,
      perspective: normalized.perspective || undefined,
    },
  };
}

export function mapBrandSections(form: BrandFormState, uploads?: UploadedBrandAssets) {
  const uploaded = uploads;
  const normalized = normalizeBrandSelections(form);
  const logoAssets = uploaded?.logos?.length ? uploaded.logos : uploaded?.logo ? [uploaded.logo] : [];

  return [
    {
      section_code: "identity",
      payload: {
        brand_name: form.core.name || "",
        brand_description: form.core.description || "",
        industry_category: normalized.industryCategory || "",
        key_differentiators: splitList(form.core.differentiators),
        logo_asset_id: logoAssets[0]?.id || null,
        logo_asset_ids: assetIds(logoAssets),
        logo_asset_path: logoAssets[0]?.storage_path || null,
        logo_asset_url: logoAssets[0]?.asset_url || null,
        logo_assets: assetDescriptors(logoAssets),
        website_url: form.additional.websiteUrl || "",
        social_profiles: {
          linkedin: form.additional.linkedin || "",
          instagram: form.additional.instagram || "",
          x: form.additional.x || "",
        },
        audience_type: normalized.selectedAudiences[0] || "",
        target_geography: {
          country: normalized.location || "",
        },
      },
      completion_percent: 100,
    },
    {
      section_code: "foundations",
      payload: {
        brand_mission: form.additional.brandMission || "",
        brand_vision: form.additional.brandVision || "",
        brand_promise: form.additional.brandPromise || "",
        market_positioning: form.additional.marketPositioning || "",
        role_of_digital_platforms: form.additional.roleOfDigitalPlatforms || "",
        social_media_challenges: splitList(form.additional.socialMediaChallenges),
        business_problem_or_opportunity: form.additional.businessProblemOrOpportunity || "",
        perception_challenge: form.additional.perceptionChallenge || "",
        human_insight: form.additional.humanInsight || "",
        brand_advantage: form.additional.brandAdvantage || "",
        industry_context: {
          strategy: form.additional.strategy || "",
          market_maturity: normalized.marketMaturity || "",
          brand_archetype: normalized.brandArchetype || "",
          buying_stage: normalized.buyingStage || "",
          compliance_level: normalized.complianceLevel || "",
          competitor_brand_name: form.additional.competitorBrandName || "",
        },
      },
      completion_percent: 100,
    },
    {
      section_code: "voice_tone",
      payload: {
        tone_attributes: normalized.coreToneAttributes,
        tone_intensity: toneIntensity(normalized.coreToneAttributes),
        primary_emotion: form.voiceTone.primaryEmotion || "",
        secondary_emotion: form.voiceTone.secondaryEmotion || "",
        avoided_emotion: form.voiceTone.avoidedEmotion || "",
        content_complexity: normalized.contentComplexity || "",
        sentence_length: normalized.sentenceLength || "",
        perspective: normalized.perspective || "",
      },
      completion_percent: 100,
    },
    {
      section_code: "personas",
      payload: {
        personas: [
          {
            name: normalized.selectedAudiences[0] || "Primary Audience",
            role: "Primary buyer persona",
            psychographics: {
              goals: splitList(form.targetAudience.goals),
              motivations: splitList(form.targetAudience.motivations),
              fears_and_pain_points: splitList(form.targetAudience.fearsAndPainPoints),
              objections: splitList(form.targetAudience.objections),
              content_consumption_behavior: splitList(form.targetAudience.contentConsumptionBehavior),
            },
            demographics: {
              age_range: form.targetAudience.ageRange || "",
              gender: form.targetAudience.gender || "",
              region: normalized.location || "",
              education_level: normalized.educationLevel || "",
              employment_status: normalized.employmentStatus || "",
              professional_background: normalized.professionalBackground || "",
              household_size: normalized.householdSize || "",
              language_preference: normalized.languagePreference || "",
              income_level: normalized.incomeLevel || "",
              family_status_or_life_stage: form.targetAudience.familyStatusOrLifeStage || "",
              socio_economic_segment: form.targetAudience.socioEconomicSegment || "",
              digital_access: normalized.digitalAccess || "",
            },
            audience_goals: splitList(form.targetAudience.goals),
            motivations: splitList(form.targetAudience.motivations),
            fears_and_pain_points: splitList(form.targetAudience.fearsAndPainPoints),
            objections: splitList(form.targetAudience.objections),
            content_behavior: {
              preferred_channels: splitList(form.targetAudience.contentConsumptionBehavior),
              selected_audiences: normalized.selectedAudiences,
              audience_insight_asset_ids: assetIds(uploaded?.audienceInsights || []),
              audience_insights: assetDescriptors(uploaded?.audienceInsights || []),
            },
            language_preference: normalized.languagePreference || "",
            is_default: true,
          },
        ],
      },
      completion_percent: 100,
    },
    {
      section_code: "guardrails",
      payload: {
        dos: splitList(form.brandRules.whatToDo),
        donts: splitList(form.brandRules.whatNotToDo),
        restricted_claims: splitList(form.brandRules.restrictedClaims),
        restricted_topics: splitList(form.brandRules.restrictedTopics),
        blocked_words: splitList(form.brandRules.blockedWordsPhrases),
        positive_word_bank: splitList(form.brandRules.positiveWordBank),
        replaceable_words: splitList(form.brandRules.replaceableWords),
        negative_word_bank: splitList(form.brandRules.negativeWordBank),
        custom_rules: normalized.selectedRules,
        positive_word_bank_asset_ids: assetIds(uploaded?.positiveWordBankUploads || []),
        replaceable_word_asset_ids: assetIds(uploaded?.replaceableWordUploads || []),
        negative_word_bank_asset_ids: assetIds(uploaded?.negativeWordBankUploads || []),
        word_bank_assets: {
          positive: assetDescriptors(uploaded?.positiveWordBankUploads || []),
          replaceable: assetDescriptors(uploaded?.replaceableWordUploads || []),
          negative: assetDescriptors(uploaded?.negativeWordBankUploads || []),
        },
      },
      completion_percent: 100,
    },
    {
      section_code: "objectives",
      payload: {
        objectives: [
          {
            name: form.additional.brandAdvantage || form.additional.brandMission || "Brand Growth",
            description: form.additional.strategy || form.additional.marketPositioning || "",
            content_type: "social_post",
            platform_scope: "multiplatform",
            is_default: true,
            configuration: {
              business_problem_or_opportunity: form.additional.businessProblemOrOpportunity || "",
              perception_challenge: form.additional.perceptionChallenge || "",
              human_insight: form.additional.humanInsight || "",
              market_positioning: form.additional.marketPositioning || "",
              role_of_digital_platforms: form.additional.roleOfDigitalPlatforms || "",
              social_media_challenges: splitList(form.additional.socialMediaChallenges),
              market_maturity: normalized.marketMaturity || "",
              brand_archetype: normalized.brandArchetype || "",
              buying_stage: normalized.buyingStage || "",
              compliance_level: normalized.complianceLevel || "",
            },
          },
        ],
      },
      completion_percent: 100,
    },
    {
      section_code: "visual_identity",
      payload: {
        brand_mood: form.visualIdentity.brandMood || "",
        visual_style: form.visualIdentity.visualStyle || "",
        logo_placement: {
          allowed_positions: form.visualIdentity.allowedLogoPlacements,
          default_position: form.visualIdentity.defaultLogoPlacement || "",
        },
        brand_color_palette: {
          primary: form.visualIdentity.primaryColor || "",
          secondary: form.visualIdentity.secondaryColor || "",
          additional: form.visualIdentity.additionalColors
            .filter((color) => color.name || color.hex)
            .map((color) => ({ name: color.name, hex: color.hex })),
        },
        typography: {
          primary_style: form.visualIdentity.typography || "",
        },
        reference_creative_asset_ids: assetIds(uploaded?.referenceCreatives || []),
        mood_board_asset_ids: assetIds(uploaded?.moodBoards || []),
        reference_creatives: assetDescriptors(uploaded?.referenceCreatives || []),
        mood_boards: assetDescriptors(uploaded?.moodBoards || []),
        color_palette_asset_ids: assetIds(uploaded?.colorPaletteUploads || []),
        color_palette_uploads: assetDescriptors(uploaded?.colorPaletteUploads || []),
        font_style_guide_asset_ids: assetIds(uploaded?.fontStyleGuide || []),
        font_style_guides: assetDescriptors(uploaded?.fontStyleGuide || []),
      },
      completion_percent: 100,
    },
    {
      section_code: "prompt_intelligence",
      payload: {
        prompt_starters: [
          { label: "Audience", value: normalized.selectedAudiences.join(", ") },
          { label: "Strategy", value: form.additional.strategy || "" },
          { label: "Brand mood", value: form.visualIdentity.brandMood || "" },
          { label: "Brand voice", value: normalized.coreToneAttributes.join(", ") },
        ].filter((item) => item.value),
        platform_rules: {
          supported_platforms: ["linkedin", "instagram", "x", "youtube_thumbnail"],
          recommended_templates: templateDescriptors(uploaded?.templateFiles || []),
        },
      },
      completion_percent: 100,
    },
    {
      section_code: "knowledge",
      payload: {
        template_ids: (uploaded?.templateFiles || []).map((item) => item.id),
        template_files: templateDescriptors(uploaded?.templateFiles || []),
        other_document_asset_ids: assetIds(uploaded?.otherDocuments || []),
        other_documents: assetDescriptors(uploaded?.otherDocuments || []),
        audience_insight_asset_ids: assetIds(uploaded?.audienceInsights || []),
        website: form.additional.websiteUrl || "",
        competitor_brand_name: form.additional.competitorBrandName || "",
        social_profiles: {
          linkedin: form.additional.linkedin || "",
          instagram: form.additional.instagram || "",
          x: form.additional.x || "",
        },
      },
      completion_percent: 100,
    },
  ];
}
