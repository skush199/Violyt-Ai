export const metadata = {
  title: "Login - Violyt",
  description: "Access your brand intelligence workspace",
};

export default function MainAuthLandingPage({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-white md:grid md:grid-cols-2">
      <div className="relative hidden min-h-screen overflow-hidden md:flex md:flex-col md:justify-between">
        <div className="absolute inset-0 bg-[linear-gradient(123deg,#8266BA_0%,#624CA6_38%,#3C2F8F_83%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_90%,rgba(255,255,255,0.18),transparent_34%)]" />

        <div className="relative px-8 py-10 lg:px-[34px] lg:py-[40px]">
          <p className="font-dmSans text-[32px] font-bold tracking-[-0.02em] text-white">Violyt</p>
        </div>

        <div className="relative px-8 pb-14 lg:px-[34px] lg:pb-[94px]">
          <h1 className="max-w-[476px] font-dmSans text-[52px] font-semibold leading-[0.96] tracking-[-0.05em] text-white lg:text-[66px]">
            Scale Without
            <br />
            Brand Dilution.
          </h1>
          <p className="mt-5 font-manrope text-[18px] font-semibold text-white lg:text-[20px]">
            Intelligence That Protects Your Brand.
          </p>
        </div>
      </div>

      <div className="flex min-h-screen items-center justify-center px-6 py-12 md:px-16 lg:px-[145px]">
        {children}
      </div>
    </div>
  );
}
