# Implementation Plan: Image Processing Architecture

## Context

The architecture document `docs/image_processing_architecture.md` describes a comprehensive image processing pipeline for the RAG system with these key features:

1. **Image Triage** — Size-based filtering to skip decorative/small images (< 100x100px)
2. **Dual OCR Engine** — Fast on-premise OCR (PaddleOCR/Tesseract) for text-heavy images + VLM (Gemini) for charts/diagrams
3. **Structured VLM Output** — Prompt engineering to force structured Markdown/JSON output from VLM to prevent hallucination
4. **Presigned URLs** — Generate time-limited S3 URLs for frontend to render source images
5. **Visual Evidence** — Return `image_url`, `page_number`, `bbox` in citations for frontend rendering

---

## Current State Assessment

### What Exists (✓)

| Component | Location | Status |
|-----------|----------|--------|
| ImageChunker with OCR callback | `rag_document_pipeline/chunking/strategies/image.py` | ✓ Functional |
| GeminiOCR with SSRF protection | `rag_core/providers/ocr/gemini.py` | ✓ Functional |
| ImageData/LayoutElement models | `rag_contracts/elements.py` | ✓ Functional |
| MinIO S3 image upload | `apps/worker/src/worker/services/ingestion.py:44-68` | ✓ Functional |
| pgvector with JSONB metadata | `rag_core/indexing/pgvector.py` | ✓ Functional |
| MultimodalChunker routing | `rag_document_pipeline/chunking/multimodal.py` | ✓ Functional |
| OCR config wiring | `apps/worker/src/worker/dependencies.py:71-79` | ✓ Functional |

### Gaps to Implement (✗)

1. ✗ **Image Triage** — No size-based filtering (min_width, min_height, aspect ratio checks)
2. ✗ **Dual OCR Engine** — Only Gemini VLM exists; no fast on-premise OCR fallback (PaddleOCR/Tesseract)
3. ✗ **Structured VLM Prompt** — Current GeminiOCR uses generic "transcribe" prompt, not structured chart/diagram analysis
4. ✗ **Presigned URLs** — `ObjectStoragePort` has no `presigned_get_url` method
5. ✗ **Visual Evidence in Citations** — `Citation` class doesn't include `image_uri` from chunk metadata; frontend can't render source images

---

## Step 1: Add Image Triage to ImageChunker

**File:** `packages/rag-document-pipeline/src/rag_document_pipeline/chunking/strategies/image.py`

**Changes:**
- Add `min_width`, `min_height`, `max_aspect_ratio` parameters to `ImageChunker.__init__`
- Add `_should_skip_image(element: LayoutElement) -> bool` method that:
  - Reads image dimensions from `element.image_data` metadata (parser must populate `width`/`height`)
  - Returns `True` if width < min_width OR height < min_height OR aspect_ratio > max_aspect_ratio
  - Logs skip reason in `element.metadata["triage_skip_reason"]`
- In `_chunk_image`, check `_should_skip_image` before OCR; if skipped, return chunk with `indexable=False` and `metadata["triage_skipped"] = True`

**New signature:**
```python
def __init__(
    self,
    *,
    ocr_fn: Any = None,
    max_ocr_length: int = DEFAULT_MAX_OCR_LENGTH,
    min_width: int = 100,
    min_height: int = 100,
    max_aspect_ratio: float = 10.0,
) -> None:
```

**Parser Update Required:**
- `OpenDataLoaderParser._to_elements` must populate `element.metadata["width"]` and `element.metadata["height"]` from image dimensions
- Add `Pillow>=10.0.0` to `packages/rag-document-pipeline/pyproject.toml` dependencies
- OpenDataLoader JSON may not include these fields, so we must read from PIL after parser extracts the image

**Implementation:**
```python
# In _to_elements, after creating ImageData:
if element_type in ("image", "figure") and uri:
    # Try to read dimensions from local file
    try:
        from PIL import Image
        if Path(uri).exists():
            with Image.open(uri) as img:
                metadata["width"] = img.width
                metadata["height"] = img.height
    except Exception as exc:
        logger.warning("Could not read image dimensions from %s: %s", uri, exc)
```

