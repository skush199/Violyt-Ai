import type { Metadata } from "next";
import localFont from "next/font/local";
import { GeistSans } from 'geist/font/sans'
import { GeistMono } from 'geist/font/mono'
import "./globals.css";
import { SidebarProvider } from "@/context/SidebarContext";
import OfflineBanner from "@/components/OfflineBanner";
import { NetworkProvider } from "@/context/network-provider";
import { TanstackProviders } from "@/providers/tanstackProvider";

const manrope = localFont({
    src: "../public/fonts/Manrope/Manrope-VariableFont_wght.ttf",
    variable: "--font-manrope",
    display: "swap",
});

const dmSans = localFont({
    src: "../public/fonts/DM_Sans/DMSans-VariableFont_opsz,wght.ttf",
    variable: "--font-dmSans",
    display: "swap",
});

export const metadata: Metadata = {
    title: "Violyt",
    description: "Violyt AI brand platform",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" suppressHydrationWarning>
            <body
                className={`${GeistSans.variable} ${GeistMono.variable} ${manrope.variable} ${dmSans.variable} antialiased`}
            >
                <TanstackProviders>
                    <NetworkProvider>
                        <SidebarProvider>
                            <OfflineBanner />
                            {children}
                        </SidebarProvider>
                    </NetworkProvider>
                </TanstackProviders>
            </body>
        </html>
    );
}
