from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

from docx import Document

from app.core.config import BASE_DIR, get_settings


class ContentFormatGuideService:
    GUIDE_NAME_PATTERNS = (
        "*Content Formats Guide*.docx",
        "*Content Format Guide*.docx",
    )
    CACHE_FILE_NAMES = (
        "content_format_guide.cache.json",
        "content-format-guide.cache.json",
    )

    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _normalize_text(value: Any, limit: int | None = None) -> str:
        text = " ".join(str(value or "").split()).strip()
        if limit is None or not text:
            return text
        return text[:limit].rstrip(" ,.;:")

    def _candidate_paths(self) -> list[Path]:
        candidates: list[Path] = []
        if self.settings.content_format_guide_path:
            candidates.append(Path(self.settings.content_format_guide_path))
        docs_dir = BASE_DIR / "docs"
        if docs_dir.exists():
            for pattern in self.GUIDE_NAME_PATTERNS:
                candidates.extend(docs_dir.glob(pattern))
        downloads_dir = Path.home() / "Downloads"
        if downloads_dir.exists():
            for pattern in self.GUIDE_NAME_PATTERNS:
                candidates.extend(downloads_dir.glob(pattern))
        seen: set[str] = set()
        resolved: list[Path] = []
        for path in candidates:
            key = str(path).casefold()
            if key in seen:
                continue
            seen.add(key)
            resolved.append(path)
        return resolved

    def _resolve_path(self) -> Path | None:
        for path in self._candidate_paths():
            if path.exists() and path.is_file():
                return path
        return None

    def _resolve_cache_path(self) -> Path | None:
        docs_dir = BASE_DIR / "docs"
        if not docs_dir.exists():
            return None
        for filename in self.CACHE_FILE_NAMES:
            candidate = docs_dir / filename
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _load_cached_payload(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _extract_paragraphs(path: Path) -> list[str]:
        document = Document(path)
        paragraphs = [
            " ".join(paragraph.text.split()).strip()
            for paragraph in document.paragraphs
            if paragraph.text and paragraph.text.strip()
        ]
        return [paragraph for paragraph in paragraphs if paragraph]

    @staticmethod
    def _collect_section(
        paragraphs: list[str],
        *,
        keywords: tuple[str, ...],
        max_items: int = 5,
    ) -> list[str]:
        matches: list[str] = []
        lowered = [paragraph.casefold() for paragraph in paragraphs]
        for index, paragraph_lower in enumerate(lowered):
            if not any(keyword in paragraph_lower for keyword in keywords):
                continue
            for candidate in paragraphs[index : index + max_items]:
                normalized = " ".join(candidate.split()).strip()
                if normalized and normalized not in matches:
                    matches.append(normalized)
                if len(matches) >= max_items:
                    return matches
        return matches

    @staticmethod
    def _format_rules(section_lines: list[str]) -> list[str]:
        rules: list[str] = []
        for line in section_lines:
            normalized = re.sub(r"^[\-\u2022\*\d\.\)\s]+", "", line).strip()
            if normalized and normalized not in rules:
                rules.append(normalized)
        return rules

    @staticmethod
    def _section_slice(
        paragraphs: list[str],
        *,
        start_markers: tuple[str, ...],
        end_markers: tuple[str, ...] = (),
    ) -> list[str]:
        lowered = [paragraph.casefold() for paragraph in paragraphs]
        start_index = next(
            (
                index
                for index, line in enumerate(lowered)
                if any(marker.casefold() in line for marker in start_markers)
            ),
            None,
        )
        if start_index is None:
            return []
        end_index = len(paragraphs)
        for index in range(start_index + 1, len(paragraphs)):
            if any(marker.casefold() in lowered[index] for marker in end_markers):
                end_index = index
                break
        return paragraphs[start_index + 1 : end_index]

    @staticmethod
    def _block_slice(
        section_lines: list[str],
        *,
        heading: str,
        stop_headings: tuple[str, ...],
    ) -> list[str]:
        lowered = [line.casefold() for line in section_lines]
        heading_lower = heading.casefold()
        start_index = next(
            (index for index, line in enumerate(lowered) if line == heading_lower or heading_lower in line),
            None,
        )
        if start_index is None:
            return []
        end_index = len(section_lines)
        for index in range(start_index + 1, len(section_lines)):
            if any(stop.casefold() == lowered[index] or stop.casefold() in lowered[index] for stop in stop_headings):
                end_index = index
                break
        return section_lines[start_index + 1 : end_index]

    @staticmethod
    def _lines_after_label(
        block: list[str],
        *,
        start_markers: tuple[str, ...],
        stop_markers: tuple[str, ...] = (),
    ) -> list[str]:
        lowered = [line.casefold() for line in block]
        start_index = next(
            (
                index
                for index, line in enumerate(lowered)
                if any(marker.casefold() in line for marker in start_markers)
            ),
            None,
        )
        if start_index is None:
            return []
        collected: list[str] = []
        for line in block[start_index + 1 :]:
            lowered_line = line.casefold()
            if any(marker.casefold() in lowered_line for marker in stop_markers):
                break
            collected.append(line)
        return collected

    @classmethod
    def _definition_for_heading(
        cls,
        section_lines: list[str],
        *,
        heading: str,
        stop_headings: tuple[str, ...],
    ) -> str:
        block = cls._block_slice(section_lines, heading=heading, stop_headings=stop_headings)
        return cls._normalize_text(block[0] if block else "", limit=320)

    @staticmethod
    def _parse_export_lines(lines: list[str]) -> dict[str, dict[str, str]]:
        export_map: dict[str, dict[str, str]] = {}
        for line in lines:
            if ":" not in line:
                continue
            label, value = [part.strip() for part in line.split(":", 1)]
            lowered = label.casefold()
            if "instagram" in lowered:
                platform = "instagram"
            elif "linkedin" in lowered:
                platform = "linkedin"
            elif "x" in lowered or "twitter" in lowered:
                platform = "x"
            elif "infographic" in lowered:
                platform = "all"
            else:
                continue
            if "static" in lowered:
                format_name = "static"
            elif "carousel" in lowered:
                format_name = "carousel"
            elif "infographic" in lowered:
                format_name = "infographic"
            else:
                continue
            export_map.setdefault(platform, {})[format_name] = value
        return export_map

    @classmethod
    def _compose_platform_guidance(cls, block: list[str]) -> dict[str, Any]:
        notes = cls._format_rules(block)
        return {
            "summary": cls._normalize_text(" ".join(block[:3]), limit=320),
            "notes": notes,
        }

    def load(self) -> dict[str, Any]:
        path = self._resolve_path()
        if path is None:
            cache_path = self._resolve_cache_path()
            if cache_path is None:
                return {}
            cached_payload = self._load_cached_payload(cache_path)
            if cached_payload:
                cached_payload.setdefault("source_path", str(cache_path))
            return cached_payload
        paragraphs = self._extract_paragraphs(path)
        if not paragraphs:
            cache_path = self._resolve_cache_path()
            if cache_path is None:
                return {}
            cached_payload = self._load_cached_payload(cache_path)
            if cached_payload:
                cached_payload.setdefault("source_path", str(cache_path))
            return cached_payload
        definitions_section = self._section_slice(
            paragraphs,
            start_markers=("1. Definitions",),
            end_markers=("2. Platform Differences",),
        )
        platform_section = self._section_slice(
            paragraphs,
            start_markers=("2. Platform Differences",),
            end_markers=("3. Content Style Expectations",),
        )
        style_section = self._section_slice(
            paragraphs,
            start_markers=("3. Content Style Expectations",),
            end_markers=("4. File Formats and Usage", "5. Practical Export Rules"),
        )
        export_section = self._section_slice(
            paragraphs,
            start_markers=("5. Practical Export Rules",),
            end_markers=("6. Summary",),
        )
        summary_section = self._section_slice(
            paragraphs,
            start_markers=("6. Summary",),
        )

        static_definition = self._definition_for_heading(
            definitions_section,
            heading="Static Content",
            stop_headings=("Carousel", "Infographic"),
        )
        carousel_definition = self._definition_for_heading(
            definitions_section,
            heading="Carousel",
            stop_headings=("Infographic",),
        )
        infographic_definition = self._definition_for_heading(
            definitions_section,
            heading="Infographic",
            stop_headings=(),
        )

        static_block = self._block_slice(
            style_section,
            heading="Static Content",
            stop_headings=("Carousel", "Infographic"),
        )
        carousel_block = self._block_slice(
            style_section,
            heading="Carousel",
            stop_headings=("Infographic",),
        )
        infographic_block = self._block_slice(
            style_section,
            heading="Infographic",
            stop_headings=(),
        )

        static_include = self._format_rules(
            self._lines_after_label(
                static_block,
                start_markers=("What to include",),
                stop_markers=("Style:",),
            )
        )
        static_style = self._format_rules(
            self._lines_after_label(
                static_block,
                start_markers=("Style:",),
            )
        )
        carousel_ten_slide_structure = self._format_rules(
            self._lines_after_label(
                carousel_block,
                start_markers=("Structure (for a 10 page carousel)",),
                stop_markers=("Structure (for a 5 page carousel)", "Style:"),
            )
        )
        carousel_five_slide_structure = self._format_rules(
            self._lines_after_label(
                carousel_block,
                start_markers=("Structure (for a 5 page carousel)",),
                stop_markers=("Style:",),
            )
        )
        carousel_style = self._format_rules(
            self._lines_after_label(
                carousel_block,
                start_markers=("Style:",),
            )
        )
        infographic_include = self._format_rules(
            self._lines_after_label(
                infographic_block,
                start_markers=("What to include",),
                stop_markers=("Style:",),
            )
        )
        infographic_style = self._format_rules(
            self._lines_after_label(
                infographic_block,
                start_markers=("Style:",),
            )
        )

        instagram_block = self._block_slice(
            platform_section,
            heading="Instagram",
            stop_headings=("LinkedIn", "X (Twitter)", "Key Insight:"),
        )
        linkedin_block = self._block_slice(
            platform_section,
            heading="LinkedIn",
            stop_headings=("X (Twitter)", "Key Insight:"),
        )
        x_block = self._block_slice(
            platform_section,
            heading="X (Twitter)",
            stop_headings=("Key Insight:",),
        )
        key_insight_lines = self._lines_after_label(
            platform_section,
            start_markers=("Key Insight:",),
        )

        static_lines = [*static_include, *static_style]
        carousel_lines = [
            *carousel_ten_slide_structure,
            "Preferred pacing: 5 slides when the story supports it.",
            *carousel_five_slide_structure,
            *carousel_style,
        ]
        infographic_lines = [*infographic_include, *infographic_style]
        instagram_lines = self._format_rules(instagram_block)
        linkedin_lines = self._format_rules(linkedin_block)

        summary_lines = [
            static_definition,
            carousel_definition,
            infographic_definition,
            *key_insight_lines[:1],
            *summary_section[:3],
        ]
        summary = " ".join(summary_lines[:8]).strip()
        return {
            "source_path": str(path),
            "summary": self._normalize_text(summary, limit=1600),
            "rules": {
                "static": self._format_rules(static_lines),
                "carousel": self._format_rules(carousel_lines),
                "infographic": self._format_rules(infographic_lines),
                "instagram": self._format_rules(instagram_lines),
                "linkedin": self._format_rules(linkedin_lines),
            },
            "definitions": {
                "static": static_definition,
                "carousel": carousel_definition,
                "infographic": infographic_definition,
            },
            "format_expectations": {
                "static": {
                    "include": static_include,
                    "style": static_style,
                    "quality_priorities": static_style,
                },
                "carousel": {
                    "structure": [*carousel_ten_slide_structure, *carousel_five_slide_structure],
                    "style": carousel_style,
                    "quality_priorities": [
                        *carousel_style,
                        "One idea per slide.",
                        "Open with a hook and land on a closing CTA.",
                    ],
                    "preferred_slide_count": 5,
                    "max_slide_count": 10,
                },
                "infographic": {
                    "include": infographic_include,
                    "style": infographic_style,
                    "quality_priorities": [
                        *infographic_style,
                        "Structure the visual so it educates quickly.",
                    ],
                    "source_attribution_required": any(
                        "source attribution" in line.casefold() for line in infographic_include
                    ),
                },
            },
            "platform_guidance": {
                "instagram": self._compose_platform_guidance(instagram_block),
                "linkedin": self._compose_platform_guidance(linkedin_block),
                "x": self._compose_platform_guidance(x_block),
            },
            "export_guidance": {
                "lines": self._format_rules(export_section),
                "by_platform_format": self._parse_export_lines(export_section),
            },
            "key_insights": self._format_rules(key_insight_lines),
        }
