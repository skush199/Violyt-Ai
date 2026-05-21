"use client";

export function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
        return;
      }
      reject(new Error(`Unable to read file "${file.name}".`));
    };
    reader.onerror = () => reject(reader.error || new Error(`Unable to read file "${file.name}".`));
    reader.readAsDataURL(file);
  });
}

export function stripFileExtension(filename: string) {
  return filename.replace(/\.[^.]+$/, "");
}
