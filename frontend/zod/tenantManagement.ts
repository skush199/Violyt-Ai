import { TenantFormData } from "@/types/tenant.types";
import z, { ZodError } from "zod";


export const tenantSchema = z.object({
    tenant: z.object({
        name: z.string().min(1, "Tenant name is required"),
        email: z.email("Valid email is required"),
        phone: z.string().min(1, "Phone is required"),
        address1: z.string().min(1, "Address is required"),
        address2: z.string().optional(),
        city: z.string().min(2, "City is required"),
        state: z.string().min(2, "State is required"),
        zip: z.string().min(5, "Zip code is invalid"),
        logo: z.instanceof(File).or(z.string()).optional(),
        country: z.string().min(2, "Country is required")
    }),
    admin: z.object({
        name: z.string().min(1, "Admin name is required"),
        email: z.email("Valid email is required"),
        phone: z.string().min(10, "Phone is required")
    }),
    usage: z.object({
        startMonth: z.string().min(1, "Start month is required"),
        endMonth: z.string().min(1, "End month is required"),
        renewsCredits: z.boolean(),
        maxContentGenerations: z.string().min(1, "Max content generations is required"),
        maxVisualGenerations: z.string().min(1, "Max visual generations is required"),
        maxOcrPages: z.string().min(1, "Max OCR pages is required"),
        maxUsers: z.string().min(1, "Max users is required"),
        maxBrandSpaces: z.string().min(1, "Max brand spaces is required")
    })
})


export type FormErrors = Partial<{
    tenant: Partial<Record<keyof TenantFormData["tenant"], string>>
    admin: Partial<Record<keyof TenantFormData["admin"], string>>
    usage: Partial<Record<keyof TenantFormData["usage"], string>>
}>


export function formatZodErrors(
    zodError: ZodError<TenantFormData>
): FormErrors {

    const formatted: FormErrors = {}

    zodError.issues.forEach((issue) => {
        const [section, field] = issue.path

        // Ensure valid structure
        if (
            typeof section !== "string" ||
            typeof field !== "string"
        ) return

        // Initialize section if not exists
        if (!formatted[section as keyof FormErrors]) {
            formatted[section as keyof FormErrors] = {}
        }

        // 🔥 FIX: safe assignment
        const sectionErrors =
            formatted[section as keyof FormErrors] as Record<string, string>

        sectionErrors[field] = issue.message
    })

    return formatted
}
