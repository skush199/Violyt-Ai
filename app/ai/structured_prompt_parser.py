from __future__ import annotations

import re
from typing import Any


class StructuredPromptParser:
    """
    Parser for extracting structured information from user prompts.
    Handles title/subtitle extraction, data tables, visual element requests, etc.
    """
    
    @classmethod
    def parse_prompt(cls, prompt: str) -> dict[str, Any]:
        """
        Parse a prompt into structured components.
        
        Returns:
            Dictionary with:
            - title: Extracted title
            - subtitle: Extracted subtitle
            - body: Main body text
            - data_table: Extracted data in structured format
            - visual_elements: List of requested visual elements
            - chart_type: Type of chart requested
            - special_instructions: Special formatting or style requests
        """
        result = {
            "title": None,
            "subtitle": None,
            "body": None,
            "data_table": None,
            "visual_elements": [],
            "chart_type": None,
            "special_instructions": [],
            "ordered_story_beats": [],
            "disclaimer_request": {"requested": False, "placement": "", "style": ""},
            "raw_sections": {}
        }
        
        # Extract title
        result["title"] = cls._extract_title(prompt)
        
        # Extract subtitle/subheading
        result["subtitle"] = cls._extract_subtitle(prompt)
        
        # Extract data table
        result["data_table"] = cls._extract_data_table(prompt)
        
        # Extract visual elements
        result["visual_elements"] = cls._extract_visual_elements(prompt)
        
        # Extract chart type
        result["chart_type"] = cls._extract_chart_type(prompt)
        
        # Extract special instructions
        result["special_instructions"] = cls._extract_special_instructions(prompt)

        # Extract ordered story beats for carousel/infographic briefs
        result["ordered_story_beats"] = cls._extract_ordered_story_beats(prompt)

        # Extract disclaimer/footer intent
        result["disclaimer_request"] = cls._extract_disclaimer_request(prompt)
        
        # Extract body (everything not in other sections)
        result["body"] = cls._extract_body(prompt, result)
        
        # Store raw sections for reference
        result["raw_sections"] = cls._extract_raw_sections(prompt)
        
        return result
    
    @classmethod
    def _extract_title(cls, prompt: str) -> str | None:
        """Extract title from prompt."""
        # Pattern: "Title - ..." or "Title: ..."
        patterns = [
            r"[Tt]itle\s*[-:]\s*(.+?)(?:\n|[Ss]ub|$)",
            r"^(.+?)(?:\n[Ss]ub|\n[Yy]ear|\n[Ss]how|\nAt\s+bottom)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, prompt, re.MULTILINE)
            if match:
                title = match.group(1).strip()
                # Clean up if it's too long (likely not a title)
                if len(title) < 200:
                    return title
        
        return None
    
    @classmethod
    def _extract_subtitle(cls, prompt: str) -> str | None:
        """Extract subtitle/subheading from prompt."""
        patterns = [
            r"[Ss]ub(?:title|heading)\s*[-:]\s*(.+?)(?:\n|$)",
            r"[Ss]ub[-\s]?[Hh]eading\s*[-:]\s*(.+?)(?:\n|$)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, prompt, re.MULTILINE)
            if match:
                subtitle = match.group(1).strip()
                if len(subtitle) < 300:
                    return subtitle
        
        return None
    
    @classmethod
    def _extract_data_table(cls, prompt: str) -> dict[str, Any] | None:
        """
        Extract structured data table from prompt.
        
        Handles formats like:
        - "Year: 2017, 2022, 2025\nValue: 16, 41, 76"
        - "2017: 16, 2022: 41, 2025: 76"
        """
        # Pattern 1: Separate rows for labels and values
        year_match = re.search(r"[Yy]ear[\s:]+(.+?)(?:\n|$)", prompt)
        value_match = re.search(r"(?:[Vv]alue|[Aa]mount|[Pp]ortfolio)[^:]*[\s:]+(.+?)(?:\n|$)", prompt)
        
        if year_match and value_match:
            years = re.findall(r"\d{4}", year_match.group(1))
            values_text = value_match.group(1)
            
            # Extract numeric values with units
            value_pattern = r"[₹$€£¥]?\s*(\d+(?:[.,]\d+)*)\s*(lakh\s+crore|crore|lakh|billion|million|thousand|k|m|b)?"
            value_matches = re.findall(value_pattern, values_text, re.IGNORECASE)
            
            if years and value_matches:
                data_points = []
                for i, year in enumerate(years):
                    if i < len(value_matches):
                        value_str, unit = value_matches[i]
                        data_points.append({
                            "label": year,
                            "value": value_str,
                            "unit": unit or ""
                        })
                
                return {
                    "type": "series",
                    "x_axis": "year",
                    "y_axis": "value",
                    "data_points": data_points
                }
        
        # Pattern 2: Inline format "2017: 16, 2022: 41"
        inline_pattern = r"(\d{4})[\s:]+[₹$€£¥]?\s*(\d+(?:[.,]\d+)*)\s*(lakh\s+crore|crore|lakh|billion|million|k|m|b)?"
        inline_matches = re.findall(inline_pattern, prompt, re.IGNORECASE)
        
        if inline_matches:
            data_points = []
            for year, value_str, unit in inline_matches:
                data_points.append({
                    "label": year,
                    "value": value_str,
                    "unit": unit or ""
                })
            
            return {
                "type": "series",
                "x_axis": "year",
                "y_axis": "value",
                "data_points": data_points
            }
        
        return None
    
    @classmethod
    def _extract_visual_elements(cls, prompt: str) -> list[str]:
        """Extract requested visual elements."""
        elements = []
        prompt_lower = prompt.lower()
        
        element_patterns = {
            "arrow": r"arrow|pointing|direction|upward|downward",
            "person": r"person|people|woman|man|professional|business\s+person",
            "chart": r"chart|graph|visualization|bar\s+chart|line\s+chart",
            "icon": r"icon|symbol|pictogram",
            "calculator": r"calculator|calculation",
            "money": r"money|currency|cash|coins|bills",
            "globe": r"globe|world|global",
            "illustration": r"illustration|illustrated|custom\s+art",
        }
        
        for element, pattern in element_patterns.items():
            if re.search(pattern, prompt_lower):
                elements.append(element)
        
        return elements
    
    @classmethod
    def _extract_chart_type(cls, prompt: str) -> str | None:
        """Extract the type of chart requested."""
        prompt_lower = prompt.lower()
        
        chart_types = {
            "bar_chart": r"bar\s+chart|bar\s+graph|vertical\s+bar",
            "line_chart": r"line\s+chart|line\s+graph|trend\s+line",
            "pie_chart": r"pie\s+chart|donut\s+chart",
            "area_chart": r"area\s+chart|area\s+graph",
            "comparison": r"comparison|versus|vs\.|compare",
            "infographic": r"infographic|data\s+visual",
        }
        
        for chart_type, pattern in chart_types.items():
            if re.search(pattern, prompt_lower):
                return chart_type
        
        return None
    
    @classmethod
    def _extract_special_instructions(cls, prompt: str) -> list[str]:
        """Extract special formatting or style instructions."""
        instructions = []
        prompt_lower = prompt.lower()
        
        # Style instructions
        if re.search(r"show\s+(?:this\s+)?in\s+(.+?)\s+style", prompt_lower):
            match = re.search(r"show\s+(?:this\s+)?in\s+(.+?)\s+style", prompt_lower)
            if match:
                instructions.append(f"style: {match.group(1)}")
        
        # Position instructions
        if re.search(r"at\s+(?:the\s+)?bottom", prompt_lower):
            instructions.append("position: bottom")
        if re.search(r"at\s+(?:the\s+)?top", prompt_lower):
            instructions.append("position: top")
        
        # Arrow direction
        if re.search(r"arrow\s+going\s+up|upward\s+arrow", prompt_lower):
            instructions.append("arrow: upward")
        if re.search(r"arrow\s+going\s+down|downward\s+arrow", prompt_lower):
            instructions.append("arrow: downward")
        
        # Source attribution
        source_match = re.search(r"[Ss]ource[\s:]+(.+?)(?:\n|$)", prompt)
        if source_match:
            instructions.append(f"source: {source_match.group(1).strip()}")
        
        return instructions

    @classmethod
    def _extract_ordered_story_beats(cls, prompt: str) -> list[str]:
        """Extract explicit ordered story/narrative instructions from long-form briefs."""
        prompt_text = " ".join(str(prompt or "").split())
        if not prompt_text:
            return []

        segment = ""
        segment_patterns = [
            r"Structure it like (?:a )?(?:story|journey)\s*:\s*(.+?)(?=\bTone\s*:|\bDesign direction\s*:|\bImportant\s*:|$)",
            r"Structure it as\s*:\s*(.+?)(?=\bTone\s*:|\bDesign direction\s*:|\bImportant\s*:|$)",
            r"Step-wise storytelling\s*[:\-]?\s*(.+?)(?=\bTone\s*:|\bDesign direction\s*:|\bImportant\s*:|$)",
        ]
        for pattern in segment_patterns:
            match = re.search(pattern, prompt_text, re.IGNORECASE)
            if match:
                segment = match.group(1).strip()
                break

        if not segment:
            segment = prompt_text

        action_pattern = re.compile(
            r"(?P<prefix>Start with|Begin with|Open with|Lead with|Explain|Show|Then connect(?: it)?(?: to)?|Connect(?: it)?(?: to)?|Then|Move to|Follow with|End with|Close with|Finish with)\s+"
            r"(?P<body>.+?)(?=(?:\s+(?:Start with|Begin with|Open with|Lead with|Explain|Show|Then connect(?: it)?(?: to)?|Connect(?: it)?(?: to)?|Then|Move to|Follow with|End with|Close with|Finish with)\b)|$)",
            re.IGNORECASE,
        )
        beats: list[str] = []
        for match in action_pattern.finditer(segment):
            prefix = " ".join(str(match.group("prefix") or "").split()).strip()
            body = " ".join(str(match.group("body") or "").split()).strip(" .;:-")
            text = f"{prefix} {body}".strip()
            if text and text.casefold() not in {item.casefold() for item in beats}:
                beats.append(text)

        if beats:
            return beats[:8]

        stepwise_match = re.search(
            r"step(?:-|\s)?by(?:-|\s)?step.+?\bwith\s+(.+?)(?=\bTone\s*:|\bDesign direction\s*:|\bImportant\s*:|$)",
            prompt_text,
            re.IGNORECASE,
        )
        if stepwise_match:
            raw_items = re.split(r",|\band\b", stepwise_match.group(1))
            stepwise_beats = [
                " ".join(item.split()).strip(" .;:-")
                for item in raw_items
                if " ".join(item.split()).strip(" .;:-")
            ]
            if stepwise_beats:
                return stepwise_beats[:8]

        line_candidates = [
            re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
            for line in re.split(r"(?:\n|(?<=\.)\s+)", segment)
            if str(line or "").strip()
        ]
        for line in line_candidates:
            lowered = line.casefold()
            if any(
                lowered.startswith(prefix)
                for prefix in (
                    "start with",
                    "begin with",
                    "open with",
                    "lead with",
                    "explain",
                    "show",
                    "then connect",
                    "connect",
                    "move to",
                    "follow with",
                    "end with",
                    "close with",
                    "finish with",
                )
            ):
                if lowered not in {item.casefold() for item in beats}:
                    beats.append(line.strip(" .;:-"))
        return beats[:8]

    @classmethod
    def _extract_disclaimer_request(cls, prompt: str) -> dict[str, Any]:
        """Extract whether the prompt explicitly requests a disclaimer/footer."""
        prompt_lower = str(prompt or "").lower()
        requested = "disclaimer" in prompt_lower
        placement = ""
        style = ""
        if requested:
            if any(token in prompt_lower for token in ("bottom", "footer", "at the bottom")):
                placement = "bottom_footer"
            elif "top" in prompt_lower:
                placement = "top"
            if "risk disclaimer" in prompt_lower:
                style = "financial_risk"
            elif "subtle" in prompt_lower or "small" in prompt_lower:
                style = "subtle"
        return {
            "requested": requested,
            "placement": placement,
            "style": style,
        }
    
    @classmethod
    def _extract_body(cls, prompt: str, parsed_result: dict[str, Any]) -> str | None:
        """Extract the main body text, excluding other extracted sections."""
        # Remove title, subtitle, data sections
        body = prompt
        
        # Remove title line
        if parsed_result.get("title"):
            body = re.sub(r"[Tt]itle\s*[-:]\s*.+?(?:\n|$)", "", body, count=1)
        
        # Remove subtitle line
        if parsed_result.get("subtitle"):
            body = re.sub(r"[Ss]ub(?:title|heading)\s*[-:]\s*.+?(?:\n|$)", "", body, count=1)
        
        # Remove data table lines
        body = re.sub(r"[Yy]ear[\s:]+.+?(?:\n|$)", "", body)
        body = re.sub(r"(?:[Vv]alue|[Aa]mount|[Pp]ortfolio)[^:]*[\s:]+.+?(?:\n|$)", "", body)
        
        # Remove "Show this in..." instructions
        body = re.sub(r"[Ss]how\s+this\s+in\s+.+?(?:\n|$)", "", body)
        
        # Remove "At bottom write..." instructions
        body = re.sub(r"[Aa]t\s+bottom\s+write\s+this:.+?(?:\n|$)", "", body, flags=re.DOTALL)
        
        # Remove source line
        body = re.sub(r"[Ss]ource[\s:]+.+?(?:\n|$)", "", body)
        
        # Clean up
        body = body.strip()
        
        return body if body else None
    
    @classmethod
    def _extract_raw_sections(cls, prompt: str) -> dict[str, str]:
        """Extract all identifiable sections as raw text."""
        sections = {}
        
        # Title section
        title_match = re.search(r"([Tt]itle\s*[-:]\s*.+?)(?:\n|$)", prompt)
        if title_match:
            sections["title"] = title_match.group(1).strip()
        
        # Subtitle section
        subtitle_match = re.search(r"([Ss]ub(?:title|heading)\s*[-:]\s*.+?)(?:\n|$)", prompt)
        if subtitle_match:
            sections["subtitle"] = subtitle_match.group(1).strip()
        
        # Data section
        data_match = re.search(r"([Yy]ear[\s:]+.+?(?:\n|$)(?:[Vv]alue|[Aa]mount).+?(?:\n|$))", prompt, re.DOTALL)
        if data_match:
            sections["data"] = data_match.group(1).strip()
        
        # Bottom text section
        bottom_match = re.search(r"([Aa]t\s+bottom\s+write\s+this:.+?)(?:\n[Ss]ource|$)", prompt, re.DOTALL)
        if bottom_match:
            sections["bottom_text"] = bottom_match.group(1).strip()
        
        # Source section
        source_match = re.search(r"([Ss]ource[\s:]+.+?)(?:\n|$)", prompt)
        if source_match:
            sections["source"] = source_match.group(1).strip()
        
        return sections
    
    @classmethod
    def format_for_metadata(cls, parsed: dict[str, Any]) -> dict[str, Any]:
        """
        Format parsed prompt data for use in metadata fields.
        
        Returns structured metadata that can be used in text payload.
        """
        metadata = {}
        
        if parsed.get("title"):
            metadata["title"] = parsed["title"]
        
        if parsed.get("subtitle"):
            metadata["subheading"] = parsed["subtitle"]
            metadata["supporting_line"] = parsed["subtitle"]
        
        if parsed.get("data_table"):
            data_table = parsed["data_table"]
            stat_highlights = []
            for dp in data_table.get("data_points", []):
                stat_highlights.append(f"{dp['label']}: {dp['value']} {dp['unit']}")
            metadata["stat_highlights"] = stat_highlights
        
        if parsed.get("visual_elements"):
            metadata["visual_elements"] = parsed["visual_elements"]
        
        if parsed.get("chart_type"):
            metadata["chart_type"] = parsed["chart_type"]
        
        if parsed.get("special_instructions"):
            metadata["special_instructions"] = parsed["special_instructions"]

        if parsed.get("ordered_story_beats"):
            metadata["ordered_story_beats"] = [
                str(item).strip()
                for item in (parsed.get("ordered_story_beats") or [])
                if str(item).strip()
            ][:8]

        disclaimer_request = parsed.get("disclaimer_request")
        if isinstance(disclaimer_request, dict) and disclaimer_request.get("requested"):
            metadata["disclaimer_request"] = {
                "requested": True,
                "placement": str(disclaimer_request.get("placement") or "").strip(),
                "style": str(disclaimer_request.get("style") or "").strip(),
            }
        
        return metadata
