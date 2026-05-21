import type { Dispatch, SetStateAction } from "react";

import type {
  AssetCategoryRoutingResponse,
  AssetProcessingStatusResponse,
} from "@/lib/api/contracts";

export type BrandUploadItem = {
  id: string;
  name: string;
  tags?: string[];
  previewUrl?: string;
  file?: File | null;
  uploadedAssetId?: string;
  storagePath?: string;
  assetUrl?: string;
  lifecycleState?: string;
  channel?: string;
  mimeType?: string;
  pageCount?: number;
  processingError?: string | null;
  kind?: "knowledge" | "template";
  templateKind?: string;
  analysisJson?: Record<string, unknown>;
  fieldKey?: string;
  assetCategory?: string;
  validationState?: string;
  validationSummaryJson?: Record<string, unknown>;
  structuredDataJson?: Record<string, unknown>;
  normalizedDataJson?: Record<string, unknown>;
  processingStatus?: AssetProcessingStatusResponse;
  routing?: AssetCategoryRoutingResponse;
  isActive?: boolean;
};

export interface CoreBrandFields {
  logo: BrandUploadItem | null;
  logos: BrandUploadItem[];
  name: string;
  description: string;
  industryCategory: string;
  differentiators: string;
}

export interface VoiceToneFields {
  coreToneAttributes: string[];
  primaryEmotion: string;
  secondaryEmotion: string;
  avoidedEmotion: string;
  contentComplexity: string;
  sentenceLength: string;
  perspective: string;
}

export interface TargetAudienceFields {
  selectedAudiences: string[];
  goals: string;
  motivations: string;
  fearsAndPainPoints: string;
  objections: string;
  contentConsumptionBehavior: string;
  audienceInsights: BrandUploadItem[];
  ageRange: string;
  gender: string;
  location: string;
  educationLevel: string;
  employmentStatus: string;
  professionalBackground: string;
  householdSize: string;
  languagePreference: string;
  incomeLevel: string;
  familyStatusOrLifeStage: string;
  socioEconomicSegment: string;
  digitalAccess: string;
}

export interface AdditionalColorField {
  name: string;
  hex: string;
}

export interface VisualIdentityFields {
  brandMood: string;
  visualStyle: string;
  allowedLogoPlacements: string[];
  defaultLogoPlacement: string;
  referenceCreatives: BrandUploadItem[];
  moodBoards: BrandUploadItem[];
  primaryColor: string;
  secondaryColor: string;
  additionalColors: AdditionalColorField[];
  colorPaletteUploads: BrandUploadItem[];
  typography: string;
  fontStyleGuide: BrandUploadItem[];
}

export interface BrandRuleFields {
  selectedRules: string[];
  positiveWordBank: string;
  positiveWordBankUploads: BrandUploadItem[];
  replaceableWords: string;
  replaceableWordUploads: BrandUploadItem[];
  negativeWordBank: string;
  negativeWordBankUploads: BrandUploadItem[];
  whatToDo: string;
  whatNotToDo: string;
  restrictedTopics: string;
  restrictedClaims: string;
  blockedWordsPhrases: string;
}

export interface BrandKnowledgeFields {
  templateFiles: BrandUploadItem[];
  otherDocuments: BrandUploadItem[];
}

export interface AdditionalDetailFields {
  brandMission: string;
  brandVision: string;
  brandPromise: string;
  marketPositioning: string;
  roleOfDigitalPlatforms: string;
  socialMediaChallenges: string;
  businessProblemOrOpportunity: string;
  perceptionChallenge: string;
  humanInsight: string;
  brandAdvantage: string;
  strategy: string;
  marketMaturity: string;
  brandArchetype: string;
  buyingStage: string;
  complianceLevel: string;
  competitorBrandName: string;
  websiteUrl: string;
  linkedin: string;
  instagram: string;
  x: string;
}

export interface BrandFormState {
  core: CoreBrandFields;
  voiceTone: VoiceToneFields;
  targetAudience: TargetAudienceFields;
  visualIdentity: VisualIdentityFields;
  brandRules: BrandRuleFields;
  brandKnowledge: BrandKnowledgeFields;
  additional: AdditionalDetailFields;
}

