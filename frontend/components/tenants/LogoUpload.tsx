"use client";

import { apiOrigin } from "@/lib/env";
import Image from "next/image";
import { UploadCloud } from "lucide-react";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Label } from "../ui/label";

const MAX_SIZE = 2 * 1024 * 1024;
const ALLOWED_TYPES = ["image/png", "image/jpeg"];

function resolvePreview(value?: File | string | null) {
  if (!value) {
    return null;
  }
  if (typeof value === "string") {
    if (value.startsWith("blob:") || value.startsWith("data:") || value.startsWith("http")) {
      return value;
    }
    return `${apiOrigin}/storage/${value}`;
  }
  return URL.createObjectURL(value);
}

const TenantLogoUpload = ({ value, onChange }: { value?: File | string | null; onChange: (logo: File) => void }) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const preview = useMemo(() => resolvePreview(value), [value]);

  useEffect(() => {
    return () => {
      if (preview?.startsWith("blob:")) {
        URL.revokeObjectURL(preview);
      }
    };
  }, [preview]);

  const validateFile = (file: File) => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      setError("Only PNG or JPEG allowed");
      return false;
    }

    if (file.size > MAX_SIZE) {
      setError("File size should be less than 2MB");
      return false;
    }

    return true;
  };

  const handleFile = (file: File) => {
    if (!validateFile(file)) {
      return;
    }

    onChange(file);
    setError(null);
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0];
    if (selected) {
      handleFile(selected);
    }
  };

  return (
    <div className="w-full space-y-3">
      <Label className="flex flex-col items-start gap-1 text-base font-medium leading-6 text-[#2F3342]">
        <span className="text-base">Tenant logo</span>
        <span className="text-base font-normal text-[#4B5563]">Custom branding in widget</span>
      </Label>

      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          const droppedFile = event.dataTransfer.files?.[0];
          if (droppedFile) {
            handleFile(droppedFile);
          }
        }}
        className={`flex h-[77px] w-[191px] flex-col items-center justify-center rounded-[10px] border hover:border-2 cursor-pointer border-dashed text-center transition ${
          dragActive ? "border-primary bg-primary/5" : "border-primary/80 bg-white"
        }`}
      >
        {preview ? (
          <Image
            src={preview}
            alt="logo preview"
            width={160}
            height={64}
            unoptimized
            className="h-14 w-auto object-contain"
          />
        ) : (
          <>
            <UploadCloud className="mb-1 h-5 w-5 text-primary" />
            <span className="text-base font-medium leading-[22px] text-[#2F3342]">Upload logo</span>
          </>
        )}
      </button>

      {error ? <p className="text-sm text-red-500">{error}</p> : null}

      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept="image/png, image/jpeg"
        onChange={handleFileChange}
      />
    </div>
  );
};

export default TenantLogoUpload;
