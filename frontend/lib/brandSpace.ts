import type { ComponentType } from "react";
import AdditionalDetails from "@/components/brandSpaces/tabs/AdditionalDetails";
import BrandKnowledge from "@/components/brandSpaces/tabs/BrandKnowledge";
import BrandRules from "@/components/brandSpaces/tabs/BrandRules";
import CoreBrandSignals from "@/components/brandSpaces/tabs/CoreBrandSignals";
import TargetAudience from "@/components/brandSpaces/tabs/TargetAudience";
import VisualIdentity from "@/components/brandSpaces/tabs/VisualIdentity";
import VoiceTone from "@/components/brandSpaces/tabs/VoiceTone";
import type { BrandTabProps } from "@/types/brand-space.types";

type BrandSpaceTab = {
    id: number;
    label: string;
    value: string;
    content: ComponentType<BrandTabProps>;
};

export const brandSpaceTabs: BrandSpaceTab[] = [
    {
        id: 1,
        label: "Core Brand Signals",
        value: "core_brand_signals",
        content: CoreBrandSignals
    },
    {
        id: 2,
        label: "Voice & Tone",
        value: "voice_tone",
        content: VoiceTone
    },
    {
        id: 3,
        label: "Target Audience",
        value: "target_audience",
        content: TargetAudience
    },
    {
        id: 4,
        label: "Visual Identity",
        value: "visual_identity",
        content: VisualIdentity
    },
    {
        id: 5,
        label: "Brand Rules",
        value: "brand_rules",
        content: BrandRules
    },
    {
        id: 6,
        label: "Brand Knowledge",
        value: "brand_knowledge",
        content: BrandKnowledge
    },
    {
        id: 7,
        label: "Additional Details",
        value: "additional_details",
        content: AdditionalDetails
    },
];
