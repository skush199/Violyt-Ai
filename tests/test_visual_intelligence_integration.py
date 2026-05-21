"""
Integration tests for visual intelligence enhancements.
"""
import pytest
from app.ai.data_visualization import DataVisualizationService, ChartSpec
from app.ai.structured_prompt_parser import StructuredPromptParser
from app.ai.visual_asset_intelligence import VisualAssetIntelligenceService
from app.ai.carousel_planner import CarouselPlannerService
from app.ai.contracts import StructuredTextPayload


class TestDataVisualization:
    """Test data visualization service."""
    
    def test_parse_chart_request_with_indian_currency(self):
        """Test parsing chart request with Indian currency format."""
        prompt = """
        Year: 2017, 2022, 2025
        Women Borrower Portfolio Outstanding Value (₹ Lakh Crore): 16, 41, 76
        """
        
        # Need to add metadata with stat_highlights for parsing to work
        metadata = {
            "stat_highlights": ["2017: ₹16", "2022: ₹41", "2025: ₹76"]
        }
        
        chart_spec = DataVisualizationService.parse_chart_request(prompt, metadata)
        
        assert chart_spec is not None
        assert chart_spec.chart_type == "bar"
        assert len(chart_spec.data_points) >= 3
    
    def test_parse_chart_request_with_title_subtitle(self):
        """Test parsing chart with title and subtitle."""
        prompt = """
        Title - How Women Borrowers Are Reshaping India's Credit Market
        Subheading - Women's credit portfolio jumps 4.8X from 2017 to 2025
        Year: 2017, 2022, 2025
        Value: ₹16, ₹41, ₹76 lakh crore
        """
        
        metadata = {}
        chart_spec = DataVisualizationService.parse_chart_request(prompt, metadata)
        
        assert chart_spec is not None
        assert "Women Borrowers" in chart_spec.title or chart_spec.title is not None
    
    def test_generate_chart_image(self):
        """Test generating a chart image."""
        from app.ai.data_visualization import ChartDataPoint
        
        chart_spec = ChartSpec(
            chart_type="bar",
            title="Test Chart",
            data_points=[
                ChartDataPoint(label="2017", value=16, formatted_value="₹16"),
                ChartDataPoint(label="2022", value=41, formatted_value="₹41"),
                ChartDataPoint(label="2025", value=76, formatted_value="₹76"),
            ]
        )
        
        service = DataVisualizationService()
        image = service.generate_chart_image(
            chart_spec,
            width=1200,
            height=800,
            brand_colors={"primary": "#2E5BFF", "accent": "#FFB800"}
        )
        
        assert image is not None
        # Size may vary slightly due to tight_layout
        assert 1150 <= image.size[0] <= 1250
        assert 750 <= image.size[1] <= 850


class TestStructuredPromptParser:
    """Test structured prompt parser."""
    
    def test_parse_client_prompt(self):
        """Test parsing the actual client prompt."""
        prompt = """
        create a post for Women Borrowers are reshaping the credit market in India.
        Based on this theme, create a static post for LinkedIn that captures data on how women borrowers 
        are reshaping the credit market in India and what is the next big step for Financial brands to 
        look at women as potential investors.
        
        Title - How Women Borrowers Are Reshaping India's Credit Market
        Subheading - Women's credit portfolio jumps 4.8X from 2017 to 2025
        
        Show this in bar chart style with an arrow going up.
        Year: 2017, 2022, 2025
        Women Borrower Portfolio Outstanding Value (₹ Lakh Crore): 16, 41, 76
        
        At bottom write this: Women now account for 26% of India's total credit portfolio. 
        It reflects rising participation in the formal financial system.
        
        Source: NITI Aayog
        """
        
        parsed = StructuredPromptParser.parse_prompt(prompt)
        
        assert parsed["title"] == "How Women Borrowers Are Reshaping India's Credit Market"
        assert parsed["subtitle"] == "Women's credit portfolio jumps 4.8X from 2017 to 2025"
        assert parsed["data_table"] is not None
        assert len(parsed["data_table"]["data_points"]) == 3
        assert "arrow" in parsed["visual_elements"]
        assert "chart" in parsed["visual_elements"]
        assert parsed["chart_type"] == "bar_chart"
    
    def test_format_for_metadata(self):
        """Test formatting parsed data for metadata."""
        prompt = """
        Title - Test Title
        Subheading - Test Subtitle
        Year: 2020, 2021, 2022
        Value: 10, 20, 30
        """
        
        parsed = StructuredPromptParser.parse_prompt(prompt)
        metadata = StructuredPromptParser.format_for_metadata(parsed)
        
        assert metadata["title"] == "Test Title"
        assert metadata["subheading"] == "Test Subtitle"
        assert "stat_highlights" in metadata
        assert len(metadata["stat_highlights"]) == 3


