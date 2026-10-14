# Eleven module project framework pack

An owner-side project management framework as a pack: eleven management areas, two phases (project
development and construction execution), one gate between them, and one frame document per area that is
approved at the gate and binding afterwards.

The pack contains data only. It selects the platform modules and gives them the framework's vocabulary.

## What it switches on

`oe_project_governance`, `oe_stakeholders`, `oe_delivery_model`, `oe_permits`, `oe_plant_register`,
`oe_staffing`, `oe_site_logistics`, `oe_design_management`, `oe_procurement_concept`,
`oe_commitment_release`, `oe_economics`, `oe_quality_concept`, `oe_engineering_brief`, `oe_hse_frame`, together with the validation rule set of each.

## What it ships

| File | Catalogue kind | Content |
|---|---|---|
| `catalogues/phase_model/eleven_areas_framework.json` | `phase_model` | 2 phases, 1 gate, 11 areas, 174 working folders, 11 frame document types, 49 readiness criteria |
| `catalogues/stakeholder_framework/eleven_areas_framework.json` | `stakeholder_framework` | stakeholder categories, analysis methods, roles, bodies, decision types, mandate template |
| `catalogues/delivery_forms/eleven_areas_framework.json` | `delivery_forms` | the delivery forms the framework names, with risk categories, criteria and package templates |
| `catalogues/permit_type/eleven_areas_framework_de.json` | `permit_type` | German roadmap entries on top of the shipped `de` catalogue |
| `catalogues/permit_type/eleven_areas_framework_de_by.json` | `permit_type` | the same entries on top of the shipped Bavarian catalogue (`de_by`), the default for projects in DE-BY |
| `catalogues/permit_type/eleven_areas_framework_de_bw.json` | `permit_type` | the same entries on top of the shipped Baden-Wuerttemberg catalogue (`de_bw`), the default for projects in DE-BW |
| `catalogues/site_logistics/eleven_areas_framework_de.json` | `site_logistics` | German site logistics catalogue that extends the shipped `de` catalogue and adds no figure of its own |
| `catalogues/hse_frame/eleven_areas_framework_de.json` | `hse_frame` | German HSE frame catalogue on top of the shipped `de` catalogue: topics, safety coordinator roles, requirement templates and the particularly hazardous works, with the legal basis of each |
| `catalogues/hse_frame/eleven_areas_framework_de_by.json` | `hse_frame` | the same on top of the shipped Bavarian catalogue (`de_by`), the default for projects in DE-BY |
| `catalogues/hse_frame/eleven_areas_framework_de_bw.json` | `hse_frame` | the same on top of the shipped Baden-Wuerttemberg catalogue (`de_bw`), the default for projects in DE-BW |

Every entry carries its label in German and English. Country facts (permit periods, procurement thresholds,
retention rules, noise limits, load classes) are not in this pack: they come from the catalogues the platform
resolves from the project's country.

The pack installs two demo projects of common types, each in the Land whose building code it follows: `residential-regensburg`, a quarter of four multi-family buildings in Bavaria, and `school-ludwigsburg`, a primary school with a sports hall in Baden-Wuerttemberg. A project's Land picks its permit catalogue. `demo/demo_project.json` carries the demo story of the Bavarian project for the governance seed: catalogue pins, area owners, the eleven frame documents and the state of the gate. Rows on the module screens come from the module seeders.

## Install

The pack ships with the platform and is listed under Modules, where it is applied. As a dropped pack, put the
folder that holds `manifest.json` into `<data dir>/packs/`: that manifest is validated and never executed.
`manifest.py` states the same manifest for the source tree; change both together.

## License

AGPL-3.0-or-later. OpenConstructionERP is authored and owned by DataDrivenConstruction.
