# Module `plant_register`: main components, long-lead items and procurement route (spec v1, 2026-10-11)

Sources: `mod5/INTEGRATION.md` (platform, file:line, worktree `wt-gates` HEAD 4059f178c), `gates/SPEC_v1.md`
(module 1), `mod2/SPEC.md` (commitment and release matrix), `mod3/SPEC.md` (delivery model, `ContractPackage`,
`OwnerFurnishedItem`), `elf/SPEC.md` module 4 (Ausruestung). Research URLs in section 12.
Name: dir `plant_register`, tables `oe_plant_*`, API under `/api/v1/projects/{project_id}/plant/...`.

## 1. Purpose
One project register of the plant and equipment the owner must specify, secure and hand over: main components
(transformer, switchgear, chiller, generator, lift, process unit, facade system ...), user equipment, operating
equipment. Per item it answers: what must it do (performance, redundancy, maintainability, vendor neutral or
bound), how long does it take to get (lead time WITH the date it was asked and from whom), when must it be
ordered (latest order date, back from the schedule need date), is factory capacity held (slot reservation),
who buys it and who installs it (procurement route, applying module 3), where are the delivery limits to
the user, and what spares and maintenance concept goes with it into operation.
Plus three small frame sections of module 4 that are not per item: site plant and crane positions
(stored in `site_logistics`, see Decision 6), construction-phase IT services, and the frame-document summary.

This module IS the long-lead list of the platform (Decision 1). The register's approved state is the content of
the governance frame document `m04_equipment_frame` (`elf_module_framework.json:1366`, required at
`development_to_execution`), folders `dev_plant_requirements` .. `dev_operating_equipment`, `exec_equipment_plan`,
`exec_spare_parts`, `exec_site_setup_list`, `exec_it_telecom` (`:470-530`). No parallel approval engine.

## 2. Catalogue data (kind `plant_register`, governance resolver)
Registered with `register_catalogue_kind` (`project_governance/catalogue_kinds.py:107`); shipped files
`plant_register/catalogues/neutral.json` (default) and pack overrides; tenant versions through `CatalogueStore`.
A project pins `(source, id, version)`. Every number carries `source_url` + `review_status`
(`confirmed | unconfirmed`); market lead times are always `unconfirmed` defaults, only a project quote is evidence.
- `component_classes[]`: `code`, `name_key`, `item_class` (main_component | user_equipment | operating_equipment),
  `discipline` (electrical | mechanical | conveying | process | structure | envelope | it), `typical_lead_weeks`
  {min, max, as_of, source_url, review_status}, `quote_max_age_days` (default 90), `needs_slot_reservation_above_weeks`,
  `critical_by_default` (bool), `default_spare_categories[]`, `default_maintenance_strategy`, `ifc_class` (string
  for BIM link only, no IFC library). v1 classes: power_transformer, distribution_transformer, mv_switchgear,
  lv_switchboard, generator, ups, battery_storage, chiller, cooling_tower, boiler, heat_pump, ahu, lift, escalator,
  sprinkler_pump, bms_controls, facade_unit, structural_steel_package, process_unit, crane_permanent, kitchen_equipment,
  medical_equipment, it_core_network.
- `redundancy_schemes[]`: N, N+1, N+2, 2N, 2N+1 (code, name_key, description_key, source_url).
- `procurement_routes[]`: neutral codes `contractor_furnished_installed` (CFCI), `owner_furnished_contractor_installed`
  (OFCI), `owner_furnished_owner_installed` (OFOI), `owner_procured_novated` (owner orders, assigns the order to
  the contractor), with aliases per country (DE "bauseits beigestellt", Beistellung). Source: IFC
  `Pset_ConstructionAdministration` (CFCI/OFCI/OFOI acronyms).
- `lead_time_sources[]`: supplier_quote, market_sounding, supplier_catalogue, historic_order, expert_estimate,
  framework_agreement; each with `evidence_rank` (1 best) used by rule 6.
- `spare_categories[]`: commissioning_spares, operating_consumables, strategic_spares (insurance / capital),
  special_tools.
- `maintenance_strategies[]`: preventive_interval, condition_based, vendor_service_contract, run_to_failure.
- `delivery_limit_steps[]`: supply, deliver_to_site, offload, set_in_place, connect, test, commission, accept,
  train, document (the columns of the delivery-limit matrix).