---

## Step 2: Add Fast On-Premise OCR Provider (Tesseract)

**New File:** `packages/rag-core/src/rag_core/providers/ocr/tesseract.py`

**Implementation:**
```python
class TesseractOCR:
    """Fast on-premise OCR using Tesseract for text-heavy images (scans, invoices)."""
    
    def __init__(self, *, lang: str = "eng+vie", timeout: float = 30.0) -> None:
        self.lang = lang
        self.timeout = timeout
    
    def __call__(self, image_source: str) -> str:
        """Extract text using Tesseract OCR."""
        import pytesseract
        from PIL import Image
        
        if image_source.startswith(("http://", "https://")):
            # Download to temp file
            ...
        
        image = Image.open(image_source)
        text = pytesseract.image_to_string(image, lang=self.lang)
        return text.strip()
```

**Dependencies:** Add `pytesseract>=0.3.10` and `Pillow>=10.0.0` to `packages/rag-core/pyproject.toml`

**Config:** Add `OCR_FAST_ENABLED: bool = True` and `OCR_FAST_LANG: str = "eng+vie"` to `core/src/core/config.py`

---

## Step 3: Implement Dual OCR Engine Router

**New File:** `packages/rag-core/src/rag_core/providers/ocr/router.py`

**Implementation:**
```python
class DualOCRRouter:
    """Route images to fast OCR (Tesseract) or VLM (Gemini) based on heuristics."""
    
    def __init__(
        self,
        fast_ocr: OCRProvider | None = None,
        vlm_ocr: OCRProvider | None = None,
    ) -> None:
        self.fast_ocr = fast_ocr
        self.vlm_ocr = vlm_ocr
    
    def __call__(self, image_source: str) -> str:
        """Try fast OCR first; fallback to VLM if result is empty or low-quality."""
        if self.fast_ocr:
            try:
                text = self.fast_ocr(image_source)
                if text and len(text) > 20:  # Minimum viable OCR result
                    return text
            except Exception:
                pass
        
        if self.vlm_ocr:
            return self.vlm_ocr(image_source)
        
        return ""
```

**Wire in `apps/worker/src/worker/dependencies.py`:**
```python
def _get_ocr_fn():
    if not getattr(settings, "OCR_ENABLED", True):
        return None
    
    fast_ocr = None
    if getattr(settings, "OCR_FAST_ENABLED", True):
        try:
            from rag_core.providers.ocr.tesseract import TesseractOCR
            fast_ocr = TesseractOCR(lang=getattr(settings, "OCR_FAST_LANG", "eng+vie"))
        except Exception as exc:
            logger.warning("Fast OCR unavailable: %s", exc)
    
    vlm_ocr = None
    try:
        vlm_ocr = GeminiOCR(model=getattr(settings, "OCR_MODEL", "gemini-2.0-flash"))
    except Exception as exc:
        logger.warning("VLM OCR unavailable: %s", exc)
    
    if fast_ocr and vlm_ocr:
        from rag_core.providers.ocr.router import DualOCRRouter
        return DualOCRRouter(fast_ocr=fast_ocr, vlm_ocr=vlm_ocr)
    
    return fast_ocr or vlm_ocr
```

---

## Step 4: Structured VLM Prompt for Charts/Diagrams

**File:** `packages/rag-core/src/rag_core/providers/ocr/gemini.py`

**Changes:**
- Add `GeminiVisionAnalyzer` class (separate from `GeminiOCR`) with structured prompt
- Prompt forces output in Markdown format with sections: `Loại hình`, `Tiêu đề`, `Thông điệp chính`, `Dữ liệu chi tiết`, `Văn bản nhìn thấy (OCR)`
- Use `response_schema` to enforce JSON output if Gemini supports it

