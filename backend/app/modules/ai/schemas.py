"""‌⁠‍AI Estimation Pydantic schemas - request/response models.

Defines schemas for AI settings management, quick/photo estimate requests,
and estimate job responses with generated BOQ items.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


# ── v3 §10 money serialisation helper ─────────────────────────────────────
# Money fields are stored / accepted as ``Decimal`` but emitted as plain
# decimal *strings* in JSON. ``float`` silently drops precision past ~15
# significant digits; emitting a string keeps totals exact and locale-neutral.
# Mirrors backend/app/modules/boq/schemas.py::_serialise_money.
def _serialise_money(v: Decimal | None) -> str | None:
    if v is None:
        return None
    if not isinstance(v, Decimal):
        try:
            v = Decimal(str(v))
        except (InvalidOperation, ValueError):
            return "0"
    if not v.is_finite():
        return "0"
    return format(v, "f")


# ── AI Settings schemas ──────────────────────────────────────────────────────


class AISettingsUpdate(BaseModel):
    """‌⁠‍Update per-user AI configuration (API keys, preferred model)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    mistral_api_key: str | None = None
    groq_api_key: str | None = None
    deepseek_api_key: str | None = None
    together_api_key: str | None = None
    fireworks_api_key: str | None = None
    perplexity_api_key: str | None = None
    cohere_api_key: str | None = None
    ai21_api_key: str | None = None
    xai_api_key: str | None = None
    zhipu_api_key: str | None = None
    baidu_api_key: str | None = None
    yandex_api_key: str | None = None
    gigachat_api_key: str | None = None
    kimi_api_key: str | None = None
    # Custom base URL for local providers (Ollama, vLLM), e.g. "http://host:11434"
    ollama_base_url: str | None = None
    vllm_base_url: str | None = None
    preferred_model: str | None = Field(default=None, max_length=100)
    # Per-provider model-id override, e.g. {"gemini": "gemini-2.5-flash",
    # "openrouter": "anthropic/claude-sonnet-4"}. Lets users track provider
    # model renames/retirements without an app release (issue #129). A blank
    # value for a provider clears the override (falls back to the default).
    model_overrides: dict[str, str] | None = Field(
        default=None,
        description="Per-provider model id override (provider -> model id).",
    )


class AISettingsResponse(BaseModel):
    """‌⁠‍AI settings returned from the API.

    API keys are masked - only the last 4 characters are shown.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    user_id: UUID
    anthropic_api_key_set: bool = False
    openai_api_key_set: bool = False
    gemini_api_key_set: bool = False
    openrouter_api_key_set: bool = False
    mistral_api_key_set: bool = False
    groq_api_key_set: bool = False
    deepseek_api_key_set: bool = False
    together_api_key_set: bool = False
    fireworks_api_key_set: bool = False
    perplexity_api_key_set: bool = False
    cohere_api_key_set: bool = False
    ai21_api_key_set: bool = False
    xai_api_key_set: bool = False
    zhipu_api_key_set: bool = False
    baidu_api_key_set: bool = False
    yandex_api_key_set: bool = False
    gigachat_api_key_set: bool = False
    kimi_api_key_set: bool = False
    ollama_base_url: str | None = None
    vllm_base_url: str | None = None
    preferred_model: str
    # Effective per-provider model id the platform will send (override if the
    # user set one, otherwise the built-in default). Drives the editable
    # "Model name" field in Settings > AI.
    model_overrides: dict[str, str] = Field(default_factory=dict)
    default_models: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Estimate request schemas ─────────────────────────────────────────────────


class QuickEstimateRequest(BaseModel):
    """Text-based quick estimation request.

    The AI analyses the description and generates a full BOQ.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    description: str = Field(..., min_length=10, max_length=5000, description="Project description")
    project_type: str | None = Field(
        default=None,
        max_length=100,
        description="Building type: office, residential, warehouse, etc.",
    )
    area_m2: float | None = Field(default=None, gt=0, le=1_000_000, description="Total area in m2")
    location: str | None = Field(default=None, max_length=200, description="City or country for pricing context")
    currency: str | None = Field(default=None, max_length=10, description="Currency code: EUR, USD, GBP, etc.")
    standard: str | None = Field(
        default=None,
        max_length=50,
        description="Classification standard: din276, nrm, masterformat",
    )
    project_id: UUID | None = Field(default=None, description="Optional project to link the estimate job to")


