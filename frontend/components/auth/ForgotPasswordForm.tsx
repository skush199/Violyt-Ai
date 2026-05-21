"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { API } from "@/lib/api/endpoints";
import { getApiErrorMessage } from "@/lib/api/error-message";
import { request } from "@/lib/api/request";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!email.trim()) {
      setError("Work email is required.");
      return;
    }

    try {
      setIsSubmitting(true);
      setError("");
      const response = await request(API.AUTH.FORGOT_PASSWORD, {
        data: { email },
      });
      setMessage(response.message || "If the email exists, a reset link has been sent.");
    } catch (forgotPasswordError) {
      setError(getApiErrorMessage(forgotPasswordError, "Unable to request a reset link."));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-[417px] space-y-6">
      <div className="space-y-3 text-left">
        <h1 className="font-dmSans text-[42px] font-bold leading-none tracking-[-0.04em] text-black md:text-[48px]">
          Reset your password
        </h1>
        <p className="font-manrope text-[18px] font-medium leading-6 text-[#2D2D2D]">
          Enter your work email and we&apos;ll send you an activation link to set a new password.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5 rounded-[2px] border border-[#ECEEF5] bg-white p-6 shadow-[0_10px_24px_-22px_rgba(15,23,42,0.45)]">
        <div className="space-y-2">
          <label htmlFor="forgot-email" className="text-base font-normal leading-6 text-[#121212]">
            Work Email
          </label>
          <Input
            id="forgot-email"
            type="email"
            placeholder="Enter your work email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            disabled={isSubmitting}
            className="h-12 rounded-none border-none bg-[#F5F7FA] px-4 text-sm text-[#121212] placeholder:text-[#8C8C8C] focus-visible:ring-2 focus-visible:ring-primary/20"
          />
        </div>

        {message ? (
          <div className="rounded-[2px] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {message}
          </div>
        ) : null}
        {error ? (
          <div className="rounded-[2px] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <Button
          type="submit"
          disabled={isSubmitting}
          className="h-12 w-full rounded-none bg-primary text-base font-bold text-white hover:bg-primary/90"
        >
          {isSubmitting ? "Sending..." : "Send Reset Link"}
        </Button>

        <Button asChild variant="outline" className="h-12 w-full rounded-none border-[#D7DBEA] bg-white text-base font-semibold text-[#2D2D2D] hover:bg-[#F7F7FB]">
          <Link href="/auth/login">Back to login</Link>
        </Button>
      </form>
    </div>
  );
}
