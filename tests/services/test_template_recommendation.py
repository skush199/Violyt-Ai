from __future__ import annotations

import asyncio
import sys
import types
from importlib.machinery import ModuleSpec
from types import SimpleNamespace
from uuid import uuid4

import pytest

docx_stub = types.ModuleType("docx")
docx_stub.Document = object
docx_shared_stub = types.ModuleType("docx.shared")
docx_shared_stub.Inches = lambda value: value
reportlab_stub = types.ModuleType("reportlab")
reportlab_lib_stub = types.ModuleType("reportlab.lib")
reportlab_utils_stub = types.ModuleType("reportlab.lib.utils")
reportlab_utils_stub.ImageReader = object
reportlab_pdfgen_stub = types.ModuleType("reportlab.pdfgen")
reportlab_canvas_stub = types.ModuleType("reportlab.pdfgen.canvas")
pdfplumber_stub = types.ModuleType("pdfplumber")
cv2_stub = types.ModuleType("cv2")
webcolors_stub = types.ModuleType("webcolors")
webcolors_stub.rgb_to_name = lambda *args, **kwargs: "black"
skimage_stub = types.ModuleType("skimage")
skimage_color_stub = types.ModuleType("skimage.color")
skimage_color_stub.rgb2lab = lambda value: value
skimage_color_stub.deltaE_ciede2000 = lambda left, right: 0.0
sklearn_stub = types.ModuleType("sklearn")
sklearn_cluster_stub = types.ModuleType("sklearn.cluster")
pptx_stub = types.ModuleType("pptx")
langchain_text_splitters_stub = types.ModuleType("langchain_text_splitters")
langchain_openai_stub = types.ModuleType("langchain_openai")
langchain_community_stub = types.ModuleType("langchain_community")
langchain_vectorstores_stub = types.ModuleType("langchain_community.vectorstores")


