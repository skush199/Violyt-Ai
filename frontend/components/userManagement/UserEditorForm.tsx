"use client";

import { isAxiosError } from "axios";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { FormField, StyledInput } from "@/components/brandSpaces/tabs/FormFields";
import { PlatformPageTitle, SectionCard } from "@/components/platformOwner/PlatformOwnerPrimitives";
import { useBrands } from "@/hooks/useBrands";
import { useSaveTenantUser, useTenantUserDetail } from "@/hooks/useTeamAccess";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "../ui/select";

type UserEditorFormProps = {
    mode: "create" | "edit";
    userId?: string;
};

type UserEditorState = {
    fullName: string;
    email: string;
    contactNumber: string;
    roleCode: "tenant_user" | "brand_user";
    selectedBrands: string[];
};

type FormErrorState = {
    fullName?: string;
    email?: string;
    contactNumber?: string;
    selectedBrands?: string;
};

type SubmissionFeedback = {
    title: string;
    description: string;
};

function getMutationErrorMessage(error: unknown, mode: UserEditorFormProps["mode"]) {
    if (isAxiosError(error)) {
        const detail = error.response?.data?.detail;
        if (typeof detail === "string" && detail.trim()) {
            return detail;
        }
    }
    return mode === "create"
        ? "We could not create the user right now."
        : "We could not save the changes right now.";
}

