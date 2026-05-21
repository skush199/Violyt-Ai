"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { PencilLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StyledInput } from "@/components/brandSpaces/tabs/FormFields";
import { PlatformPageTitle, SectionCard } from "@/components/platformOwner/PlatformOwnerPrimitives";
import { useLogout } from "@/hooks/useLogout";
import { useRBAC } from "@/hooks/useRBAC";
import { useGetTenantUsageSummary } from "@/hooks/tenantAdmins/useGetTenants";
import { useChangePassword, useDeleteProfile, useProfile, useUpdateProfile } from "@/hooks/useAuthProfile";
import type { TenantUsageSummary } from "@/lib/api/contracts";
import { clearAuthTokens } from "@/lib/api/session";
import Image from "next/image";
import { Progress } from "../ui/progress";

type EditableField = "full_name" | "email" | "phone_number" | null;

export default function TenantAdminProfile() {
  const router = useRouter();
  const { user } = useRBAC();
  const logout = useLogout();
  const { data: profile } = useProfile();
  const updateProfile = useUpdateProfile();
  const changePassword = useChangePassword();
  const deleteProfile = useDeleteProfile();
  const usageTenantId = user?.tenantId ?? "";
  const { data: usageSummary } = useGetTenantUsageSummary(usageTenantId);
  const [notificationsOverride, setNotificationsOverride] = useState<boolean | null>(null);
  const [editingField, setEditingField] = useState<EditableField>(null);
  const [editValue, setEditValue] = useState("");
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: "",
    newPassword: "",
    confirmPassword: "",
  });
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const notifications = notificationsOverride ?? (profile?.extra?.notifications_enabled === false ? false : true);

  const account = useMemo(
    () => ({
      fullName: profile?.full_name || user?.name || "",
      email: profile?.email || user?.email || "",
      contactNumber:
        (typeof profile?.extra?.phone_number === "string" ? profile.extra.phone_number : undefined) ||
        user?.phone ||
        "+91 49652845732",
    }),
    [profile?.email, profile?.extra, profile?.full_name, user?.email, user?.name, user?.phone],
  );

  const openFieldDialog = (field: Exclude<EditableField, null>) => {
    setEditingField(field);
    setError(null);
    setFeedback(null);
    setEditValue(
      field === "full_name" ? account.fullName : field === "email" ? account.email : account.contactNumber,
    );
  };

  const handleSaveField = () => {
    if (!editingField) {
      return;
    }
    updateProfile.mutate(
      {
        full_name: editingField === "full_name" ? editValue : undefined,
        email: editingField === "email" ? editValue : undefined,
        phone_number: editingField === "phone_number" ? editValue : undefined,
      },
      {
        onSuccess: () => {
          setFeedback("Profile updated successfully.");
          setEditingField(null);
        },
        onError: () => {
          setError("Unable to save profile changes right now.");
        },
      },
    );
  };

  const handleNotificationToggle = (checked: boolean) => {
    setNotificationsOverride(checked);
    updateProfile.mutate(
      { notifications_enabled: checked },
      {
        onSuccess: () => setFeedback("Notification preference updated."),
        onError: () => {
          setNotificationsOverride(null);
          setError("Unable to update notification preference right now.");
        },
      },
    );
  };

  const handlePasswordSave = () => {
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setError("New password and confirm password must match.");
      return;
    }
    changePassword.mutate(
      {
        current_password: passwordForm.currentPassword,
        new_password: passwordForm.newPassword,
      },
      {
        onSuccess: () => {
          setFeedback("Password updated successfully.");
          setError(null);
          setPasswordDialogOpen(false);
          setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
        },
        onError: () => {
          setError("Unable to update password. Please check the current password and try again.");
        },
      },
    );
  };

  const handleDeleteAccount = () => {
    deleteProfile.mutate(undefined, {
      onSuccess: () => {
        clearAuthTokens();
        router.replace("/auth/login");
      },
      onError: () => setError("Unable to delete the account right now."),
    });
  };

  return (
    <>
      <div className="w-full px-8 py-10">
        <div className="mx-auto max-w-[1110px] space-y-4">
          <PlatformPageTitle title="Profile" />

          {feedback ? <p className="text-sm text-emerald-600">{feedback}</p> : null}
          {error ? <p className="text-sm text-red-500">{error}</p> : null}

          <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
            <SectionCard title="Account Details">
            <ProfileDetailRow label="Full Name" value={account.fullName} onEdit={() => openFieldDialog("full_name")} />
            <ProfileDetailRow label="Email Address" value={account.email} onEdit={() => openFieldDialog("email")} />
            <ProfileDetailRow
              label="Contact Number"
              value={account.contactNumber}
              onEdit={() => openFieldDialog("phone_number")}
            />
            </SectionCard>

            <SectionCard title="Usage Detail">
            {usageSummary ? (
              <div className="space-y-4">
                <MetricRow label="Total Capacity" value={aggregatePercent(usageSummary)} />
                <MetricRow
                  label="Content"
                  value={toPercent(
                    usageSummary?.consumption.content_generations,
                    usageSummary?.limits.max_content_generations,
                  )}
                />
                <MetricRow
                  label="Visuals"
                  value={toPercent(
                    usageSummary?.consumption.image_generations,
                    usageSummary?.limits.max_image_generations,
                  )}
                />
                <MetricRow
                  label="OCR"
                  value={toPercent(usageSummary?.consumption.ocr_pages, usageSummary?.limits.max_ocr_pages)}
                />
                <MetricRow label="Users" value={toPercent(usageSummary?.consumption.users, usageSummary?.limits.max_users)} />
                <MetricRow
                  label="Brand Spaces"
                  value={toPercent(usageSummary?.consumption.brand_spaces, usageSummary?.limits.max_brand_spaces)}
                />
              </div>
            ) : (
              <p className="text-sm text-slate-500">
                Usage details will appear here once your tenant workspace has active limits and consumption data.
              </p>
            )}
            </SectionCard>
          </div>

          <SettingsRow
            title="Notifications"
            description="Enable or disable alerts and updates"
            trailing={<Switch checked={notifications} onCheckedChange={handleNotificationToggle} />}
          />

          <SettingsRow
            title="Privacy Policy"
            description="Review how your personal information is collected, used, and protected on the platform. View Privacy & Policy."
          />

          <SettingsRow
            title="Disclaimer"
            description="Read the terms outlining platform limitations, responsibilities, and usage conditions. View Disclaimer."
          />

          <SettingsRow
            title="Change password"
            description="Update your account password to keep your account secure."
            trailing={
              <Button variant={"ghost"} type="button" className="text-primary" onClick={() => setPasswordDialogOpen(true)}>
                <Image src="/actions_icons/pencil.svg" alt="edit icon" width={16} height={16} className="font-semibold" />
              </Button>
            }
          />

          <SettingsRow
            title="Sign out of your account"
            trailing={
              <Button
                className="rounded-none bg-primary/72 p-6 text-base hover:bg-primary/90"
                onClick={() => logout.mutate()}
              >
                Logout
              </Button>
            }
          />

          <SettingsRow
            title="Delete your account"
            description="Permanently delete your account and associated data from the platform. This action cannot be undone."
            trailing={
              <Button
                variant="outline"
                className="rounded-none border-red-200 p-6 text-base text-[#FF6D5E] hover:bg-red-50 hover:text-[#FF6D5E]"
                onClick={() => setDeleteDialogOpen(true)}
              >
                Delete account
              </Button>
            }
          />
        </div>
      </div>

      <Dialog open={editingField !== null} onOpenChange={(open) => (!open ? setEditingField(null) : null)}>
        <DialogContent className="max-w-lg rounded-2xl border-0 p-8 shadow-[0_20px_80px_-24px_rgba(15,23,42,0.25)]">
          <DialogHeader>
            <DialogTitle className="text-3xl text-slate-900">Update Profile Detail</DialogTitle>
            <DialogDescription className="text-sm text-slate-500">
              Save the updated account information shown in the profile screen.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <StyledInput value={editValue} onChange={(event) => setEditValue(event.target.value)} />
          </div>
          <DialogFooter className="flex-row justify-end gap-3">
            <Button variant="outline" className="rounded-none px-5 py-4" onClick={() => setEditingField(null)}>
              Cancel
            </Button>
            <Button className="rounded-none bg-primary px-5 py-4 hover:bg-primary/90" onClick={handleSaveField}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={passwordDialogOpen} onOpenChange={setPasswordDialogOpen}>
        <DialogContent className="max-w-xl rounded-2xl border-0 p-8 shadow-[0_20px_80px_-24px_rgba(15,23,42,0.25)]">
          <DialogHeader>
            <DialogTitle className="text-3xl text-slate-900">Change Password</DialogTitle>
            <DialogDescription className="text-sm text-slate-500">
              Update your password to keep your account secure.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <StyledInput
              type="password"
              placeholder="Current password"
              value={passwordForm.currentPassword}
              onChange={(event) => setPasswordForm((current) => ({ ...current, currentPassword: event.target.value }))}
            />
            <StyledInput
              type="password"
              placeholder="New password"
              value={passwordForm.newPassword}
              onChange={(event) => setPasswordForm((current) => ({ ...current, newPassword: event.target.value }))}
            />
            <StyledInput
              type="password"
              placeholder="Confirm new password"
              value={passwordForm.confirmPassword}
              onChange={(event) => setPasswordForm((current) => ({ ...current, confirmPassword: event.target.value }))}
            />
          </div>
          <DialogFooter className="flex-row justify-end gap-3">
            <Button variant="outline" className="rounded-none px-5 py-4" onClick={() => setPasswordDialogOpen(false)}>
              Cancel
            </Button>
            <Button className="rounded-none bg-primary px-5 py-4 hover:bg-primary/90" onClick={handlePasswordSave}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent className="max-w-[460px] rounded-2xl border-0 px-8 py-10 shadow-[0_20px_80px_-24px_rgba(15,23,42,0.25)]">
          <AlertDialogHeader className="items-center text-center">
            <AlertDialogTitle className="text-5xl font-semibold tracking-tight text-slate-900">Delete Account?</AlertDialogTitle>
            <AlertDialogDescription className="text-xl text-slate-700">
              This action will deactivate your account and sign you out immediately.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="mt-4 flex-row justify-center gap-6">
            <AlertDialogAction className="h-12 min-w-[152px] rounded-none bg-[#FF6D5E] text-base hover:bg-[#FF6D5E]/90" onClick={handleDeleteAccount}>
              Confirm
            </AlertDialogAction>
            <AlertDialogCancel className="h-12 min-w-[152px] rounded-none border-slate-900 text-base text-slate-900 hover:bg-slate-50">
              Cancel
            </AlertDialogCancel>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function aggregatePercent(usageSummary?: TenantUsageSummary) {
  if (!usageSummary?.limits || !usageSummary.consumption) {
    return 0;
  }
  const pairs: Array<[number | undefined, number | undefined]> = [
    [usageSummary.consumption.content_generations, usageSummary.limits.max_content_generations],
    [usageSummary.consumption.image_generations, usageSummary.limits.max_image_generations],
    [usageSummary.consumption.ocr_pages, usageSummary.limits.max_ocr_pages],
    [usageSummary.consumption.users, usageSummary.limits.max_users],
    [usageSummary.consumption.brand_spaces, usageSummary.limits.max_brand_spaces],
  ];
  const percentages = pairs.map(([value, max]) => toPercent(value, max));
  return Math.round(percentages.reduce((sum, current) => sum + current, 0) / percentages.length);
}

function toPercent(value?: number, max?: number) {
  if (!max || max <= 0) {
    return 0;
  }
  return Math.min(100, Math.round(((value || 0) / max) * 100));
}

function ProfileDetailRow({ label, value, onEdit }: { label: string; value: string; onEdit: () => void }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 pb-4 last:border-none last:pb-0">
      <div className="space-y-1">
        <p className="text-sm font-medium text-slate-500">{label}</p>
        <p className="text-base font-medium text-slate-800">{value}</p>
      </div>
      <Button type="button" variant={"ghost"} onClick={onEdit}>
        <Image src="/actions_icons/pencil.svg" alt="edit icon" width={16} height={16}
            className="font-semibold"
        />
      </Button>
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>{label}</span>
        <span>{value}%</span>
      </div>
      <Progress indicatorClassName="bg-[#9E9E9E]" value={value} className="h-3 rounded-none" />
      {/* <div className="h-2 rounded-full bg-slate-200">
        <div className="h-2 rounded-full bg-primary" style={{ width: `${value}%` }} />
      </div> */}
    </div>
  );
}

function SettingsRow({
  title,
  description,
  trailing,
}: {
  title: string;
  description?: string;
  trailing?: ReactNode;
}) {
  return (
    <SectionCard title={title} description={description} className="flex items-center justify-between gap-4 px-5 py-4">
      {/* <div>
        {description ? <p className="mt-1 text-sm text-slate-500">{description}</p> : null}
      </div> */}
      {trailing}
    </SectionCard>
  );
}
