"use client";

import { type ComponentProps, ReactNode, useId, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Eye, FileText, ImagePlus, Loader2, Plus, Upload, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { BrandUploadItem } from "@/types/brand-space.types";

type FormFieldProps = {
  label: string;
  required?: boolean;
  children: ReactNode;
  hint?: string;
  error?: string;
};

type UploadCollectionProps = {
  label: string;
  acceptedFormats: string;
  items: BrandUploadItem[];
  onAdd: (files: FileList | null) => void;
  onRemove: (itemId: string) => void;
  multiple?: boolean;
  tags?: string[];
  className?: string;
};

type SingleUploadProps = {
  label: string;
  acceptedFormats: string;
  item: BrandUploadItem | null;
  onChange: (files: FileList | null) => void;
  onRemove: () => void;
  className?: string;
};

export function FormField({ label, required, children, hint, error }: FormFieldProps) {
  return (
    <label className="block space-y-2">
      <span className="text-base font-medium text-slate-700">
        {label}
        {required ? <span className="ml-1 text-red-500">*</span> : null}
      </span>
      {hint ? <p className="text-sm text-slate-500">{hint}</p> : null}
      {children}
      {error ? <p className="text-sm text-red-500">{error}</p> : null}
    </label>
  );
}

export function FormSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-[1.65rem] font-semibold text-slate-800">{title}</h2>
        {description ? <p className="mt-1 text-sm text-slate-500">{description}</p> : null}
      </div>
      <div className="space-y-6">{children}</div>
    </div>
  );
}

