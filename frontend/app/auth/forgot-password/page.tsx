import MainAuthLandingPage from "@/components/auth/MainLandingPage";
import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";

export const metadata = {
  title: "Forgot Password - Violyt",
  description: "Get help regaining access to Violyt",
};

export default function ForgotPasswordPage() {
  return (
    <MainAuthLandingPage>
      <ForgotPasswordForm />
    </MainAuthLandingPage>
  );
}
