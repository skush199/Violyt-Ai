import {
  CheckboxList,
  FileUploadCollection,
  FormField,
  FormSection,
  FormSubsection,
  StyledInput,
  StyledSelect,
  StyledTextarea,
} from "./FormFields";
import {
  AUDIENCE_OPTIONS,
  DIGITAL_ACCESS_OPTIONS,
  EDUCATION_LEVEL_OPTIONS,
  EMPLOYMENT_STATUS_OPTIONS,
  HOUSEHOLD_SIZE_OPTIONS,
  INCOME_LEVEL_OPTIONS,
  LANGUAGE_PREFERENCE_OPTIONS,
  LOCATION_OPTIONS,
  PROFESSIONAL_BACKGROUND_OPTIONS,
} from "@/lib/brand-space-options";
import {
  createBrandUploadItem,
  updateBrandFormSection,
  type BrandTabProps,
} from "@/types/brand-space.types";

const TargetAudience = ({ form, setForm, onRemoveUpload }: BrandTabProps) => {
  const updateField = <TKey extends keyof typeof form.targetAudience>(
    key: TKey,
    value: (typeof form.targetAudience)[TKey],
  ) => updateBrandFormSection(setForm, "targetAudience", key, value);

  const toggleAudience = (value: string) => {
    const nextValues = form.targetAudience.selectedAudiences.includes(value)
      ? form.targetAudience.selectedAudiences.filter((item) => item !== value)
      : [...form.targetAudience.selectedAudiences, value];
    updateField("selectedAudiences", nextValues);
  };

  const addAudienceInsights = (files: FileList | null) => {
    if (!files?.length) {
      return;
    }
    updateField("audienceInsights", [
      ...form.targetAudience.audienceInsights,
      ...Array.from(files).map((file) => createBrandUploadItem(file)),
    ]);
  };

  return (
    <FormSection title="Select Target Audience" description="Capture the audience details that should condition generation and recommendations.">
      <FormField label="Select Target Audience" required>
        <CheckboxList
          options={AUDIENCE_OPTIONS}
          values={form.targetAudience.selectedAudiences}
          onToggle={toggleAudience}
        />
      </FormField>

      <FormSubsection title="Advanced" description="Optional fields to further refine your brand intelligence">
        <div className="grid gap-8 lg:grid-cols-2">
          <div className="space-y-5">
            <h4 className="text-lg font-semibold text-slate-800">Psychographic Details</h4>
            <FormField label="Goals">
              <StyledTextarea
                placeholder="What the persona wants to achieve"
                value={form.targetAudience.goals}
                onChange={(e) => updateField("goals", e.target.value)}
              />
            </FormField>
            <FormField label="Motivations">
              <StyledTextarea
                placeholder="What drives the persona"
                value={form.targetAudience.motivations}
                onChange={(e) => updateField("motivations", e.target.value)}
              />
            </FormField>
            <FormField label="Fears and Pain Points">
              <StyledTextarea
                placeholder="What concerns or frustrates the persona"
                value={form.targetAudience.fearsAndPainPoints}
                onChange={(e) => updateField("fearsAndPainPoints", e.target.value)}
              />
            </FormField>
            <FormField label="Objections">
              <StyledTextarea
                placeholder="What the persona may object"
                value={form.targetAudience.objections}
                onChange={(e) => updateField("objections", e.target.value)}
              />
            </FormField>
            <FormField label="Content Consumption Behavior">
              <StyledTextarea
                placeholder="How the persona consumes content"
                value={form.targetAudience.contentConsumptionBehavior}
                onChange={(e) => updateField("contentConsumptionBehavior", e.target.value)}
              />
            </FormField>
            <FileUploadCollection
              label="Upload Audience Insights"
              acceptedFormats="PDF, DOC, DOCX, PPT, PPTX, PNG, JPG, JPEG, WEBP"
              items={form.targetAudience.audienceInsights}
              onAdd={addAudienceInsights}
              onRemove={(itemId) => {
                if (onRemoveUpload) {
                  void onRemoveUpload(itemId);
                  return;
                }
                updateField(
                  "audienceInsights",
                  form.targetAudience.audienceInsights.filter((item) => item.id !== itemId),
                );
              }}
              multiple
            />
          </div>

          <div className="space-y-5">
            <h4 className="text-lg font-semibold text-slate-800">Demographic Details</h4>
            <FormField label="Age Range">
              <StyledInput
                placeholder="Enter age range"
                value={form.targetAudience.ageRange}
                onChange={(e) => updateField("ageRange", e.target.value)}
              />
            </FormField>
            <FormField label="Gender">
              <StyledInput
                placeholder="Enter gender"
                value={form.targetAudience.gender}
                onChange={(e) => updateField("gender", e.target.value)}
              />
            </FormField>
            <FormField label="Location">
              <StyledSelect
                value={form.targetAudience.location}
                onValueChange={(value) => updateField("location", value)}
                placeholder="Select location"
                options={LOCATION_OPTIONS}
              />
            </FormField>
            <FormField label="Education Level">
              <StyledSelect
                value={form.targetAudience.educationLevel}
                onValueChange={(value) => updateField("educationLevel", value)}
                placeholder="Select education level"
                options={EDUCATION_LEVEL_OPTIONS}
              />
            </FormField>
            <FormField label="Employment Status">
              <StyledSelect
                value={form.targetAudience.employmentStatus}
                onValueChange={(value) => updateField("employmentStatus", value)}
                placeholder="Select employment status"
                options={EMPLOYMENT_STATUS_OPTIONS}
              />
            </FormField>
            <FormField label="Professional Background">
              <StyledSelect
                value={form.targetAudience.professionalBackground}
                onValueChange={(value) => updateField("professionalBackground", value)}
                placeholder="Select professional background"
                options={PROFESSIONAL_BACKGROUND_OPTIONS}
              />
            </FormField>
            <FormField label="Household Size">
              <StyledSelect
                value={form.targetAudience.householdSize}
                onValueChange={(value) => updateField("householdSize", value)}
                placeholder="Number of people in the household"
                options={HOUSEHOLD_SIZE_OPTIONS}
              />
            </FormField>
            <FormField label="Language Preference">
              <StyledSelect
                value={form.targetAudience.languagePreference}
                onValueChange={(value) => updateField("languagePreference", value)}
                placeholder="Preferred language"
                options={LANGUAGE_PREFERENCE_OPTIONS}
              />
            </FormField>
            <FormField label="Income Level">
              <StyledSelect
                value={form.targetAudience.incomeLevel}
                onValueChange={(value) => updateField("incomeLevel", value)}
                placeholder="Select income range"
                options={INCOME_LEVEL_OPTIONS}
              />
            </FormField>
            <FormField label="Family Status or Life Stage">
              <StyledInput
                placeholder="Current family or life stage"
                value={form.targetAudience.familyStatusOrLifeStage}
                onChange={(e) => updateField("familyStatusOrLifeStage", e.target.value)}
              />
            </FormField>
            <FormField label="Socio-economic Segment">
              <StyledInput
                placeholder="Socio economic classification"
                value={form.targetAudience.socioEconomicSegment}
                onChange={(e) => updateField("socioEconomicSegment", e.target.value)}
              />
            </FormField>
            <FormField label="Digital Access">
              <StyledSelect
                value={form.targetAudience.digitalAccess}
                onValueChange={(value) => updateField("digitalAccess", value)}
                placeholder="Access to digital platforms and devices"
                options={DIGITAL_ACCESS_OPTIONS}
              />
            </FormField>
          </div>
        </div>
      </FormSubsection>
    </FormSection>
  );
};

export default TargetAudience;
