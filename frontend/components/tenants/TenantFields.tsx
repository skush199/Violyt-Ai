"use client";

import { ChevronDown } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import type { TenantFormData } from "@/types/tenant.types";
import type { FormErrors } from "@/zod/tenantManagement";
import TenantLogoUpload from "./LogoUpload";

interface TenantFieldsProps {
    form: TenantFormData["tenant"];
    setForm: (tenant: TenantFormData["tenant"]) => void;
    errors: FormErrors["tenant"];
    clearError: (field: string) => void;
}

export default function TenantFields({ form, setForm, errors, clearError }: TenantFieldsProps) {
    return (
        <div className="grid gap-10 xl:grid-cols-[minmax(0,692px)_191px] xl:items-start">
            <div className="space-y-7">
                <div className="grid gap-6 xl:grid-cols-[454px_395px] xl:items-start">
                    <div className="space-y-6">
                        <Field
                            id="tenant-name"
                            label="Tenant Name"
                            value={form.name}
                            placeholder="Enter name"
                            error={errors?.name}
                            onChange={(value) => {
                                setForm({ ...form, name: value });
                                clearError("name");
                            }}
                        />

                        <Field
                            id="tenant-email"
                            label="Tenant Contact Email"
                            value={form.email}
                            placeholder="Enter email address"
                            error={errors?.email}
                            onChange={(value) => {
                                setForm({ ...form, email: value });
                                clearError("email");
                            }}
                        />

                        <Field
                            id="tenant-phone"
                            label="Tenant Contact Number"
                            value={form.phone}
                            placeholder="Enter contact number"
                            error={errors?.phone}
                            onChange={(value) => {
                                setForm({ ...form, phone: value });
                                clearError("phone");
                            }}
                        />
                    </div>

                    <div className="pt-0.5">
                        <TenantLogoUpload value={form.logo} onChange={(logo) => setForm({ ...form, logo })} />
                    </div>
                    <div className="space-y-5">
                        <h2 className="text-lg font-medium leading-[26px] text-[#2F3342]">Tenant Address</h2>

                        <Field
                            id="address-1"
                            label="Address 1"
                            value={form.address1}
                            placeholder="Enter address line 1"
                            error={errors?.address1}
                            onChange={(value) => {
                                setForm({ ...form, address1: value });
                                clearError("address1");
                            }}
                        />

                        <Field
                            id="address-2"
                            label="Address 2"
                            value={form.address2 || ""}
                            placeholder="Enter address line 2"
                            onChange={(value) => setForm({ ...form, address2: value })}
                        />

                        <div className="grid gap-6 sm:grid-cols-[217px_209px]">
                            <Field
                                id="city"
                                label="City"
                                value={form.city}
                                placeholder="Enter city"
                                error={errors?.city}
                                onChange={(value) => {
                                    setForm({ ...form, city: value });
                                    clearError("city");
                                }}
                            />
                            <Field
                                id="state"
                                label="State"
                                value={form.state}
                                placeholder="Enter state"
                                error={errors?.state}
                                trailingIcon
                                onChange={(value) => {
                                    setForm({ ...form, state: value });
                                    clearError("state");
                                }}
                            />
                        </div>

                        <div className="grid gap-6 sm:grid-cols-[217px_209px]">
                            <Field
                                id="zip"
                                label="ZIP"
                                value={form.zip}
                                placeholder="Enter ZIP code"
                                error={errors?.zip}
                                onChange={(value) => {
                                    setForm({ ...form, zip: value });
                                    clearError("zip");
                                }}
                            />
                            <Field
                                id="country"
                                label="Country"
                                value={form.country}
                                placeholder="Enter country"
                                error={errors?.country}
                                trailingIcon
                                onChange={(value) => {
                                    setForm({ ...form, country: value });
                                    clearError("country");
                                }}
                            />
                        </div>
                    </div>
                </div>

            </div>
        </div>
    );
}

function Field({
    id,
    label,
    value,
    placeholder,
    error,
    trailingIcon = false,
    onChange,
}: {
    id: string;
    label: string;
    value: string;
    placeholder: string;
    error?: string;
    trailingIcon?: boolean;
    onChange: (value: string) => void;
}) {
    return (
        <div className="space-y-2.5">
            <Label htmlFor={id} className="text-base font-medium leading-6 text-[#2F3342]">
                {label}
            </Label>
            <div className="relative">
                <Input
                    id={id}
                    value={value}
                    placeholder={placeholder}
                    className="h-12 rounded-[10px] border-none bg-input-field px-4 text-sm text-[#2F3342] placeholder:text-[#A7A7A7] focus-visible:ring-2 focus-visible:ring-primary/20"
                    onChange={(event) => onChange(event.target.value)}
                />
                {trailingIcon ? <ChevronDown className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" /> : null}
            </div>
            {error ? <p className="text-sm text-red-500">{error}</p> : null}
        </div>
    );
}