class _KMeansStub:
    def __init__(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        pass


class _VisionClientStub:
    def __init__(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        pass


class _ImageStub:
    def __init__(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        pass


class _ImageContextStub:
    def __init__(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        pass


class _CredentialsStub:
    @staticmethod
    def from_service_account_file(path):  # noqa: ANN001, D401
        return path


class _RecursiveCharacterTextSplitterStub:
    def __init__(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        pass

    def split_text(self, text):  # noqa: ANN001, D401
        return [text]


class _OpenAIEmbeddingsStub:
    def __init__(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        pass

    def embed_query(self, text):  # noqa: ANN001, D401
        return [0.0]

    def embed_documents(self, texts):  # noqa: ANN001, D401
        return [[0.0] for _ in texts]


class _FAISSStub:
    @classmethod
    def from_texts(cls, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        return cls()

    @classmethod
    def load_local(cls, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        return cls()

    def save_local(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        return None

    def add_embeddings(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        return None

    def add_texts(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        return None

    def similarity_search_with_score(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        return []


class _PresentationStub:
    def __init__(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        self.slides = []


google_stub = types.ModuleType("google")
google_cloud_stub = types.ModuleType("google.cloud")
google_vision_stub = types.ModuleType("google.cloud.vision")
google_vision_stub.ImageAnnotatorClient = _VisionClientStub
google_vision_stub.Image = _ImageStub
google_vision_stub.ImageContext = _ImageContextStub
google_oauth2_stub = types.ModuleType("google.oauth2")
google_service_account_stub = types.ModuleType("google.oauth2.service_account")
google_service_account_stub.Credentials = _CredentialsStub
dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *args, **kwargs: None
dotenv_stub.dotenv_values = lambda *args, **kwargs: {}
sklearn_cluster_stub.KMeans = _KMeansStub
pptx_stub.Presentation = _PresentationStub
langchain_text_splitters_stub.RecursiveCharacterTextSplitter = (
    _RecursiveCharacterTextSplitterStub
)
langchain_openai_stub.OpenAIEmbeddings = _OpenAIEmbeddingsStub
langchain_vectorstores_stub.FAISS = _FAISSStub
for module in [
    docx_stub,
    docx_shared_stub,
    reportlab_stub,
    reportlab_lib_stub,
    reportlab_utils_stub,
    reportlab_pdfgen_stub,
    reportlab_canvas_stub,
    pdfplumber_stub,
    cv2_stub,
    webcolors_stub,
    skimage_stub,
    skimage_color_stub,
    sklearn_stub,
    sklearn_cluster_stub,
    pptx_stub,
    langchain_text_splitters_stub,
    langchain_openai_stub,
    langchain_community_stub,
    langchain_vectorstores_stub,
    google_stub,
    google_cloud_stub,
    google_vision_stub,
    google_oauth2_stub,
    google_service_account_stub,
    dotenv_stub,
]:
    module.__spec__ = ModuleSpec(module.__name__, loader=None)
sys.modules.setdefault("docx", docx_stub)
sys.modules.setdefault("docx.shared", docx_shared_stub)
sys.modules.setdefault("reportlab", reportlab_stub)
sys.modules.setdefault("reportlab.lib", reportlab_lib_stub)
sys.modules.setdefault("reportlab.lib.utils", reportlab_utils_stub)
sys.modules.setdefault("reportlab.pdfgen", reportlab_pdfgen_stub)
sys.modules.setdefault("reportlab.pdfgen.canvas", reportlab_canvas_stub)
sys.modules.setdefault("pdfplumber", pdfplumber_stub)
sys.modules.setdefault("cv2", cv2_stub)
sys.modules.setdefault("webcolors", webcolors_stub)
sys.modules.setdefault("skimage", skimage_stub)
sys.modules.setdefault("skimage.color", skimage_color_stub)
sys.modules.setdefault("sklearn", sklearn_stub)
sys.modules.setdefault("sklearn.cluster", sklearn_cluster_stub)
sys.modules.setdefault("pptx", pptx_stub)
sys.modules.setdefault("langchain_text_splitters", langchain_text_splitters_stub)
sys.modules.setdefault("langchain_openai", langchain_openai_stub)
sys.modules.setdefault("langchain_community", langchain_community_stub)
sys.modules.setdefault("langchain_community.vectorstores", langchain_vectorstores_stub)
sys.modules.setdefault("google", google_stub)
sys.modules.setdefault("google.cloud", google_cloud_stub)
sys.modules.setdefault("google.cloud.vision", google_vision_stub)
sys.modules.setdefault("google.oauth2", google_oauth2_stub)
sys.modules.setdefault("google.oauth2.service_account", google_service_account_stub)
sys.modules.setdefault("dotenv", dotenv_stub)

from app.services.template import TemplateService


class DummyTemplateRepository:
    def __init__(self, templates: list[SimpleNamespace]) -> None:
        self.templates = templates

    async def list_by_brand(self, brand_space_id, tenant_id=None):  # noqa: ANN001
        return list(self.templates)


class DummyTemplateMetadataRepository:
    def __init__(self, metadata_by_template_id: dict[str, SimpleNamespace]) -> None:
        self.metadata_by_template_id = metadata_by_template_id

    async def get_by_template(self, template_id):  # noqa: ANN001
        return self.metadata_by_template_id[template_id]


def _template(
    *,
    name: str,
    kind: str,
    tags: list[str],
    matcher_features: dict,
    analysis_json: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        description=f"{name} template",
        kind=kind,
        storage_path=f"{name.lower().replace(' ', '_')}.png",
        tags=tags,
        matcher_features_json=matcher_features,
        analysis_json=analysis_json or {"overlay_safe": True, "layout_type": kind},
    )


def _metadata(
    *,
    zone_roles: list[str],
    supported_platforms: list[str] | None = None,
    supported_formats: list[str] | None = None,
    page_count: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        zone_map={
            "layout_type": "static",
            "background_style": {"dominant_mode": "graphic"},
            "zones": [{"role": role} for role in zone_roles],
        },
        platform_rules={"supported_platforms": supported_platforms or ["instagram"]},
        export_rules={"supported_formats": supported_formats or ["png"]},
        editable_fields=zone_roles,
        sizing_rules={"page_count": page_count},
    )


def test_recommend_reranks_with_semantic_signal_and_logs_selection(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    prompt = "Create a before and after story that explains how our workflow changed after automation."
    explainer_template = _template(
        name="Workflow Explainer Promo",
        kind="static",
        tags=["explainer", "promotion"],
        matcher_features={
            "layout_type": "static",
            "content_patterns": ["explainer", "promotion"],
            "supported_platforms": ["instagram"],
            "supported_exports": ["png"],
            "overlay_safe": True,
        },
    )
    transformation_template = _template(
        name="Transformation Story Carousel",
        kind="static",
        tags=["story", "evolution"],
        matcher_features={
            "layout_type": "carousel",
            "content_patterns": ["comparison", "multi_section"],
            "supported_platforms": ["instagram"],
            "supported_exports": ["png"],
            "overlay_safe": True,
        },
    )
    metadata_by_id = {
        explainer_template.id: _metadata(zone_roles=["headline", "body", "cta"]),
        transformation_template.id: _metadata(
            zone_roles=["headline", "body", "image", "cta"],
            page_count=3,
        ),
    }

    service = TemplateService(session=None)
    service.templates = DummyTemplateRepository(
        [explainer_template, transformation_template]
    )
    service.metadata = DummyTemplateMetadataRepository(metadata_by_id)
    service.asset_delivery = SimpleNamespace(
        build_signed_url=lambda **_: "signed://template"
    )

    def fake_semantic_similarity_map(
        cls,
        prompt_text: str,  # noqa: ARG001
        studio_panel: dict,  # noqa: ARG001
        candidates: list[dict],
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        for candidate in candidates:
            scores[candidate["template_id"]] = (
                0.18
                if candidate["template"].name == "Workflow Explainer Promo"
                else 0.93
            )
        return scores

    monkeypatch.setattr(
        TemplateService,
        "_semantic_similarity_map",
        classmethod(fake_semantic_similarity_map),
    )

    caplog.set_level("INFO")
    recommendations = asyncio.run(
        service.recommend(
            tenant_id=uuid4(),
            brand_space_id=uuid4(),
            prompt=prompt,
            studio_panel={
                "platform_preset": "instagram",
                "format": "static",
                "file_type": "png",
            },
            brand_context={"identity": {}, "visual_identity": {}, "guardrails": {}},
            limit=2,
        )
    )

    assert [item.name for item in recommendations] == [
        "Transformation Story Carousel",
        "Workflow Explainer Promo",
    ]
    assert recommendations[0].editability_score is not None
    assert (
        recommendations[0].score_breakdown["semantic_similarity"]
        > recommendations[1].score_breakdown["semantic_similarity"]
    )
    assert any(
        "template.recommend.complete" in record.getMessage() for record in caplog.records
    )
