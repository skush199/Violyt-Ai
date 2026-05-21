from app.services.upload_preflight import UploadPreflightService


def test_upload_preflight_accepts_svg_logo_uploads() -> None:
    service = UploadPreflightService()
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40"><rect width="120" height="40" fill="#F4C542"/></svg>"""

    result = service.validate_bytes(
        filename="jiraaf-logo.svg",
        mime_type="image/svg+xml",
        content=svg,
    )

    assert result.detected_extension == ".svg"
    assert result.normalized_mime_type == "image/svg+xml"
    assert result.hints == {"vector_image": True}
