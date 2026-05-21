// import { LoginForm } from '@/components/auth/login-form';

import { LoginForm } from "@/components/auth/LoginForm";
import MainAuthLandingPage from "@/components/auth/MainLandingPage";
import Image from "next/image";

export const metadata = {
    title: 'Login - Violyt',
    description: 'Access your brand intelligence workspace',
};

export default function LoginPage() {
  return (
    <MainAuthLandingPage>
      <div className="w-full max-w-[417px]">
        <div className="mb-8 flex flex-col gap-8">
          <Image src="/logo.svg" alt="Violyt Logo" width={54} height={54} priority />
          <div className="space-y-3 text-left">
            <h1 className="font-dmSans text-[42px] font-bold leading-none tracking-[-0.04em] text-black md:text-[48px]">
              Welcome to Violyt
            </h1>
            <p className="font-manrope text-[18px] font-medium leading-6 text-[#2D2D2D]">
              Access your brand intelligence workspace.
            </p>
          </div>
        </div>

        <LoginForm />
      </div>
    </MainAuthLandingPage>
  );
}
