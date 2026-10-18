# Implementation Plan --- Adaptive RAG Document Chunking

**Status:** Proposed implementation specification. Thresholds in this
document are experimental defaults, not proven optimal values.

## 1. Objective

Implement one shared, testable document-processing pipeline that
preserves document structure, element-specific content, context, and
source traceability while allowing different chunking policies for legal
documents, SOPs, reports, business plans, and internal wiki pages.

### Design principles

-   Prefer parser-provided structure over regex heuristics.
-   Route tables and figures separately from ordinary prose.
-   Use a shared engine with small domain policies, not five duplicated
    pipelines.
-   Preserve relevant context in chunk text, metadata, or retrievable
    relationships.
-   Enforce token limits using the target embedding model's tokenizer
    where possible.
-   Treat semantic splitting thresholds as benchmark parameters.
-   Record fallbacks and failures; do not silently lose content.
-   Measure retrieval quality separately from unit-test success.

## 2. Target architecture

``` mermaid
flowchart TD
    A[PDF / DOCX / HTML / Wiki] --> B[Parser and layout analysis]
    B --> C[Normalized Document IR]
    C --> D[Element and document classification]
    D --> E[Adaptive Chunking Router]
    E --> F[Domain and structure policies]
    D --> G[Table processor]
    D --> H[Image and chart processor]
    F --> I[Context enrichment]
    G --> I
    H --> I
    I --> J[Validation and integrity report]
    J --> K[Chunk repository]
    K --> L[Embedding and indexing]
    L --> M[Vector + lexical retrieval]
```

  -----------------------------------------------------------------------
  Component                           Responsibility
  ----------------------------------- -----------------------------------
  Parser adapter                      Convert parser-specific output to a
                                      normalized representation

  Normalizer                          Normalize IDs, element types,
                                      reading order, sections and source
                                      locations

  Classifier                          Determine document/element type and
                                      retain uncertainty

  Router                              Choose a policy; keep routing
                                      separate from chunking
                                      implementation

  Domain policy                       Preserve legal clauses, procedures,
                                      report periods, scenarios or wiki
                                      structure

  Element processor                   Preserve table/figure-specific
                                      structure

  Context enricher                    Add concise breadcrumbs and
                                      relevant inherited context

  Validator                           Check size, coverage, metadata and
                                      source traceability

  Index adapter                       Idempotent writes, version handling
                                      and embedding/index integration
  -----------------------------------------------------------------------

## 3. Suggested module layout

Adapt this to the existing repository; do not move files or create empty
abstractions just to match this tree.

``` text
rag_document_pipeline/
  models/
    document.py
    chunk.py
    metadata.py
  parsing/
    adapter.py
    normalize.py
  routing/
    classifier.py
    chunking_router.py
  chunking/
    base.py
    text.py
    hierarchy.py
    semantic.py
    legal.py
    procedure.py
    report.py
    business_plan.py
    wiki.py
  elements/
    table.py
    figure.py
    chart.py
  enrichment/
    context.py
    metadata.py
    relationships.py
  validation/
    chunk_validator.py
    integrity_report.py
  indexing/
    repository.py
    embedding.py
  evaluation/
    benchmark_runner.py
  tests/
    unit/
    integration/
    fixtures/
```

## 4. Core data contracts

These examples are starting contracts, not drop-in code. Align naming
and validation with the project's existing models.

``` python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SourceLocation:
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    source_element_id: str | None = None

@dataclass
class ElementIR:
    element_id: str
    element_type: str  # text, heading, list, table, image, chart, formula, unknown
    order: int
    text: str | None = None
    parent_section_id: str | None = None
    source: SourceLocation = field(default_factory=SourceLocation)
    payload: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None

@dataclass
class SectionIR:
    section_id: str
    title: str | None
    level: int | None
    parent_section_id: str | None
    element_ids: list[str] = field(default_factory=list)
    section_path: list[str] = field(default_factory=list)

@dataclass
class DocumentIR:
    document_id: str
    version_id: str
    title: str | None
    document_type: str
    elements: list[ElementIR]
    sections: list[SectionIR]
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    document_version_id: str
    text: str
    element_type: str
    section_path: list[str] = field(default_factory=list)
    source_element_ids: list[str] = field(default_factory=list)
    page_numbers: list[int] = field(default_factory=list)
    parent_chunk_id: str | None = None
    relationships: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    strategy: str = "unknown"
    token_count: int | None = None
```

### Contract rules

-   `document_id` identifies the logical document; `version_id`
    identifies one content version.
-   Preserve parser element IDs when available, but scope them to a
    document/version if they are not globally unique.
-   `order` preserves parser reading order.
-   Document the coordinate convention used for `bbox`.
-   `section_path` is a breadcrumb; it does not replace parent IDs.
-   Unknown type or metadata is valid. Never fabricate values to fill
    fields.
