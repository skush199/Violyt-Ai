import {
  CheckboxList,
  FormField,
  FormSection,
  FormSubsection,
  StyledInput,
  StyledSelect,
} from "./FormFields";
import {
  CONTENT_COMPLEXITY_OPTIONS,
  CORE_TONE_OPTIONS,
  PERSPECTIVE_OPTIONS,
  SENTENCE_LENGTH_OPTIONS,
} from "@/lib/brand-space-options";
import { updateBrandFormSection, type BrandTabProps } from "@/types/brand-space.types";

const VoiceTone = ({ form, setForm }: BrandTabProps) => {
  const updateField = <TKey extends keyof typeof form.voiceTone>(
    key: TKey,
    value: (typeof form.voiceTone)[TKey],
  ) => updateBrandFormSection(setForm, "voiceTone", key, value);

  const toggleToneAttribute = (value: string) => {
    const nextValues = form.voiceTone.coreToneAttributes.includes(value)
      ? form.voiceTone.coreToneAttributes.filter((item) => item !== value)
      : [...form.voiceTone.coreToneAttributes, value];
    updateField("coreToneAttributes", nextValues);
  };

  return (
    <FormSection title="Tone Attributes">
      <FormField label="Core Tone Attributes" required>
        <CheckboxList
          options={CORE_TONE_OPTIONS}
          values={form.voiceTone.coreToneAttributes}
          onToggle={toggleToneAttribute}
        />
      </FormField>

      <FormSubsection title="Advanced" description="Optional fields to further refine your brand intelligence">
        <div className="grid gap-5 md:grid-cols-2">
          <FormField label="Primary Emotion">
            <StyledInput
              placeholder="The dominant feeling this brand creates"
              value={form.voiceTone.primaryEmotion}
              onChange={(e) => updateField("primaryEmotion", e.target.value)}
            />
          </FormField>
          <FormField label="Content Complexity">
            <StyledSelect
              value={form.voiceTone.contentComplexity}
              onValueChange={(value) => updateField("contentComplexity", value)}
              placeholder="Select content complexity"
              options={CONTENT_COMPLEXITY_OPTIONS}
            />
          </FormField>

          <FormField label="Secondary Emotion">
            <StyledInput
              placeholder="The supporting emotional layer"
              value={form.voiceTone.secondaryEmotion}
              onChange={(e) => updateField("secondaryEmotion", e.target.value)}
            />
          </FormField>
          <FormField label="Sentence Length">
            <StyledSelect
              value={form.voiceTone.sentenceLength}
              onValueChange={(value) => updateField("sentenceLength", value)}
              placeholder="Select sentence length"
              options={SENTENCE_LENGTH_OPTIONS}
            />
          </FormField>

          <FormField label="Avoided Emotion">
            <StyledInput
              placeholder="What this brand never wants to make people feel"
              value={form.voiceTone.avoidedEmotion}
              onChange={(e) => updateField("avoidedEmotion", e.target.value)}
            />
          </FormField>
          <FormField label="Perspective">
            <StyledSelect
              value={form.voiceTone.perspective}
              onValueChange={(value) => updateField("perspective", value)}
              placeholder="Select perspective"
              options={PERSPECTIVE_OPTIONS}
            />
          </FormField>
        </div>
      </FormSubsection>
    </FormSection>
  );
};

export default VoiceTone;
