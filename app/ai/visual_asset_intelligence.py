from __future__ import annotations

import re
from typing import Any


class VisualAssetIntelligenceService:
    """
    Service for parsing visual requirements from prompts and enhancing image generation
    with specific illustration styles, data visualization needs, and visual element specifications.
    """

    CHART_TYPE_PATTERNS = {
        "bar_chart": r"(?:bar\s+chart|bar\s+graph|vertical\s+bar|horizontal\s+bar)",
        "line_chart": r"(?:line\s+chart|line\s+graph|trend\s+line)",
        "pie_chart": r"(?:pie\s+chart|donut\s+chart|circular\s+chart)",
        "area_chart": r"(?:area\s+chart|area\s+graph|filled\s+line)",
        "scatter_plot": r"(?:scatter\s+plot|scatter\s+chart|dot\s+plot)",
        "comparison": r"(?:comparison|versus|vs\.|compare|side[- ]by[- ]side)",
        "timeline": r"(?:timeline|chronological|over\s+time|progression)",
        "infographic": r"(?:infographic|data\s+visual|stat\s+visual)",
    }

    ILLUSTRATION_STYLE_PATTERNS = {
        "3d": r"(?:3d|three[- ]dimensional|isometric|depth|shadow|perspective)",
        "flat": r"(?:flat\s+design|flat\s+style|minimal|minimalist|simple)",
        "editorial": r"(?:editorial|magazine|premium|sophisticated|refined)",
        "geometric": r"(?:geometric|abstract|shapes|angular)",
        "hand_drawn": r"(?:hand[- ]drawn|sketch|illustrated|artistic)",
        "corporate": r"(?:corporate|professional|business|formal)",
        "modern": r"(?:modern|contemporary|sleek|clean)",
        "gradient": r"(?:gradient|color\s+blend|smooth\s+transition)",
    }

    VISUAL_ELEMENT_PATTERNS = {
        "arrow": r"(?:arrow|pointing|direction|upward|downward|growth\s+arrow)",
        "person": r"(?:person|people|woman|man|professional|business\s+person|suit)",
        "icon": r"(?:icon|symbol|pictogram|glyph)",
        "chart": r"(?:chart|graph|visualization|data\s+viz)",
        "calculator": r"(?:calculator|calculation|compute)",
        "money": r"(?:money|currency|cash|coins|bills|rupee|dollar)",
        "globe": r"(?:globe|world|global|international)",
        "growth": r"(?:growth|increase|rising|upward\s+trend)",
        "comparison": r"(?:comparison|before\s+and\s+after|side\s+by\s+side)",
    }

    DATA_EXTRACTION_PATTERNS = {
        "year": r"(?:year|yr)[\s:]*(\d{4})",
        "percentage": r"(\d+(?:\.\d+)?)\s*%",
        "currency": r"[₹$€£¥]\s*(\d+(?:[.,]\d+)*(?:\s*(?:lakh|crore|million|billion|k|m|b))?)",
        "number_with_unit": r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)",
    }

    @classmethod
    def parse_visual_requirements(cls, prompt: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Parse the prompt to extract visual requirements including:
        - Chart types needed
        - Illustration style preferences
        - Specific visual elements requested
        - Data points for visualization
        """
        prompt_lower = prompt.lower()
        metadata = metadata or {}

        # Detect chart types
        chart_types = []
        for chart_type, pattern in cls.CHART_TYPE_PATTERNS.items():
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                chart_types.append(chart_type)

        # Detect illustration style
        illustration_styles = []
        for style, pattern in cls.ILLUSTRATION_STYLE_PATTERNS.items():
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                illustration_styles.append(style)

        # Default to editorial if no style detected
        if not illustration_styles:
            illustration_styles = ["editorial", "modern"]

        # Detect visual elements
        visual_elements = []
        for element, pattern in cls.VISUAL_ELEMENT_PATTERNS.items():
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                visual_elements.append(element)

        # Extract data points
        data_points = cls._extract_data_points(prompt)

        # Parse structured data from metadata
        structured_data = cls._parse_structured_data_from_metadata(metadata)

        return {
            "chart_types": chart_types,
            "illustration_styles": illustration_styles,
            "visual_elements": visual_elements,
            "data_points": data_points,
            "structured_data": structured_data,
            "has_data_visualization": bool(chart_types or data_points or structured_data),
            "requires_custom_illustration": bool(visual_elements),
        }

    @classmethod
    def _extract_data_points(cls, prompt: str) -> list[dict[str, Any]]:
        """Extract numerical data points from the prompt."""
        data_points = []

        # Extract years
        years = re.findall(cls.DATA_EXTRACTION_PATTERNS["year"], prompt)

        # Extract percentages
        percentages = re.findall(cls.DATA_EXTRACTION_PATTERNS["percentage"], prompt)

        # Extract currency values
        currency_matches = re.findall(cls.DATA_EXTRACTION_PATTERNS["currency"], prompt)

        # Try to pair years with values
        if years and (percentages or currency_matches):
            values = currency_matches if currency_matches else percentages
            for i, year in enumerate(years):
                if i < len(values):
                    data_points.append({
                        "year": year,
                        "value": values[i],
                        "type": "currency" if currency_matches else "percentage"
                    })

        return data_points

    @classmethod
    def _parse_structured_data_from_metadata(cls, metadata: dict[str, Any]) -> dict[str, Any] | None:
        """
        Parse structured data from metadata fields like stat_highlights or proof_points.
        """
        if not metadata:
            return None

        stat_highlights = metadata.get("stat_highlights", []) or []
        proof_points = metadata.get("proof_points", []) or []

        # Look for data patterns in stat highlights
        data_series = []
        for stat in stat_highlights:
            if not isinstance(stat, str):
                continue

            # Try to extract year: value pairs
            year_match = re.search(r"(\d{4})[\s:]+([₹$€£¥]?\s*\d+(?:[.,]\d+)*(?:\s*(?:lakh|crore|million|billion|k|m|b))?)", stat)
            if year_match:
                data_series.append({
                    "label": year_match.group(1),
                    "value": year_match.group(2)
                })

        if data_series:
            return {
                "type": "series",
                "data": data_series
            }

        return None

    @classmethod
    def enhance_image_prompt_with_visual_intelligence(
        cls,
        base_prompt: str,
        visual_requirements: dict[str, Any],
        brand_visual_brief: dict[str, Any] | None = None,
    ) -> str:
        """
        Enhance the image generation prompt with specific visual intelligence
        based on parsed requirements.
        """
        enhancements = []

        brand_visual_brief = brand_visual_brief or {}

        # Add illustration style guidance
        illustration_styles = visual_requirements.get("illustration_styles", [])
        if illustration_styles:
            style_desc = cls._get_illustration_style_description(illustration_styles)
            enhancements.append(f"ILLUSTRATION STYLE: {style_desc}")

        # Add chart/data visualization guidance
        chart_types = visual_requirements.get("chart_types", [])
        if chart_types:
            chart_desc = cls._get_chart_visualization_guidance(chart_types, visual_requirements)
            enhancements.append(f"DATA VISUALIZATION: {chart_desc}")

        # Add specific visual element guidance
        visual_elements = visual_requirements.get("visual_elements", [])
        if visual_elements:
            element_desc = cls._get_visual_element_guidance(visual_elements)
            enhancements.append(f"REQUIRED VISUAL ELEMENTS: {element_desc}")

        # Add brand illustration library guidance
        reusable_assets = brand_visual_brief.get("reusable_design_assets", []) or []
        illustration_assets = [
            a for a in reusable_assets
            if isinstance(a, dict) and a.get("asset_kind") in {"illustration", "icon", "decorative"}
        ]
        if illustration_assets:
            asset_guidance = cls._get_brand_asset_guidance(illustration_assets)
            enhancements.append(f"BRAND ILLUSTRATION LIBRARY: {asset_guidance}")

        # Add composition guidance for data visualization
        if visual_requirements.get("has_data_visualization"):
            enhancements.append(
                "COMPOSITION: Create a structured infographic-style layout with clear data visualization. "
                "Use professional chart rendering with proper axes, labels, and data points. "
                "Ensure charts are readable, accurate, and visually prominent."
            )

        # Combine enhancements with base prompt
        if enhancements:
            enhanced_sections = [
                "VISUAL INTELLIGENCE ENHANCEMENTS:",
                *enhancements,
                "",
                "BASE CREATIVE REQUIREMENTS:",
                base_prompt
            ]
            return "\n\n".join(enhanced_sections)

        return base_prompt

    @classmethod
    def _get_illustration_style_description(cls, styles: list[str]) -> str:
        """Generate detailed illustration style description."""
        style_descriptions = {
            "3d": "Use 3D illustration style with depth, shadows, and perspective. Create volumetric objects with realistic lighting and shading. Add subtle gradients for dimension.",
            "flat": "Use flat design style with solid colors, minimal shadows, and clean geometric shapes. Keep illustrations simple and modern.",
            "editorial": "Use premium editorial illustration style with sophisticated composition, refined color palette, and professional finish. Think magazine-quality visuals.",
            "geometric": "Use geometric abstract style with clean shapes, angular forms, and structured composition.",
            "hand_drawn": "Use hand-drawn illustration style with organic lines, artistic touches, and human feel.",
            "corporate": "Use professional corporate illustration style with clean lines, business-appropriate imagery, and formal aesthetic.",
            "modern": "Use modern contemporary illustration style with sleek design, current trends, and fresh aesthetic.",
            "gradient": "Use gradient-rich illustration style with smooth color transitions and depth through color blending.",
        }

        descriptions = [style_descriptions.get(style, f"{style} style") for style in styles[:2]]
        return " ".join(descriptions)

    @classmethod
    def _get_chart_visualization_guidance(cls, chart_types: list[str], visual_requirements: dict[str, Any]) -> str:
        """Generate specific chart visualization guidance."""
        chart_guidance = {
            "bar_chart": "Create a professional bar chart with clearly labeled axes, distinct bars with proper spacing, and data labels. Use brand colors for bars with subtle gradients or solid fills. Ensure bars are proportional to data values.",
            "line_chart": "Create a clean line chart with smooth curves, clear data points, grid lines, and labeled axes. Use brand primary color for the line with subtle shadow or glow effect.",
            "pie_chart": "Create a modern pie/donut chart with clear segments, percentage labels, and legend. Use brand color palette for segments with good contrast.",
            "comparison": "Create a side-by-side comparison visualization with clear before/after or option A vs option B layout. Use contrasting colors and visual separators.",
            "timeline": "Create a horizontal or vertical timeline with clear milestones, dates, and progression indicators. Use arrows or connecting lines to show flow.",
            "infographic": "Create a structured infographic layout with multiple data visualization elements, icons, and clear information hierarchy.",
        }

        primary_chart = chart_types[0] if chart_types else "bar_chart"
        guidance = chart_guidance.get(primary_chart, "Create clear data visualization with proper labeling and brand colors.")

        # Add data point guidance if available
        data_points = visual_requirements.get("data_points", [])
        if data_points:
            guidance += f" Visualize these specific data points: {', '.join([f'{dp.get('year')}: {dp.get('value')}' for dp in data_points[:5]])}."

        return guidance

    @classmethod
    def _get_visual_element_guidance(cls, elements: list[str]) -> str:
        """Generate guidance for specific visual elements."""
        element_descriptions = {
            "arrow": "Include an arrow only when the content explicitly needs directional movement, comparison flow, or a step transition. Avoid defaulting to a generic upward growth arrow.",
            "person": "Include a professional illustration of a person in business attire (suit/formal wear). Use modern illustration style with clean lines and brand colors. Position prominently but not dominating the composition.",
            "icon": "Include relevant icons that support the message. Use consistent icon style (line, filled, or duotone) matching brand aesthetic.",
            "chart": "Include data visualization charts as primary visual elements. Make charts prominent, readable, and professionally rendered.",
            "calculator": "Include a calculator illustration with visible buttons and display. Use 3D style or flat design matching overall aesthetic.",
            "money": "Include money/currency visual elements like coins, bills, or currency symbols. Use brand colors and modern illustration style.",
            "globe": "Include a globe illustration showing global/international context. Can be combined with other elements like currency symbols.",
            "growth": "If growth must be shown, use topic-specific progression cues rather than a stock rising-bars-with-arrow motif.",
            "comparison": "Include comparison visual elements showing contrast or before/after scenarios.",
        }

        descriptions = [element_descriptions.get(elem, f"Include {elem} visual element") for elem in elements[:4]]
        return " ".join(descriptions)

    @classmethod
    def _get_brand_asset_guidance(cls, assets: list[dict[str, Any]]) -> str:
        """Generate guidance for using brand illustration assets."""
        asset_descriptions = []
        for asset in assets[:3]:
            label = asset.get("label") or asset.get("asset_kind", "illustration")
            style = asset.get("style_notes", "")
            if style:
                asset_descriptions.append(f"Use {label} in {style} style")
            else:
                asset_descriptions.append(f"Include {label}")

        if asset_descriptions:
            return f"{', '.join(asset_descriptions)}. Match the established brand illustration style and color palette."

        return "Use brand-consistent illustration style with approved visual elements."