-   Track metadata provenance for important extracted/inferred values
    (`parser`, `inherited`, `regex`, `model`, or `user`). Only attach
    confidence values if their meaning is defined.

## 5. Routing policy

Route by **element type first**, then document/domain policy, then
optional semantic splitting.

``` python
def route(element, context):
    if element.element_type == "table":
        return table_processor
    if element.element_type in {"image", "chart"}:
        return figure_or_chart_processor

    policies = {
        "legal": legal_policy,
        "sop": procedure_policy,
        "progress_report": report_policy,
        "business_plan": business_plan_policy,
        "internal_doc": wiki_policy,
    }
    return policies.get(context.document_type, generic_structure_policy)
```

Production code must handle unknown/low-confidence classification, mixed
documents, exceptions and policy configuration. Prefer an explicit
user/source document type; otherwise infer from headings and content
signals. When confidence is low, use generic structure-aware chunking
rather than forcing a specialized path. Allow section-level overrides
only when the use case needs them.

## 6. Domain policies

### 6.1 Legal documents --- hierarchy-aware

-   Prefer reliable hierarchy: chapter → article → clause →
    subclause/item.
-   Preserve numbering, conditions, exceptions, provisos and
    cross-references.
-   Include a compact breadcrumb such as
    `Chapter II > Article 2 > Clause 2.1`.
-   If a clause exceeds the hard token limit, split at
    subclauses/sentences and retain the parent clause ID.
-   Record that a clause was split; do not label each fragment as a
    complete clause.
-   Do not let semantic similarity override reliable legal boundaries.

Metadata: document/version, article/clause IDs, section path, effective
date if present, source pages.

### 6.2 SOP and user guides --- procedure-aware

-   Keep action, prerequisite, warning, expected result and related
    screenshot/caption together when feasible.
-   Preserve step order and conditional branches (`if`, `otherwise`,
    `then`).
-   Split long procedures into step groups linked to the procedure
    parent.
-   Do not merge unrelated procedures just to reach a target size.

Metadata: procedure title/ID, step range, section path, warning level
when present.

### 6.3 Progress and KPI reports --- period-aware

-   Preserve metric name, value, unit, reporting period, project/team,
    owner and status when present.
-   Keep applicable table headers and notes with row groups.
-   Do not mix reporting periods without explicit labels.
-   Keep separate projects distinguishable.

Metadata: project, report period, metric, unit, owner/status where
available.

### 6.4 Business plans --- context-aware

-   Preserve scenario, assumptions, currency, unit and fiscal period for
    forecasts.
-   Include or reference table title, headers, units and footnotes.
-   Link forecast chunks to relevant assumption chunks.
-   Do not append every assumption to every chunk; add only relevant
    context.

Metadata: plan/version, scenario, currency, unit, fiscal period,
assumption references.

### 6.5 Internal wiki and handbook --- structure-first

-   Split at reliable headings, paragraphs and list boundaries first.
-   Apply semantic splitting only to long prose sections that lack
    useful internal boundaries or remain too large.
-   Preserve a list's introduction if it changes how its items should be
    interpreted.
-   Preserve links and references as metadata or relationships.

Metadata: department/topic/document type, updated time if present,
access level and section path.

### 6.6 Generic fallback

Use heading → paragraph/list → sentence boundaries, then recursive
splitting only if the piece still exceeds the token budget. Record the
selected strategy and fallback reason. Do not silently drop unsplittable
content.

## 7. Element-specific processing

### Tables

Preserve table title/caption, multi-level headers, row labels,
units/currency, reporting period, footnotes, source page and element ID.
For large tables, emit row-group chunks with repeated applicable
headers. Avoid splitting rows unless the representation explicitly
supports it. Keep structured rows/columns in addition to searchable text
when numerical questions matter.

### Images and screenshots

Keep a stable asset ID/URI, caption, OCR text, page/bounding box, parent
section and related step/text IDs. Label generated vision descriptions
as generated; never present them as verbatim source text.

### Charts

Where supported, preserve title, axes, units, series labels, values,
time period, legend and source notes. If values cannot be extracted
reliably, store the image and a qualified description; do not invent
precise data points.

## 8. Context enrichment and metadata

Use this priority order:

