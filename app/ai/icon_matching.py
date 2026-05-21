"""
Icon Style Matching Service

Matches semantic icon needs to brand-consistent icon assets,
ensuring visual style coherence (line-art vs solid vs 3D).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


class IconMatchingService:
    """
    Service for matching semantic icon requirements to brand-aligned icon assets.

    Ensures icons match the brand's visual style (line-art, solid, 3D, etc.)
    and color palette.
    """

    def match_icon(
        self,
        semantic_need: str,
        brand_context: dict[str, Any],
        preferred_style: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Match semantic icon need to brand-consistent icon asset.

        Args:
            semantic_need: Semantic description (e.g., "arrow", "chart", "person")
            brand_context: Full brand context including visual_identity
            preferred_style: Optional style override (e.g., "line-art", "solid")

        Returns:
            Icon asset metadata or None if no match found
        """
        # Extract brand's icon library
        visual_identity = brand_context.get("visual_identity", {})
        icon_asset_ids = visual_identity.get("icon_asset_ids", [])

        if not icon_asset_ids:
            return None

        # Infer brand's icon style from visual identity
        icon_style = preferred_style or self._infer_icon_style(visual_identity)

        # Get brand color palette
        brand_color_palette = visual_identity.get("brand_color_palette", {})

        # TODO: Implement actual icon matching logic
        # This would require:
        # 1. Loading icon assets from icon_asset_ids
        # 2. Filtering by style (line-art vs solid vs 3D)
        # 3. Semantic matching against icon keywords/tags
        # 4. Color compliance checking
        # 5. Recoloring if needed

        # Placeholder: Return structure for matched icon
        return {
            "icon_asset_id": icon_asset_ids[0] if icon_asset_ids else None,
            "semantic_need": semantic_need,
            "matched_style": icon_style,
            "needs_recolor": False,
            "target_color": brand_color_palette.get("primary"),
        }

    def _infer_icon_style(self, visual_identity: dict[str, Any]) -> str:
        """
        Infer brand's preferred icon style from visual identity.

        Returns:
            Icon style: "line-art", "solid", "3d", "duotone"
        """
        # Check visual_style hints
        visual_style = visual_identity.get("visual_style", "")
        if isinstance(visual_style, str):
            visual_style_lower = visual_style.lower()
            if "line" in visual_style_lower or "minimal" in visual_style_lower:
                return "line-art"
            if "3d" in visual_style_lower or "dimensional" in visual_style_lower:
                return "3d"
            if "solid" in visual_style_lower or "filled" in visual_style_lower:
                return "solid"

        # Check reference creatives for icon patterns
        reference_creatives = visual_identity.get("reference_creatives", [])
        for reference in reference_creatives:
            if not isinstance(reference, dict):
                continue
            style_chars = reference.get("style_characteristics", {})
            if isinstance(style_chars, dict):
                infographic_elements = style_chars.get("infographic_elements", {})
                if isinstance(infographic_elements, dict):
                    icon_style = infographic_elements.get("icons")
                    if icon_style in {"line", "solid", "3d"}:
                        return icon_style if icon_style != "line" else "line-art"

        # Default to line-art for modern, clean aesthetic
        return "line-art"

    def _semantic_match(
        self,
        semantic_need: str,
        candidate_icons: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        Match semantic need to best candidate icon.

        Args:
            semantic_need: What the icon should represent
            candidate_icons: List of icon assets with metadata

        Returns:
            Best matching icon or None
        """
        if not candidate_icons:
            return None

        # 1. Keyword matching (fast path)
        keyword_matches = []
        need_lower = semantic_need.lower()

        for icon in candidate_icons:
            metadata = icon.get("normalized_metadata_json") or {}
            keywords = metadata.get("keywords", [])

            # Exact keyword match
            if need_lower in keywords:
                return icon

            # Partial match
            if any(keyword in need_lower or need_lower in keyword for keyword in keywords):
                keyword_matches.append(icon)

        # If only one keyword match, use it
        if len(keyword_matches) == 1:
            return keyword_matches[0]

        # 2. LLM-based semantic matching for multiple candidates
        # Works for ANY domain: finance, fashion, cooking, tech, etc.
        if len(keyword_matches) > 1:
            return self._llm_select_best_icon(semantic_need, keyword_matches)

        # 3. If no keyword matches, use LLM to pick from all candidates
        if len(candidate_icons) > 5:
            # Too many to send to LLM, return first
            return candidate_icons[0]

        if len(candidate_icons) > 1:
            return self._llm_select_best_icon(semantic_need, candidate_icons)

        # 4. Fallback to first candidate
        return candidate_icons[0] if candidate_icons else None

    def _llm_select_best_icon(
        self,
        semantic_need: str,
        candidate_icons: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Use LLM to select best icon from candidates.

        Works for ANY domain without hardcoded categories:
        finance, fashion, cooking, tech, healthcare, education, etc.

        Args:
            semantic_need: What the icon should represent (e.g., "tax savings", "chef cooking", "luxury dress")
            candidate_icons: List of icon assets with keywords

        Returns:
            Best matching icon
        """
        if not candidate_icons:
            return candidate_icons[0] if candidate_icons else None

        # Build prompt with icon keywords
        options = []
        for idx, icon in enumerate(candidate_icons[:10]):  # Limit to 10 for prompt size
            metadata = icon.get("normalized_metadata_json", {})
            keywords = metadata.get("keywords", [])
            label = icon.get("label", "")
            keywords_str = ", ".join(keywords) if keywords else "no keywords"
            options.append(f"{idx + 1}. {label} (keywords: {keywords_str})")

        prompt = (
            f"Select the best icon to represent: '{semantic_need}'\n\n"
            f"Available icons:\n" + "\n".join(options) + "\n\n"
            f"Respond with ONLY the number (1-{len(options)}) of the best match."
        )

        try:
            # Use OpenAI for quick LLM call
            from app.core.config import get_settings
            from openai import OpenAI

            settings = get_settings()
            if not settings.openai_api_key:
                return candidate_icons[0]

            client = OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model=settings.llm_model,  # Use configured model instead of hardcoded value
                messages=[
                    {"role": "system", "content": "You are an icon selection assistant. Respond with only a number."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0,
            )

            selected_num = int(response.choices[0].message.content.strip())
            selected_idx = max(0, min(selected_num - 1, len(candidate_icons) - 1))
            return candidate_icons[selected_idx]

        except Exception:  # noqa: BLE001
            # Fallback to first candidate if LLM fails
            return candidate_icons[0]

    def _color_compliant(
        self,
        icon_asset: dict[str, Any],
        brand_color_palette: dict[str, Any],
    ) -> bool:
        """
        Check if icon color matches brand palette.

        Args:
            icon_asset: Icon asset metadata
            brand_color_palette: Brand color palette

        Returns:
            True if icon color is brand-compliant
        """
        # TODO: Implement color compliance checking
        # This would:
        # 1. Extract icon's current color
        # 2. Check if it matches any palette role
        # 3. Return compliance status

        # Placeholder: Assume compliant
        return True

    def _recolor_icon(
        self,
        icon_asset: dict[str, Any],
        target_color: str,
    ) -> dict[str, Any]:
        """
        Recolor icon to match brand palette.

        Args:
            icon_asset: Icon asset to recolor
            target_color: Target hex color

        Returns:
            Recolored icon asset metadata
        """
        # TODO: Implement icon recoloring
        # This would:
        # 1. Load icon SVG/vector data
        # 2. Modify fill/stroke colors
        # 3. Return new asset reference

        # Placeholder: Return original with recolor flag
        recolored = dict(icon_asset)
        recolored["recolored_to"] = target_color
        return recolored
