"use client";

import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { FormField, StyledInput } from "@/components/brandSpaces/tabs/FormFields";
import { PlatformPageTitle, SectionCard } from "@/components/platformOwner/PlatformOwnerPrimitives";
import { resolveBrandLogoUrl } from "@/lib/brand-assets";
import { useBrands } from "@/hooks/useBrands";
import { useTenantUserDetail } from "@/hooks/useTeamAccess";

type AssignedBrand = {
  id: string;
  name: string;
  logo: string | null;
};

export default function UserOverview({ userId }: { userId: string }) {
  const { data: liveUser, isLoading } = useTenantUserDetail(userId);
  const { data: brands } = useBrands();

  const user = liveUser
    ? {
        fullName: liveUser.full_name,
        email: liveUser.email,
        contactNumber: liveUser.phone_number || "",
        role: liveUser.role_codes.includes("tenant_user") ? "Tenant User" : "Brand User",
        brandAssignments: liveUser.brand_space_ids.map((brandId) => {
          const brand = (brands || []).find((item) => item.id === brandId);
          return {
            id: brandId,
            name: brand?.name || brandId,
            logo: brand ? resolveBrandLogoUrl(brand) : null,
          };
        }) satisfies AssignedBrand[],
      }
    : null;

  if (!user && isLoading) {
    return <div className="w-full px-6 py-10 text-sm text-slate-500">Loading user details...</div>;
  }

  if (!user) {
    return <div className="w-full px-6 py-10 text-sm text-slate-500">User not found.</div>;
  }

  const isBrandUser = user.role === "Brand User";

  return (
    <div className="w-full px-6 py-5">
      <div className="mx-auto max-w-[1110px] space-y-6">
        <PlatformPageTitle
          title={`${user.fullName || (isBrandUser ? "{Brand user name}" : "{Tenant User name}")} Overview`}
          action={
          <Button asChild className="rounded-none bg-primary px-6 py-4 text-base hover:bg-primary/90">
            <Link href={`/user_management/${userId}?edit=true`}>Edit</Link>
          </Button>
        }
        />

        <SectionCard title="User Details">
          <div className="max-w-[458px] space-y-5">
            <FormField label="Full Name" required>
              <StyledInput value={user.fullName} readOnly />
            </FormField>

            <FormField label="Email Address" required>
              <StyledInput value={user.email} readOnly />
            </FormField>

            <FormField label="Contact Number" required>
              <StyledInput value={user.contactNumber} readOnly />
            </FormField>

            <FormField label="User Role" required>
              <StyledInput value={user.role} readOnly />
            </FormField>
          </div>
        </SectionCard>

        {isBrandUser ? (
          <SectionCard title="Brand Spaces Assigned">
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {user.brandAssignments.map((brand) => (
                <div key={brand.id} className="flex min-h-[104px] flex-col items-center justify-center gap-3 rounded-[2px] border border-[#ECEEF5] bg-[#FAFBFF] p-4">
                  {brand.logo ? (
                    <div className="relative h-10 w-20">
                      <Image src={brand.logo} alt={brand.name} fill sizes="80px" className="object-contain" />
                    </div>
                  ) : (
                    <span className="text-sm font-semibold text-slate-700">{brand.name}</span>
                  )}
                  <span className="text-sm text-[#6B7280]">{brand.name}</span>
                </div>
              ))}
            </div>
          </SectionCard>
        ) : null}
      </div>
    </div>
  );
}
