"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { TableFilterPopover } from "@/components/common/TableFilterPopover";
import { PlatformPageTitle, Pager, SearchField } from "@/components/platformOwner/PlatformOwnerPrimitives";
import { useGetTenants } from "@/hooks/tenantAdmins/useGetTenants";
import { formatShortDate, getActivityLabel } from "@/lib/platform-owner";
import {
    CREATED_DATE_FILTER_OPTIONS,
    RECENT_ACTIVITY_FILTER_OPTIONS,
    type CreatedDateFilter,
    type RecentActivityFilter,
    getRecentActivityStatus,
    matchesCreatedDateFilter,
} from "@/lib/table-filters";
import Image from "next/image";

const PAGE_SIZE_OPTIONS = [10, 25, 50];

export default function TenantManagementPage() {
    const router = useRouter();
    const { data, isLoading, error } = useGetTenants();
    const [search, setSearch] = useState("");
    const [createdFilter, setCreatedFilter] = useState<CreatedDateFilter>("all");
    const [activityFilter, setActivityFilter] = useState<RecentActivityFilter>("all");
    const [pageSize, setPageSize] = useState(10);
    const [page, setPage] = useState(1);
    const activeFilterCount = Number(createdFilter !== "all") + Number(activityFilter !== "all");

    const items = useMemo(() => {
        const source = data || [];
        const query = search.toLowerCase();
        return source.filter((tenant) => {
            const matchesQuery =
                !search.trim() ||
                [tenant.name, tenant.tenant_admin_name, tenant.contact_email].some((value) =>
                    value?.toLowerCase().includes(query),
                );
            const matchesCreated = matchesCreatedDateFilter(tenant.created_at, createdFilter);
            const matchesActivity =
                activityFilter === "all" || getRecentActivityStatus(tenant.last_active_at) === activityFilter;

            return matchesQuery && matchesCreated && matchesActivity;
        });
    }, [activityFilter, createdFilter, data, search]);

    const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
    const currentPage = Math.min(page, totalPages);
    const startIndex = (currentPage - 1) * pageSize;
    const pageItems = items.slice(startIndex, startIndex + pageSize);

    if (isLoading) {
        return <div className="p-5 text-sm text-slate-500">Loading tenants...</div>;
    }

    if (error) {
        return <div className="p-5 text-sm text-red-500">Unable to load tenants.</div>;
    }

    return (
        <div className="w-full px-6 py-6">
            <div className="max-w-[1110px] space-y-8">
                <PlatformPageTitle
                    title="Tenant Management"
                    action={
                        <Button
                            onClick={() => router.push("/tenants/create")}
                            className="flex h-12 items-center gap-2 rounded-xs bg-primary/72 px-5 text-base font-semibold hover:bg-primary/90"
                        >
                            <Image src={"/actions_icons/add.svg"} alt="Add" width={16} height={16} />
                            {/* <PlusCircle fill="white" className="text-primary/72 h-6 w-6" /> */}
                            New Tenant
                        </Button>
                    }
                />

                <div className="flex items-center justify-between gap-4">
                    <h2 className="text-xl font-semibold tracking-tight text-[#2F3342]">Tenant Accounts</h2>
                    <div className="flex flex-wrap gap-4">
                        <SearchField value={search} onChange={(value) => {
                            setSearch(value);
                            setPage(1);
                        }} />
                        <TableFilterPopover
                            createdLabel="Date Created"
                            createdValue={createdFilter}
                            createdOptions={CREATED_DATE_FILTER_OPTIONS}
                            onCreatedChange={(value) => {
                                setCreatedFilter(value);
                                setPage(1);
                            }}
                            activityLabel="Active Last 30 Days"
                            activityValue={activityFilter}
                            activityOptions={RECENT_ACTIVITY_FILTER_OPTIONS}
                            onActivityChange={(value) => {
                                setActivityFilter(value);
                                setPage(1);
                            }}
                            onClear={() => {
                                setCreatedFilter("all");
                                setActivityFilter("all");
                                setPage(1);
                            }}
                            activeFilterCount={activeFilterCount}
                            buttonAriaLabel="Open tenant filters"
                        />
                    </div>
                </div>

                <div className="rounded-[2px] border border-[#ECEEF5] bg-white shadow-[0_10px_24px_-22px_rgba(15,23,42,0.45)]">
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-left text-sm">
                            <thead className="bg-[#F6F7FC] text-[#4B5563]">
                                <tr>
                                    <th className="px-4 py-4 font-bold">Tenant Name</th>
                                    <th className="px-4 py-4 font-bold">Date Created</th>
                                    <th className="px-4 py-4 font-bold">Tenant Admin</th>
                                    <th className="px-4 py-4 font-bold">Brand Spaces</th>
                                    <th className="px-4 py-4 font-bold">Active (Last 30 Days)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {pageItems.length ? (
                                    pageItems.map((tenant) => (
                                        <tr
                                            key={tenant.id}
                                            className="cursor-pointer border-b border-[#F1F2F6] text-[#4B5563] hover:bg-[#FAFAFD]"
                                            onClick={() => router.push(`/tenants/${tenant.id}`)}
                                        >
                                            <td className="px-4 py-3">{tenant.name}</td>
                                            <td className="px-4 py-3">{formatShortDate(tenant.created_at)}</td>
                                            <td className="px-4 py-3">{tenant.tenant_admin_name || "-"}</td>
                                            <td className="px-4 py-3">{tenant.brand_space_count}</td>
                                            <td className="px-4 py-3">{getActivityLabel(tenant.last_active_at)}</td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr>
                                        <td colSpan={5} className="px-4 py-8 text-center text-[#6B7280]">
                                            No tenants match the selected filters
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div className="flex items-center justify-between text-sm text-[#4B5563]">
                    <div className="flex items-center gap-3">
                        <span>Show</span>
                        <select
                            className="h-9 rounded-[8px] border border-[#D5D8E8] bg-white px-3"
                            value={pageSize}
                            onChange={(event) => {
                                setPageSize(Number(event.target.value));
                                setPage(1);
                            }}
                        >
                            {PAGE_SIZE_OPTIONS.map((option) => (
                                <option key={option} value={option}>
                                    {option}
                                </option>
                            ))}
                        </select>
                        <span>Entries</span>
                    </div>
                    <Pager
                        page={currentPage}
                        totalPages={totalPages}
                        onPrevious={() => setPage((value) => Math.max(1, value - 1))}
                        onNext={() => setPage((value) => Math.min(totalPages, value + 1))}
                    />
                </div>
            </div>
        </div>
    );
}
