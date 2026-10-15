"""Manifest of the Owner's Project Control pack.

The pack is data only: it selects the platform modules and ships catalogues
for them. The fields are written here as literals because a pack in the source
tree is found and checked through its ``manifest.py``, several checks read this
file as text, and a field written any other way reads to them as not declared.

``manifest.json`` beside this file states the same manifest for a pack dropped
into the data directory, where it is validated and never executed. The two are
held equal by ``backend/tests/unit/test_eleven_areas_pack_files.py``; change
both together.
"""

from __future__ import annotations

from app.core.partner_pack.manifest import PartnerBranding, PartnerPackManifest

MANIFEST = PartnerPackManifest(
    slug="eleven-areas-framework",
    partner_name="Owner's Project Control",
    partner_url=None,
    pack_version="0.1.0",
    pack_type="industry",
    description=(
        "Owner-side project management in eleven management areas over two phases, project development "
        "and construction execution, with one gate between them and one approved frame document per area. "
        "Selects the platform modules that fill those areas and ships the framework's phase model, "
        "stakeholder and mandate framework, delivery forms, German permit roadmap additions, a German "
        "site logistics catalogue and German health, safety and environment frame catalogues for the country "
        "and two Laender as catalogue data in German and English."
    ),
    default_locale="de",
    additional_locales={"de": "locales/de.json", "en": "locales/en.json"},
    cwicr_regions=[],
    default_currency="EUR",
    default_tax_template=None,
    default_methodology=None,
    validation_rule_packs=[],
    validation_rule_sets=[
        "project_governance",
        "commitment_release",
        "economics",
        "delivery_model",
        "permits",
        "plant_register",
        "procurement_concept",
        "design_management",
        "stakeholders",
        "quality_concept",
        "staffing",
        "site_logistics",
        "engineering_brief",
        "hse_frame",
        "project_handbook",
    ],
    default_modules=[
        "oe_project_governance",
        "oe_stakeholders",
        "oe_delivery_model",
        "oe_permits",
        "oe_plant_register",
        "oe_staffing",
        "oe_engineering_brief",
        "oe_site_logistics",
        "oe_design_management",
        "oe_procurement_concept",
        "oe_commitment_release",
        "oe_economics",
        "oe_quality_concept",
        "oe_hse_frame",
        "oe_project_handbook",
    ],
    hidden_modules=[],
    default_company_profile="owner_client",
    branding=PartnerBranding(
        primary_color="#0F2C5F",
        accent_color=None,
        favicon_path=None,
        logo_path=None,
        powered_by_text="Powered by OpenConstructionERP",
    ),
    demo_template_ids=["residential-regensburg", "school-ludwigsburg"],
    onboarding_script_path=None,
    metadata={
        "industry": "owner_project_management",
        "country": "XX",
        "framework": {"phases": 2, "gates": 1, "areas": 11, "frame_documents": 11},
        "catalogues": [
            {
                "kind": "phase_model",
                "id": "eleven_areas_framework",
                "version": 1,
                "path": "catalogues/phase_model/eleven_areas_framework.json",
                "default_for_new_projects": True,
            },
            {
                "kind": "stakeholder_framework",
                "id": "eleven_areas_framework",
                "version": 1,
                "path": "catalogues/stakeholder_framework/eleven_areas_framework.json",
                "default_for_new_projects": True,
            },
            {
                "kind": "delivery_forms",
                "id": "eleven_areas_framework",
                "version": 1,
                "path": "catalogues/delivery_forms/eleven_areas_framework.json",
                "default_for_new_projects": True,
            },
            {
                "kind": "handbook_model",
                "id": "eleven_areas_framework",
                "version": 1,
                "path": "catalogues/handbook_model/eleven_areas_framework.json",
                "default_for_new_projects": True,
            },
            {
                "kind": "permit_type",
                "id": "eleven_areas_framework_de",
                "version": 1,
                "path": "catalogues/permit_type/eleven_areas_framework_de.json",
                "default_for_countries": ["DE"],
            },
            {
                "kind": "permit_type",
                "id": "eleven_areas_framework_de_by",
                "version": 1,
                "path": "catalogues/permit_type/eleven_areas_framework_de_by.json",
                "default_for_countries": ["DE-BY"],
            },
            {
                "kind": "permit_type",
                "id": "eleven_areas_framework_de_bw",
                "version": 1,
                "path": "catalogues/permit_type/eleven_areas_framework_de_bw.json",
                "default_for_countries": ["DE-BW"],
            },
            {
                "kind": "site_logistics",
                "id": "eleven_areas_framework_de",
                "version": 1,
                "path": "catalogues/site_logistics/eleven_areas_framework_de.json",
                "default_for_countries": ["DE"],
            },
            {
                "kind": "hse_frame",
                "id": "eleven_areas_framework_de",
                "version": 1,
                "path": "catalogues/hse_frame/eleven_areas_framework_de.json",
                "default_for_countries": ["DE"],
            },
            {
                "kind": "hse_frame",
                "id": "eleven_areas_framework_de_by",
                "version": 1,
                "path": "catalogues/hse_frame/eleven_areas_framework_de_by.json",
                "default_for_countries": ["DE-BY"],
            },
            {
                "kind": "hse_frame",
                "id": "eleven_areas_framework_de_bw",
                "version": 1,
                "path": "catalogues/hse_frame/eleven_areas_framework_de_bw.json",
                "default_for_countries": ["DE-BW"],
            },
        ],
        "catalogues_resolved_by_project_country": [
            "authority_schedule",
            "abort_basis",
            "plant_register",
            "procurement_procedures",
            "drawing_numbering",
            "design_reports",
            "quality_concept",
            "staffing_model",
            "engineering_brief_model",
        ],
        "demo": {"path": "demo/demo_project.json"},
    },
)
