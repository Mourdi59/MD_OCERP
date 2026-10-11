# Module 6 `site_logistics` (extended): site areas, access, media, logistics and transport (spec v1, 2026-10-11)

Sources: `mod11/INTEGRATION.md` (platform, file:line, worktree `wt-gates`), `gates/SPEC_v1.md` (module 1),
`mod5/SPEC.md` (plant register, Decision 6: plant and crane positions live here), `elf/SPEC.md:64-69` and
`elf/GAP_5-8.md:35-52` (framework module 6: C 1, P 5, M 7). Research URLs in section 12.
Name: the existing module dir `site_logistics` is EXTENDED (Decision 1). New tables `oe_site_logistics_*`. New API
under `/api/v1/projects/{project_id}/logistics/...`; the legacy `/api/v1/site-logistics/...` routes (gates, zones,
deliveries, `site_logistics/router.py:146-530`) stay unchanged.

## 1. Purpose
One place where a project plans and runs how the site is laid out, reached, supplied and kept on good terms with its
surroundings. It answers: which areas exist per expansion stage and does the area balance close (site, storage, site
setup, operating, expansion); how heavy can traffic be at each access; which utilities (power, water, sewage, telecom,
heat) are available with what capacity versus demand, and is the connection applied for; how goods flow (delivery,
storage, just in time, aligned to takt areas); inbound and outbound transports; heavy transports with route, permit
and time window; customs data for imported or exported goods (HS code, incoterm, origin, documents); and the
neighbourhood (site traffic, noise limits and quiet hours, municipality coordination, complaints).
The approved state is the content of governance frame document `m06_logistics_frame`
(`elf_module_framework.json:1384`, required at `development_to_execution`), folders `dev_area_management` ..
`exec_customs` (`:680-760`). No parallel approval engine.

## 2. Catalogue data (kind `site_logistics`, governance resolver)
Registered with `register_catalogue_kind` (`project_governance/catalogue_kinds.py:107`); shipped
`site_logistics/catalogues/neutral.json` plus pack overrides (`de`, `uk`, `us` as first packs); tenant versions through
`CatalogueStore`. A project pins `(source, id, version)`. Every statutory number carries `source_url`,
`jurisdiction`, `as_of`, `review_status` (`confirmed | unconfirmed`).
- `area_kinds[]`: site_total, building_footprint, storage, laydown, site_setup (offices, welfare), traffic_route,
  operating (permanent use), expansion_reserve, green_retained, third_party (leased, public road occupancy). Each with
  `counts_in_balance` (bool) and `balance_group` (built | logistics | reserve | external).
- `access_kinds[]`: road_gate, pedestrian, rail_siding, waterside_quay, crane_oversail.
- `load_classes[]`: neutral `axle_load_t`, `gross_weight_t`, `max_height_m`, `max_width_m`, `max_length_m`,
  `turning_radius_m`; national defaults (EU Directive 96/53/EC maxima, US federal bridge formula) as data with source.
- `media_kinds[]`: power, water, sewage, stormwater, telecom, district_heat, gas; each with `capacity_unit`
  (kVA, m3/h, l/s, Mbit/s, kW) and `phase` (construction | operation | both).
- `transport_kinds[]`: inbound_delivery, outbound_waste, outbound_spoil, outbound_return, heavy_oversize,
  just_in_time, abnormal_load_escort.
- `permit_kinds[]` (transport only): oversize_permit, road_occupancy, traffic_order, escort_notification,
  night_work, crane_oversail_consent. National name and authority as data (DE: Erlaubnis/Genehmigung nach
  StVO §29/§46 and §70 StVZO; UK: STGO notification / VR1; US: state oversize permit), `typical_lead_days`
  `unconfirmed`.
- `incoterms[]`: the 11 Incoterms 2020 codes (EXW, FCA, CPT, CIP, DAP, DPU, DDP, FAS, FOB, CFR, CIF) with
  `risk_transfer_point`, `import_clearance_by` (buyer|seller), `sea_only` (bool). Version tag `2020`; a later
  revision ships as a new catalogue version, never an edit.
