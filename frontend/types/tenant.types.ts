export interface TenantFormData {
    tenant: {
        name: string
        email: string
        phone: string
        logo?: File | string
        address1: string
        address2?: string
        city: string
        state: string
        zip: string
        country: string
    }

    admin: {
        name: string
        email: string
        phone?: string
    }

    usage: {
        startMonth: string
        endMonth: string
        renewsCredits: boolean
        maxContentGenerations: string
        maxVisualGenerations: string
        maxOcrPages: string
        maxUsers: string
        maxBrandSpaces: string
    }
}


export interface User {
    id: string;
    name: string;
    email: string;
    role: string;
    phone?: string;
    notificationsEnabled?: boolean;
    twoFactorEnabled?: boolean;
}
