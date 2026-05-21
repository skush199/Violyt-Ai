from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.contracts import StructuredTextPayload
from app.ai.data_visualization import ChartSpec


@dataclass
class SlideBlueprint:
    """Blueprint for a single carousel slide."""
    slide_number: int
    role: str  # cover, detail, data_viz, closing
    headline: str
    supporting_line: str | None = None
    proof_points: list[str] | None = None
    cta: str | None = None
    chart_spec: ChartSpec | None = None
    visual_elements: list[str] | None = None
    layout_archetype: str = "editorial_corner_split"
    primary_visual_type: str = "illustration"  # illustration, chart, icon_grid
    cta_style: dict[str, Any] | None = None  # CTA button styling from brand template

    def __post_init__(self):
        if self.proof_points is None:
            self.proof_points = []
        if self.visual_elements is None:
            self.visual_elements = []
        if self.cta_style is None:
            self.cta_style = {}


class CarouselPlannerService:
    """
    Service for planning multi-slide carousel content distribution.
    Breaks content into logical slides with proper visual hierarchy.
    """
    
    @classmethod
    def plan_carousel_slides(
        cls,
        text_payload: StructuredTextPayload,
        data_elements: list[ChartSpec] | None = None,
        brand_assets: list[dict[str, Any]] | None = None,
        brand_context: dict[str, Any] | None = None,
        reference_images: list[dict[str, Any]] | None = None,
        max_slides: int = 10,
    ) -> list[SlideBlueprint]:
        """
        Plan carousel slides from text payload and data elements.

        Args:
            text_payload: Structured text content
            data_elements: List of chart specifications
            brand_assets: Available brand illustration assets
            brand_context: Brand context including CTA templates
            reference_images: Available reference images with storage paths
            max_slides: Maximum number of slides to generate

        Returns:
            List of slide blueprints
        """
        metadata = text_payload.metadata or {}
        data_elements = data_elements or []
        brand_assets = brand_assets or []
        reference_images = reference_images or []

        slides = []

        # Slide 1: Cover slide
        cover_slide = cls._create_cover_slide(text_payload, brand_assets)
        slides.append(cover_slide)

        # Determine content distribution strategy
        has_reference_images = len(reference_images) >= 2
        has_data_viz = bool(data_elements)
        proof_points = metadata.get("proof_points", []) or []
        stat_highlights = metadata.get("stat_highlights", []) or []

        if has_reference_images:
            # Image-driven carousel: cover + image-driven detail slides + closing
            slides.extend(cls._plan_image_driven_slides(
                text_payload, reference_images, brand_assets, max_slides - 2
            ))
        elif has_data_viz:
            # Data-driven carousel: cover + context + data viz + closing
            slides.extend(cls._plan_data_driven_slides(
                text_payload, data_elements, brand_assets, max_slides - 2
            ))
        elif len(proof_points) >= 3 or len(stat_highlights) >= 3:
            # Multi-point carousel: cover + detail slides + closing
            slides.extend(cls._plan_multi_point_slides(
                text_payload, brand_assets, max_slides - 2
            ))
        else:
            # Simple carousel: cover + detail + closing
            slides.extend(cls._plan_simple_slides(
                text_payload, brand_assets, max_slides - 2
            ))
        
        # Final slide: Closing/CTA slide
        closing_slide = cls._create_closing_slide(text_payload, brand_assets, brand_context)
        slides.append(closing_slide)
        
        # Limit to max_slides
        return slides[:max_slides]
    
    @classmethod
    def _create_cover_slide(
        cls,
        text_payload: StructuredTextPayload,
        brand_assets: list[dict[str, Any]],
    ) -> SlideBlueprint:
        """Create the cover slide."""
        metadata = text_payload.metadata or {}
        
        # Use title from metadata if available, otherwise headline
        headline = metadata.get("title") or text_payload.headline
        supporting_line = metadata.get("subheading") or metadata.get("supporting_line") or ""
        
        # Select visual elements for cover
        visual_elements = cls._select_visual_elements_for_role("cover", metadata, brand_assets)
        
        return SlideBlueprint(
            slide_number=1,
            role="cover",
            headline=headline,
            supporting_line=supporting_line,
            cta=text_payload.cta if text_payload.cta else None,
            visual_elements=visual_elements,
            layout_archetype="editorial_hero",
            primary_visual_type="illustration"
        )
    
    @classmethod
    def _create_closing_slide(
        cls,
        text_payload: StructuredTextPayload,
        brand_assets: list[dict[str, Any]],
        brand_context: dict[str, Any] | None = None,
    ) -> SlideBlueprint:
        """Create the closing/CTA slide using brand CTA template if available."""
        metadata = text_payload.metadata or {}
        brand_context = brand_context or {}

        # Try to load brand CTA template
        cta_templates = brand_context.get("brand_assets", {}).get("cta_templates", [])
        default_template = None
        if cta_templates and isinstance(cta_templates, list):
            # Find default template or use first one
            default_template = next(
                (t for t in cta_templates if isinstance(t, dict) and t.get("is_default")),
                cta_templates[0] if cta_templates else None,
            )

        if default_template:
            # Use CTA template to populate slide
            brand_name = brand_context.get("identity", {}).get("brand_name", "")

            # Populate template placeholders
            headline = default_template.get("headline_template", "")
            if "{brand}" in headline or "{product}" in headline:
                headline = headline.replace("{brand}", brand_name).replace("{product}", brand_name)
            if not headline:
                # TODO: Load from brand_context.brand_profile.get("default_cta_text", "Take Action")
                headline = text_payload.cta or "Take Action"

            supporting_line = default_template.get("body_template", "")
            if "{brand}" in supporting_line or "{product}" in supporting_line:
                supporting_line = supporting_line.replace("{brand}", brand_name).replace("{product}", brand_name)
            if not supporting_line:
                # Fallback to last stat/proof point
                stat_highlights = metadata.get("stat_highlights", []) or []
                proof_points = metadata.get("proof_points", []) or []
                if stat_highlights:
                    supporting_line = stat_highlights[-1]
                elif proof_points:
                    supporting_line = proof_points[-1]

            # TODO: Load fallback from brand_context.brand_profile.get("default_cta_text", "Learn More")
            cta_text = default_template.get("button_text", text_payload.cta or "Learn More")

            # Extract CTA styling
            cta_style = {
                "background_color": default_template.get("button_color"),
                "text_color": default_template.get("button_text_color", "#FFFFFF"),
                "button_style": default_template.get("button_style", "rounded"),
                "icon": default_template.get("icon_hint"),
            }

            visual_theme = default_template.get("visual_theme", "illustration")
        else:
            # Fallback to generic closing slide
            # TODO: Load from brand_context.brand_profile.get("default_cta_text", "Take Action")
            headline = text_payload.cta or "Take Action"

            stat_highlights = metadata.get("stat_highlights", []) or []
            proof_points = metadata.get("proof_points", []) or []

            supporting_line = ""
            if stat_highlights:
                supporting_line = stat_highlights[-1]
            elif proof_points:
                supporting_line = proof_points[-1]

            cta_text = text_payload.cta
            cta_style = {}
            visual_theme = "illustration"

        visual_elements = cls._select_visual_elements_for_role("closing", metadata, brand_assets)

        return SlideBlueprint(
            slide_number=999,  # Will be renumbered
            role="closing",
            headline=headline,
            supporting_line=supporting_line,
            cta=cta_text,
            visual_elements=visual_elements,
            layout_archetype="editorial_corner_split",
            primary_visual_type=visual_theme,
            cta_style=cta_style,
        )

    @classmethod
    def _plan_image_driven_slides(
        cls,
        text_payload: StructuredTextPayload,
        reference_images: list[dict[str, Any]],
        brand_assets: list[dict[str, Any]],
        max_detail_slides: int,
    ) -> list[SlideBlueprint]:
        """Plan slides driven by reference images - one image per slide.

        CRITICAL: Each slide must bind to a valid reference image storage_path.
        """
        slides = []
        metadata = text_payload.metadata or {}
        proof_points = metadata.get("proof_points", []) or []
        stat_highlights = metadata.get("stat_highlights", []) or []

        # Create one slide per reference image (up to max_detail_slides)
        num_slides = min(len(reference_images), max_detail_slides, 6)

        skipped_count = 0
        for idx in range(num_slides):
            ref_image = reference_images[idx]
            slide_number = idx + 2  # Start from slide 2 (after cover)

            # CRITICAL: Extract and validate image storage path
            storage_path = ref_image.get("storage_path") or ref_image.get("path")
            if not storage_path or storage_path == "unknown" or storage_path == "null":
                logger.warning(f"Skipping slide {slide_number}: reference image {idx} has invalid storage_path '{storage_path}'")
                skipped_count += 1
                continue

            # Use stat highlights or proof points for headlines if available
            if idx < len(stat_highlights):
                headline = stat_highlights[idx]
            elif idx < len(proof_points):
                headline = proof_points[idx]
            elif idx == 0 and text_payload.headline:
                headline = text_payload.headline
            else:
                headline = f"Slide {idx + 1}"

            # Use proof points or body text for supporting lines
            if idx < len(proof_points) and idx != len(stat_highlights):
                supporting_line = proof_points[idx] if idx < len(proof_points) else None
            elif text_payload.body and idx == 0:
                # Use first 150 chars of body for first detail slide
                supporting_line = text_payload.body[:150] + ("..." if len(text_payload.body) > 150 else "")
            else:
                supporting_line = None

            caption = ref_image.get("caption") or ref_image.get("name") or ""

            # Visual elements include the reference image
            visual_elements = [storage_path]

            logger.info(f"Carousel slide {slide_number}: bound reference image '{storage_path}' (caption: '{caption[:50] if caption else 'none'}')")

            slides.append(SlideBlueprint(
                slide_number=slide_number,
                role="detail",
                headline=headline,
                supporting_line=supporting_line,
                visual_elements=visual_elements,
                layout_archetype="image_led_social",
                primary_visual_type="image"
            ))

        if skipped_count > 0:
            logger.warning(f"Skipped {skipped_count}/{num_slides} slides due to invalid storage_path values")

        logger.info(f"Created {len(slides)} image-driven carousel slides from {len(reference_images)} reference images")
        return slides

    @classmethod
    def _plan_data_driven_slides(
        cls,
        text_payload: StructuredTextPayload,
        data_elements: list[ChartSpec],
        brand_assets: list[dict[str, Any]],
        max_detail_slides: int,
    ) -> list[SlideBlueprint]:
        """Plan slides for data-driven carousel."""
        slides = []
        metadata = text_payload.metadata or {}
        stat_highlights = metadata.get("stat_highlights", []) or []
        proof_points = metadata.get("proof_points", []) or []
        
        # Slide 2: Context/setup slide
        context_headline = stat_highlights[0] if stat_highlights else "Key Insight"
        context_supporting = proof_points[0] if proof_points else text_payload.body[:200]
        
        slides.append(SlideBlueprint(
            slide_number=2,
            role="detail",
            headline=context_headline,
            supporting_line=context_supporting,
            proof_points=proof_points[:2] if len(proof_points) > 2 else [],
            visual_elements=cls._select_visual_elements_for_role("context", metadata, brand_assets),
            layout_archetype="insight_corner_split",
            primary_visual_type="illustration"
        ))
        
        # Slide 3: Data visualization slide
        primary_chart = data_elements[0] if data_elements else None
        
        if primary_chart:
            slides.append(SlideBlueprint(
                slide_number=3,
                role="data_viz",
                headline=primary_chart.title or "Data Insights",
                supporting_line=primary_chart.subtitle,
                chart_spec=primary_chart,
                visual_elements=["chart"],
                layout_archetype="infographic_stack",
                primary_visual_type="chart"
            ))
        
        return slides
    
    @classmethod
    def _plan_multi_point_slides(
        cls,
        text_payload: StructuredTextPayload,
        brand_assets: list[dict[str, Any]],
        max_detail_slides: int,
    ) -> list[SlideBlueprint]:
        """Plan slides for multi-point carousel (3+ proof points)."""
        slides = []
        metadata = text_payload.metadata or {}
        proof_points = metadata.get("proof_points", []) or []
        stat_highlights = metadata.get("stat_highlights", []) or []
        
        # Create detail slides for each major point
        num_detail_slides = min(len(proof_points), max_detail_slides)
        
        for i in range(num_detail_slides):
            headline = stat_highlights[i] if i < len(stat_highlights) else f"Key Point {i+1}"
            supporting_line = proof_points[i] if i < len(proof_points) else ""
            
            # Get additional proof points for this slide
            slide_proof_points = []
            if i * 2 + 1 < len(proof_points):
                slide_proof_points = proof_points[i * 2 : i * 2 + 2]
            
            slides.append(SlideBlueprint(
                slide_number=i + 2,
                role="detail",
                headline=headline,
                supporting_line=supporting_line,
                proof_points=slide_proof_points,
                visual_elements=cls._select_visual_elements_for_role("detail", metadata, brand_assets),
                layout_archetype="checklist_corner_card" if slide_proof_points else "insight_corner_split",
                primary_visual_type="illustration"
            ))
        
        return slides
    
    @classmethod
    def _plan_simple_slides(
        cls,
        text_payload: StructuredTextPayload,
        brand_assets: list[dict[str, Any]],
        max_detail_slides: int,
    ) -> list[SlideBlueprint]:
        """Plan slides for simple carousel (1-2 detail slides)."""
        slides = []
        metadata = text_payload.metadata or {}
        
        # Single detail slide
        supporting_line = metadata.get("supporting_line") or text_payload.body[:200]
        proof_points = metadata.get("proof_points", []) or []
        
        slides.append(SlideBlueprint(
            slide_number=2,
            role="detail",
            headline="Key Insight",
            supporting_line=supporting_line,
            proof_points=proof_points[:3],
            visual_elements=cls._select_visual_elements_for_role("detail", metadata, brand_assets),
            layout_archetype="insight_corner_split",
            primary_visual_type="illustration"
        ))
        
        return slides
    
    @classmethod
    def _select_visual_elements_for_role(
        cls,
        role: str,
        metadata: dict[str, Any],
        brand_assets: list[dict[str, Any]],
    ) -> list[str]:
        """Select appropriate visual elements for a slide role."""
        visual_elements = []
        
        requested_elements = metadata.get("visual_elements", []) or []
        
        if role == "cover":
            # Cover slide: hero illustration or brand visual
            if "person" in requested_elements:
                visual_elements.append("person_illustration")
            if "icon" in requested_elements:
                visual_elements.append("brand_icon")
            if not visual_elements:
                visual_elements.append("hero_illustration")
        
        elif role == "context":
            # Context slide: supporting illustration
            if "icon" in requested_elements:
                visual_elements.append("icon_set")
            else:
                visual_elements.append("supporting_illustration")
        
        elif role == "detail":
            # Detail slide: icons or small illustrations
            visual_elements.append("icon_grid")
        
        elif role == "data_viz":
            # Data viz slide: chart is primary
            visual_elements.append("chart")
        
        elif role == "closing":
            # Closing slide: CTA-focused visual
            visual_elements.append("cta_illustration")
        
        return visual_elements
    
    @classmethod
    def renumber_slides(cls, slides: list[SlideBlueprint]) -> list[SlideBlueprint]:
        """Renumber slides sequentially."""
        for i, slide in enumerate(slides, start=1):
            slide.slide_number = i
        return slides