- `customs_document_kinds[]`: commercial_invoice, packing_list, certificate_of_origin, bill_of_lading, air_waybill,
  cmr, import_declaration, export_declaration, ata_carnet, dual_use_licence, preferential_origin_statement.
- `noise_limits[]`: per jurisdiction and zone type (residential, mixed, industrial), `day_dba`, `night_dba`,
  `day_hours`, `quiet_hours`, `source_url`. DE AVV Baulaerm values, UK BS 5228 is a method (no fixed limits ->
  project value), US local ordinance -> project value. All `unconfirmed` until reviewed.
- `neighbour_issue_kinds[]`: noise, dust, vibration, traffic, parking, dirt_on_road, light, access_blocked, damage.
- Thresholds: `area_balance_tolerance_pct` (default 2), `media_reserve_pct` (default 10), `permit_warn_days` (14),
  `customs_hs_digits_min` (6).

## 3. Entities (project-scoped, FK CASCADE on project, tenant via project access)
EXTEND existing: `Gate` (`models.py:32`) gets nullable columns `access_kind`, `max_axle_load_t`, `max_gross_t`,
`max_height_m`, `max_width_m`, `max_length_m`, `turning_radius_m`. `LaydownZone` (`:66`) gets `site_area_id`
(FK SET NULL to `SiteArea`). `DeliveryBooking` (`:95`) gets `transport_id` (FK SET NULL), `direction`
(inbound | outbound, default inbound), `gross_weight_t`, soft `plant_item_id` (mod5), soft `takt_location_id`. No
existing column is renamed or removed.

NEW:
- `ExpansionStage` (`oe_site_logistics_stage`): `code`, `title`, `ordinal`, `from_activity_id` / `to_activity_id`
  (soft schedule Activity; dates READ, Decision 7) or `from_date`/`to_date` fixed, `state` `planned -> active -> closed`.
  At least one stage per project (`stage_0` created on first use).
- `SiteArea` (`oe_site_logistics_area`): `code`, `name`, `area_kind`, `geometry` (GeoJSON Polygon in the project
  local or WGS84 frame; `area_m2` computed when geometry present, else `area_m2_declared`), soft `geo_overlay_id`
  (`geo_hub` overlay of kind site_plan), soft `takt_location_id`, `owner_party`.
- `AreaAllocation` (`oe_site_logistics_area_allocation`): `(site_area_id, stage_id)` -> `area_kind` for that stage,
  `allocated_m2` (Decimal, <= area), `use_note`. Unique pair. The area balance is computed from these rows.
- `MediaConnection` (`oe_site_logistics_media`): `media_kind`, `phase`, `provider_name` (free text or soft vendor id),
  `connection_point` (text + optional point geometry), `available_capacity` + `capacity_unit`,
  `contracted_capacity`, `application_ref`, `applied_on`, `promised_on`, `connected_on`, soft `document_ref` (CDE).
  FSM `identified -> requested -> offered -> contracted -> connected -> disconnected`.
- `MediaDemand` (`oe_site_logistics_media_demand`): `media_connection_id`, `stage_id`, `consumer` (text, or soft
  `site_plant_position_id`, soft `plant_item_id`), `peak_demand` (Decimal, same unit), `simultaneity_factor` (0..1,
  default 1). Balance computed: sum(peak * factor) * (1 + reserve) vs contracted.
- `SitePlantPosition` (`oe_site_logistics_plant_position`, from mod5 Decision 6): `kind` (mod5 catalogue
  `site_plant_kinds`), `name`, `x`,`y` (site plan frame) or point geometry, `reach_m`, `max_load_t`, `stage_id`,
  `from`/`to` (dates or soft activities), soft `equipment_id` (`equipment.Equipment`), `laydown_zone_id` (FK SET NULL),
  `power_demand_kva` (feeds `MediaDemand` automatically, rule 9).
- `LogisticsConcept` (`oe_site_logistics_concept`, one per project): `strategy` per material flow JSON list
  `{flow_code, description, mode: stock | just_in_time | kanban | direct_install, storage_area_id, takt_schedule_id,
  buffer_days}`, `delivery_hours` (overrides gate hours only narrower), `max_deliveries_per_hour`, `rules_text`,
  soft `document_ref`. Content is versioned only through governance (frame document = CDE revisions).
