import { Suspense } from "react";
import Image from "next/image";
import MainAuthLandingPage from "@/components/auth/MainLandingPage";
import { ActivateForm } from "@/components/auth/ActivateForm";

export const metadata = {
  title: "Activate - Violyt",
  description: "Activate your Violyt workspace access",
};

export default function ActivatePage() {
  return (
    <MainAuthLandingPage>
      <div className="w-full max-w-md">
        <div className="text-start mb-8">
          <Image src="/logo.svg" alt="Violyt Logo" width={56} height={56} />
          <h1 className="font-dmSans text-5xl font-extrabold text-gray-900 my-4 tracking-tight">
            Welcome to Violyt
          </h1>
          <p className="text-gray-600 font-semibold">
            Access your brand intelligence workspace.
          </p>
        </div>

        <Suspense fallback={<div className="py-6 text-sm text-gray-500">Loading activation form...</div>}>
          <ActivateForm />
        </Suspense>
      </div>
    </MainAuthLandingPage>
  );
}
