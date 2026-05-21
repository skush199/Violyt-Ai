import {
  CheckboxList,
  FileUploadCollection,
  FormField,
  FormSection,
  FormSubsection,
  StyledTextarea,
} from "./FormFields";
import { BRAND_RULE_OPTIONS } from "@/lib/brand-space-options";
import { createBrandUploadItem, updateBrandFormSection, type BrandTabProps } from "@/types/brand-space.types";

const BrandRules = ({ form, setForm, onRemoveUpload }: BrandTabProps) => {
  const updateField = <TKey extends keyof typeof form.brandRules>(
    key: TKey,
    value: (typeof form.brandRules)[TKey],
  ) => updateBrandFormSection(setForm, "brandRules", key, value);

  const toggleRule = (value: string) => {
    const nextRules = form.brandRules.selectedRules.includes(value)
      ? form.brandRules.selectedRules.filter((item) => item !== value)
      : [...form.brandRules.selectedRules, value];
    updateField("selectedRules", nextRules);
  };

  const addUploads = (
    key: "positiveWordBankUploads" | "replaceableWordUploads" | "negativeWordBankUploads",
    files: FileList | null,
  ) => {
    if (!files?.length) {
      return;
    }
    updateField(key, [...form.brandRules[key], ...Array.from(files).map((file) => createBrandUploadItem(file))]);
  };

  return (
    <FormSection title="Set The Rules. Violyt Will Follow Them.">
      <FormField label="Set The Rules. Violyt Will Follow Them." required>
        <CheckboxList options={BRAND_RULE_OPTIONS} values={form.brandRules.selectedRules} onToggle={toggleRule} />
      </FormField>

      <div className="grid gap-8 lg:grid-cols-2">
        <div className="space-y-5">
          <FormSubsection title="Brand Word Banks">
            <FormField label="Positive Word Bank">
              <StyledTextarea
                placeholder="Words and phrases that feel right for this brand"
                value={form.brandRules.positiveWordBank}
                onChange={(e) => updateField("positiveWordBank", e.target.value)}
              />
            </FormField>
            <FileUploadCollection
              label="Upload Positive Word Bank"
              acceptedFormats="PDF, DOC, DOCX, PNG, JPG, JPEG"
              items={form.brandRules.positiveWordBankUploads}
              onAdd={(files) => addUploads("positiveWordBankUploads", files)}
              onRemove={(itemId) => {
                if (onRemoveUpload) {
                  void onRemoveUpload(itemId);
                  return;
                }
                updateField(
                  "positiveWordBankUploads",
                  form.brandRules.positiveWordBankUploads.filter((item) => item.id !== itemId),
                );
              }}
            />

            <FormField label="Replaceable Words">
              <StyledTextarea
                placeholder="Words to rephrase, with preferred alternatives"
                value={form.brandRules.replaceableWords}
                onChange={(e) => updateField("replaceableWords", e.target.value)}
              />
            </FormField>
            <FileUploadCollection
              label="Upload Replaceable Words"
              acceptedFormats="PDF, DOC, DOCX, PNG, JPG, JPEG"
              items={form.brandRules.replaceableWordUploads}
              onAdd={(files) => addUploads("replaceableWordUploads", files)}
              onRemove={(itemId) => {
                if (onRemoveUpload) {
                  void onRemoveUpload(itemId);
                  return;
                }
                updateField(
                  "replaceableWordUploads",
                  form.brandRules.replaceableWordUploads.filter((item) => item.id !== itemId),
                );
              }}
            />

            <FormField label="Negative Word Bank">
              <StyledTextarea
                placeholder="Words this brand always avoids"
                value={form.brandRules.negativeWordBank}
                onChange={(e) => updateField("negativeWordBank", e.target.value)}
              />
            </FormField>
            <FileUploadCollection
              label="Upload Negative Word Bank"
              acceptedFormats="PDF, DOC, DOCX, PNG, JPG, JPEG"
              items={form.brandRules.negativeWordBankUploads}
              onAdd={(files) => addUploads("negativeWordBankUploads", files)}
              onRemove={(itemId) => {
                if (onRemoveUpload) {
                  void onRemoveUpload(itemId);
                  return;
                }
                updateField(
                  "negativeWordBankUploads",
                  form.brandRules.negativeWordBankUploads.filter((item) => item.id !== itemId),
                );
              }}
            />
          </FormSubsection>
        </div>

        <div className="space-y-5">
          <FormSubsection title="Custom Rules">
            <FormField label="What To Do">
              <StyledTextarea
                placeholder="Behaviours the AI must always apply"
                value={form.brandRules.whatToDo}
                onChange={(e) => updateField("whatToDo", e.target.value)}
              />
            </FormField>
            <FormField label="What NOT To Do">
              <StyledTextarea
                placeholder="Behaviours the AI must never replicate"
                value={form.brandRules.whatNotToDo}
                onChange={(e) => updateField("whatNotToDo", e.target.value)}
              />
            </FormField>
          </FormSubsection>

          <FormSubsection title="Forbidden Prompt Patterns">
            <FormField label="Restricted Topics" required>
              <StyledTextarea
                placeholder="Topics the AI must avoid generating content about."
                value={form.brandRules.restrictedTopics}
                onChange={(e) => updateField("restrictedTopics", e.target.value)}
              />
            </FormField>
            <FormField label="Restricted Claims" required>
              <StyledTextarea
                placeholder="Claims or statements the AI must not make"
                value={form.brandRules.restrictedClaims}
                onChange={(e) => updateField("restrictedClaims", e.target.value)}
              />
            </FormField>
            <FormField label="Blocked Words / Phrases" required>
              <StyledTextarea
                placeholder="Words or phrases the AI must not use"
                value={form.brandRules.blockedWordsPhrases}
                onChange={(e) => updateField("blockedWordsPhrases", e.target.value)}
              />
            </FormField>
          </FormSubsection>
        </div>
      </div>
    </FormSection>
  );
};

export default BrandRules;
