import {
  FileUploadCollection,
  FormField,
  FormSection,
  StyledInput,
  StyledSelect,
  StyledTextarea,
} from "./FormFields";
import { INDUSTRY_OPTIONS } from "@/lib/brand-space-options";
import {
  createBrandUploadItem,
  updateBrandFormSection,
  type BrandTabProps,
} from "@/types/brand-space.types";

const CoreBrandSignals = ({ form, setForm, onRemoveUpload }: BrandTabProps) => {
  const updateField = <TKey extends keyof typeof form.core>(key: TKey, value: (typeof form.core)[TKey]) =>
    updateBrandFormSection(setForm, "core", key, value);

  const logoItems = form.core.logos.length ? form.core.logos : form.core.logo ? [form.core.logo] : [];

  const addLogos = (files: FileList | null) => {
    if (!files?.length) {
      return;
    }
    const nextLogos = [
      ...logoItems,
      ...Array.from(files).map((file) => createBrandUploadItem(file, ["Logo"])),
    ];
    updateField("logos", nextLogos);
    updateField("logo", nextLogos[0] || null);
  };

  return (
    <FormSection title="Brand Details">
      <FileUploadCollection
        label="Upload Brand Logos"
        acceptedFormats="SVG, PNG, JPG, JPEG, WEBP, PDF"
        items={logoItems}
        onAdd={addLogos}
        onRemove={(itemId) => {
          if (onRemoveUpload) {
            void onRemoveUpload(itemId);
            return;
          }
          const nextLogos = logoItems.filter((item) => item.id !== itemId);
          updateField("logos", nextLogos);
          updateField("logo", nextLogos[0] || null);
        }}
        multiple
        tags={["Logo"]}
      />

      <div className="grid gap-5 lg:max-w-3xl">
        <FormField label="Brand Name" required>
          <StyledInput
            placeholder="Enter the brand name"
            value={form.core.name}
            onChange={(e) => updateField("name", e.target.value)}
          />
        </FormField>

        <FormField label="Brand Description" required>
          <StyledTextarea
            placeholder="Describe the brand"
            value={form.core.description}
            onChange={(e) => updateField("description", e.target.value)}
          />
        </FormField>

        <FormField label="Industry Category" required>
          <StyledSelect
            value={form.core.industryCategory}
            onValueChange={(value) => updateField("industryCategory", value)}
            placeholder="Select the industry category"
            options={INDUSTRY_OPTIONS}
          />
        </FormField>

        <FormField label="Key Differentiators">
          <StyledTextarea
            placeholder="What makes this brand genuinely different"
            value={form.core.differentiators}
            onChange={(e) => updateField("differentiators", e.target.value)}
          />
        </FormField>
      </div>
    </FormSection>
  );
};

export default CoreBrandSignals;
