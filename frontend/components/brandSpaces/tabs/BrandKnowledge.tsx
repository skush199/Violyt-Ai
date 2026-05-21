import { FileUploadCollection, FormSection } from "./FormFields";
import { createBrandUploadItem, updateBrandFormSection, type BrandTabProps } from "@/types/brand-space.types";

const BrandKnowledge = ({ form, setForm, onRemoveUpload }: BrandTabProps) => {
  const updateField = <TKey extends keyof typeof form.brandKnowledge>(
    key: TKey,
    value: (typeof form.brandKnowledge)[TKey],
  ) => updateBrandFormSection(setForm, "brandKnowledge", key, value);

  const addUploads = (key: "templateFiles" | "otherDocuments", files: FileList | null) => {
    if (!files?.length) {
      return;
    }
    const defaultTags = key === "templateFiles" ? ["Template", "Graphics"] : undefined;
    updateField(key, [...form.brandKnowledge[key], ...Array.from(files).map((file) => createBrandUploadItem(file, defaultTags))]);
  };

  return (
    <FormSection title="Documentation">
      <FileUploadCollection
        label="Template"
        acceptedFormats="PDF, DOC, DOCX, PPT, PPTX, PNG, JPG, JPEG, WEBP"
        items={form.brandKnowledge.templateFiles}
        onAdd={(files) => addUploads("templateFiles", files)}
        onRemove={(itemId) => {
          if (onRemoveUpload) {
            void onRemoveUpload(itemId);
            return;
          }
          updateField(
            "templateFiles",
            form.brandKnowledge.templateFiles.filter((item) => item.id !== itemId),
          );
        }}
        multiple
        tags={["Template", "Graphics"]}
      />

      <FileUploadCollection
        label="Other documentation"
        acceptedFormats="PDF, DOC, DOCX, PPT, PPTX, PNG, JPG, JPEG, WEBP"
        items={form.brandKnowledge.otherDocuments}
        onAdd={(files) => addUploads("otherDocuments", files)}
        onRemove={(itemId) => {
          if (onRemoveUpload) {
            void onRemoveUpload(itemId);
            return;
          }
          updateField(
            "otherDocuments",
            form.brandKnowledge.otherDocuments.filter((item) => item.id !== itemId),
          );
        }}
        multiple
      />
    </FormSection>
  );
};

export default BrandKnowledge;