- `Transport` (`oe_site_logistics_transport`): `direction` (inbound|outbound), `transport_kind`, `title`,
  `carrier_name`, `origin`, `destination`, `planned_window_start/end`, soft `po_id` / `plant_item_id` /
  `waste_record_ref`, dimensions and `gross_weight_t`, `is_heavy` DERIVED (exceeds any catalogue or gate limit; never a
  stored flag), `route_geojson` (LineString, optional), `route_notes`, `escort_required`, soft `customs_case_id`.
  FSM `planned -> permit_pending -> scheduled -> in_transit -> arrived -> closed` (+ `cancelled`). Deliveries at a
  gate are `DeliveryBooking` rows linked by `transport_id`; the booking stays the gate slot (Decision 3).
- `TransportPermit` (`oe_site_logistics_transport_permit`): `transport_id` (nullable, one permit may cover several
  transports via `oe_site_logistics_permit_transport` link table), `permit_kind`, `authority`, `reference`,
  `applied_on`, `valid_from`, `valid_to`, `allowed_windows` JSON list (weekday/time ranges), `conditions` text,
  `route_geojson`, soft `document_ref`. FSM `draft -> applied -> granted | refused -> expired`. If module 4 permits
  register exists, it links by soft `authority_permit_id` and this table stays the transport-specific detail
  (Decision 4).
- `CustomsCase` (`oe_site_logistics_customs_case`): `direction` (import|export), `incoterm` (catalogue code) +
  `incoterm_version`, `named_place`, `country_of_origin` / `country_of_destination` (ISO 3166-1 alpha-2),
  `declarant_party`, `broker_name`, `customs_value` (Decimal) + `currency`, `declaration_ref`, `cleared_on`, soft
  `po_id`. FSM `open -> documents_complete -> declared -> cleared | held -> closed`.
- `CustomsLine` (`oe_site_logistics_customs_line`): `customs_case_id`, `description`, `hs_code` (6 to 10 digits,
  string), soft `commodity_code_id` (`supplier_catalogs.CommodityCode`, for cross-reference only), `quantity`, `unit`,
  `net_mass_kg`, `value`, `origin_country`, `preferential_origin` (bool).
- `CustomsDocument` (`oe_site_logistics_customs_document`): `customs_case_id`, `kind`, `required` (bool, from the
  incoterm + direction template), `document_ref` (CDE revision), `state` `missing -> received -> verified`.
- `NeighbourhoodPlan` (one per project, `oe_site_logistics_neighbourhood`): `zone_type`, `noise_limit_source`
  (catalogue entry id or `project`), `day_dba`, `night_dba`, `quiet_hours` JSON, `site_traffic_routes` (GeoJSON),
  `parking_note`, `municipality_contact`, soft `correspondence_thread_id`.
- `NeighbourIssue` (`oe_site_logistics_neighbour_issue`): `kind`, `reported_on`, `reporter` (free text, may be
  anonymous, no personal data required), `location` (point), `description`, linked soft `transport_id` /
  `delivery_id`, `response`, FSM `received -> acknowledged -> action_taken -> closed`, `response_due` (catalogue
  default 5 days).
- `CoordinationEntry` (`oe_site_logistics_coordination`), a dated log row separate from issues: (`date`, `body` (municipality, utility, police, neighbours), `topic`, `outcome`,
  `next_action_due`, soft `correspondence_id`).

Computed on read: area balance per stage, media balance per stage, `is_heavy`, permit coverage of a transport window,
customs completeness, quiet-hour conflicts.

