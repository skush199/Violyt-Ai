"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, FolderOpen, MoreVertical } from "lucide-react";
import { useSidebar } from "@/context/SidebarContext";
import {
    buildBrandWorkspaceHref,
    resolveBrandByRouteKey,
    resolveBrandRouteKey,
} from "@/lib/brand-routing";
import { sidebarItems } from "@/lib/sidebarItems";
import { cn } from "@/lib/utils";
import { useRBAC } from "@/hooks/useRBAC";
import { useBrands } from "@/hooks/useBrands";
import { Button } from "./ui/button";
import { NotificationDrawer } from "./NotificationDrawer";
import { Tooltips } from "./Tooltip";

export default function Sidebar() {
    const { isSidebarOpen, toggleSidebar } = useSidebar();
    const { user, canAccessModule } = useRBAC();
    const { data: brands } = useBrands(user?.role !== "PLATFORM_OWNER");
    const path = usePathname();

    const isWorkspacePath = path.startsWith("/brand_space/") && !path.startsWith("/brand_space/new");
    const currentBrandKey = isWorkspacePath ? path.split("/")[2] : undefined;
    const liveBrands = brands || [];
    const currentBrand = resolveBrandByRouteKey(liveBrands, currentBrandKey);
    const workspaceBrands = liveBrands.filter((brand) => brand.lifecycle_state !== "deleted" && brand.lifecycle_state !== "archived");

    const filteredSidebarItems = sidebarItems.filter((item) => (user ? canAccessModule(item.module) : false));
    const isPlatformOwner = user?.role === "PLATFORM_OWNER";

    return (
        <aside
            className={cn(
                "sticky top-2 flex shrink-0 flex-col overflow-hidden border border-[#ECEEF5] bg-sidebar-primary text-[#666666] transition-all duration-300 ease-in-out",
                isPlatformOwner
                    ? "h-[calc(100vh-16px)] w-[280px] rounded-[4px]"
                    : isSidebarOpen
                        ? "h-[calc(100vh-16px)] w-84 rounded-xl"
                        : "h-[calc(100vh-16px)] w-20 rounded-xl",
            )}
        >
            <div className={cn("flex items-center justify-between px-4 py-5", !isPlatformOwner && !isSidebarOpen && "justify-center px-3")}>
                <span className={cn("font-dmSans text-[36px] font-bold tracking-[-0.03em] text-primary", !isPlatformOwner && !isSidebarOpen && "hidden")}>
                    Violyt
                </span>
                <Tooltips content={!isSidebarOpen ? "Toggle Sidebar" : ""}>
                    <Button
                        variant="ghost"
                        onClick={() => toggleSidebar()}
                        className={cn(
                            "h-8 w-8 cursor-e-resize rounded-md p-0 text-primary transition hover:bg-[#ECEEF7]",
                            !isPlatformOwner && !isSidebarOpen && "cursor-pointer",
                        )}
                    >
                        <Image src="/toggleSidebar.svg" alt="toggle" width={16} height={16} className="h-4 w-4" />
                    </Button>
                </Tooltips>
            </div>

            <nav className="flex flex-1 flex-col justify-between px-2 pb-3">
                <div className="space-y-1">
                    {filteredSidebarItems.map((item) => {
                        const iconName = item.icon.replace(/^\//, "");
                        const activeItem =
                            path === item.href ||
                            (item.href ? path.startsWith(`${item.href}/`) : false) ||
                            (item.href === "/brand_space" && isWorkspacePath);
                        const icon = activeItem ? `/sidebar/${iconName}-white.svg` : `/sidebar/${iconName}.svg`;

                        return (
                            <div key={item.id} className="w-full">
                                {item.href ? (
                                    <Link
                                        href={item.href}
                                        className={cn(
                                            "flex items-center gap-3 px-4 py-3 text-base transition",
                                            activeItem ? "bg-primary text-white" : "text-[#5F6372] hover:bg-[#EFF1F8]",
                                            !isPlatformOwner && !isSidebarOpen && "justify-center px-3",
                                        )}
                                    >
                                        <Image src={icon} width={20} height={20} alt={item.name} className="h-5 w-5" />
                                        <span className={cn("text-[15px]", !isPlatformOwner && !isSidebarOpen && "hidden")}>{item.name}</span>
                                    </Link>
                                ) : (
                                    <NotificationDrawer>
                                        <button
                                            className={cn(
                                                "flex w-full items-center gap-3 px-4 py-3 text-left text-base text-[#5F6372] transition hover:bg-[#EFF1F8]",
                                                !isPlatformOwner && !isSidebarOpen && "justify-center px-3",
                                            )}
                                            type="button"
                                        >
                                            <Image src={icon} width={20} height={20} alt={item.name} className="h-5 w-5" />
                                            <span className={cn("text-[15px]", !isPlatformOwner && !isSidebarOpen && "hidden")}>{item.name}</span>
                                        </button>
                                    </NotificationDrawer>
                                )}

                                {item.href === "/brand_space" && isSidebarOpen && isWorkspacePath && currentBrand ? (
                                    <div className="mt-2 space-y-2 pl-3">
                                        <div className="flex items-center gap-2 px-3 text-sm font-medium text-[#3C2F8F]">
                                            <ChevronDown className="h-4 w-4" />
                                            <span>Brand Spaces</span>
                                        </div>

                                        <div className="rounded-md bg-[#3C2F8F] px-3 py-3 text-white">
                                            <div className="flex items-center justify-between">
                                                <Link href={buildBrandWorkspaceHref(currentBrand)} className="flex items-center gap-2 text-base font-medium">
                                                    <FolderOpen className="h-4 w-4" />
                                                    <span>{currentBrand.name}</span>
                                                </Link>
                                                <MoreVertical className="h-4 w-4" />
                                            </div>
                                            <div className="mt-3 space-y-2 border-l border-white/20 pl-4">
                                                <span className="block text-left text-sm text-white/90">Workspace active</span>
                                            </div>
                                        </div>

                                        {workspaceBrands
                                            .filter((brand) => resolveBrandRouteKey(brand) !== resolveBrandRouteKey(currentBrand))
                                            .slice(0, 2)
                                            .map((brand) => (
                                                <Link
                                                    key={brand.id}
                                                    href={buildBrandWorkspaceHref(brand)}
                                                    className="flex items-center gap-2 px-3 py-2 text-base text-[#666666] transition hover:bg-gray-200"
                                                >
                                                    <FolderOpen className="h-4 w-4" />
                                                    <span>{brand.name}</span>
                                                </Link>
                                            ))}
                                    </div>
                                ) : null}
                            </div>
                        );
                    })}
                </div>

                <div className="px-1">
                    <Link
                        href="/profile"
                        className={cn(
                            "flex items-center gap-3 rounded-[10px] px-3 py-2 transition hover:bg-[#EFF1F8]",
                            !isPlatformOwner && !isSidebarOpen && "justify-center px-2",
                        )}
                    >
                        <span className="flex h-[38px] w-[38px] items-center justify-center rounded-full bg-[#52B2CF] text-base font-medium text-white">
                            {user?.name?.[0] || "P"}
                        </span>
                        <span className={cn("text-[15px] font-medium text-[#2F3342]", !isPlatformOwner && !isSidebarOpen && "hidden")}>
                            {user?.name || "Indo Sakura"}
                        </span>
                    </Link>
                </div>
            </nav>
        </aside>
    );
}
