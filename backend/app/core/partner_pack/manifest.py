"""PartnerPackManifest - the Pydantic schema each partner pack exports."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PartnerBranding(BaseModel):
    """Branding overrides applied at runtime when a pack is active."""

    primary_color: str = Field(
        default="#0F2C5F",
        description="Hex (#RRGGBB). Replaces --oe-primary at boot.",
    )
    accent_color: str | None = Field(
        default=None,
        description="Optional secondary brand colour. Replaces --oe-accent.",
    )
    favicon_path: str | None = Field(
        default=None,
        description="Path inside the pack package to a favicon. Streamed via /api/v1/partner-pack/favicon.",
    )
    logo_path: str = Field(
        default="logo.svg",
        description="Path inside the pack package to the partner logo. Streamed via /api/v1/partner-pack/logo.",
    )
    powered_by_text: str | None = Field(
        default=None,
        description=(
            "Co-branding line shown next to the partner logo. "
            "Defaults to 'Powered by OpenConstructionERP · In partnership with {partner_name}'."
        ),
    )


class PartnerPackManifest(BaseModel):
    """Manifest exported by a partner pack via the entry-point group.

    The pack's ``pyproject.toml`` declares::

        [project.entry-points."openconstructionerp.partner_packs"]
        batimatech-ca = "openconstructionerp_batimatech_ca:MANIFEST"

    where ``MANIFEST`` is a module-level ``PartnerPackManifest`` instance
    (or a dict the loader coerces into one).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slug: str = Field(
        ...,
        description="Stable lowercase identifier, e.g. 'batimatech-ca'.",
        pattern=r"^[a-z][a-z0-9\-]{2,40}$",
    )
    partner_name: str = Field(
        ...,
        description="Display name of the partner organisation.",
        min_length=2,
        max_length=80,
    )
    partner_url: str | None = Field(
        default=None,
        description="Partner homepage. Used as the link target on the logo strip.",
    )
    pack_version: str = Field(
        default="0.1.0",
        description="Pack version (semver). Independent of core version.",
    )
    description: str = Field(
        default="",
        description="One-paragraph human-readable description (English).",
        max_length=800,
    )

    # Locale & region presets
    default_locale: str = Field(
        default="en",
        description="BCP-47 locale code used as the new boot default.",
        min_length=2,
        max_length=10,
    )
    additional_locales: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Optional extra locales the pack ships. Mapping locale_code -> path inside the pack package to a JSON file."
        ),
    )

    # Cost DB presets
    cwicr_regions: list[str] = Field(
        default_factory=list,
        description="CWICR marketplace slugs to preload, e.g. ['cwicr-eng-toronto'].",
    )
    default_currency: str = Field(
        default="EUR",
        description="ISO 4217 default currency.",
        pattern=r"^[A-Z]{3}$",
    )
    default_tax_template: str | None = Field(
        default=None,
        description="Tax template slug to set as default (e.g. 'ca_gst_pst').",
    )

    # Validation rule presets
    validation_rule_packs: list[str] = Field(
        default_factory=list,
        description=(
            "Built-in validation rule-pack slugs to enable by default. "
            "Packs cannot ship new rule classes (Shape A); they only switch "
            "on rules that already exist in the core."
        ),
    )

    # Module presets
    default_modules: list[str] = Field(
        default_factory=list,
        description=(
            "Module slugs to keep enabled in the sidebar by default. "
            "Empty list means 'all modules visible'. Users can still "
            "show/hide modules via the sidebar menu editor."
        ),
    )
    hidden_modules: list[str] = Field(
        default_factory=list,
        description=("Module slugs to hide by default for this pack. Users can re-enable via the sidebar editor."),
    )

    # Branding (logo, colours, favicon)
    branding: PartnerBranding = Field(default_factory=PartnerBranding)

    # Demo project presets
    demo_template_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Optional explicit list of demo project ids (keys of "
            "``DEMO_TEMPLATES``) this pack installs. When set, the one-click "
            "installer seeds exactly these (in order, de-duplicated) instead of "
            "deriving the list from the flagship demo's country. Empty list "
            "keeps the default flagship + country-fill behaviour."
        ),
    )

    # Onboarding script - declarative YAML/JSON applied at first login
    onboarding_script_path: str | None = Field(
        default=None,
        description=(
            "Path inside the pack package to a YAML/JSON onboarding script. "
            "Replaces the default OnboardingWizard steps when set."
        ),
    )

    # Free-form metadata for partners who want to surface extra data
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------
    @property
    def effective_powered_by(self) -> str:
        """Co-branding string. Default preserves AGPL attribution."""
        if self.branding.powered_by_text:
            return self.branding.powered_by_text
        return f"Powered by OpenConstructionERP · In partnership with {self.partner_name}"

    def to_public_dict(self) -> dict[str, Any]:
        """Serialise for the /api/v1/partner-pack/current endpoint.

        Strips internal-only fields (file paths inside the pack package
        are not useful to the frontend; they get exposed via dedicated
        streaming endpoints).
        """
        return {
            "slug": self.slug,
            "partner_name": self.partner_name,
            "partner_url": self.partner_url,
            "pack_version": self.pack_version,
            "description": self.description,
            "default_locale": self.default_locale,
            "additional_locales": sorted(self.additional_locales.keys()),
            "cwicr_regions": self.cwicr_regions,
            "default_currency": self.default_currency,
            "default_tax_template": self.default_tax_template,
            "validation_rule_packs": self.validation_rule_packs,
            "demo_template_ids": self.demo_template_ids,
            "default_modules": self.default_modules,
            "hidden_modules": self.hidden_modules,
            "branding": {
                "primary_color": self.branding.primary_color,
                "accent_color": self.branding.accent_color,
                "has_logo": True,  # always streamed even if pack omits - fallback handled
                "has_favicon": self.branding.favicon_path is not None,
                "powered_by_text": self.effective_powered_by,
            },
            "has_onboarding_script": self.onboarding_script_path is not None,
            "metadata": self.metadata,
        }
