import Image from "next/image";
import MainAuthLandingPage from "@/components/auth/MainLandingPage";
import Setup2faForm from "@/components/auth/Setup2faForm";

export const metadata = {
  title: "Setup 2FA - Violyt",
  description: "Set up two-factor authentication for Violyt",
};

export default function SetupTwoFactorPage() {
  return (
    <MainAuthLandingPage>
      <div className="w-full max-w-md">
        <div className="mb-8 text-start">
          <Image src="/logo.svg" alt="Violyt Logo" width={56} height={56} />
          <h1 className="my-4 font-dmSans text-5xl font-extrabold tracking-tight text-gray-900">
            Two-Factor Authentication
          </h1>
          <p className="font-semibold text-gray-600">Secure your account with Google Authenticator</p>
        </div>

        <Setup2faForm />
      </div>
    </MainAuthLandingPage>
  );
}