## 4. Rules (each is a test)
1 Area balance: per stage, sum of `allocated_m2` of balance-counted kinds equals `site_total` within tolerance;
else `area_balance_not_closed` (warning in dev, error at the gate).
2 An allocation may not exceed its area (`allocation_exceeds_area`); overlapping polygons of two areas in the same
stage with different kinds are a warning (`area_overlap`), computed with a pure shapely-free polygon test on the
server (Decision 9).
3 Every stage must have >= 1 storage or laydown allocation and >= 1 site_setup allocation while active
(`stage_without_storage`, `stage_without_site_setup`).
4 A `LaydownZone` linked to a `SiteArea` inherits the stage view; unlinked zones are reported by `zone_not_mapped`
(warning) so legacy data keeps working.
5 Heavy load: a `DeliveryBooking` or `Transport` whose weight or dimensions exceed its gate limits is rejected at
approval (`gate_load_exceeded`, error). Gates with no limits set warn once (`gate_limits_unknown`).
6 `is_heavy` is derived; a heavy transport cannot reach `scheduled` without a `granted` permit whose validity covers
the window and whose `allowed_windows` contain it (`heavy_without_permit`, `window_outside_permit`).
7 Permit expiry: `valid_to` within `permit_warn_days` while transports remain -> warning + notification; passed ->
state `expired`, linked transports flagged.
8 Media balance: per stage and media, demand with reserve > contracted capacity -> `media_capacity_short` (error at
gate); demand without a connection -> `media_unsourced`.
9 `SitePlantPosition.power_demand_kva` creates or updates its `MediaDemand` row (service, idempotent on position id);
no second number.
10 Media lead: a connection needed for a stage (stage start) but not `contracted` with `promised_on` after stage start
-> `media_late` (error).
11 JIT: a flow with mode `just_in_time` needs a `takt_schedule_id` and its deliveries need `takt_location_id`; a JIT
delivery whose window is more than `buffer_days` before the takt activity start of that location ->
`jit_too_early` (warning); after -> `jit_late` (error). Takt dates READ from `schedule_advanced`.
12 Delivery hours: concept `delivery_hours` narrower than gate hours applies; deliveries outside -> existing rule
`site_logistics.delivery_within_gate_hours` (`validators.py:221`) is EXTENDED to read the concept.
13 Quiet hours: any approved delivery or transport window inside `quiet_hours` without a granted `night_work` permit
-> `quiet_hours_conflict` (error).
14 Customs: every line `hs_code` digits only, length >= `customs_hs_digits_min` (`hs_code_invalid`); incoterm must
exist in the pinned version (`incoterm_unknown`); `sea_only` incoterm with a non-sea transport mode -> warning.
15 Required customs documents are derived from direction + incoterm (importer-cleared terms require import
declaration on our side, DDP does not); case cannot be `declared` while a required document is `missing`.
16 Who clears: `declarant_party` must match `import_clearance_by` of the incoterm for imports, else warning
`declarant_mismatch_incoterm`.
17 Customs value is Decimal; currency ISO 4217; no float anywhere (money rules).
18 Neighbour issue past `response_due` without `acknowledged` -> `neighbour_issue_overdue` + notification to m06 owner.
19 State `in_transit` onward for inbound transports linked to a PO reads goods receipt (`procurement/models.py:241`) for
`arrived`; never a second receipt record.
20 Tenant isolation and IDOR: every handler `verify_project_access`; ids of another project -> 404, including link
tables and the legacy routes when they receive the new FKs.
21 All labels i18n; exports PDF + XLSX via `core/register_export`: area balance, media balance, transport list with
permits, customs case file index, neighbourhood log, m06 frame summary.

## 5. API (`/api/v1/projects/{project_id}/logistics/...`, envelope `{items,total,offset,limit}`)
`stages`, `areas`, `areas/{id}/allocations` (bulk put per stage), `balance?stage=` (area + media read model),
`media`, `media/{id}/demands`, `plant-positions`, `concept` (get/put), `transports`, `transports/{id}/transition`,
`permits`, `permits/{id}/transition`, `customs`, `customs/{id}/lines`, `customs/{id}/documents`, `neighbourhood`
(get/put), `neighbour-issues`, `coordination`, `readiness`, `catalogue`, `frame-summary`,
`export/{balance|media|transports|customs|neighbourhood|frame}`.
Permissions: `site_logistics.read`, `site_logistics.edit` (existing, `permissions.py`), new `site_logistics.customs`
(customs values are commercial; editor without it sees lines without value).

