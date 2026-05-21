"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { StyledInput } from "@/components/brandSpaces/tabs/FormFields";
import { PlatformPageTitle, SectionCard } from "@/components/platformOwner/PlatformOwnerPrimitives";
import Setup2faForm from "@/components/auth/Setup2faForm";
import { useLogout } from "@/hooks/useLogout";
import { useProfile, useTwoFactorStatus, useUpdateProfile } from "@/hooks/useAuthProfile";
import { useRBAC } from "@/hooks/useRBAC";
import { DialogTitle } from "@radix-ui/react-dialog";
import { Label } from "../ui/label";

export default function OwnerProfile() {
  const { user } = useRBAC();
  const logout = useLogout();
  const { data: profile } = useProfile();
  const { data: twoFactorStatus } = useTwoFactorStatus();
  const updateProfile = useUpdateProfile();
  const [notificationsOverride, setNotificationsOverride] = useState<boolean | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [twoFactorOpen, setTwoFactorOpen] = useState(false);
  const [form, setForm] = useState({ fullName: "", email: "", phoneNumber: "" });

  const account = useMemo(
    () => ({
      fullName: profile?.full_name || user?.name || "-",
      email: profile?.email || user?.email || "-",
      phoneNumber:
        (typeof profile?.extra?.phone_number === "string" ? profile.extra.phone_number : undefined) ||
        user?.phone ||
        "-",
    }),
    [profile?.email, profile?.extra, profile?.full_name, user?.email, user?.name, user?.phone],
  );

  const notifications = notificationsOverride ?? (profile?.extra?.notifications_enabled === false ? false : true);

  return (
    <>
      <div className="w-full px-5 py-5">
        <div className="mx-auto max-w-[1110px] space-y-5">
          <PlatformPageTitle title="Profile" />

          <div className="grid gap-4 lg:grid-cols-[1fr_50%]">
            <SectionCard title="Account Details">
            <ProfileRow label="Full Name" value={account.fullName} onEdit={() => {
              setForm(account);
              setEditOpen(true);
            }} />
            <ProfileRow label="Email Address" value={account.email} onEdit={() => {
              setForm(account);
              setEditOpen(true);
            }} />
            <ProfileRow label="Contact Number" value={account.phoneNumber} onEdit={() => {
              setForm(account);
              setEditOpen(true);
            }} />
            </SectionCard>

            <SectionCard title="Two Factor Authentication" className="space-y-4">
            <p className="text-sm text-[#6B7280]">
              {twoFactorStatus?.enabled
                ? "Google Authenticator is currently enabled for this account."
                : "Manage two-factor authentication using Google Authenticator"}
            </p>
            <Button
              className="rounded-none bg-primary/72 p-6 text-base hover:bg-primary/90"
              onClick={() => setTwoFactorOpen(true)}
            >
              {twoFactorStatus?.enabled ? "Manage 2FA Security" : "2FA Security"}
            </Button>
            </SectionCard>
          </div>

          <SettingRow
            title="Notifications"
            description="Enable or disable alerts and updates"
            trailing={
              <Switch
                checked={notifications}
                onCheckedChange={(checked) => {
                  setNotificationsOverride(checked);
                  updateProfile.mutate({ notifications_enabled: checked });
                }}
              />
            }
          />

          <SettingRow
            title="Privacy Policy"
            description="Review how your personal information is collected, used, and protected on the platform. View Privacy & Policy."
          />

          <SettingRow
            title="Sign out of your account"
            trailing={
              <Button className="rounded-none bg-primary/72 p-6 text-base hover:bg-primary/90" onClick={() => logout.mutate()}>
                Logout
              </Button>
            }
          />
        </div>
      </div>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-lg rounded-2xl border-0 px-8 py-8 shadow-[0_20px_80px_-24px_rgba(15,23,42,0.25)]">
            <DialogTitle className="text-2xl font-semibold text-[#111827]">Edit Profile</DialogTitle>
          <div className="space-y-4">
            {/* <h2 className="text-3xl font-semibold text-[#111827]"></h2> */}
            <Label className="text-gray-500">Full name</Label>
            <StyledInput placeholder="Full name" value={form.fullName} onChange={(event) => setForm((current) => ({ ...current, fullName: event.target.value }))} />
            {/* <StyledInput value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} /> */}
            <Label className="text-gray-500">Phone number</Label>
            <StyledInput placeholder="Phone number" value={form.phoneNumber} onChange={(event) => setForm((current) => ({ ...current, phoneNumber: event.target.value }))} />
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" className="rounded-none px-5 py-4" onClick={() => setEditOpen(false)}>
                Cancel
              </Button>
              <Button
                className="rounded-none bg-primary/72 px-5 py-4 hover:bg-primary/90"
                onClick={() =>
                  updateProfile.mutate(
                    {
                      full_name: form.fullName,
                      email: form.email,
                      phone_number: form.phoneNumber,
                    },
                    {
                      onSuccess: () => setEditOpen(false),
                    },
                  )
                }
              >
                Save
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={twoFactorOpen} onOpenChange={setTwoFactorOpen}>
        <DialogContent className="max-w-[540px] rounded-none border-0 p-0 shadow-[0_24px_80px_-28px_rgba(15,23,42,0.4)]">
          <div className="bg-white px-10 py-12">
            <div className="mx-auto max-w-[320px] space-y-5">
              <h2 className="text-center text-[38px] font-extrabold leading-none text-[#111827]">Two-Factor Authentication</h2>
              <p className="text-center text-sm text-[#52525B]">
                {twoFactorStatus?.enabled
                  ? "Manage your Google Authenticator protection for this account."
                  : "Secure your account with Google Authenticator."}
              </p>
              <Setup2faForm compact onConfigured={() => undefined} />
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ProfileRow({
  label,
  value,
  onEdit,
}: {
  label: string;
  value: string;
  onEdit: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-[#F1F2F6] pb-4 last:border-none last:pb-0">
      <div>
        <p className="text-sm font-medium text-[#6B7280]">{label}</p>
        <p className="mt-2 text-[#2F3342]">{value}</p>
      </div>
      {
        label !== "Email Address" ? (
          <button type="button" onClick={onEdit} className="text-primary">
            <Pencil className="h-5 w-5" />
          </button>
        ) : null
      }
      {/* <button type="button" onClick={onEdit} className="text-primary">
        <Pencil className="h-5 w-5" />
      </button> */}
    </div>
  );
}

function SettingRow({
  title,
  description,
  trailing,
}: {
  title: string;
  description?: string;
  trailing?: ReactNode;
}) {
  return (
    <SectionCard title={title} description={description} className="flex items-center justify-between gap-4 px-4 py-4">
      {/* <div>
        {description ? <p className="mt-1 text-sm text-[#6B7280]">{description}</p> : null}
      </div> */}
      {trailing}
    </SectionCard>
  );
}
