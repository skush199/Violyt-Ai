# Brand-Aligned Content Generation - Quick Reference Guide

## Overview

This guide explains how to use the new brand-aligned content generation features that make all styling dynamic from brand context.

---

## Feature 1: Dynamic Background Colors

### What it does:
Automatically applies brand-specific background colors to all generated content.

### How to use:
1. Upload reference samples to brand space
2. System extracts color palette via OCR/vision analysis
3. Background color stored in `brand_color_palette["background"]`
4. Generation automatically uses this color

### Manual Override (if needed):
```python
# In brand context editor or via API
brand_context["visual_identity"]["brand_color_palette"]["background"] = "#FAF8F5"
```

### Example:
- **Jiraaf**: Cream background (#FAF8F5)
- **Tech Brand**: Dark blue (#1A1A2E)
- **Wellness Brand**: Soft green (#E8F5E9)

---

## Feature 2: Legal Disclaimers

### What it does:
Automatically detects and adds legal disclaimers to all generated content.

### How to use:

#### Automatic Detection (Recommended):
1. Upload reference creative with disclaimer in footer
2. System OCRs footer text
3. If contains legal keywords → Stored in `brand_legal_assets`
4. Automatically appears on future generations

#### Manual Creation:
```sql
INSERT INTO brand_legal_assets (
    tenant_id, brand_space_id, asset_type, text_template,
    applies_to_formats, position, font_size, text_color
) VALUES (
    'tenant-uuid', 'brand-uuid', 'disclaimer',
    'Mutual fund investments are subject to market risks. Read all scheme related documents carefully.',
    ARRAY['carousel', 'static', 'infographic'],
    'footer', 8, '#666666'
);
```

### Legal Keywords Detected:
- disclaimer, regulated by, subject to, terms and conditions
- SEBI, AMFI, mutual fund, investments are subject to
- copyright, all rights reserved, privacy policy

### Format Control:
Control which formats show disclaimers via `applies_to_formats`:
- `['carousel']` - Only carousels
- `['static', 'infographic']` - Static posts and infographics
- `['carousel', 'static', 'infographic']` - All formats

---

## Feature 3: CTA Templates

### What it does:
Creates brand-specific call-to-action slides with custom styling.

### How to use:

#### Manual Creation:
```sql
INSERT INTO brand_cta_templates (
    tenant_id, brand_space_id, template_name,
    headline_template, body_template,
    button_text, button_color, button_text_color,
    button_style, is_default
) VALUES (
    'tenant-uuid', 'brand-uuid', 'product_pitch',
    'Discover how {brand} can transform your portfolio',
    'Start your investment journey today',
    'Explore Now', '#F7941D', '#FFFFFF',
    'rounded', true
);
```

#### Template Placeholders:
- `{brand}` - Replaced with brand name
- `{product}` - Replaced with product/brand name

#### Button Styles:
- `rounded` - Rounded corners (8px radius)
- `pill` - Fully rounded ends (999px radius)
- `sharp` - Square corners (0px radius)

### Example Templates:

**E-commerce**:
```json
{
  "headline_template": "Ready to shop?",
  "button_text": "Shop Now",
  "button_color": "#FF6B6B",
  "button_style": "pill"
}
```

**Finance**:
```json
{
  "headline_template": "Start investing with {brand}",
  "button_text": "Get Started",
  "button_color": "#2E7D32",
  "button_style": "rounded"
}
```

**SaaS**:
```json
{
  "headline_template": "See {product} in action",
  "button_text": "Book Demo",
  "button_color": "#1976D2",
  "button_style": "sharp"
}
```

---

## Feature 4: Numbered Badges

### What it does:
Replaces generic bullet points with branded numbered badges (01, 02, 03).

### How to use:

#### Via Template Vision (Future):
Upload reference with numbered badges → Auto-detected

#### Manual Configuration (Current):
Add to visual reference asset's `style_characteristics`:
```json
{
  "component_motifs": {
    "numbered_badges": {
      "detected": true,
      "shape": "rounded_rect",
      "badge_color": "#F7941D",
      "text_color": "#FFFFFF",
      "radius_px": 12,
      "padding_px": 8,
      "number_format": "01"
    }
  }
}
```

### Number Formats:
- `"01"` - Zero-padded (01, 02, 03, ...)
- `"1"` - Simple numbers (1, 2, 3, ...)

### Color Examples:
- **Energetic**: Orange (#F7941D) on white
- **Professional**: Navy (#1A237E) on white
- **Modern**: Black (#000000) on light gray (#F5F5F5)

---

## Feature 5: Background Boxes for Subheadings

### What it does:
Adds colored background boxes behind subheadings and section labels.

### How to use:

#### Manual Configuration:
Add to visual reference asset's `style_characteristics`:
```json
{
  "component_motifs": {
    "text_background_boxes": {
      "detected": true,
      "applies_to_roles": ["subheading", "section_label"],
      "box_color": "#FAF0E6",
      "border_radius_px": 8,
      "padding_x": 12,
      "padding_y": 8
    }
  }
}
```

### Roles it Applies To:
- `supporting_line` - Supporting/secondary text
- `subheading` - Section subheadings
- `section_label` - Section labels/tags

### Design Examples:

**Minimal**:
```json
{
  "box_color": "#F5F5F5",
  "border_radius_px": 4,
  "padding_x": 8,
  "padding_y": 4
}
```

**Bold**:
```json
{
  "box_color": "#FFF9C4",
  "border_radius_px": 12,
  "padding_x": 16,
  "padding_y": 10
}
```

**Premium**:
```json
{
  "box_color": "#E8EAF6",
  "border_radius_px": 0,
  "padding_x": 20,
  "padding_y": 12
}
```

---

## Feature 6: Icon Style Matching

### What it does:
Ensures all icons match brand's visual style (line-art vs solid vs 3D).

### How to use:

#### Automatic Style Detection:
System infers icon style from:
1. Visual style hints in brand context
2. Icon style in reference creatives
3. Default: line-art for modern aesthetic

#### Manual Override:
```python
from app.ai.icon_matching import IconMatchingService

icon_matcher = IconMatchingService()
matched_icon = icon_matcher.match_icon(
    semantic_need="chart",  # What icon represents
    brand_context=resolved_brand_context,
    preferred_style="line-art"  # Optional override
)
```

#### Icon Styles Supported:
- `line-art` - Outlined, minimal, modern
- `solid` - Filled, bold, impactful
- `3d` - Dimensional, realistic, premium
- `duotone` - Two-color, balanced, versatile

#### Style Detection Logic:
```
Visual style contains "minimal" → line-art
Visual style contains "3d" → 3d
Visual style contains "solid" → solid
Reference creatives have line icons → line-art
Default → line-art
```

---

## Complete Workflow Example: Setting Up Jiraaf

### Step 1: Upload Reference Samples
```
Upload: FTA 1.pdf, FTA 2.pdf, FTA 3.pdf
- System extracts: cream background, legal disclaimer, orange badges
```

### Step 2: Create CTA Template
```sql
INSERT INTO brand_cta_templates (...) VALUES (
  ..., 'Discover how Jiraaf can help you',
  'Start your investment journey',
  'Explore Now', '#F7941D', '#FFFFFF', 'rounded', true
);
```

### Step 3: Configure Component Motifs (Manual for now)
```json
{
  "numbered_badges": {
    "detected": true,
    "badge_color": "#F7941D",
    "text_color": "#FFFFFF"
  },
  "text_background_boxes": {
    "detected": true,
    "box_color": "#FAF0E6"
  }
}
```

### Step 4: Generate Content
```
Prompt: "Create an FTA carousel about tax-saving mutual funds"

Output:
✅ Cream background (#FAF8F5)
✅ SEBI disclaimer on every slide
✅ Orange numbered badges (01, 02, 03)
✅ Cream boxes for subheadings
✅ "Explore Now" CTA button in orange
✅ Jiraaf logo, proper placement
```

---

## Troubleshooting

### Issue: Background still white
**Check**:
1. Is `brand_color_palette["background"]` set?
2. Is the value a valid hex color?
3. Is it different from "#FFFFFF"?

**Fix**: Set background color in brand context

### Issue: Disclaimer not appearing
**Check**:
1. Does `brand_legal_assets` table have entry for this brand?
2. Does `applies_to_formats` include current format?
3. Is disclaimer text not empty?

**Fix**: Insert legal asset record

### Issue: CTA button not styled
**Check**:
1. Does `brand_cta_templates` table have entry?
2. Is `is_default` set to true?
3. Are button_color and button_text_color valid hex codes?

**Fix**: Insert CTA template record

### Issue: Generic bullets instead of badges
**Check**:
1. Is `numbered_badges` in component_motifs?
2. Is `detected` set to true?
3. Is `shape` set to "rounded_rect"?

**Fix**: Update visual_reference_asset.style_characteristics

### Issue: Subheadings have no background
**Check**:
1. Is `text_background_boxes` in component_motifs?
2. Is `box_color` a valid hex code?
3. Does element role match `applies_to_roles`?

**Fix**: Update component_motifs configuration

---

## Database Queries for Debugging

### Check Legal Disclaimers:
```sql
SELECT asset_type, text_template, applies_to_formats
FROM brand_legal_assets
WHERE brand_space_id = 'your-brand-uuid';
```

### Check CTA Templates:
```sql
SELECT template_name, button_text, button_color, is_default
FROM brand_cta_templates
WHERE brand_space_id = 'your-brand-uuid';
```

### Check Background Color:
```sql
SELECT resolved_brand_context->'visual_identity'->'brand_color_palette'->'background'
FROM brand_spaces
WHERE id = 'your-brand-uuid';
```

### Check Component Motifs:
```sql
SELECT style_characteristics->'component_motifs'
FROM visual_reference_assets
WHERE brand_space_id = 'your-brand-uuid';
```

---

## Best Practices

### 1. Always Upload Reference Samples
- Upload 3-5 representative samples
- Include legal disclaimers in samples
- Show consistent styling patterns

### 2. Review Auto-Detected Settings
- Check extracted colors are correct
- Verify disclaimer text is accurate
- Confirm component motifs match brand

### 3. Create Multiple CTA Templates
- Different templates for different campaigns
- Set one as default with `is_default=true`
- Use template placeholders for flexibility

### 4. Test Across Formats
- Generate carousel, static, infographic
- Verify disclaimers appear correctly
- Check styling consistency

### 5. Maintain Brand Consistency
- Keep legal disclaimers up-to-date
- Update CTA templates seasonally
- Review generated content regularly

---

## API Usage (Future)

### Create Legal Disclaimer:
```python
POST /api/v1/brand-spaces/{brand_space_id}/legal-assets
{
  "asset_type": "disclaimer",
  "text_template": "Your disclaimer text here",
  "applies_to_formats": ["carousel", "static"],
  "font_size": 8,
  "text_color": "#666666"
}
```

### Create CTA Template:
```python
POST /api/v1/brand-spaces/{brand_space_id}/cta-templates
{
  "template_name": "holiday_campaign",
  "headline_template": "Holiday special from {brand}",
  "button_text": "Shop Sale",
  "button_color": "#D32F2F",
  "button_style": "pill",
  "is_default": false
}
```

### Update Component Motifs:
```python
PATCH /api/v1/visual-references/{asset_id}
{
  "style_characteristics": {
    "component_motifs": {
      "numbered_badges": {
        "detected": true,
        "badge_color": "#F7941D"
      }
    }
  }
}
```

---

## Support

For issues or questions:
1. Check IMPLEMENTATION_SUMMARY.md for technical details
2. Review database schema in migration 0008
3. Examine code comments in modified files
4. Test with check_migration.py script
