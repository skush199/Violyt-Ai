import json
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from app.ai.brand_asset_analysis import BrandAssetAnalyzer
from app.ai.template_vision import TemplateVisionAnalyzer


def test_brand_asset_analyzer_selects_cover_dense_and_cta_pages() -> None:
    analyzer = BrandAssetAnalyzer.__new__(BrandAssetAnalyzer)
    workspace = Path(mkdtemp(prefix="brand-analysis-", dir="C:\\tmp"))

    try:
        images = []
        analysis_paths = []
        page_specs = [
            (
                "page_1.png",
                {
                    "page_dimensions": {"image_width_px": 1000, "image_height_px": 1000},
                    "sentences": [
                        {"text": "Planning your retirement", "bounding_box": {"x": 60, "y": 70, "width": 500, "height": 90}},
                    ],
                },
            ),
            (
                "page_2.png",
                {
                    "page_dimensions": {"image_width_px": 1000, "image_height_px": 1000},
                    "sentences": [
                        {"text": "What to know", "bounding_box": {"x": 40, "y": 60, "width": 420, "height": 70}},
                        {"text": "Step 1", "bounding_box": {"x": 40, "y": 150, "width": 320, "height": 60}},
                        {"text": "Step 2", "bounding_box": {"x": 40, "y": 240, "width": 320, "height": 60}},
                        {"text": "Step 3", "bounding_box": {"x": 40, "y": 330, "width": 320, "height": 60}},
                    ],
                },
            ),
            (
                "page_3.png",
                {
                    "page_dimensions": {"image_width_px": 1000, "image_height_px": 1000},
                    "sentences": [
                        {"text": "Get started today", "bounding_box": {"x": 60, "y": 100, "width": 420, "height": 70}},
                        {"text": "Learn more", "bounding_box": {"x": 60, "y": 820, "width": 240, "height": 50}},
                    ],
                },
            ),
        ]

        for filename, analysis in page_specs:
            image_path = workspace / filename
            image_path.write_bytes(b"placeholder")
            analysis_path = workspace / f"{image_path.stem}_analysis.json"
            analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
            images.append(str(image_path))
            analysis_paths.append(str(analysis_path))

        selected = analyzer._select_representative_visual_pages(
            absolute_path=str(workspace / "deck.pdf"),
            images=images,
            analysis_paths=analysis_paths,
        )

        assert [record["page_index"] for record in selected] == [1, 2, 3]
        assert selected[1]["density_score"] > selected[0]["density_score"]
        assert selected[2]["cta_score"] > 0
    finally:
        rmtree(workspace, ignore_errors=True)


def test_template_vision_analyze_pages_merges_partial_page_results() -> None:
    class StubAnalyzer:
        def __init__(self) -> None:
            self.results = {
                "page-1": {
                    "background_style": {"type": "gradient", "description": "deep blue gradient"},
                    "layout_type": "editorial explainer",
                    "editable_zones": [{"role": "headline"}],
                    "component_motifs": {"numbered_badges": {"detected": True}},
                    "visual_hierarchy": {"focal_role": "headline", "density": "airy"},
                    "content_structure": {"storytelling": "benefit stack", "cta_prominence": "measured"},
                    "image_treatment": {"style": "diagram led"},
                    "brand_cues": {"tone_keywords": ["trustworthy"]},
                },
                "page-2": {
                    "background_style": {"type": "gradient", "description": "deep blue gradient"},
                    "layout_type": "editorial explainer",
                    "editable_zones": [{"role": "headline"}, {"role": "proof_module"}],
                    "component_motifs": {"text_background_boxes": {"detected": True}},
                    "visual_hierarchy": {"focal_role": "proof_module", "density": "dense"},
                    "content_structure": {"storytelling": "data story", "cta_prominence": "subtle"},
                    "image_treatment": {"style": "editorial illustration"},
                    "brand_cues": {"trust_markers": ["data cues"]},
                },
                "page-3": None,
            }

        def analyze(self, image_path, fallback):
            return self.results.get(image_path, fallback)

    fallback = {
        "background_style": {"type": "flat"},
        "layout_type": "template",
        "editable_zones": [],
        "component_motifs": {},
    }

    merged = TemplateVisionAnalyzer.analyze_pages(
        StubAnalyzer(),
        ["page-1", "page-2", "page-3"],
        fallback,
    )

    assert merged["layout_type"] == "editorial explainer"
    assert merged["analysis_confidence"] == 0.6667
    assert len(merged["page_analysis_summary"]) == 2
    assert merged["component_motifs"]["numbered_badges"]["page_support"] == 1
    assert merged["component_motifs"]["text_background_boxes"]["page_support_ratio"] == 0.5
    assert merged["visual_hierarchy"]["focal_role"] in {"headline", "proof_module"}
    assert merged["content_structure"]["cta_prominence"] in {"measured", "subtle"}
    assert merged["image_treatment"]["style"] in {"diagram led", "editorial illustration"}