## 6. Screens (project tab `/projects/:id/logistics`, existing FE `site-logistics` reused for gates/deliveries)
1 Site plan: geo_hub site_plan overlay + area polygons coloured by kind, stage slider, gates with load badges, plant
positions with reach circles (shared with mod5 screen 5).
2 Balance: per stage table areas by group with m2 and %, closing line red/green; media bars demand vs contracted.
3 Logistics concept: flows table (mode, storage area, takt link, buffer), delivery rules.
4 Transports board: inbound / outbound columns, heavy badge, permit chip with validity, window on a day timeline next
to gate slots.
5 Customs: case list, case page with incoterm card (who carries risk, who clears), lines with HS code, document
checklist.
6 Neighbourhood: limits and quiet hours, issue log with due chips, coordination log.
7 Frame summary: printable m06 document.

## 7. Validation rule set `site_logistics` (existing set EXTENDED)
area_balance_closed, allocation_within_area, area_overlap, stage_has_storage, stage_has_site_setup, zone_mapped,
gate_load_respected, gate_limits_known, heavy_transport_permitted, permit_not_expiring, media_capacity_sufficient,
media_sourced, media_on_time, jit_aligned_to_takt, delivery_within_gate_hours (extended), quiet_hours_respected,
hs_code_valid, incoterm_known, customs_documents_complete, declarant_matches_incoterm, neighbour_issue_on_time.
Readiness provider for area `m06_logistics` at `development_to_execution`: zero errors; balance closed for every
planned stage; every media for the first stage contracted; concept saved and exported to CDE; every known heavy
transport has a permit applied; neighbourhood plan with a limit source set.

## 8. Tests first
1 Unit pure: FSMs (transport, permit, media, customs, issue); area balance table (tolerance edges, empty stage,
declared vs geometry area); polygon overlap; media balance with simultaneity and reserve; `is_heavy` per limit; permit
window coverage incl. overnight windows; JIT early/late; quiet-hour conflict across midnight; HS code validator;
incoterm document template for all 11 codes x direction; catalogue loader (every statutory value has source_url, all
national values `unconfirmed` until reviewed).
2 Service + PG: plant position power creates demand idempotently; legacy gate/zone/delivery routes still pass their
tests with new nullable columns; transport arrived read from goods receipt; delivery-within-hours reads concept;
readiness provider output.
3 Security: other tenant read/write 404 on every new route and link table; editor without `site_logistics.customs`
gets no customs value; IDOR list in `ci-postgres.yml` and `tests/unit/test_idor_router_guards.py`.
4 API contract. 5 Migration up/down/up (new tables + nullable columns only). 6 Frontend vitest: balance table, stage
slider, permit chip, incoterm card. 7 E2E: two stages, areas balanced, crane position adds power demand, media short
-> fix, heavy transport blocked until permit granted, import case with HS code and documents, gate readiness green.

## 9. Build order
tests 1 -> catalogue kind + neutral JSON (+ de/uk/us overlays) -> models + migration (incl. mod5 plant position) ->
services/FSMs -> router + permissions -> integrations (governance readiness + frame summary, schedule/takt reads,
procurement GR read, geo_hub overlay link, mod5 plant item link, correspondence link, notifications, events) ->
frontend -> i18n all locales -> E2E -> cloud CI.

## 10. Open questions
None open; all decided below.

## 11. Example (neutral, illustrative)
Site 12 000 m2. Stage 1 (earthworks): footprint 0, laydown 3 000, site setup 800, traffic 2 200, reserve 6 000 = 12 000.
Stage 2 (structure): footprint 5 400, laydown 1 800, setup 800, traffic 1 600, reserve 2 400. Tower crane 2 x 60 kVA,
offices 40 kVA, simultaneity 0.8, reserve 10 % -> 140.8 kVA vs contracted 160 kVA: ok. Transformer 62 t (mod5 item)
exceeds gate gross limit 44 t: heavy, needs oversize permit with night window 22:00-05:00, which conflicts with quiet
hours 20:00-07:00 -> night_work permit required too. Imported switchgear: FCA named place, HS 853720, buyer clears import.

