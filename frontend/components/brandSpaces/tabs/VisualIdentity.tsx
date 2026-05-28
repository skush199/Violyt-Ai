import {
  CheckboxList,
  AddMoreButton,
  AdditionalColorRow,
  FileUploadCollection,
  FormField,
  FormSection,
  FormSubsection,
  StyledSelect,
  StyledInput,
} from "./FormFields";
import {
  isLogoPlacementOption,
  LOGO_PLACEMENT_OPTIONS,
  normalizeLogoPlacementPolicy,
} from "@/lib/logo-placement";
import { createBrandUploadItem, updateBrandFormSection, type BrandTabProps } from "@/types/brand-space.types";

const DOCUMENT_UPLOAD_FORMATS = "PDF, DOC, DOCX, PPT, PPTX, TXT, MD, CSV, JSON, PNG, JPG, JPEG, WEBP";

const VisualIdentity = ({ form, setForm, onRemoveUpload, onFontGuideUploadAdded }: BrandTabProps) => {
  const logoPlacementPolicy = normalizeLogoPlacementPolicy(
    form.visualIdentity.allowedLogoPlacements,
    form.visualIdentity.defaultLogoPlacement,
  );

  const updateField = <TKey extends keyof typeof form.visualIdentity>(
    key: TKey,
    value: (typeof form.visualIdentity)[TKey],
  ) => updateBrandFormSection(setForm, "visualIdentity", key, value);

  const toggleLogoPlacement = (placement: string) => {
    if (!isLogoPlacementOption(placement)) {
      return;
    }
    setForm((current) => {
      const currentPolicy = normalizeLogoPlacementPolicy(
        current.visualIdentity.allowedLogoPlacements,
        current.visualIdentity.defaultLogoPlacement,
      );
      const nextPlacements = currentPolicy.allowedLogoPlacements.includes(placement)
        ? currentPolicy.allowedLogoPlacements.filter((item) => item !== placement)
        : [...currentPolicy.allowedLogoPlacements, placement];
      const nextPolicy = normalizeLogoPlacementPolicy(nextPlacements, currentPolicy.defaultLogoPlacement);
      return {
        ...current,
        visualIdentity: {
          ...current.visualIdentity,
          allowedLogoPlacements: nextPolicy.allowedLogoPlacements,
          defaultLogoPlacement: nextPolicy.defaultLogoPlacement,
        },
      };
    });
  };

  const updateDefaultLogoPlacement = (value: string) => {
    if (!isLogoPlacementOption(value)) {
      return;
    }
    setForm((current) => {
      const currentPolicy = normalizeLogoPlacementPolicy(
        current.visualIdentity.allowedLogoPlacements,
        current.visualIdentity.defaultLogoPlacement,
      );
      if (!currentPolicy.allowedLogoPlacements.includes(value)) {
        return current;
      }
      return {
        ...current,
        visualIdentity: {
          ...current.visualIdentity,
          allowedLogoPlacements: currentPolicy.allowedLogoPlacements,
          defaultLogoPlacement: value,
        },
      };
    });
  };

  const addUploads = (
    key: "referenceCreatives" | "moodBoards" | "colorPaletteUploads" | "fontStyleGuide",
    files: FileList | null,
  ) => {
    if (!files?.length) {
      return;
    }
    const uploadItems = Array.from(files).map((file) => createBrandUploadItem(file));
    updateField(key, [...form.visualIdentity[key], ...uploadItems]);
    if (key === "fontStyleGuide" && onFontGuideUploadAdded) {
      void onFontGuideUploadAdded(uploadItems);
    }
  };

  return (
    <FormSection title="Visual Identity Training">
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="space-y-5">
          <FormField label="Brand Mood">
            <StyledInput
              placeholder="Overall mood the brand conveys"
              value={form.visualIdentity.brandMood}
              onChange={(e) => updateField("brandMood", e.target.value)}
            />
          </FormField>
          <FormField label="Visual Style">
            <StyledInput
              placeholder="Visual style the brand uses"
              value={form.visualIdentity.visualStyle}
              onChange={(e) => updateField("visualStyle", e.target.value)}
            />
          </FormField>

          <FormSubsection
            title="Logo Placement Policy"
            description="Choose the corners or zones this brand allows for logo placement. The generator will pick from these options and reserve that area so no image or text overlaps it."
          >
            <FormField label="Allowed logo positions">
              <CheckboxList
                options={[...LOGO_PLACEMENT_OPTIONS]}
                values={logoPlacementPolicy.allowedLogoPlacements}
                onToggle={toggleLogoPlacement}
              />
            </FormField>
            <FormField
              label="Default logo position"
              hint="Used as the preferred anchor when the chosen layout has more than one allowed option."
            >
              <StyledSelect
                value={logoPlacementPolicy.defaultLogoPlacement}
                onValueChange={updateDefaultLogoPlacement}
                placeholder={
                  logoPlacementPolicy.allowedLogoPlacements.length
                    ? "Select default logo position"
                    : "Select an allowed position first"
                }
                options={logoPlacementPolicy.allowedLogoPlacements}
                disabled={!logoPlacementPolicy.allowedLogoPlacements.length}
              />
            </FormField>
          </FormSubsection>

          <FormSubsection title="Upload documentation">
            <FileUploadCollection
              label="Reference creatives"
              acceptedFormats={DOCUMENT_UPLOAD_FORMATS}
              items={form.visualIdentity.referenceCreatives}
              onAdd={(files) => addUploads("referenceCreatives", files)}
              onRemove={(itemId) => {
                if (onRemoveUpload) {
                  void onRemoveUpload(itemId);
                  return;
                }
                updateField(
                  "referenceCreatives",
                  form.visualIdentity.referenceCreatives.filter((item) => item.id !== itemId),
                );
              }}
            />
            <FileUploadCollection
              label="Mood boards"
              acceptedFormats={DOCUMENT_UPLOAD_FORMATS}
              items={form.visualIdentity.moodBoards}
              onAdd={(files) => addUploads("moodBoards", files)}
              onRemove={(itemId) => {
                if (onRemoveUpload) {
                  void onRemoveUpload(itemId);
                  return;
                }
                updateField(
                  "moodBoards",
                  form.visualIdentity.moodBoards.filter((item) => item.id !== itemId),
                );
              }}
            />
          </FormSubsection>
        </div>

        <div className="space-y-5">
          <FormSubsection title="Brand Color Palette (HEX)">
            <div className="grid gap-3 md:grid-cols-2">
              <div className="flex h-12 items-center rounded-xl bg-input-field px-4 py-3 text-sm text-slate-600">
                Primary color
              </div>
              <StyledInput
                placeholder="Define color code"
                value={form.visualIdentity.primaryColor}
                onChange={(e) => updateField("primaryColor", e.target.value)}
              />
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="flex h-12 items-center rounded-xl bg-input-field px-4 py-3 text-sm text-slate-600">
                Secondary color
              </div>
              <StyledInput
                placeholder="Define color code"
                value={form.visualIdentity.secondaryColor}
                onChange={(e) => updateField("secondaryColor", e.target.value)}
              />
            </div>
            {form.visualIdentity.additionalColors.map((color, index) => (
              <AdditionalColorRow
                key={`${color.name}-${index}`}
                name={color.name}
                hex={color.hex}
                onNameChange={(value) => {
                  const nextColors = [...form.visualIdentity.additionalColors];
                  nextColors[index] = { ...nextColors[index], name: value };
                  updateField("additionalColors", nextColors);
                }}
                onHexChange={(value) => {
                  const nextColors = [...form.visualIdentity.additionalColors];
                  nextColors[index] = { ...nextColors[index], hex: value };
                  updateField("additionalColors", nextColors);
                }}
                canRemove={form.visualIdentity.additionalColors.length > 1}
                onRemove={() =>
                  updateField(
                    "additionalColors",
                    form.visualIdentity.additionalColors.filter((_, itemIndex) => itemIndex !== index),
                  )
                }
              />
            ))}
            <div className="flex justify-end">
              <AddMoreButton
                onClick={() =>
                  updateField("additionalColors", [...form.visualIdentity.additionalColors, { name: "", hex: "" }])
                }
              />
            </div>
          </FormSubsection>

          <FileUploadCollection
            label="Upload Color Palette"
            acceptedFormats={DOCUMENT_UPLOAD_FORMATS}
            items={form.visualIdentity.colorPaletteUploads}
            onAdd={(files) => addUploads("colorPaletteUploads", files)}
            onRemove={(itemId) => {
              if (onRemoveUpload) {
                void onRemoveUpload(itemId);
                return;
              }
              updateField(
                "colorPaletteUploads",
                form.visualIdentity.colorPaletteUploads.filter((item) => item.id !== itemId),
              );
            }}
          />

          <FormField label="Typography" required>
            <StyledInput
              placeholder="Enter typography or upload font style guide"
              value={form.visualIdentity.typography}
              onChange={(e) => updateField("typography", e.target.value)}
            />
          </FormField>

          <FileUploadCollection
            label="Upload Font Style Guide"
            acceptedFormats={DOCUMENT_UPLOAD_FORMATS}
            items={form.visualIdentity.fontStyleGuide}
            onAdd={(files) => addUploads("fontStyleGuide", files)}
            onRemove={(itemId) => {
              if (onRemoveUpload) {
                void onRemoveUpload(itemId);
                return;
              }
              updateField(
                "fontStyleGuide",
                form.visualIdentity.fontStyleGuide.filter((item) => item.id !== itemId),
              );
            }}
          />
        </div>
      </div>
    </FormSection>
  );
};

export default VisualIdentity;