**New Class:**
```python
class GeminiVisionAnalyzer:
    """Analyze charts/diagrams with structured output to prevent hallucination."""
    
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        ...
    
    def __call__(self, image_source: str) -> str:
        """Return structured Markdown analysis of chart/diagram."""
        prompt = """[IMAGE_ANALYSIS]
Analyze this chart or diagram. Return ONLY the following sections in Vietnamese:

Loại hình: [Type: bar chart, pie chart, flow diagram, etc.]
Tiêu đề: [Title or axis labels]
Thông điệp chính: [Key insight or trend]
Dữ liệu chi tiết:
- [List specific data points with numbers]
Văn bản nhìn thấy (OCR): [Any visible text/labels]

If data is unclear, write "Không rõ" (unclear). Do NOT invent numbers."""
        ...
```

**Config:** Add `VISION_ANALYSIS_ENABLED: bool = True` to config

---

## Step 5: Add Presigned URL Generation to ObjectStoragePort

**File:** `core/src/core/storage/ports/storage_port.py`

**Changes:**
```python
class ObjectStoragePort(ABC):
    ...
    @abstractmethod
    def presigned_get_url(self, storage_uri: str, *, expires_in: int = 3600) -> str:
        """Generate a presigned GET URL for temporary access."""
        pass
```

**File:** `core/src/core/storage/adapters/minio.py`

**Implementation:**
```python
def presigned_get_url(self, storage_uri: str, *, expires_in: int = 3600) -> str:
    """Generate a presigned GET URL valid for `expires_in` seconds."""
    bucket, object_key = self._parse_uri(storage_uri)
    from minio.helpers import url_replace  # Not needed, use get_presigned_url
    
    url = self._client.get_presigned_url(
        "GET",
        bucket,
        object_key,
        expires=timedelta(seconds=expires_in),
    )
    return url
```

**File:** `core/src/core/storage/adapters/local.py`

**Implementation:**
```python
def presigned_get_url(self, storage_uri: str, *, expires_in: int = 3600) -> str:
    """Local storage returns file:// URL (no presign needed)."""
    return storage_uri
```

---

## Step 6: Return Visual Evidence in Citations

**Background:** Citations are built in `packages/rag-core/src/rag_core/providers/generation/service.py:209` from `SearchResult.chunk`, which already has `bboxes` and `metadata`. The `metadata` dict contains `image_uri` for image chunks. We need to:
1. Pass `metadata` (or just `image_uri`) from `Citation` to the chat-api layer
2. Generate presigned URL at the chat-api service layer (not at rag-core, to keep rag-core storage-agnostic)

**File:** `packages/rag-core/src/rag_core/providers/generation/service.py`

**Changes:**
```python
class Citation:
    def __init__(
        self,
        *,
        document_id: str,
        chunk_id: str,
        page_number: int,
        bbox: tuple[float, float, float, float] | None = None,
        quote: str = "",
        image_uri: str | None = None,  # NEW FIELD
    ) -> None:
        self.document_id = document_id
        self.chunk_id = chunk_id
        self.page_number = page_number
        self.bbox = bbox
        self.quote = quote
        self.image_uri = image_uri  # NEW FIELD
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "page_number": page_number,
            "bbox": list(self.bbox) if self.bbox else None,
            "quote": self.quote,
            "image_uri": self.image_uri,  # NEW FIELD
        }
```

**And in `_extract_citations` method (line 209):**
```python
bbox = chunk.bboxes[0] if chunk.bboxes else None
image_uri = chunk.metadata.get("image_uri") if chunk.metadata else None  # NEW
citations.append(
    Citation(
        document_id=chunk.document_id,
        chunk_id=chunk.id,
        page_number=chunk.page_start,
        bbox=bbox,
        image_uri=image_uri,  # NEW
    )
)
```

**File:** `apps/chat-api/src/chat_api/modules/messages/application/services.py`

**Changes:**
```python
# Line 83-96: Add presigned URL generation
for citation in raw_citations:
    try:
        citation_document_id = uuid.UUID(citation["document_id"])
    except (ValueError, KeyError):
        continue
    
    # NEW: Generate presigned URL if image_uri exists
    image_url = None
    if citation.get("image_uri"):
        try:
            from core.storage import create_storage_adapter
            from core.config import settings
            storage = create_storage_adapter(settings)
            image_url = storage.presigned_get_url(
                citation["image_uri"],
                expires_in=3600,
            )
        except Exception as exc:
            logger.warning("Failed to generate presigned URL: %s", exc)
    
    assistant_msg.add_citation(
        chunk_id=citation.get("chunk_id", ""),
        document_id=citation_document_id,
        page_number=citation.get("page_number", 1),
        bbox=citation.get("bbox") or [],
        quote=citation.get("quote"),
        relevance_score=citation.get("relevance_score"),
        image_url=image_url,  # NEW
    )
```