export function FormSubsection({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-4", className)}>
      <div>
        <h3 className="text-xl font-semibold text-slate-800">{title}</h3>
        {description ? <p className="mt-1 text-sm text-slate-500">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

export function StyledInput(props: ComponentProps<typeof Input>) {
  return (
    <Input
      {...props}
      className={cn(
        "h-12 rounded-xl border-none bg-input-field px-4 py-3 text-sm shadow-none focus-visible:ring-2 focus-visible:ring-primary/20",
        props.className,
      )}
    />
  );
}

export function StyledTextarea(props: ComponentProps<typeof Textarea>) {
  return (
    <Textarea
      {...props}
      className={cn(
        "min-h-24 rounded-xl border-none bg-input-field px-4 py-3 text-sm shadow-none focus-visible:ring-2 focus-visible:ring-primary/20",
        props.className,
      )}
    />
  );
}

export function StyledSelect({
  value,
  onValueChange,
  placeholder,
  options,
  disabled = false,
}: {
  value: string;
  onValueChange: (value: string) => void;
  placeholder: string;
  options: readonly string[];
  disabled?: boolean;
}) {
  return (
    <Select value={value || undefined} onValueChange={onValueChange} disabled={disabled}>
      <SelectTrigger className="h-12 w-full rounded-xl border-none bg-input-field px-4 py-3 text-left text-sm shadow-none focus-visible:ring-2 focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option} value={option}>
            {option}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function CheckboxList({
  options,
  values,
  onToggle,
  className,
}: {
  options: string[];
  values: string[];
  onToggle: (value: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("space-y-3", className)}>
      {options.map((option) => {
        const checked = values.includes(option);
        return (
          <label key={option} className="flex items-center gap-3 text-base text-slate-700">
            <Checkbox checked={checked} onCheckedChange={() => onToggle(option)} />
            <span>{option}</span>
          </label>
        );
      })}
    </div>
  );
}

export function FileUploadField({
  label,
  acceptedFormats,
  item,
  onChange,
  onRemove,
  className,
}: SingleUploadProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const inputId = useId();

  return (
    <div className={cn("space-y-3", className)}>
      <div>
        <p className="text-base font-medium text-slate-700">{label}</p>
        <p className="text-sm text-slate-500">Formats accepted: {acceptedFormats}</p>
      </div>
      <input
        id={inputId}
        ref={inputRef}
        type="file"
        className="hidden"
        accept={acceptedFormatsToAccept(acceptedFormats)}
        onChange={(event) => {
          onChange(event.target.files);
          event.currentTarget.value = "";
        }}
      />
      {item ? (
        <UploadedFileCard item={item} onRemove={onRemove} />
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex h-24 w-40 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 text-sm text-slate-600 transition hover:border-primary/40 hover:bg-slate-50"
        >
          <Upload className="mb-2 h-4 w-4" />
          Upload logo
        </button>
      )}
    </div>
  );
}

export function FileUploadCollection({
  label,
  acceptedFormats,
  items,
  onAdd,
  onRemove,
  multiple = true,
  tags,
  className,
}: UploadCollectionProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const inputId = useId();

  return (
    <div className={cn("space-y-3", className)}>
      <div>
        <p className="text-base font-medium text-slate-700">{label}</p>
        <p className="text-sm text-slate-500">Formats accepted: {acceptedFormats}</p>
      </div>
      <input
        id={inputId}
        ref={inputRef}
        type="file"
        className="hidden"
        accept={acceptedFormatsToAccept(acceptedFormats)}
        multiple={multiple}
        onChange={(event) => {
          onAdd(event.target.files);
          event.currentTarget.value = "";
        }}
      />
      <div className="flex flex-wrap gap-4">
        {items.map((item) => (
          <UploadedFileCard key={item.id} item={item} onRemove={() => onRemove(item.id)} />
        ))}
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex h-28 w-40 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white text-sm text-slate-600 transition hover:border-primary/40 hover:bg-slate-50"
        >
          <Upload className="mb-2 h-4 w-4" />
          Upload
          {tags?.length ? (
            <div className="mt-3 flex flex-wrap justify-center gap-1">
              {tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-500"
                >
                  {tag}
                </span>
              ))}
            </div>
          ) : null}
        </button>
      </div>
    </div>
  );
}

export function AdditionalColorRow({
  name,
  hex,
  onNameChange,
  onHexChange,
  canRemove,
  onRemove,
}: {
  name: string;
  hex: string;
  onNameChange: (value: string) => void;
  onHexChange: (value: string) => void;
  canRemove: boolean;
  onRemove: () => void;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
      <StyledInput placeholder="Define color name" value={name} onChange={(e) => onNameChange(e.target.value)} />
      <StyledInput placeholder="Define color code" value={hex} onChange={(e) => onHexChange(e.target.value)} />
      <div className="flex items-center justify-end">
        {canRemove ? (
          <Button type="button" variant="ghost" size="icon-sm" onClick={onRemove}>
            <X className="h-4 w-4" />
          </Button>
        ) : (
          <span className="w-7" />
        )}
      </div>
    </div>
  );
}

export function AddMoreButton({
  onClick,
  children = "Add more",
}: {
  onClick: () => void;
  children?: ReactNode;
}) {
  return (
    <button type="button" onClick={onClick} className="inline-flex items-center gap-2 text-sm font-medium text-primary">
      <Plus className="h-4 w-4" />
      {children}
    </button>
  );
}

function UploadedFileCard({
  item,
  onRemove,
}: {
  item: BrandUploadItem;
  onRemove: () => void;
}) {
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const previewSource = item.previewUrl || item.assetUrl;
  const isImagePreview =
    Boolean(previewSource) &&
    (
      String(item.mimeType || "").startsWith("image/") ||
      /\.(png|jpe?g|webp|svg)$/i.test(String(previewSource || ""))
    );
  const normalizedState = (item.lifecycleState || "").toLowerCase();
  const isReadyToUpload = normalizedState === "selected";
  const isQueued = ["uploaded", "queued"].includes(normalizedState);
  const isProcessing = ["uploading", "processing", "analyzing"].includes(normalizedState);
  const isReady = ["indexed", "complete", "ready"].includes(normalizedState);
  const isFailed = normalizedState === "failed";
  const statusLabel =
    normalizedState === "selected"
      ? "Ready"
      : normalizedState === "uploading"
      ? "Uploading"
      : normalizedState === "uploaded" || normalizedState === "queued"
        ? "Queued"
      : normalizedState === "analyzing"
        ? "Analyzing"
        : normalizedState === "processing"
          ? "Processing"
          : normalizedState === "indexed" || normalizedState === "complete" || normalizedState === "ready"
            ? "Synced"
            : normalizedState === "failed"
              ? "Failed"
              : item.lifecycleState;
  return (
    <>
      <div className="w-40 rounded-xl border border-slate-200 bg-white p-3 shadow-[0_10px_20px_-18px_rgba(15,23,42,0.45)]">
        <div className="flex items-start justify-between gap-2">
          <button
            type="button"
            onClick={() => isImagePreview && setIsPreviewOpen(true)}
            disabled={!isImagePreview}
            className={cn(
              "flex h-10 w-10 items-center justify-center overflow-hidden rounded-lg bg-sky-50 text-sky-500 transition",
              isImagePreview ? "hover:bg-sky-100" : "cursor-default",
            )}
          >
            {isImagePreview ? <Eye className="h-4 w-4" /> : item.assetUrl ? <ImagePlus className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
          </button>
          <button type="button" className="text-slate-400 transition hover:text-slate-700" onClick={onRemove}>
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-3 line-clamp-2 text-sm font-medium text-slate-700">{item.name}</p>
        {statusLabel ? (
          <div className="mt-2 flex items-center gap-1.5 text-[11px] uppercase tracking-[0.18em]">
            {isReadyToUpload ? <FileText className="h-3.5 w-3.5 text-slate-500" /> : null}
            {isProcessing ? <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> : null}
            {isQueued ? <Loader2 className="h-3.5 w-3.5 text-amber-500" /> : null}
            {isReady ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : null}
            {isFailed ? <AlertCircle className="h-3.5 w-3.5 text-red-500" /> : null}
            <span className={isFailed ? "text-red-500" : isReady ? "text-emerald-600" : isQueued ? "text-amber-600" : isReadyToUpload ? "text-slate-500" : "text-slate-400"}>
              {statusLabel}
            </span>
          </div>
        ) : null}
        {item.pageCount ? <p className="mt-1 text-[11px] text-slate-500">{item.pageCount} OCR page{item.pageCount > 1 ? "s" : ""}</p> : null}
        {item.processingError ? <p className="mt-1 text-[11px] text-red-500">{item.processingError}</p> : null}
        {item.tags?.length ? (
          <div className="mt-2 flex flex-wrap gap-1">
            {item.tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-500"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <Dialog open={isPreviewOpen} onOpenChange={setIsPreviewOpen}>
        <DialogContent className="max-w-4xl border-slate-200 bg-white p-4">
          <DialogHeader>
            <DialogTitle className="truncate pr-8 text-base text-slate-900">{item.name}</DialogTitle>
          </DialogHeader>
          {previewSource ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={previewSource} alt={item.name} className="max-h-[75vh] w-full rounded-xl object-contain" />
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

function acceptedFormatsToAccept(value: string) {
  return value
    .split(/[,\s/]+/)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)
    .map((item) => {
      if (item.startsWith(".")) {
        return item;
      }
      if (item.includes("/")) {
        return item;
      }
      return `.${item}`;
    })
    .join(",");
}