export const emptyBrandFormState: BrandFormState = {
  core: {
    logo: null,
    logos: [],
    name: "",
    description: "",
    industryCategory: "",
    differentiators: "",
  },
  voiceTone: {
    coreToneAttributes: [],
    primaryEmotion: "",
    secondaryEmotion: "",
    avoidedEmotion: "",
    contentComplexity: "",
    sentenceLength: "",
    perspective: "",
  },
  targetAudience: {
    selectedAudiences: [],
    goals: "",
    motivations: "",
    fearsAndPainPoints: "",
    objections: "",
    contentConsumptionBehavior: "",
    audienceInsights: [],
    ageRange: "",
    gender: "",
    location: "",
    educationLevel: "",
    employmentStatus: "",
    professionalBackground: "",
    householdSize: "",
    languagePreference: "",
    incomeLevel: "",
    familyStatusOrLifeStage: "",
    socioEconomicSegment: "",
    digitalAccess: "",
  },
  visualIdentity: {
    brandMood: "",
    visualStyle: "",
    allowedLogoPlacements: [],
    defaultLogoPlacement: "",
    referenceCreatives: [],
    moodBoards: [],
    primaryColor: "",
    secondaryColor: "",
    additionalColors: [{ name: "", hex: "" }],
    colorPaletteUploads: [],
    typography: "",
    fontStyleGuide: [],
  },
  brandRules: {
    selectedRules: [],
    positiveWordBank: "",
    positiveWordBankUploads: [],
    replaceableWords: "",
    replaceableWordUploads: [],
    negativeWordBank: "",
    negativeWordBankUploads: [],
    whatToDo: "",
    whatNotToDo: "",
    restrictedTopics: "",
    restrictedClaims: "",
    blockedWordsPhrases: "",
  },
  brandKnowledge: {
    templateFiles: [],
    otherDocuments: [],
  },
  additional: {
    brandMission: "",
    brandVision: "",
    brandPromise: "",
    marketPositioning: "",
    roleOfDigitalPlatforms: "",
    socialMediaChallenges: "",
    businessProblemOrOpportunity: "",
    perceptionChallenge: "",
    humanInsight: "",
    brandAdvantage: "",
    strategy: "",
    marketMaturity: "",
    brandArchetype: "",
    buyingStage: "",
    complianceLevel: "",
    competitorBrandName: "",
    websiteUrl: "",
    linkedin: "",
    instagram: "",
    x: "",
  },
};

export type BrandFormSetter = Dispatch<SetStateAction<BrandFormState>>;
export type BrandFormSectionKey = keyof BrandFormState;

export interface BrandTabProps {
  form: BrandFormState;
  setForm: BrandFormSetter;
  onRemoveUpload?: (itemId: string) => void | Promise<void>;
  onFontGuideUploadAdded?: (items: BrandUploadItem[]) => void | Promise<void>;
}

export function updateBrandFormSection<
  TSection extends BrandFormSectionKey,
  TKey extends keyof BrandFormState[TSection],
>(
  setForm: BrandFormSetter,
  section: TSection,
  key: TKey,
  value: BrandFormState[TSection][TKey],
) {
  setForm((prev) => ({
    ...prev,
    [section]: {
      ...prev[section],
      [key]: value,
    },
  }));
}

export function createBrandUploadItem(file: File, tags?: string[]): BrandUploadItem {
  const generatedId =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

  const previewUrl = file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined;

  return {
    id: generatedId,
    name: file.name,
    tags,
    previewUrl,
    file,
    mimeType: file.type || "application/octet-stream",
    lifecycleState: "selected",
  };
}

export function createPersistedBrandUploadItem(item: BrandUploadItem): BrandUploadItem {
  return {
    ...item,
    file: null,
  };
}