**File:** `apps/chat-api/src/chat_api/modules/messages/domain/entity.py`

**Changes:**
```python
@dataclass
class MessageCitation:
    ...
    image_url: str | None = None  # Presigned URL for visual evidence
```

**And update `Message.add_citation` signature:**
```python
def add_citation(
    self,
    *,
    chunk_id: str,
    document_id: uuid.UUID,
    page_number: int,
    bbox: list[float] | None = None,
    quote: str | None = None,
    relevance_score: float | None = None,
    image_url: str | None = None,  # NEW
) -> None:
    citation = MessageCitation(
        id=uuid7(),
        message_id=self.id,
        chunk_id=chunk_id,
        document_id=document_id,
        page_number=page_number,
        bbox=bbox or [],
        quote=quote,
        relevance_score=relevance_score,
        image_url=image_url,  # NEW
    )
    self.citations.append(citation)
```

**File:** `apps/chat-api/src/chat_api/modules/messages/presentation/dtos.py`

**Changes:**
```python
class CitationResponse(BaseModel):
    ...
    image_url: str | None = None
```

**File:** `apps/chat-api/src/chat_api/modules/messages/application/mapper.py`

**Changes:**
```python
def to_dto(cit: MessageCitation) -> CitationDTO:
    return CitationDTO(
        ...
        image_url=cit.image_url,
    )
```

---

## Step 7: Update Worker Dependencies for Dual OCR + Vision

**File:** `apps/worker/src/worker/dependencies.py`

**Changes:**
- Update `_get_ocr_fn()` to use `DualOCRRouter` (Step 3)
- Add `_get_vision_analyzer_fn()` for `GeminiVisionAnalyzer`
- Pass both to `DocumentPipeline.hybrid_semantic()`

**New signature:**
```python
def get_document_pipeline() -> DocumentPipeline:
    ...
    ocr_fn = _get_ocr_fn()
    vision_fn = _get_vision_analyzer_fn()  # New
    
    return DocumentPipeline.hybrid_semantic(
        embed_fn=embed_fn,
        ocr_fn=ocr_fn,
        vision_fn=vision_fn,  # New parameter
        ...
    )
```

**File:** `packages/rag-document-pipeline/src/rag_document_pipeline/pipeline.py`

**Changes:**
- Add `vision_fn: Any = None` parameter to `DocumentPipeline.__init__` and `hybrid_semantic()`
- Pass `vision_fn` to `MultimodalChunker`

**File:** `packages/rag-document-pipeline/src/rag_document_pipeline/chunking/multimodal.py`

**Changes:**
- Add `vision_fn: Any = None` parameter
- Pass to `ImageChunker(vision_fn=vision_fn)`

**File:** `packages/rag-document-pipeline/src/rag_document_pipeline/chunking/strategies/image.py`

**Changes:**
- Add `vision_fn: Any = None` parameter to `ImageChunker.__init__`
- In `_chunk_image`, if `vision_fn` exists and image is a chart/diagram (not text-heavy), call `vision_fn` instead of `ocr_fn`
- Heuristic: if OCR result is < 50 chars but image is large (> 500x500), likely a chart → use vision

---

## Step 8: Populate Image Dimensions in Parser

**File:** `packages/rag-document-pipeline/src/rag_document_pipeline/parsers/opendataloader.py`

**Changes:**
- In `_to_elements`, after creating `ImageData`, read image dimensions using PIL
- Populate `element.metadata["width"]` and `element.metadata["height"]`

**Implementation:**
```python
if element_type in ("image", "figure"):
    uri = item.get("data")
    ...
    image_data = ImageData(uri=uri, caption=caption)
    
    # Populate dimensions for triage
    if uri and Path(uri).exists():
        try:
            from PIL import Image
            with Image.open(uri) as img:
                metadata["width"] = img.width
                metadata["height"] = img.height
        except Exception:
            pass
```

