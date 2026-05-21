"use client";

import PLATFORM_OWNERProfile from "@/components/profiles/OwnerProfile";
import TenantAdminProfile from "@/components/profiles/TenantAdminProfile";
import { useRBAC } from "@/hooks/useRBAC";

export default function ProfilePage() {
    const { user } = useRBAC();

    return (
        <div className="w-full bg-white">
            {user?.role === "PLATFORM_OWNER" ? <PLATFORM_OWNERProfile /> : <TenantAdminProfile />}
        </div>
    );
}