export function updateBrandUploadItemState(
  form: BrandFormState,
  itemId: string,
  patch: Partial<BrandUploadItem>,
): BrandFormState {
  const normalizedPatch =
    patch.uploadedAssetId || patch.storagePath || patch.assetUrl
      ? {
          ...patch,
          file: null,
        }
      : patch;
  const updateList = (items: BrandUploadItem[]) =>
    items.map((item) => (item.id === itemId ? { ...item, ...normalizedPatch } : item));

  return {
    ...form,
    core: {
      ...form.core,
      logo:
        form.core.logo?.id === itemId
          ? {
              ...form.core.logo,
              ...normalizedPatch,
            }
          : form.core.logo,
      logos: updateList(form.core.logos),
    },
    targetAudience: {
      ...form.targetAudience,
      audienceInsights: updateList(form.targetAudience.audienceInsights),
    },
    visualIdentity: {
      ...form.visualIdentity,
      referenceCreatives: updateList(form.visualIdentity.referenceCreatives),
      moodBoards: updateList(form.visualIdentity.moodBoards),
      colorPaletteUploads: updateList(form.visualIdentity.colorPaletteUploads),
      fontStyleGuide: updateList(form.visualIdentity.fontStyleGuide),
    },
    brandRules: {
      ...form.brandRules,
      positiveWordBankUploads: updateList(form.brandRules.positiveWordBankUploads),
      replaceableWordUploads: updateList(form.brandRules.replaceableWordUploads),
      negativeWordBankUploads: updateList(form.brandRules.negativeWordBankUploads),
    },
    brandKnowledge: {
      ...form.brandKnowledge,
      templateFiles: updateList(form.brandKnowledge.templateFiles),
      otherDocuments: updateList(form.brandKnowledge.otherDocuments),
    },
  };
}

export function findBrandUploadItem(form: BrandFormState, itemId: string): BrandUploadItem | null {
  const groupedItems: Array<BrandUploadItem | null | undefined> = [
    form.core.logo,
    ...form.core.logos,
    ...form.targetAudience.audienceInsights,
    ...form.visualIdentity.referenceCreatives,
    ...form.visualIdentity.moodBoards,
    ...form.visualIdentity.colorPaletteUploads,
    ...form.visualIdentity.fontStyleGuide,
    ...form.brandRules.positiveWordBankUploads,
    ...form.brandRules.replaceableWordUploads,
    ...form.brandRules.negativeWordBankUploads,
    ...form.brandKnowledge.templateFiles,
    ...form.brandKnowledge.otherDocuments,
  ];

  return groupedItems.find((item) => item?.id === itemId) || null;
}

export function removeBrandUploadItem(form: BrandFormState, itemId: string): BrandFormState {
  const removeFromList = (items: BrandUploadItem[]) => items.filter((item) => item.id !== itemId);
  const nextLogos = removeFromList(form.core.logos);
  const primaryLogo =
    form.core.logo?.id === itemId
      ? nextLogos[0] || null
      : form.core.logo || nextLogos[0] || null;

  return {
    ...form,
    core: {
      ...form.core,
      logo: primaryLogo,
      logos: nextLogos,
    },
    targetAudience: {
      ...form.targetAudience,
      audienceInsights: removeFromList(form.targetAudience.audienceInsights),
    },
    visualIdentity: {
      ...form.visualIdentity,
      referenceCreatives: removeFromList(form.visualIdentity.referenceCreatives),
      moodBoards: removeFromList(form.visualIdentity.moodBoards),
      colorPaletteUploads: removeFromList(form.visualIdentity.colorPaletteUploads),
      fontStyleGuide: removeFromList(form.visualIdentity.fontStyleGuide),
    },
    brandRules: {
      ...form.brandRules,
      positiveWordBankUploads: removeFromList(form.brandRules.positiveWordBankUploads),
      replaceableWordUploads: removeFromList(form.brandRules.replaceableWordUploads),
      negativeWordBankUploads: removeFromList(form.brandRules.negativeWordBankUploads),
    },
    brandKnowledge: {
      ...form.brandKnowledge,
      templateFiles: removeFromList(form.brandKnowledge.templateFiles),
      otherDocuments: removeFromList(form.brandKnowledge.otherDocuments),
    },
  };
}
