"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { API } from "@/lib/api/endpoints";
import { getApiErrorMessage } from "@/lib/api/error-message";
import { request } from "@/lib/api/request";
import { setAuthTokens } from "@/lib/api/session";

export function ActivateForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activationToken = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleActivate = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!activationToken) {
      setError("Activation token is missing.");
      return;
    }
    if (!password || password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    try {
      setIsSubmitting(true);
      setError("");
      const tokens = await request(API.AUTH.ACTIVATE, {
        data: {
          token: activationToken,
          password,
        },
      });
      setAuthTokens(tokens.access_token, tokens.refresh_token);
      router.replace("/dashboard");
    } catch (activationError: unknown) {
      setError(getApiErrorMessage(activationError, "Activation failed."));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleActivate} className="w-full space-y-6">
      <div className="space-y-2">
        <label htmlFor="password" className="text-sm font-medium text-gray-700">
          Create Password
        </label>
        <div className="relative">
          <Input
            id="password"
            type={showPassword ? "text" : "password"}
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="bg-[#6B6B6B]/5 border-none focus-visible:ring-primary/50 rounded-none p-5"
          />
          <button
            type="button"
            onClick={() => setShowPassword((value) => !value)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500"
          >
            {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
          </button>
        </div>
      </div>

      <div className="space-y-2">
        <label
          htmlFor="confirm-password"
          className="text-sm font-medium text-gray-700"
        >
          Confirm Password
        </label>
        <div className="relative">
          <Input
            id="confirm-password"
            type={showConfirmPassword ? "text" : "password"}
            placeholder="Re-enter your password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="bg-[#6B6B6B]/5 border-none focus-visible:ring-primary/50 rounded-none p-5"
          />
          <button
            type="button"
            onClick={() => setShowConfirmPassword((value) => !value)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500"
          >
            {showConfirmPassword ? <EyeOff size={20} /> : <Eye size={20} />}
          </button>
        </div>
      </div>

      <Button
        type="submit"
        disabled={isSubmitting}
        className="w-full bg-[#3C2F8F] hover:bg-[#2A1F6F] text-white font-semibold p-5 rounded-none"
      >
        {isSubmitting ? "Activating..." : "Activate"}
      </Button>

      {error ? <p className="text-sm text-red-500">{error}</p> : null}

      <p className="text-base text-gray-500 text-start">
        Secure access to your brand intelligence environment.
      </p>
    </form>
  );
}