## 12. Sources
- Incoterms 2020, 11 rules, ICC: https://iccwbo.org/business-solutions/incoterms-rules/incoterms-2020/
- Harmonized System, 6-digit international level, WCO: https://www.wcoomd.org/en/topics/nomenclature/overview/what-is-the-harmonized-system.aspx
- EU weights and dimensions, Directive 96/53/EC: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:31996L0053
- DE oversize transport permit, StVO §29 (3) and §46: https://www.gesetze-im-internet.de/stvo_2013/__29.html ,
  https://www.gesetze-im-internet.de/stvo_2013/__46.html ; StVZO §70: https://www.gesetze-im-internet.de/stvzo_2012/__70.html
- DE construction noise, AVV Baulaerm: https://www.verwaltungsvorschriften-im-internet.de/bsvwvbund_19081970_IG19700819.htm
- UK abnormal loads (STGO), notification: https://www.gov.uk/esdal-and-abnormal-loads ; construction noise code BS 5228-1
  (method, no fixed limits): https://knowledge.bsigroup.com/products/code-of-practice-for-noise-and-vibration-control-on-construction-and-open-sites-noise
- US size and weight, oversize permits by state: https://ops.fhwa.dot.gov/freight/sw/index.htm
- ISO 3166 country codes: https://www.iso.org/iso-3166-country-codes.html ; ISO 4217: https://www.iso.org/iso-4217-currency-codes.html
- Not yet verified by a reviewer (all `unconfirmed`): every numeric limit above, permit lead times, the customs document
  template per incoterm (derived from the ICC rule texts, A2/B2 clearance clauses).

## Decisions (agent, 2026-10-11; binding unless the lead overrides)
1. EXTEND `site_logistics`, no new module. Reason: it already owns gates, laydown zones and delivery slots for the
   same project and is module 6 "Logistikkonzept" (gap list C/P); a second module would split the site plan in two.
   New routes are project-scoped under `/projects/{id}/logistics`; legacy routes kept for existing clients.
2. Area balance is computed from `AreaAllocation(area, stage)`, never stored totals. Reason: stored sums drift, and the
   framework asks for the balance per expansion stage, which is exactly the allocation table.
3. `DeliveryBooking` stays the gate slot; `Transport` is the movement (origin, route, permit, customs) and may own
   several bookings. Reason: a heavy transport and a pallet delivery both need a slot, only one needs a route permit.
4. Transport permits are a specific table here. If the module 4 permits register ships, it links by soft
   `authority_permit_id`; the register holds generic status, this table holds windows, route and dimensions.
   `hse_advanced.PermitToWork` is work safety, not transport, and is not reused (LINK only for night work hazards).
5. Customs is data, not a filing engine: HS code, incoterm, origin, value, documents. Filing to a national customs
   system can later be an `authority_submission` profile (data-driven XML, `authority_submission/models.py:1-30`).
   HS code is its own field; `supplier_catalogs.CommodityCode` (UNSPSC/CPV) is a different classification and is only
   cross-referenced, never mapped automatically (no reliable mapping exists).
6. Incoterms are catalogue data with a version tag, not an enum. Reason: ICC revises them (2010, 2020); old cases keep
   their version.
7. Stage dates and takt dates are READ from `schedule` / `schedule_advanced` via soft activity / takt ids, fixed date
   only as fallback. Reason: one date source.
8. Media demand of site plant comes from `SitePlantPosition` (mod5 Decision 6 table lives here); plant item operating
   loads (mod5) can be linked as `phase=operation` demand. One number per consumer.
9. Geometry as GeoJSON in JSON columns with a small pure-Python polygon area/overlap helper; no PostGIS requirement
   (single-database simplicity; PostGIS optional later), no new dependency.
10. Neighbour reports store no personal data by default (free-text reporter, optional); privacy by design.
11. Noise limits: shipped values are jurisdiction data `unconfirmed`; where a country sets no fixed value (UK, US) the
    project enters its consented value with source `project`.
12. Customs values behind `site_logistics.customs` permission. Reason: invoice values are commercially sensitive and
    site staff booking deliveries do not need them.