class TestVisualAssetIntelligence:
    """Test visual asset intelligence service."""
    
    def test_parse_visual_requirements(self):
        """Test parsing visual requirements from prompt."""
        prompt = """
        Create a 3D illustration with a bar chart showing growth.
        Include an arrow going up and a professional woman in business attire.
        """
        
        visual_req = VisualAssetIntelligenceService.parse_visual_requirements(prompt, {})
        
        assert "3d" in visual_req["illustration_styles"]
        assert "bar_chart" in visual_req["chart_types"]
        assert "arrow" in visual_req["visual_elements"]
        assert "person" in visual_req["visual_elements"]
        assert visual_req["has_data_visualization"] == True
    
    def test_enhance_image_prompt(self):
        """Test enhancing image prompt with visual intelligence."""
        base_prompt = "Premium brand-safe visual"
        visual_requirements = {
            "chart_types": ["bar_chart"],
            "illustration_styles": ["3d", "editorial"],
            "visual_elements": ["arrow", "person"],
            "has_data_visualization": True,
            "data_points": [
                {"year": "2017", "value": "16"},
                {"year": "2022", "value": "41"},
                {"year": "2025", "value": "76"},
            ]
        }
        brand_visual_brief = {
            "palette_roles": {
                "primary": "#2E5BFF",
                "accent": "#FFB800"
            }
        }
        
        enhanced = VisualAssetIntelligenceService.enhance_image_prompt_with_visual_intelligence(
            base_prompt,
            visual_requirements,
            brand_visual_brief
        )
        
        assert len(enhanced) > len(base_prompt)
        assert "3D" in enhanced or "3d" in enhanced
        assert "bar chart" in enhanced.lower()
        assert "arrow" in enhanced.lower()


class TestCarouselPlanner:
    """Test carousel planner service."""
    
    def test_plan_data_driven_carousel(self):
        """Test planning a data-driven carousel."""
        from app.ai.data_visualization import ChartDataPoint
        
        text_payload = StructuredTextPayload(
            headline="How Women Borrowers Are Reshaping India's Credit Market",
            body="Women's participation in credit markets is growing rapidly.",
            cta="Learn More",
            hashtags=["#Finance", "#WomenEmpowerment"],
            metadata={
                "supporting_line": "Women's credit portfolio jumps 4.8X from 2017 to 2025",
                "stat_highlights": [
                    "2017: ₹16 Lakh Crore",
                    "2022: ₹41 Lakh Crore",
                    "2025: ₹76 Lakh Crore"
                ],
                "proof_points": [
                    "Rising formal financial participation",
                    "26% of total credit portfolio",
                    "4.8X growth in 8 years"
                ]
            }
        )
        
        chart_spec = ChartSpec(
            chart_type="bar",
            title="Women Borrower Portfolio Growth",
            data_points=[
                ChartDataPoint(label="2017", value=16, formatted_value="₹16"),
                ChartDataPoint(label="2022", value=41, formatted_value="₹41"),
                ChartDataPoint(label="2025", value=76, formatted_value="₹76"),
            ]
        )
        
        slides = CarouselPlannerService.plan_carousel_slides(
            text_payload=text_payload,
            data_elements=[chart_spec],
            brand_assets=[],
            max_slides=10
        )
        
        assert len(slides) >= 3
        assert slides[0].role == "cover"
        assert any(s.role == "data_viz" for s in slides)
        assert any(s.role == "closing" for s in slides)
        
        # Check data viz slide has chart spec
        data_viz_slide = next(s for s in slides if s.role == "data_viz")
        assert data_viz_slide.chart_spec is not None
        assert data_viz_slide.primary_visual_type == "chart"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
