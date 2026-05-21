"use client";

import { useMemo, useState } from "react";
import { Copy, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useDisableTwoFactor,
  useEnableTwoFactor,
  useSetupTwoFactor,
  useTwoFactorStatus,
} from "@/hooks/useAuthProfile";

type Setup2faFormProps = {
  compact?: boolean;
  onConfigured?: () => void;
};

export default function Setup2faForm({ compact = false, onConfigured }: Setup2faFormProps) {
  const { data: status } = useTwoFactorStatus();
  const setupTwoFactor = useSetupTwoFactor();
  const enableTwoFactor = useEnableTwoFactor();
  const disableTwoFactor = useDisableTwoFactor();
  const [code, setCode] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [copied, setCopied] = useState(false);
  const setupData = useMemo(
    () => (setupTwoFactor.data?.secret ? setupTwoFactor.data : null),
    [setupTwoFactor.data],
  );

  const handleCopySecret = async () => {
    if (!setupData?.secret) {
      return;
    }
    await navigator.clipboard.writeText(setupData.secret);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const handleEnable = () => {
    if (!code.trim()) {
      return;
    }
    enableTwoFactor.mutate(
      { code: code.trim() },
      {
        onSuccess: () => {
          setCode("");
          onConfigured?.();
        },
      },
    );
  };

  const handleDisable = () => {
    if (!disableCode.trim()) {
      return;
    }
    disableTwoFactor.mutate(
      { code: disableCode.trim() },
      {
        onSuccess: () => {
          setDisableCode("");
          setupTwoFactor.reset();
          onConfigured?.();
        },
      },
    );
  };

  if (status?.enabled) {
    return (
      <div className="space-y-5">
        <div className="rounded-2xl bg-[#F6F7FC] p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-white">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <p className="text-base font-semibold text-slate-900">Authenticator protection is enabled</p>
              <p className="text-sm text-slate-500">Enter a fresh code from Google Authenticator if you want to disable 2FA.</p>
            </div>
          </div>
        </div>
        <Input
          value={disableCode}
          onChange={(event) => setDisableCode(event.target.value)}
          placeholder="Enter 6 digit code"
          className="h-12 rounded-none border-none bg-[#6B6B6B]/5 px-4"
        />
        <Button
          onClick={handleDisable}
          disabled={disableTwoFactor.isPending || disableCode.trim().length !== 6}
          className="w-full rounded-none bg-[#5A4BB0] py-5 text-base font-semibold hover:bg-[#4A3C98]"
        >
          {disableTwoFactor.isPending ? "Disabling..." : "Disable Authenticator"}
        </Button>
      </div>
    );
  }

  if (!setupData) {
    return (
      <div className="space-y-5">
        <p className="text-sm leading-6 text-slate-500">
          Set up Google Authenticator to add an extra verification step whenever you access the workspace.
        </p>
        <Button
          onClick={() => setupTwoFactor.mutate()}
          disabled={setupTwoFactor.isPending}
          className="w-full rounded-none bg-[#5A4BB0] py-5 text-base font-semibold hover:bg-[#4A3C98]"
        >
          {setupTwoFactor.isPending ? "Preparing..." : "Setup Authenticator"}
        </Button>
        {status?.pending_setup ? (
          <p className="text-xs text-slate-500">
            A previous setup session exists. Starting setup again will regenerate the secret.
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className={`${compact ? "space-y-4" : "space-y-5"}`}>
        <div className="flex justify-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={setupData.qr_code_url || ""}
            alt="Two-factor QR code"
            className="h-40 w-40 rounded-xl border border-slate-200 bg-white p-2"
          />
        </div>
        <p className="text-center text-sm text-slate-500">
          Scan the QR code using Google Authenticator, or enter the secret key manually.
        </p>
        <div className="rounded-xl bg-[#F6F7FC] p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Setup Key</p>
          <div className="mt-2 flex items-center justify-between gap-3">
            <p className="break-all text-sm font-semibold tracking-[0.2em] text-slate-900">{setupData.secret}</p>
            <Button type="button" variant="outline" className="rounded-none" onClick={handleCopySecret}>
              <Copy className="mr-2 h-4 w-4" />
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        </div>
      </div>
      <Input
        value={code}
        onChange={(event) => setCode(event.target.value)}
        placeholder="Enter 6 digit code"
        className="h-12 rounded-none border-none bg-[#6B6B6B]/5 px-4"
      />
      <Button
        onClick={handleEnable}
        disabled={enableTwoFactor.isPending || code.trim().length !== 6}
        className="w-full rounded-none bg-[#5A4BB0] py-5 text-base font-semibold hover:bg-[#4A3C98]"
      >
        {enableTwoFactor.isPending ? "Verifying..." : "Verify & Enable 2FA"}
      </Button>
    </div>
  );
}