export default function UserEditorForm({ mode, userId }: UserEditorFormProps) {
    const router = useRouter();
    const { data: brands } = useBrands();
    const { data: liveUser, isLoading } = useTenantUserDetail(userId || "");
    const saveUser = useSaveTenantUser(userId);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [errors, setErrors] = useState<FormErrorState>({});
    const [submissionFeedback, setSubmissionFeedback] = useState<SubmissionFeedback | null>(null);

    const [form, setForm] = useState<UserEditorState | null>(null);
    const initialForm = useMemo<UserEditorState>(() => {
        if (liveUser) {
            return {
                fullName: liveUser.full_name,
                email: liveUser.email,
                contactNumber: liveUser.phone_number || "",
                roleCode: liveUser.role_codes.includes("tenant_user") ? "tenant_user" : "brand_user",
                selectedBrands: liveUser.brand_space_ids,
            };
        }
        return {
            fullName: "",
            email: "",
            contactNumber: "",
            roleCode: "brand_user",
            selectedBrands: [],
        };
    }, [liveUser]);
    const resolvedForm = form ?? initialForm;

    const availableBrands = useMemo(
        () =>
            (brands || []).filter((brand) => brand.lifecycle_state !== "deleted").map((brand) => ({
                id: brand.id,
                name: brand.name,
            })),
        [brands],
    );

    const roleLabel = resolvedForm.roleCode === "tenant_user" ? "Tenant User" : "Brand User";
    const title =
        mode === "create"
            ? "Create User"
            : `Edit ${resolvedForm.fullName || (resolvedForm.roleCode === "tenant_user" ? "{Tenant User name}" : "{Brand user name}")}`;

    const showBrandAssignment = resolvedForm.roleCode === "brand_user";

    const updateForm = (patch: Partial<UserEditorState>) => {
        setForm((current) => ({ ...(current ?? resolvedForm), ...patch }));
    };

    const toggleBrand = (brandId: string) => {
        setErrors((current) => ({ ...current, selectedBrands: undefined }));
        updateForm({
            selectedBrands: resolvedForm.selectedBrands.includes(brandId)
                ? resolvedForm.selectedBrands.filter((item) => item !== brandId)
                : [...resolvedForm.selectedBrands, brandId],
        });
    };

    const validate = () => {
        const nextErrors: FormErrorState = {};
        if (!resolvedForm.fullName.trim()) {
            nextErrors.fullName = "Full name is required.";
        }
        if (!resolvedForm.email.trim()) {
            nextErrors.email = "Email address is required.";
        }
        if (!resolvedForm.contactNumber.trim()) {
            nextErrors.contactNumber = "Contact number is required.";
        }
        if (showBrandAssignment && resolvedForm.selectedBrands.length === 0) {
            nextErrors.selectedBrands = "Assign at least one brand space for a brand user.";
        }
        setErrors(nextErrors);
        return Object.keys(nextErrors).length === 0;
    };

    const submit = () => {
        setSubmissionFeedback(null);
        saveUser.mutate(
            {
                full_name: resolvedForm.fullName,
                email: resolvedForm.email,
                phone_number: resolvedForm.contactNumber,
                role_code: resolvedForm.roleCode,
                brand_space_ids: showBrandAssignment ? resolvedForm.selectedBrands : [],
            },
            {
                onSuccess: (savedUser) => {
                    setConfirmOpen(false);
                    if (mode === "create") {
                        const params = new URLSearchParams({
                            created: "1",
                            email: savedUser.activation_email?.recipient_email || savedUser.email,
                            emailStatus: savedUser.activation_email?.delivered
                                ? "sent"
                                : savedUser.activation_email?.attempted
                                    ? "failed"
                                    : "skipped",
                        });
                        if (savedUser.activation_email?.reason) {
                            params.set("emailReason", savedUser.activation_email.reason);
                        }
                        router.push(`/user_management?${params.toString()}`);
                        return;
                    }
                    router.push(`/user_management/${savedUser.id}`);
                },
                onError: (error) => {
                    setSubmissionFeedback({
                        title: mode === "create" ? "User creation failed" : "Could not save changes",
                        description: getMutationErrorMessage(error, mode),
                    });
                },
            },
        );
    };

    if (mode === "edit" && isLoading && !liveUser) {
        return <div className="w-full px-6 py-10 text-sm text-slate-500">Loading user details...</div>;
    }

    if (mode === "edit" && !isLoading && !liveUser) {
        return <div className="w-full px-6 py-10 text-sm text-slate-500">User not found.</div>;
    }

    return (
        <>
            <div className="w-full px-6 py-5">
                <div className="mx-auto max-w-[1110px] space-y-6">
                    <PlatformPageTitle
                        title={title}
                        action={
                            <Button
                                onClick={() => {
                                    if (validate()) {
                                        setConfirmOpen(true);
                                    }
                                }}
                                className="h-12 rounded-[10px] bg-primary px-6 text-[15px] font-medium hover:bg-primary/90"
                            >
                                {saveUser.isPending ? (mode === "create" ? "Creating..." : "Saving...") : mode === "create" ? "Create" : "Save"}
                            </Button>
                        }
                    />

                    {submissionFeedback ? (
                        <Alert variant="destructive">
                            <AlertTitle>{submissionFeedback.title}</AlertTitle>
                            <AlertDescription>{submissionFeedback.description}</AlertDescription>
                        </Alert>
                    ) : null}

                    <SectionCard title="User Details">
                        <div className="max-w-[458px] space-y-5">
                            <FormField label="Full Name" required error={errors.fullName}>
                                <StyledInput
                                    placeholder="Enter full name"
                                    value={resolvedForm.fullName}
                                    onChange={(event) => {
                                        setErrors((current) => ({ ...current, fullName: undefined }));
                                        updateForm({ fullName: event.target.value });
                                    }}
                                />
                            </FormField>

                            <FormField label="Email Address" required error={errors.email}>
                                <StyledInput
                                    placeholder="Enter email address"
                                    value={resolvedForm.email}
                                    onChange={(event) => {
                                        setErrors((current) => ({ ...current, email: undefined }));
                                        updateForm({ email: event.target.value });
                                    }}
                                />
                            </FormField>

                            <FormField label="Contact Number" required error={errors.contactNumber}>
                                <StyledInput
                                    placeholder="Enter contact number"
                                    value={resolvedForm.contactNumber}
                                    onChange={(event) => {
                                        setErrors((current) => ({ ...current, contactNumber: undefined }));
                                        updateForm({ contactNumber: event.target.value });
                                    }}
                                />
                            </FormField>

                            <FormField label="User Role" required>
                                <Select
                                    // className="h-12 w-full rounded-[10px] border-none bg-input-field px-4 text-sm text-slate-700 outline-none"
                                    value={resolvedForm.roleCode}
                                    onValueChange={(event) => {
                                        const nextRole = event as UserEditorState["roleCode"];
                                        updateForm({
                                            roleCode: nextRole,
                                            selectedBrands: nextRole === "brand_user" ? resolvedForm.selectedBrands : [],
                                        });
                                    }}
                                >
                                    <SelectTrigger className="w-full bg-[#F5F7FA] rounded-[10px] border-none px-4 py-6 text-sm text-slate-700 cursor-pointer">
                                        <SelectValue placeholder="Select a fruit" />
                                    </SelectTrigger>

                                    <SelectContent>
                                        <SelectGroup>
                                            <SelectItem value="tenant_user">Tenant User</SelectItem>
                                            <SelectItem value="brand_user">Brand User</SelectItem>
                                        </SelectGroup>
                                    </SelectContent>
                                </Select>
                            </FormField>

                            {showBrandAssignment ? (
                                <div className="space-y-3">
                                    <p className="text-base font-medium text-slate-700">
                                        Brand Assignment <span className="text-red-500">*</span>
                                    </p>
                                    <div className="overflow-hidden rounded-[2px] border border-[#ECEEF5] bg-white">
                                        <div className="border-b border-[#ECEEF5] bg-[#F5F6FB] px-4 py-3 text-sm text-[#6B7280]">
                                            Assign brand space
                                        </div>
                                        <div className="divide-y divide-slate-100">
                                            {availableBrands.map((brand) => (
                                                <label key={brand.id} className="flex items-center gap-3 px-4 py-3 text-sm text-slate-700">
                                                    <Checkbox checked={resolvedForm.selectedBrands.includes(brand.id)} onCheckedChange={() => toggleBrand(brand.id)} />
                                                    <span>{brand.name}</span>
                                                </label>
                                            ))}
                                        </div>
                                    </div>
                                    {errors.selectedBrands ? <p className="text-sm text-red-500">{errors.selectedBrands}</p> : null}
                                </div>
                            ) : null}

                            {mode === "edit" ? (
                                <p className="text-sm text-slate-500">
                                    Editing <span className="font-medium text-slate-700">{roleLabel}</span> access and details.
                                </p>
                            ) : null}
                        </div>
                    </SectionCard>
                </div>
            </div>

            <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
                <AlertDialogContent className="max-w-[460px] rounded-2xl border-0 px-8 py-10 shadow-[0_20px_80px_-24px_rgba(15,23,42,0.25)]">
                    <AlertDialogHeader className="items-center text-center">
                        <AlertDialogTitle className="text-5xl font-semibold tracking-tight text-slate-900">Save Changes?</AlertDialogTitle>
                        <AlertDialogDescription className="text-xl text-slate-700">
                            Are you sure you want to save these changes?
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter className="mt-4 flex-row justify-center gap-6">
                        <AlertDialogAction
                            className="h-12 min-w-[152px] rounded-none bg-primary text-base hover:bg-primary/90"
                            onClick={submit}
                        >
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
