from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.path import Path as MplPath
import numpy as np
from PIL import Image


@dataclass
class ChartDataPoint:
    """Single data point in a chart."""
    label: str
    value: float
    formatted_value: str | None = None
    color: str | None = None


@dataclass
class ChartSpec:
    """Specification for a chart to be rendered."""
    chart_type: Literal["bar", "line", "pie", "area", "comparison", "timeline"]
    title: str | None = None
    subtitle: str | None = None
    data_points: list[ChartDataPoint] = None
    x_label: str | None = None
    y_label: str | None = None
    colors: list[str] | None = None
    style: dict[str, Any] | None = None
    annotations: list[dict[str, Any]] | None = None
    
    def __post_init__(self):
        if self.data_points is None:
            self.data_points = []
        if self.colors is None:
            self.colors = []
        if self.style is None:
            self.style = {}
        if self.annotations is None:
            self.annotations = []


class DataVisualizationService:
    """
    Service for parsing data visualization requests from prompts and generating
    professional charts using matplotlib.
    """
    
    CURRENCY_PATTERNS = {
        "rupee": r"[₹]\s*(\d+(?:[.,]\d+)*)\s*(lakh\s+crore|crore|lakh|thousand|k|m|b)?",
        "dollar": r"[$]\s*(\d+(?:[.,]\d+)*)\s*(billion|million|thousand|k|m|b)?",
        "euro": r"[€]\s*(\d+(?:[.,]\d+)*)\s*(billion|million|thousand|k|m|b)?",
        "generic": r"(\d+(?:[.,]\d+)*)\s*(lakh\s+crore|crore|lakh|billion|million|thousand|k|m|b)?",
    }
    
    MULTIPLIERS = {
        "lakh crore": 1_00_00_000,
        "crore": 1_00_00_000,
        "lakh": 1_00_000,
        "billion": 1_000_000_000,
        "million": 1_000_000,
        "thousand": 1_000,
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
    }

    @classmethod
    def parse_chart_request(cls, prompt: str, metadata: dict[str, Any] | None = None) -> ChartSpec | None:
        """
        Parse a prompt to extract chart specifications.
        
        Examples:
        - "bar chart showing 2017: 16, 2022: 41, 2025: 76"
        - "line graph of growth from 2020 to 2025"
        - "comparison of A vs B"
        """
        prompt_lower = prompt.lower()
        metadata = metadata or {}
        
        # Detect chart type
        chart_type = cls._detect_chart_type(prompt_lower)
        if not chart_type:
            return None
        
        # Extract title and subtitle
        title, subtitle = cls._extract_title_subtitle(prompt, metadata)
        
        # Extract data points
        data_points = cls._extract_data_points(prompt, metadata)
        
        if not data_points:
            return None
        
        # Extract labels
        x_label, y_label = cls._extract_axis_labels(prompt, metadata)
        
        # Detect annotations (like arrows, highlights)
        annotations = cls._extract_annotations(prompt)
        
        return ChartSpec(
            chart_type=chart_type,
            title=title,
            subtitle=subtitle,
            data_points=data_points,
            x_label=x_label,
            y_label=y_label,
            annotations=annotations,
        )
    
    @classmethod
    def _detect_chart_type(cls, prompt_lower: str) -> str | None:
        """Detect the type of chart requested."""
        if re.search(r"bar\s+chart|bar\s+graph|vertical\s+bar|horizontal\s+bar", prompt_lower):
            return "bar"
        if re.search(r"line\s+chart|line\s+graph|trend\s+line", prompt_lower):
            return "line"
        if re.search(r"pie\s+chart|donut\s+chart", prompt_lower):
            return "pie"
        if re.search(r"area\s+chart|area\s+graph", prompt_lower):
            return "area"
        if re.search(r"comparison|versus|vs\.|compare", prompt_lower):
            return "comparison"
        if re.search(r"timeline|chronological|over\s+time", prompt_lower):
            return "timeline"
        
        # Default to bar if data is present
        if re.search(r"\d{4}[\s:]+[₹$€£¥]?\s*\d+", prompt_lower):
            return "bar"
        
        return None
    
    @classmethod
    def _extract_title_subtitle(cls, prompt: str, metadata: dict[str, Any]) -> tuple[str | None, str | None]:
        """Extract title and subtitle from prompt or metadata."""
        title = None
        subtitle = None
        
        # Check metadata first
        if metadata:
            title = metadata.get("title") or metadata.get("headline")
            subtitle = metadata.get("subtitle") or metadata.get("subheading") or metadata.get("supporting_line")
        
        # Parse from prompt if not in metadata
        if not title:
            title_match = re.search(r"[Tt]itle[\s:-]+(.+?)(?:\n|[Ss]ub|$)", prompt)
            if title_match:
                title = title_match.group(1).strip()
        
        if not subtitle:
            subtitle_match = re.search(r"[Ss]ub(?:title|heading)[\s:-]+(.+?)(?:\n|$)", prompt)
            if subtitle_match:
                subtitle = subtitle_match.group(1).strip()
        
        return title, subtitle
    
    @classmethod
    def _extract_data_points(cls, prompt: str, metadata: dict[str, Any]) -> list[ChartDataPoint]:
        """Extract data points from prompt or metadata."""
        data_points = []
        
        # Try to extract structured data from prompt
        # Pattern: "Year: 2017, 2022, 2025\nValue: 16, 41, 76"
        year_match = re.search(r"[Yy]ear[\s:]+(.+?)(?:\n|[Vv]alue)", prompt)
        value_match = re.search(r"[Vv]alue[^:]*[\s:]+(.+?)(?:\n|$)", prompt)
        
        if year_match and value_match:
            years = re.findall(r"\d{4}", year_match.group(1))
            values_text = value_match.group(1)
            
            # Extract currency values
            for pattern_name, pattern in cls.CURRENCY_PATTERNS.items():
                value_matches = re.findall(pattern, values_text)
                if value_matches:
                    for i, (value_str, unit) in enumerate(value_matches):
                        if i < len(years):
                            value_num = cls._parse_numeric_value(value_str, unit)
                            formatted = cls._format_value(value_num, unit or "")
                            data_points.append(ChartDataPoint(
                                label=years[i],
                                value=value_num,
                                formatted_value=formatted
                            ))
                    break
        
        # Try inline pattern: "2017: ₹16, 2022: ₹41, 2025: ₹76"
        if not data_points:
            inline_matches = re.findall(
                r"(\d{4})[\s:]+[₹$€£¥]?\s*(\d+(?:[.,]\d+)*)\s*(lakh\s+crore|crore|lakh|billion|million|thousand|k|m|b)?",
                prompt,
                re.IGNORECASE
            )
            for year, value_str, unit in inline_matches:
                value_num = cls._parse_numeric_value(value_str, unit)
                formatted = cls._format_value(value_num, unit or "")
                data_points.append(ChartDataPoint(
                    label=year,
                    value=value_num,
                    formatted_value=formatted
                ))
        
        # Try metadata stat_highlights
        if not data_points and metadata:
            stat_highlights = metadata.get("stat_highlights", []) or []
            for stat in stat_highlights:
                if not isinstance(stat, str):
                    continue
                match = re.search(r"(\d{4})[\s:]+[₹$€£¥]?\s*(\d+(?:[.,]\d+)*)\s*(lakh\s+crore|crore|lakh|billion|million|k|m|b)?", stat, re.IGNORECASE)
                if match:
                    year, value_str, unit = match.groups()
                    value_num = cls._parse_numeric_value(value_str, unit or "")
                    formatted = cls._format_value(value_num, unit or "")
                    data_points.append(ChartDataPoint(
                        label=year,
                        value=value_num,
                        formatted_value=formatted
                    ))
        
        return data_points
    
    @classmethod
    def _parse_numeric_value(cls, value_str: str, unit: str | None) -> float:
        """Parse a numeric value string with optional unit."""
        # Remove commas and convert to float
        value_str = value_str.replace(",", "")
        base_value = float(value_str)
        
        # Apply multiplier if unit is present
        if unit:
            unit_lower = unit.lower().strip()
            multiplier = cls.MULTIPLIERS.get(unit_lower, 1)
            return base_value * multiplier
        
        return base_value
    
    @classmethod
    def _format_value(cls, value: float, unit: str) -> str:
        """Format a numeric value for display."""
        unit_lower = unit.lower().strip() if unit else ""
        
        if "lakh crore" in unit_lower or "crore" in unit_lower:
            return f"₹{int(value / 1_00_00_000)}"
        if "lakh" in unit_lower:
            return f"₹{int(value / 1_00_000)}"
        if "billion" in unit_lower or "b" == unit_lower:
            return f"${value / 1_000_000_000:.1f}B"
        if "million" in unit_lower or "m" == unit_lower:
            return f"${value / 1_000_000:.1f}M"
        if "thousand" in unit_lower or "k" == unit_lower:
            return f"${value / 1_000:.1f}K"
        
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.1f}B"
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if value >= 1_000:
            return f"{value / 1_000:.1f}K"
        
        return f"{int(value)}"
    
    @classmethod
    def _extract_axis_labels(cls, prompt: str, metadata: dict[str, Any]) -> tuple[str | None, str | None]:
        """Extract axis labels from prompt."""
        x_label = None
        y_label = None
        
        # Common patterns
        if re.search(r"year|time|date", prompt, re.IGNORECASE):
            x_label = "Year"
        
        if re.search(r"value|amount|portfolio|revenue|sales", prompt, re.IGNORECASE):
            if "lakh crore" in prompt.lower() or "crore" in prompt.lower():
                y_label = "Value (₹ Lakh Crore)"
            elif "billion" in prompt.lower():
                y_label = "Value ($ Billion)"
            elif "million" in prompt.lower():
                y_label = "Value ($ Million)"
            else:
                y_label = "Value"
        
        return x_label, y_label
    
    @classmethod
    def _extract_annotations(cls, prompt: str) -> list[dict[str, Any]]:
        """Extract annotation requests like arrows, highlights."""
        annotations = []
        
        # Detect arrow requests
        if re.search(r"arrow\s+(?:going\s+)?up|upward\s+arrow|growth\s+arrow", prompt, re.IGNORECASE):
            annotations.append({
                "type": "arrow",
                "direction": "up",
                "style": "growth"
            })
        
        if re.search(r"arrow\s+(?:going\s+)?down|downward\s+arrow", prompt, re.IGNORECASE):
            annotations.append({
                "type": "arrow",
                "direction": "down",
                "style": "decline"
            })
        
        # Detect highlight requests
        if re.search(r"highlight|emphasize|focus\s+on", prompt, re.IGNORECASE):
            annotations.append({
                "type": "highlight",
                "style": "emphasis"
            })
        
        return annotations
    
    def generate_chart_image(
        self,
        spec: ChartSpec,
        width: int = 1200,
        height: int = 800,
        brand_colors: dict[str, str] | None = None,
        style: str = "modern"
    ) -> Image.Image:
        """
        Generate a professional chart image from a ChartSpec.
        
        Args:
            spec: Chart specification
            width: Image width in pixels
            height: Image height in pixels
            brand_colors: Brand color palette
            style: Visual style (modern, editorial, minimal)
        
        Returns:
            PIL Image of the rendered chart
        """
        # Set up matplotlib style
        plt.style.use('seaborn-v0_8-darkgrid' if style == "modern" else 'default')
        
        # Create figure
        dpi = 100
        fig, ax = plt.subplots(figsize=(width/dpi, height/dpi), dpi=dpi)
        
        # Apply brand colors if available
        colors = self._get_chart_colors(spec, brand_colors)
        
        # Render based on chart type
        if spec.chart_type == "bar":
            self._render_bar_chart(ax, spec, colors)
        elif spec.chart_type == "line":
            self._render_line_chart(ax, spec, colors)
        elif spec.chart_type == "pie":
            self._render_pie_chart(ax, spec, colors)
        elif spec.chart_type == "area":
            self._render_area_chart(ax, spec, colors)
        elif spec.chart_type == "comparison":
            self._render_comparison_chart(ax, spec, colors)
        elif spec.chart_type == "timeline":
            self._render_timeline_chart(ax, spec, colors)
        
        # Add annotations
        self._add_annotations(ax, spec, colors)
        
        # Style the chart
        self._apply_chart_styling(ax, spec, style)
        
        # Convert to PIL Image
        buf = BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        
        return Image.open(buf)
    
    def _get_chart_colors(self, spec: ChartSpec, brand_colors: dict[str, str] | None) -> list[str]:
        """Get color palette for the chart."""
        if spec.colors:
            return spec.colors
        
        if brand_colors:
            # Use brand colors in priority order
            color_list = []
            for role in ["primary", "secondary", "accent", "tertiary"]:
                if role in brand_colors:
                    color_list.append(brand_colors[role])
            if color_list:
                return color_list
        
        # Default professional color palette
        return ["#2E5BFF", "#8C54FF", "#00D4AA", "#FFB800", "#FF6B9D"]
    
    def _render_bar_chart(self, ax, spec: ChartSpec, colors: list[str]):
        """Render a bar chart."""
        labels = [dp.label for dp in spec.data_points]
        values = [dp.value for dp in spec.data_points]
        formatted_values = [dp.formatted_value or str(int(dp.value)) for dp in spec.data_points]
        
        # Create bars with gradient effect
        bars = ax.bar(labels, values, color=colors[0], edgecolor='white', linewidth=2, alpha=0.9)
        
        # Add value labels on top of bars
        for bar, formatted_val in zip(bars, formatted_values):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   formatted_val,
                   ha='center', va='bottom', fontsize=14, fontweight='bold')
        
        # Set labels
        if spec.x_label:
            ax.set_xlabel(spec.x_label, fontsize=12, fontweight='bold')
        if spec.y_label:
            ax.set_ylabel(spec.y_label, fontsize=12, fontweight='bold')
        
        # Add title
        if spec.title:
            ax.set_title(spec.title, fontsize=16, fontweight='bold', pad=20)
        if spec.subtitle:
            ax.text(0.5, 1.05, spec.subtitle, transform=ax.transAxes,
                   ha='center', fontsize=12, style='italic')
    
    def _render_line_chart(self, ax, spec: ChartSpec, colors: list[str]):
        """Render a line chart."""
        labels = [dp.label for dp in spec.data_points]
        values = [dp.value for dp in spec.data_points]
        
        # Plot line with markers
        ax.plot(labels, values, color=colors[0], linewidth=3, marker='o', 
               markersize=10, markerfacecolor=colors[1] if len(colors) > 1 else colors[0],
               markeredgecolor='white', markeredgewidth=2)
        
        # Add value labels
        for label, value in zip(labels, values):
            formatted_val = self._format_value(value, "")
            ax.annotate(formatted_val, xy=(label, value), xytext=(0, 10),
                       textcoords='offset points', ha='center', fontsize=11, fontweight='bold')
        
        # Set labels
        if spec.x_label:
            ax.set_xlabel(spec.x_label, fontsize=12, fontweight='bold')
        if spec.y_label:
            ax.set_ylabel(spec.y_label, fontsize=12, fontweight='bold')
        
        # Add title
        if spec.title:
            ax.set_title(spec.title, fontsize=16, fontweight='bold', pad=20)
    
    def _render_pie_chart(self, ax, spec: ChartSpec, colors: list[str]):
        """Render a pie chart."""
        labels = [dp.label for dp in spec.data_points]
        values = [dp.value for dp in spec.data_points]
        
        # Create pie chart
        wedges, texts, autotexts = ax.pie(values, labels=labels, colors=colors,
                                          autopct='%1.1f%%', startangle=90,
                                          textprops={'fontsize': 11, 'fontweight': 'bold'})
        
        # Equal aspect ratio ensures circular pie
        ax.axis('equal')
        
        # Add title
        if spec.title:
            ax.set_title(spec.title, fontsize=16, fontweight='bold', pad=20)
    
    def _render_area_chart(self, ax, spec: ChartSpec, colors: list[str]):
        """Render an area chart."""
        labels = [dp.label for dp in spec.data_points]
        values = [dp.value for dp in spec.data_points]
        
        # Plot area
        ax.fill_between(range(len(labels)), values, alpha=0.3, color=colors[0])
        ax.plot(labels, values, color=colors[0], linewidth=3, marker='o', markersize=8)
        
        # Set labels
        if spec.x_label:
            ax.set_xlabel(spec.x_label, fontsize=12, fontweight='bold')
        if spec.y_label:
            ax.set_ylabel(spec.y_label, fontsize=12, fontweight='bold')
        
        # Add title
        if spec.title:
            ax.set_title(spec.title, fontsize=16, fontweight='bold', pad=20)
    
    def _render_comparison_chart(self, ax, spec: ChartSpec, colors: list[str]):
        """Render a comparison chart (grouped bars)."""
        # Similar to bar chart but with grouping
        self._render_bar_chart(ax, spec, colors)
    
    def _render_timeline_chart(self, ax, spec: ChartSpec, colors: list[str]):
        """Render a timeline chart."""
        # Similar to line chart with timeline styling
        self._render_line_chart(ax, spec, colors)
    
    def _add_annotations(self, ax, spec: ChartSpec, colors: list[str]):
        """Add annotations like arrows to the chart."""
        for annotation in spec.annotations:
            if annotation.get("type") == "arrow" and annotation.get("direction") == "up":
                # Add growth arrow
                if spec.data_points and len(spec.data_points) >= 2:
                    x_start = 0
                    x_end = len(spec.data_points) - 1
                    y_start = spec.data_points[0].value
                    y_end = spec.data_points[-1].value
                    
                    # Draw arrow
                    ax.annotate('', xy=(x_end, y_end), xytext=(x_start, y_start),
                              arrowprops=dict(arrowstyle='->', lw=3, color=colors[2] if len(colors) > 2 else colors[0],
                                            alpha=0.6))
    
    def _apply_chart_styling(self, ax, spec: ChartSpec, style: str):
        """Apply styling to the chart."""
        # Remove top and right spines for cleaner look
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        # Style grid
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        ax.set_axisbelow(True)
        
        # Style ticks
        ax.tick_params(labelsize=11)
        
        # Add subtle background
        ax.set_facecolor('#FAFAFA')