---

## Step 9: Add Configuration Settings

**File:** `core/src/core/config.py`

**New settings:**
```python
# Image Triage
IMAGE_TRIAGE_ENABLED: bool = True
IMAGE_MIN_WIDTH: int = 100
IMAGE_MIN_HEIGHT: int = 100
IMAGE_MAX_ASPECT_RATIO: float = 10.0

# Dual OCR
OCR_FAST_ENABLED: bool = True
OCR_FAST_LANG: str = "eng+vie"

# Vision Analysis
VISION_ANALYSIS_ENABLED: bool = True
VISION_MODEL: str = "gemini-2.0-flash"

# Presigned URLs
PRESIGNED_URL_EXPIRY_SECONDS: int = 3600
```

---

## Step 10: Tests

**New Test Files:**
1. `packages/rag-document-pipeline/tests/test_image_triage.py` — Test size-based filtering
2. `packages/rag-core/tests/test_dual_ocr.py` — Test DualOCRRouter fallback
3. `packages/rag-core/tests/test_vision_analyzer.py` — Test structured prompt
4. `tests/unit/test_presigned_urls.py` — Test MinIO presigned URL generation

**Updated Tests:**
- `packages/rag-document-pipeline/tests/test_chunkers.py` — Add tests for triage skip logic
- `apps/chat-api/tests/unit/test_rag_chat_service.py` — Add tests for image_url in citations

---

## Verification Plan

1. **Unit Tests:** Run `pytest packages/rag-document-pipeline/tests/test_image_triage.py -v`
2. **Integration Test:** Upload a PDF with mixed images (small icons + large charts) and verify:
   - Small images are skipped (indexable=False)
   - Large charts get structured VLM analysis
   - Citations include `image_url` presigned URLs
3. **Manual Test:** Use `scripts/demo_pipeline.py` to process a sample PDF and inspect chunk metadata
4. **API Test:** Send a chat query that retrieves an image chunk and verify `image_url` is in the response

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Tesseract not installed on system | Graceful fallback to VLM-only; log warning |
| PIL not available | Add to `pyproject.toml`; parser handles ImportError |
| Presigned URL generation fails | Return `None` for `image_url`; frontend handles missing URL |
| VLM returns malformed structured text | Parse leniently; fallback to raw text |
| Image dimensions not in parser JSON | Read from PIL; if fails, skip triage (don't block indexing) |

---

## Files to Create/Modify

**Create:**
- `packages/rag-core/src/rag_core/providers/ocr/tesseract.py`
- `packages/rag-core/src/rag_core/providers/ocr/router.py`
- `packages/rag-core/src/rag_core/providers/ocr/vision.py`
- `packages/rag-document-pipeline/tests/test_image_triage.py`
- `packages/rag-core/tests/test_dual_ocr.py`
- `packages/rag-core/tests/test_vision_analyzer.py`
- `tests/unit/test_presigned_urls.py`

**Modify:**
- `packages/rag-document-pipeline/src/rag_document_pipeline/chunking/strategies/image.py`
- `packages/rag-document-pipeline/src/rag_document_pipeline/chunking/multimodal.py`
- `packages/rag-document-pipeline/src/rag_document_pipeline/pipeline.py`
- `packages/rag-document-pipeline/src/rag_document_pipeline/parsers/opendataloader.py`
- `packages/rag-core/src/rag_core/providers/ocr/gemini.py`
- `core/src/core/storage/ports/storage_port.py`
- `core/src/core/storage/adapters/minio.py`
- `core/src/core/storage/adapters/local.py`
- `core/src/core/config.py`
- `apps/worker/src/worker/dependencies.py`
- `apps/chat-api/src/chat_api/modules/messages/application/services.py`
- `apps/chat-api/src/chat_api/modules/messages/domain/entity.py`
- `apps/chat-api/src/chat_api/modules/messages/presentation/dtos.py`
- `apps/chat-api/src/chat_api/modules/messages/application/mapper.py`
- `packages/rag-core/pyproject.toml` (add pytesseract, Pillow)