- `site_plant_kinds[]` (consumed by `site_logistics`): tower_crane, mobile_crane_pad, hoist, site_office,
  welfare, storage, temporary_power, temporary_water, concrete_plant, wheel_wash.
- `it_service_kinds[]`: cde_access, site_network, telecom, access_control, cctv, time_recording, drone_survey,
  each with default `responsible_party`.
- Thresholds: `long_lead_threshold_weeks` (default 12), `order_buffer_days` defaults per step (rule 5).

## 3. Entities (project-scoped, FK CASCADE on project, tenant via project access; new tables only)
- `PlantItem` (`oe_plant_item`): `code` (unique per project), `title`, `component_class_code`, `item_class`,
  `quantity` + `unit`, `tag` (asset tag), soft `wbs_id`, `boq_position_id`, `bim_element_ids[]`, `cx_system_id`
  (commissioning), `space_ref`; requirements: `performance` JSON (key, value, unit), `redundancy_scheme`,
  `maintainability` JSON (access, MTTR target, replacement path), `vendor_policy` (neutral | bound) + `vendor_bound_reason`
  (required when bound: standardisation, existing estate, warranty, sole source) + soft `vendor_id`
  (`supplier_catalogs.Vendor`); `critical` (bool, override of catalogue default with reason); need date:
  `need_activity_id` (soft schedule Activity) or `need_date_fixed`; `procurement_route`, `contract_package_id`
  (mod3, the package that supplies or installs), `owner_furnished_item_id` (mod3, filled iff route is owner-furnished);
  `maintenance_strategy`; `state` (below). Long-lead is DERIVED: `effective_lead_weeks >= threshold`, plus manual
  `long_lead_override` with reason. Never a stored boolean that can drift.
  FSM: `identified -> specified -> enquired -> route_set -> ordered -> manufactured -> delivered -> installed ->
  commissioned -> handed_over` (+ `cancelled`). `ordered` onward is READ from the linked PO / package contract /
  OFI state, never set by hand (rule 11).
- `LeadTimeQuote` (`oe_plant_lead_time_quote`, append-only): `plant_item_id`, `source` (catalogue code),
  `vendor_id` (soft) or `source_name`, `enquiry_date` (REQUIRED), `response_date`, `lead_weeks_min`, `lead_weeks_max`,
  `lead_basis` (from_order | from_approved_drawings | from_down_payment), `valid_until`, `document_ref` (CDE revision,
  soft), `catalogue_entry_id` (soft, when source is supplier_catalogue: `CatalogEntry.lead_time_days`), `is_basis`
  (exactly one per item), `superseded_by`.
- `SlotReservation` (`oe_plant_slot_reservation`): `plant_item_id`, `vendor_id`, `slot_from`, `slot_to`,
  `reservation_fee` (Decimal) + `currency`, `fee_refundable` (none | partial | full), `fee_credited_to_order` (bool),
  `convert_by_date` (deadline to sign the binding order), `terms` text, soft `commitment_item_id` (mod2) and
  `document_ref`. FSM `requested -> held -> converted_to_order | released | expired`. Expiry computed from
  `convert_by_date`.
- `DecisionPaper` (`oe_plant_decision_paper`): for critical items. `plant_item_id`, `question`, `options` JSON
  (vendor or technology, lead weeks from a quote id, cost from a quote, risk ref), `criteria` + scores (same Decimal
  weighted scoring as mod3, computed on read), `recommendation`, `rationale`, `approval_instance_id`
  (approval_routes target kind `plant_decision_paper`), FSM `draft -> submitted -> approved | rejected`, snapshot frozen
  on approval, `supersedes_id`.
- `DeliveryLimit` (`oe_plant_delivery_limit`): `(plant_item_id, step)` -> `party` (mod3 neutral party code or
  `contract_package_id`), `note`. One row per step from the catalogue; unique pair. User equipment uses the same rows.
- `SparePartRequirement` (`oe_plant_spare_part`): `plant_item_id`, `category`, `description`, `quantity`, `unit`,
  `supply_by` (party / package), `handover_target` (closeout slot id soft / service asset id soft), `state`
  `required -> specified -> delivered -> handed_over`.