1.  Explicit source or ingestion metadata.
2.  Parser-derived title, heading, section path and caption.
3.  Inherited context from parent sections.
4.  Deterministic rules/regex with provenance.
5.  Optional model-based extraction for high-value fields.
6.  `null`/`unknown` when evidence is insufficient.

  -----------------------------------------------------------------------
  Information             Put in chunk text?      Metadata/relationship
  ----------------------- ----------------------- -----------------------
  Section breadcrumb      Yes, when needed to     Section path and parent
                          interpret the chunk     ID
                          alone                   

  Period, unit, scenario  Yes, when it changes    Structured fields and
                          the meaning of a        relevant assumption
                          retrieved value         links

  Page/bounding box       Usually no              Source location

  Legal clause ID         Usually include         Clause ID and parent
                          label/number            article

  Table/figure caption    Include when it helps   Element ID and related
                          interpretation          IDs
  -----------------------------------------------------------------------

Metadata is not automatically visible to the answer-generating LLM.
Context assembly must explicitly include necessary metadata and any
expanded parent/related chunks. Avoid repeating large context blocks in
every chunk.

## 9. Token limits and semantic splitting

Use the target embedding model's tokenizer where possible. Character
counts are not equivalent to token counts, especially across languages.

Suggested values for initial experiments only:

  Parameter                                                    Starting point
  -------------------- ------------------------------------------------------
  Target chunk size                                           300--600 tokens
  Hard maximum                 Below the embedding model's actual input limit
  Overlap                           0--80 tokens, only if continuity benefits
  Semantic splitting                                    Off until benchmarked
  Split trigger          Token budget or absence of useful internal structure

Rules:

-   Semantic splitting proposes boundaries within prose; it does not
    replace structural parsing.
-   Define whether the threshold is cosine similarity or distance, and
    which direction means "split".
-   Batch embedding requests where possible and cache intermediate
    embeddings safely.
-   Do not assume `0.80` or `0.95` is universally correct.
-   If semantic scoring fails, use deterministic
    structure-aware/recursive splitting and record why.
-   If an atomic unit exceeds the hard limit, split by its internal
    structure; retain the original unit/parent ID and emit an integrity
    warning if no safe boundary exists.
-   Never submit an over-limit chunk to the embedding model on the
    assumption it will accept it.

## 10. Validation and failure handling

Every ingestion run should emit a report with counts, warnings and
errors.

### Validation checks

-   No empty chunks.
-   Every chunk is within the hard token limit.
-   Every chunk has document ID and version ID.
-   Source element/page references exist when the parser provides them.
-   Parent IDs and section paths resolve or are explicitly marked
    unresolved.
-   Table chunks preserve available headers/units/footnotes.
-   Legal chunks retain clause IDs and report when clauses are split.
-   Every input element is represented, intentionally filtered by a
    documented rule, or reported as a failure.
-   Inferred metadata has provenance where required.
-   Re-ingestion of the same document version is idempotent.

### Failure policy

-   Parser failure: fail the ingestion; do not index an empty document.
-   Partial parse: continue only with usable output and report omitted
    pages/elements.
-   Specialized policy failure: use generic structure-aware fallback if
    safe.
-   Element processor failure: retain source reference and warning; do
    not fabricate content.
-   Embedding failure: retry using the existing retry policy without
    duplicating indexed chunks.
-   Validation failure: quarantine/report invalid chunks rather than
    silently discarding them.

## 11. Identity, versioning, and access control

Suggested logical keys:

-   Document: `(tenant_id, document_id)`
-   Version: `(tenant_id, document_id, version_id)`
-   Chunk: `(tenant_id, document_id, version_id, chunk_id)`

Choose a deterministic chunk ID policy (stable source IDs plus
strategy/version and ordinal, or canonical content hash plus source
identity). Document what happens when content moves or changes.

Store tenant/workspace ID, ACL attributes, document/version IDs, text,
metadata, source IDs/locations, strategy/config version and embedding
model/version. On update, index the new version safely and deactivate
stale chunks according to the existing consistency model. Apply
tenant/ACL filters before exposing retrieved chunks to the LLM.

## 12. Test plan

### Unit tests

1.  Legal nested clause numbering and parent IDs.
2.  Clause exceptions remain attached when within limits.
3.  Oversized clauses split into children linked to the same clause.
4.  SOP step order, warnings and screenshot relationships.
5.  Report values preserve period and unit.
6.  Business-plan forecasts preserve scenario and assumption links.
7.  Wiki uses heading-first splitting; semantic splitting is optional.
8.  Table chunks repeat applicable headers and preserve units/footnotes.
9.  Image/chart chunks retain asset references and provenance.
10. Unknown document type uses generic fallback.
11. Empty parser output does not produce a successful empty index.
12. Hard token limit is enforced.
13. Re-ingestion is idempotent.
14. Missing metadata remains unknown rather than receiving a fabricated
    default.
15. Errors produce expected warnings/retries.

### Integration tests

-   Parse representative PDF/DOCX/HTML fixtures into normalized IR.
-   Route a mixed document containing headings, prose, tables and
    figures.
