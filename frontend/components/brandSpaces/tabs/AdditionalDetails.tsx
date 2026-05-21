import { FormField, FormSection, FormSubsection, StyledInput, StyledSelect, StyledTextarea } from "./FormFields";
import {
  BRAND_ARCHETYPE_OPTIONS,
  BUYING_STAGE_OPTIONS,
  COMPLIANCE_LEVEL_OPTIONS,
  MARKET_MATURITY_OPTIONS,
} from "@/lib/brand-space-options";
import { updateBrandFormSection, type BrandTabProps } from "@/types/brand-space.types";

const AdditionalDetails = ({ form, setForm }: BrandTabProps) => {
  const updateField = <TKey extends keyof typeof form.additional>(
    key: TKey,
    value: (typeof form.additional)[TKey],
  ) => updateBrandFormSection(setForm, "additional", key, value);

  return (
    <FormSection title="Advanced" description="Optional fields to further refine your brand intelligence">
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="space-y-5">
          <FormSubsection title="Brand Purpose and Positioning">
            <FormField label="Brand Mission">
              <StyledInput
                placeholder="Why this brand exists"
                value={form.additional.brandMission}
                onChange={(e) => updateField("brandMission", e.target.value)}
              />
            </FormField>
            <FormField label="Brand Vision">
              <StyledInput
                placeholder="Where this brand is headed"
                value={form.additional.brandVision}
                onChange={(e) => updateField("brandVision", e.target.value)}
              />
            </FormField>
            <FormField label="Brand Promise">
              <StyledInput
                placeholder="What this brand commits to every time"
                value={form.additional.brandPromise}
                onChange={(e) => updateField("brandPromise", e.target.value)}
              />
            </FormField>
            <FormField label="Market Positioning">
              <StyledInput
                placeholder="How this brand stands apart in the market"
                value={form.additional.marketPositioning}
                onChange={(e) => updateField("marketPositioning", e.target.value)}
              />
            </FormField>
            <FormField label="Role of Digital Platforms">
              <StyledInput
                placeholder="How digital platforms support the brand"
                value={form.additional.roleOfDigitalPlatforms}
                onChange={(e) => updateField("roleOfDigitalPlatforms", e.target.value)}
              />
            </FormField>
            <FormField label="Social Media Challenges">
              <StyledInput
                placeholder="Key challenges faced on social media"
                value={form.additional.socialMediaChallenges}
                onChange={(e) => updateField("socialMediaChallenges", e.target.value)}
              />
            </FormField>
          </FormSubsection>

          <FormSubsection title="Strategic Block">
            <FormField label="Business Problem or Opportunity">
              <StyledInput
                placeholder="The gap this brand was built to close"
                value={form.additional.businessProblemOrOpportunity}
                onChange={(e) => updateField("businessProblemOrOpportunity", e.target.value)}
              />
            </FormField>
            <FormField label="Perception Challenge">
              <StyledInput
                placeholder="What people actually feel before they find this brand"
                value={form.additional.perceptionChallenge}
                onChange={(e) => updateField("perceptionChallenge", e.target.value)}
              />
            </FormField>
            <FormField label="Human Insight">
              <StyledInput
                placeholder="The truth that makes this strategy work"
                value={form.additional.humanInsight}
                onChange={(e) => updateField("humanInsight", e.target.value)}
              />
            </FormField>
            <FormField label="Brand Advantage">
              <StyledInput
                placeholder="Why this brand wins"
                value={form.additional.brandAdvantage}
                onChange={(e) => updateField("brandAdvantage", e.target.value)}
              />
            </FormField>
            <FormField label="Strategy">
              <StyledTextarea
                placeholder="How the brand plans to win"
                value={form.additional.strategy}
                onChange={(e) => updateField("strategy", e.target.value)}
              />
            </FormField>
          </FormSubsection>
        </div>

        <div className="space-y-5">
          <FormSubsection title="Industry and Context Parameters">
            <FormField label="Market Maturity">
              <StyledSelect
                value={form.additional.marketMaturity}
                onValueChange={(value) => updateField("marketMaturity", value)}
                placeholder="Select market maturity"
                options={MARKET_MATURITY_OPTIONS}
              />
            </FormField>
            <FormField label="Brand Archetype">
              <StyledSelect
                value={form.additional.brandArchetype}
                onValueChange={(value) => updateField("brandArchetype", value)}
                placeholder="Select brand archetype"
                options={BRAND_ARCHETYPE_OPTIONS}
              />
            </FormField>
            <FormField label="Buying Stage">
              <StyledSelect
                value={form.additional.buyingStage}
                onValueChange={(value) => updateField("buyingStage", value)}
                placeholder="Select buying stage"
                options={BUYING_STAGE_OPTIONS}
              />
            </FormField>
            <FormField label="Compliance Level">
              <StyledSelect
                value={form.additional.complianceLevel}
                onValueChange={(value) => updateField("complianceLevel", value)}
                placeholder="Select compliance sensitivity"
                options={COMPLIANCE_LEVEL_OPTIONS}
              />
            </FormField>
            <FormField label="Competitor Brand Name">
              <StyledInput
                placeholder="Enter the competitor brand name"
                value={form.additional.competitorBrandName}
                onChange={(e) => updateField("competitorBrandName", e.target.value)}
              />
            </FormField>
            <FormField label="Website URL">
              <StyledInput
                placeholder="Enter the competitor brand's website url"
                value={form.additional.websiteUrl}
                onChange={(e) => updateField("websiteUrl", e.target.value)}
              />
            </FormField>
            <FormField label="LinkedIn">
              <StyledInput
                placeholder="LinkedIn"
                value={form.additional.linkedin}
                onChange={(e) => updateField("linkedin", e.target.value)}
              />
            </FormField>
            <FormField label="Instagram">
              <StyledInput
                placeholder="Instagram"
                value={form.additional.instagram}
                onChange={(e) => updateField("instagram", e.target.value)}
              />
            </FormField>
            <FormField label="X">
              <StyledInput
                placeholder="X"
                value={form.additional.x}
                onChange={(e) => updateField("x", e.target.value)}
              />
            </FormField>
          </FormSubsection>
        </div>
      </div>
    </FormSection>
  );
};

export default AdditionalDetails;