- `ItService` (`oe_plant_it_service`): `kind`, `description`, `responsible_party`, `needed_from` / `needed_until`
  (soft activity or date), `access_roles[]`, `cde_container_id` (soft, when kind is cde_access), state `planned ->
  provisioned -> retired`.
- Site plant and crane positions: NOT here. EXTEND `site_logistics` with `SitePlantPosition`
  (`oe_site_logistics_plant_position`: kind from catalogue, name, x/y on the site plan, `reach_m`, `max_load_t`,
  `from`/`to`, soft `equipment_id` to the contractor fleet, soft `laydown_zone_id`). This module reads it for the frame
  document (Decision 6).

Computed on read (never stored): `effective_lead_weeks` (basis quote max, else catalogue max flagged `catalogue_default`),
`need_date` (activity late_start, else start, else fixed; `date_basis` returned), `latest_order_date` (rule 5),
`float_days` = latest order date - today, `quote_age_days`.

## 4. Rules (each is a test)
1 One long-lead list: `PlantItem` is the only table that holds a project's long-lead classification for
owner-specified plant. Submittal `long_lead` / `lead_time_weeks` (`submittals/models.py:104-106`) stay for
contractor submittals; a submittal linked to a plant item shows the item's effective lead time and its own fields
are read-only in the UI (`lead_time_owned_by_plant_item`). Grep test: no new module adds a `long_lead` column.
2 A lead time without `enquiry_date` is rejected (`lead_time_without_enquiry_date`); `enquiry_date` in the future
rejected; `response_date >= enquiry_date`.
3 Quote older than the class `quote_max_age_days` at evaluation -> warning `lead_time_stale`; at the gate that
releases procurement -> error for critical items.
4 Exactly one `is_basis` quote per item once state >= `enquired`; setting a new basis supersedes the old, history kept.
5 `latest_order_date = need_date - effective_lead_weeks*7 - transport_days - install_lead_days - approval_buffer_days`
(buffers from catalogue, overridable per item). If `lead_basis = from_approved_drawings`, also subtract the submittal
review period (`Submittal.review_period_days` when linked, else catalogue default). Table-driven unit tests, Decimal-free
integer days, calendar days in v1 (Decision 8).
6 Evidence rank: an item with only `catalogue_default` or `expert_estimate` lead time cannot leave `specified` to
`route_set` if critical (`critical_without_market_evidence`).
7 `latest_order_date < today` and not ordered -> `order_overdue` (error), within `warn_days` -> warning; notification
to item owner and m04 area owner.
8 Vendor-bound needs `vendor_bound_reason`; vendor-neutral with `vendor_id` set at specification is a warning
(`neutral_spec_names_vendor`).
9 Critical items need an approved `DecisionPaper` before `route_set` (`critical_without_decision`); the paper needs
>= 2 options unless `sole_source` is the stated reason.
10 Procurement route consistency with module 3: route `owner_furnished_*` requires `owner_furnished_item_id` and the
OFI's installer package equals `contract_package_id` (OFCI) or none (OFOI); route `contractor_furnished_installed` requires a
`contract_package_id` whose `supplies=true`; `owner_procured_novated` requires both. Under a delivery form where the
owner holds no construction contracts other than one package, CFCI must point to that package. Error
`route_inconsistent_with_package_plan`.
11 Creating the OFI: setting route owner-furnished calls mod3 service to create/attach the `OwnerFurnishedItem`
(idempotent on plant item id). Lead time and enquiry date are NOT copied to the OFI; mod3 reads them from the plant item
(mod3 rule 11 uses our `need_date`/`latest_order_date`). The OFI `state` drives our `ordered`/`delivered` states.
12 Commitment: a long-lead or reserved item links to a mod2 `CommitmentItem`; mod2 reads `lead_time_days` and need date
from the plant item through a soft `plant_item_id` (extension of mod2's `requisition_id` read path), never its own copy
(`commitment_lead_time_duplicated` grep test).
13 Slot reservation: `held` needs fee, refund terms and `convert_by_date`; `convert_by_date` before `latest_order_date`
is fine, after it warns (`slot_after_order_date`); passing `convert_by_date` while `held` -> `expired` + notification;
a fee > 0 needs a commitment link before `held` (money binds only through mod2 release).
14 Delivery limits: every catalogue step has a party for main components and user equipment before
`route_set` (`delivery_limit_gap`); two parties on one step rejected (unique).
15 Spares: items with `critical=true` need >= 1 `strategic_spares` row or an explicit `no_strategic_spare_reason`.
16 Handover: `handed_over` requires spares `handed_over` or waived, and creates (on human confirm) a
`service.ServiceAsset` / BIM asset info update via their services; never writes their tables directly.
17 Redundancy: scheme N+1 / 2N etc. requires `quantity` consistent with scheme (N+1 -> quantity >= 2) warning only.
18 IT services: `cde_access` with `needed_from` before the gate to execution must have a CDE container link.
19 Tenant isolation and IDOR: every handler `verify_project_access`; ids of another project -> 404.
20 Every label i18n; exports PDF + XLSX via `core/register_export`: long-lead register, delivery-limit matrix,
decision paper, spares list, m04 frame summary.

## 5. API (`/api/v1/projects/{project_id}/plant/...`, envelope `{items,total,offset,limit}`)
`items` (CRUD, filter long_lead / critical / overdue / route / class), `items/{id}/quotes` (append, set basis),
`items/{id}/slot` (CRUD + transitions), `items/{id}/decision-paper` (CRUD, submit), `items/{id}/delivery-limits`
(bulk put), `items/{id}/spares` (CRUD), `items/{id}/route` (set route, creates OFI via mod3), `it-services` (CRUD),
`long-lead` (read view: items with computed dates sorted by float), `frame-summary` (read model for governance),
`readiness`, `catalogue`, `export/{register|limits|spares|paper|frame}`.
Permissions: `plant.read`, `plant.edit` (manager or m04 area owner), approval only via approval_routes.

## 6. Screens (project tab `/projects/:id/plant`)
1 Register: grid of items with class, critical, route, package, need date, lead weeks + quote age chip ("quoted 42 wk on
2026-08-03 by supplier"), latest order date, float bar, state. Filters as API.
2 Item drawer: requirements (performance, redundancy, maintainability, vendor policy), quotes history with enquiry dates,
slot reservation card, decision paper, delivery-limit row, spares, links (package, OFI, commitment, submittal, Cx system).
3 Long-lead timeline: items as bars from latest order date to need date over the schedule, overdue red.
4 Delivery-limit matrix: items x steps, party per cell.
5 Site and IT: crane / plant positions on the site plan (site_logistics component reused) + IT services list.
6 Frame summary: what the governance m04 document shows, printable.

## 7. Validation rule set `plant_register`
lead_time_has_enquiry_date, lead_time_fresh, single_basis_quote, critical_has_market_evidence, order_not_overdue,
vendor_bound_has_reason, critical_has_decision_paper, route_consistent_with_package_plan, slot_terms_complete,
slot_not_expired, delivery_limits_complete, critical_has_strategic_spares, redundancy_quantity, it_cde_linked.
Registered via `validators.py` + `on_startup`. Readiness provider for area `m04_equipment` at
`development_to_execution`: zero error-level violations, every critical item `route_set` with approved paper, every
long-lead item with fresh basis quote and either ordered or float >= 0, frame summary exported to CDE.

## 8. Tests first
1 Unit pure: FSMs; latest-order-date table (each lead basis, missing activity, fixed date); derived long-lead with
threshold and override; quote basis rules; route consistency per mod3 form; catalogue loader (every class has
source_url, every route has alias source, every lead-time default `unconfirmed`).
2 Service + PG: quote append and supersede; OFI creation idempotent; mod2 reads lead time via plant item; slot expiry job;
decision paper approval via approval_routes; state read from PO/OFI; handover creates ServiceAsset only after confirm.
3 Security (tests/pg + IDOR list in ci-postgres.yml): other tenant read/write 404; editor cannot approve paper.
4 API contract. 5 Migration up/down/up (tables only, incl. site_logistics extension). 6 Frontend vitest: float bar, quote
age chip, matrix. 7 E2E: create transformer, quote with enquiry date, slot reserved, paper approved, route OFCI to package,
latest order date shown, gate readiness green.

## 9. Build order
tests 1 -> catalogue kind + neutral JSON -> models + migration -> service/FSM -> router + permissions -> integrations
(mod3 OFI service, mod2 read path, approval_routes kind, governance readiness provider, submittal read-only link,
site_logistics extension, service/closeout handover) -> frontend -> i18n all locales -> E2E -> cloud CI.

## 10. Open questions
None open; all decided below.

## 11. Example (neutral, illustrative)
MV switchgear, critical, N+1, vendor neutral. Quote A 2026-08-03 52-60 wk from order; quote B 2026-08-10 44 wk from
approved drawings (+ 28 d review). Need date = energisation activity late start 2027-11-15. Basis B: latest order
2027-11-15 - 308 - 14 transport - 21 install - 28 review - 14 buffer = 2026-11-28. Slot held to 2026-11-20, fee credited.

## 12. Sources
- Lead times 2025: large power transformers ~128 weeks (Wood Mackenzie Q2 2025, via
  https://www.gigaenergy.com/blog/lead-time-delays-for-data-centers and https://www.ips.co/news/the-hidden-risk-in-data-center-growth-power-equipment-lead-times ),
  MV switchgear 44-84 weeks (https://www.globaldatacenterhub.com/p/procurement-strategy-equipment-epc ). Secondary, conflicting:
  shipped as `unconfirmed` defaults with `as_of`, which is why rule 2 demands a dated project quote.
- Ordering critical components 12-24 months before construction: https://thenextweb.com/news/us-power-companies-scramble-data-centre-equipment
- Slot / capacity reservation, fee usually non-refundable and credited to the order if signed by a deadline:
  https://www.sec.gov/Archives/edgar/data/0001828536/000182853626000101/nrgv-20260630.htm ,
  https://view.asiae.co.kr/en/article/2026041409530886171
- CFCI / OFCI / OFOI: https://standards.buildingsmart.org/IFC/DEV/IFC4_4/HTML/lexical/Pset_ConstructionAdministration.html ;
  OFCI contractor duties: https://www.fpm.iastate.edu/project_management/Facilities%20Design%20Manual/Current%20Version/Part%202%20Support%20Documents/Div%2001%20Owner%20Furnished%20Equipment.pdf
- Last responsible moment (order date backwards from need): see mod2 sources (https://www.iglc.net/papers/Details/110).
- Not yet sourced (`unconfirmed`): redundancy scheme definitions (N+1, 2N), spare categories, DE term "Beistellung",
  per-class lead time for non-electrical classes.

## Decisions (agent, 2026-10-11; binding unless the lead overrides)
1. Owner of the long-lead list: NEW `PlantItem` in this module. Reason: submittals are approval documents of the
   contractor during execution and exist too late; requisitions/POs exist only after ordering; mod2 and mod3 need the
   date before any of them. Submittal fields stay (existing data, contractor items) and become read-only when linked.
2. Long-lead is derived from the basis quote and a catalogue threshold, not a checkbox. Reason: a stored flag drifts
   from the lead time, which is what the submittal flag does today (`long_lead_without_lead_time` exists as a check).
3. Lead time history is append-only `LeadTimeQuote` with mandatory enquiry date and source. Reason: the framework demands
   "lead time WITH date of enquiry"; a single number with no date is the failure mode.
4. mod3 `OwnerFurnishedItem` keeps the route record and installer; lead time, enquiry date and need date move here and
   mod3 reads them. mod2 `CommitmentItem` reads lead time via `plant_item_id`. One number, one place.
5. Decision paper approval via `approval_routes` (new kind `plant_decision_paper`), not the governance gate. Reason:
   many papers per project, also during execution; the frame document as a whole still binds through governance.
6. Site plant and crane positions extend `site_logistics` (already owns gates, laydown zones, deliveries); module 6
   (logistics) and module 4 both read them. Equipment (`equipment` module) stays the contractor fleet, LINK only.
7. Construction-phase IT is a small `ItService` list here, linking CDE containers; no IT asset management.
8. Calendar days in v1 for order dates; working calendars of `schedule` used only through the activity date itself.
9. Spares and maintenance concept live on the item; operation hands over to `service` / BIM asset info by service
   calls on human confirm, no copy of maintenance schedules (`equipment.MaintenanceSchedule` is fleet, not plant).
10. No new top-level route; tab under project. Catalogue v1 = neutral only, country aliases as data.
