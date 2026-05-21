import MainAuthLandingPage from "@/components/auth/MainLandingPage";
import Verify2faForm from "@/components/auth/Verify2faForm";
import Image from "next/image";

export const metadata = {
    title: 'Login - Violyt',
    description: 'Access your brand intelligence workspace',
};

export default function Verify2FA() {
    return (
        <MainAuthLandingPage>
            <div className="w-full max-w-md">
                <div className="text-start mb-8">
                    <Image src={"/logo.svg"} alt="Violyt Logo" width={56} height={56} />
                    <h1 className="font-dmSans text-5xl font-extrabold text-gray-900 my-4 tracking-tight">Two-Factor Authentication</h1>
                    <p className="text-gray-600 font-semibold">Enter the 6 digit code sent to Google Authenticator</p>
                </div>
                <Verify2faForm />
            </div>
        </MainAuthLandingPage>
    );
}