-   Verify parent/related-element expansion provides required context.
-   Verify tenant/ACL filters prevent cross-tenant retrieval.
-   Verify a new document version does not leave stale active chunks.

### Retrieval benchmark

Create representative queries with expected answers/evidence spans and
source page/element IDs. Compare:

1.  Fixed/recursive baseline.
2.  Structure-aware only.
3.  Structure-aware + domain policies.
4.  Structure-aware + domain policies + selective semantic splitting.

Measure Recall@k, MRR or nDCG, answer correctness, citation accuracy,
ingestion latency, embedding tokens/cost, failure rate and percentage of
source content not represented. Tune on a development set and use a
held-out set when practical. Unit-test pass rate is not a substitute for
retrieval evaluation.

## 13. Implementation milestones

### M1 --- Contracts and generic path

-   [ ] Inspect current parser output and chunking implementation.
-   [ ] Define normalized IR, chunk and source-location contracts.
-   [ ] Add normalization adapter for the existing parser.
-   [ ] Implement generic structure-aware text chunking.
-   [ ] Add token counting and hard-limit validation.
-   [ ] Add representative fixtures and unit tests.
-   [ ] Log strategy, chunk count, token count and warnings.

**Exit criteria:** one representative document produces non-empty,
bounded, traceable chunks.

### M2 --- Elements and context

-   [ ] Implement table row-group serialization with headers/units.
-   [ ] Preserve image/chart asset references, captions and provenance.
-   [ ] Add context breadcrumbs and parent/related-element
    relationships.
-   [ ] Add content-coverage and source-traceability checks.
-   [ ] Add mixed-content integration tests.

**Exit criteria:** retrieved table/figure chunks retain enough context
to interpret them and can be traced to source.

### M3 --- Domain policies

-   [ ] Legal hierarchy policy.
-   [ ] SOP/procedure policy.
-   [ ] Report period/KPI policy.
-   [ ] Business-plan scenario/assumption policy.
-   [ ] Wiki heading-first policy.
-   [ ] Tests for each policy and generic fallback.

**Exit criteria:** domain-critical context is preserved without
duplicating generic chunking code.

### M4 --- Semantic splitting experiment

-   [ ] Add semantic boundary proposals behind a feature flag.
-   [ ] Define metric and threshold semantics.
-   [ ] Add batching/cache where appropriate.
-   [ ] Benchmark against structure-only baseline.
-   [ ] Enable only for document groups where gains justify cost.

**Exit criteria:** semantic splitting is enabled only when evaluation
shows measurable benefit.

### M5 --- Production hardening

-   [ ] Idempotent indexing and stale-version handling.
-   [ ] Tenant/ACL filters.
-   [ ] Retry/error states and ingestion reports.
-   [ ] Metrics and structured logs.
-   [ ] Retrieval benchmark and documented configuration.

**Exit criteria:** retries and re-ingestion are safe; traceability,
access control, metrics and evaluation are in place.

## 14. Configuration example

``` python
from dataclasses import dataclass

@dataclass(frozen=True)
class ChunkingConfig:
    target_chunk_tokens: int = 450
    max_chunk_tokens: int = 700
    overlap_tokens: int = 40
    enable_semantic_splitting: bool = False
    semantic_threshold: float | None = None
    tokenizer_name: str | None = None
    config_version: str = "v1"
```

These are illustrative values. Validate
`target_chunk_tokens <= max_chunk_tokens`, set the hard maximum below
the model's input limit, and define the threshold metric before enabling
semantic splitting.

## 15. Definition of done

-   [ ] One normalized IR and an explicit router/policy boundary exist.
-   [ ] Text, tables and figures use appropriate processing paths.
-   [ ] Legal, SOP, report and business-plan invariants have tests.
-   [ ] Unknown metadata remains unknown; provenance is recorded where
    required.
-   [ ] Every indexed chunk has stable document/version identity and
    source traceability.
-   [ ] Hard limits, partial failures and retries are explicit.
-   [ ] Re-ingestion is idempotent and stale versions are handled.
-   [ ] Tenant/ACL filtering is applied during retrieval.
-   [ ] Retrieval quality and ingestion cost are measured against a
    baseline.
-   [ ] Numeric thresholds are documented as measured choices, not
    assumptions.

## 16. Engineering notes

-   First inspect the current repository and adapt these contracts to
    existing types and interfaces. Avoid a broad rewrite before
    understanding current behavior.
-   Keep the first implementation deterministic. Add model-based
    classification/extraction only where it demonstrably improves
    outcomes.
-   Do not create a large class for every document type unless the rules
    truly differ.
-   Keep parser output, normalized IR, chunks and index records distinct
    so each stage can be tested independently.
-   Preserve provenance so a poor answer can be traced back to its
    source page and element.