class PhotoEstimateRequest(BaseModel):
    """Photo-based estimation request metadata.

    The photo file is uploaded separately via multipart form data.
    This schema captures the additional context fields.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    location: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, max_length=10)
    standard: str | None = Field(default=None, max_length=50)
    project_id: UUID | None = None


# ── Estimate result schemas ──────────────────────────────────────────────────


class EstimateItem(BaseModel):
    """A single work item generated by AI estimation.

    v3 §10 - ``unit_rate`` (money) is Decimal-as-string in JSON. ``total``
    is kept as ``float`` here because it is a UI-side preview value the
    frontend can recompute from ``quantity * unit_rate``; sibling
    ``CreateBOQFromEstimateRequest`` writes the persistent line totals
    via the boq service which is already Decimal-correct.
    """

    ordinal: str = ""
    description: str
    unit: str = "m2"
    quantity: float = 0.0
    unit_rate: Decimal = Decimal("0")
    total: float = 0.0
    classification: dict[str, str] = Field(default_factory=dict)
    category: str = "General"
    confidence: float | None = None

    @field_serializer("unit_rate", when_used="json")
    def _ser_unit_rate(self, v: Decimal) -> str | None:
        return _serialise_money(v)


class EstimateJobResponse(BaseModel):
    """Full AI estimation job response - status, items, and metadata.

    v3 §10 - money fields (``grand_total``, ``cost_usd_estimate``) are
    Decimal-as-string in JSON. The underlying DB column for
    ``cost_usd_estimate`` is Float (small USD values, no precision risk),
    but we still emit Decimal-as-string on the wire so the contract is
    uniform with every other money field.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    user_id: UUID
    project_id: UUID | None = None
    input_type: str
    input_text: str | None = None
    input_filename: str | None = None
    status: str
    items: list[EstimateItem] = Field(default_factory=list)
    # Resolved currency the items were priced in (ISO code or empty when the
    # currency is unknown). The frontend must show this ISO code rather than a
    # hard-coded EUR symbol, and never blend it with foreign-currency rates.
    currency: str = ""
    error_message: str | None = None
    model_used: str | None = None
    tokens_used: int = 0
    duration_ms: int = 0
    cost_usd_estimate: Decimal = Decimal("0")
    grand_total: Decimal = Decimal("0")
    created_at: datetime
    updated_at: datetime

    @field_serializer("grand_total", "cost_usd_estimate", when_used="json")
    def _ser_money(self, v: Decimal) -> str | None:
        return _serialise_money(v)


class CreateBOQFromEstimateRequest(BaseModel):
    """Request to create a real BOQ from an AI estimate job."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    boq_name: str = Field(default="AI Estimate", min_length=1, max_length=255)
    # When true, run cost-DB enrichment during BOQ creation and replace each
    # line's AI rate with the best same-currency CWICR match (recording the
    # match code on the position). Lets the user persist the regional rates
    # they reviewed in the UI instead of the raw AI guesses. Off by default so
    # the legacy "save AI rates as-is" behaviour is unchanged.
    apply_enriched: bool = False
    # Region used for the cost-DB lookup when ``apply_enriched`` is set
    # (e.g. "DE_BERLIN"). Empty = search across all regions.
    region: str = Field(default="", max_length=64)


# ── Estimate history (server-side job list) ──────────────────────────────────


class EstimateJobSummary(BaseModel):
    """Lightweight summary of an estimate job for the history list.

    Excludes the full ``items`` payload (which can be large) so the list
    endpoint stays cheap to page through. The frontend fetches the full job
    via ``GET /ai/estimate/{id}`` when the user reopens one.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None = None
    input_type: str
    input_text: str | None = None
    input_filename: str | None = None
    status: str
    items_count: int = 0
    currency: str = ""
    grand_total: Decimal = Decimal("0")
    model_used: str | None = None
    tokens_used: int = 0
    cost_usd_estimate: Decimal = Decimal("0")
    duration_ms: int = 0
    error_message: str | None = None
    created_at: datetime

    @field_serializer("grand_total", "cost_usd_estimate", when_used="json")
    def _ser_money(self, v: Decimal) -> str | None:
        return _serialise_money(v)


class EstimateJobListResponse(BaseModel):
    """Paginated list of estimate-job summaries for the current user."""

    items: list[EstimateJobSummary] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0
