from docx import Document

from app.services.content_format_guide import ContentFormatGuideService


def test_content_format_guide_loads_richer_format_and_platform_guidance(tmp_path, monkeypatch) -> None:
    guide_path = tmp_path / "Content Formats Guide for SM.docx"
    document = Document()
    for line in [
        "Content Formats Guide: Infographic, Static, and Carousel",
        "1. Definitions",
        "Static Content",
        "Static content is a single image post that delivers one clear message in one frame.",
        "Carousel",
        "A carousel is a multi-slide, swipeable post for storytelling.",
        "Infographic",
        "An infographic is a single, information-dense visual designed to educate quickly.",
        "2. Platform Differences (LinkedIn, Instagram, X)",
        "Instagram",
        "Static: Square (1:1) or portrait (4:5) images",
        "Carousel: Up to 10 slides, 1:1 or 4:5",
        "Infographic: Tall 9:16 or 4:5 (preffered)",
        "LinkedIn",
        "Static: Landscape (16:9) or square (1:1)",
        "Carousel: Multi-page PDF (each page = one slide)",
        "Infographic: Single image, 1:1 or landscape",
        "X (Twitter)",
        "Static: Landscape (16:9) preferred",
        "Carousel: No native feature (workarounds only)",
        "Infographic: Single image, 16:9 or 1:1",
        "Key Insight:",
        "LinkedIn carousels must be uploaded as PDFs, while Instagram carousels are image-based.",
        "3. Content Style Expectations",
        "Static Content",
        "What to include:",
        "One strong headline",
        "1-2 supporting lines",
        "A clear visual (illustration/photo/graphic)",
        "Brand logo and CTA",
        "Style:",
        "Clean, minimal, and impactful within 2 seconds.",
        "Carousel",
        "Structure (for a 10 page carousel)",
        "Slide 1: Hook (bold statement/question)",
        "Slides 2-8: One idea per slide",
        "Final Slide: Call-to-action",
        "Structure (for a 5 page carousel) (preferred)",
        "Slide 1: Hook (bold statement/question)",
        "Slides 2, 3 and 4: One idea per slide",
        "Final Slide: Call-to-action",
        "Style:",
        "Consistent design, easy to read, strong narrative flow.",
        "Infographic",
        "What to include:",
        "Title or question at the top",
        "Data points, comparisons, or processes",
        "Visual hierarchy (icons, sections, colors)",
        "Source attribution",
        "Style:",
        "Dense but well-organized. Should educate within 30 seconds.",
        "5. Practical Export Rules",
        "Instagram Static: PNG/JPG",
        "Instagram Carousel: Multiple PNGs or ZIP",
        "LinkedIn Static: PNG/JPG",
        "LinkedIn Carousel: Multi-page PDF",
        "Infographic (All Platforms): PNG (vertical preferred)",
        "6. Summary",
        "Static: One message, one visual, quick impact",
        "Carousel: Multi-step storytelling, swipe-based engagement",
        "Infographic: Data-driven, educational visual",
    ]:
        document.add_paragraph(line)
    document.save(guide_path)

    service = ContentFormatGuideService()
    monkeypatch.setattr(service, "_resolve_path", lambda: guide_path)

    guide = service.load()

    assert "One strong headline" in guide["rules"]["static"]
    assert "One idea per slide" in " ".join(guide["rules"]["carousel"])
    assert "multi-slide, swipeable post for storytelling" in guide["definitions"]["carousel"]
    assert guide["format_expectations"]["carousel"]["preferred_slide_count"] == 5
    assert guide["format_expectations"]["infographic"]["source_attribution_required"] is True
    assert any("Multi-page PDF" in item for item in guide["platform_guidance"]["linkedin"]["notes"])
    assert guide["export_guidance"]["by_platform_format"]["instagram"]["carousel"] == "Multiple PNGs or ZIP"
    assert "uploaded as PDFs" in guide["key_insights"][0]
