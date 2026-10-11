# Module `delivery_model`: project delivery form, risk allocation, decision record, package plan (spec v1, 2026-10-11)

Sources: `mod3/INTEGRATION.md` (platform, file:line, worktree `wt-gates` HEAD 4059f178c), `gates/SPEC_v1.md`
(module 1, which this plugs into), `elf/SPEC.md` (module 2 Vertragsmanagement; modules 4, 7, 8 apply the result).
Research URLs are listed in section 12; each was fetched or returned by search on 2026-10-11 unless marked.

## 1. Purpose
One project-level answer to "who designs, who builds, who supplies, who carries which risk, and why".
The owner compares delivery forms against weighted criteria, records the decision with an approver, allocates
every risk category to a party with a rationale, and derives a package plan (contract packages with design /
build / supply responsibility and owner-furnished items). Modules 4 (equipment procurement route), 7 (design
awards) and 8 (procurement packages) read the package plan; they do not hold their own copy of the form.
The decision record IS the content of the governance frame document `dev_delivery_form` of area
`m02_contract_management` (`elf_module_framework.json:211-214`): approval at the gate makes it binding,
changes after that go through governance change control (governance rule 4). No parallel approval engine.

Country-neutral: forms are defined by responsibility attributes (design responsibility, number of owner-side
construction contracts, price basis at award, early contractor involvement, operation / finance scope), not
by national names. National names (GU, TU, D&B, CMAR, FIDIC Yellow) are aliases on a neutral form.

## 2. Catalogue data (shipped JSON + pack + tenant versions, one resolver)
New catalogue kind `delivery_model` in the governance catalogue store (EXTEND `project_governance`
`catalogue_store.resolve_catalogue` :106, which today only parses phase catalogues; see INTEGRATION 2.1).
Shipped files `delivery_model/catalogues/*.json`: `neutral` (default), `de`, `uk`, `us`, `fidic`, `ppp_wb`.
A tenant clones, edits, publishes a version (existing `CatalogueStore` lifecycle); a project pins
`(source, id, version)`. A pack may name a default catalogue id in `metadata`, country default via
`regional_packs`. Every statutory or standard-form fact carries `source_url` + `review_status`.

Catalogue body:
- `forms[]`: `code`, `name_key`, `aliases[]` ({country, term, source_url}), attributes:
  `design_responsibility` (owner | contractor | split_at_stage | shared), `design_transfer_stage` (spine key,
  for novation / TU after LPH 4 etc.), `owner_construction_contracts` (many | one | one_per_package_managed),
  `contractor_role` (builder | manager_at_risk | manager_agency | integrator | concessionaire),
  `price_basis_at_award` (remeasure | lump_sum | gmp | target_cost | cost_reimbursable | availability_payment),
  `early_involvement` (none | preconstruction_services | two_stage | multi_party),
  `scope_extends` ([finance, operate, maintain]), `compatible_contract_types` (subset of contracts
  `CONTRACT_TYPES`), `compatible_standard_forms` (open strings, e.g. "FIDIC Yellow 2017", "JCT DB 2016",
  "NEC4 ECC Option C", "AIA A133", "VOB/B"; LINK only, never required).
- Neutral form set (v1): `design_bid_build_split` (Einzelvergabe / Fachlosvergabe, trade contracts),
  `design_bid_build_single` (GU, traditional, DBB, FIDIC Red), `design_build` (TU/GU with design, D&B,
  DB, FIDIC Yellow), `design_build_novated` (design transferred at stage), `turnkey_epc` (TÜ, FIDIC Silver),
  `cm_at_risk` (CMAR, two-stage with GMP), `cm_agency` (CM, CMa), `management_contracting` (MC),
  `partnering_two_stage` (GMP/target cost partnering models), `alliance_ipd` (alliancing, IPD, multi-party),
  `integrator` (owner-side integrator / integrated delivery manager), `ppp_dbfom` (PPP / concession),
  `underground_gbr` (FIDIC Emerald overlay: GBR-based ground risk sharing; flag, not a separate form? see Q).
  GÜ is an alias with `self_performs=false`; GU vs GÜ differ only in that attribute.
- `parties[]`: neutral roles `owner`, `designer`, `contractor`, `trade_contractor`, `construction_manager`,
  `supplier`, `operator`, `insurer`, `shared`, `public_authority`; each maps to contracts `PARTY_ROLES`
  (`contracts/schemas.py:1148`) through `contract_party_role` (no parallel vocabulary at contract level).
- `risk_categories[]`: `code`, `name_key`, `register_category` (one of the 7 closed values of
  `risk/schemas.py:119`), `description_key`. v1 list: design_errors, design_coordination, ground_conditions,
  utilities_existing, permits_approval, permit_conditions_change, scope_change_owner, quantity_variance,
  price_escalation, labour_productivity, subcontractor_default, interface_between_packages, schedule_delay,
  weather_force_majeure, change_in_law, latent_defects, commissioning_performance, operation_availability,
  financing_interest, demand_revenue, environmental_contamination, archaeology_uxo, hse_site, insurance.
- `default_allocations[]`: (form, risk_category) -> `party`, `basis` (contract | insurance | shared_pain_gain
  | statute), `rationale_key`, `source_url`. These are defaults, never applied without confirmation.
- `criteria[]`: decision criteria with default weights: cost_certainty_at_award, time_to_start, owner_control
  of design, single_point_responsibility, owner_capability_required, market_capacity, change_flexibility,
  innovation, public_procurement_constraints, lifecycle_value, funding_constraints. Each criterion carries a
  per-form default score 1-5 with rationale key (catalogue data, editable).
- `country_rules[]`: e.g. DE public client lot-splitting preference (status `needs_review`, see Q4).
- `package_templates[]`: per form, the default package shape (e.g. split -> one package per trade group;
  design_build -> design+build package plus owner consultant packages; cm_at_risk -> preconstruction services
  package then GMP package with trade packages under it; ppp -> one project agreement package).

## 3. Entities (project-scoped, FK CASCADE on project, tenant via project access; new tables only)
- `DeliveryModel` (one per project): pinned catalogue (source, id, version), `selected_form_code`,
  `state`: `draft -> under_evaluation -> proposed -> approved -> binding` (+ `reopened` -> `under_evaluation`).
  `binding` is mirrored from the governance frame document becoming binding, never set by this module alone.
  Soft `governance_document_id`. `customised` flags per attribute override (copy-on-write from catalogue).
- `DeliveryOption`: candidate forms in the comparison (2..n), each with attribute overrides and notes.
- `DecisionCriterion`: project criteria with weight (Decimal, sum = 100), copied from catalogue.
- `OptionScore`: (option, criterion) score 1-5 + rationale; weighted total computed on read, never stored.
- `DeliveryDecision` (immutable once approved): chosen option, options snapshot, scores snapshot, rationale,
  owner capability assessment (owner_has_design_team, owner_has_cm_capacity, public_client, funding source),
  proposed_by, approver_user_id via `approval_routes` instance (new `target_kind="delivery_decision"`), approved_at,
  supersedes_id. Approval may also be taken implicitly by the governance gate decision on m02 (see Q2).
- `RiskAllocation`: (model, risk_category) -> `party`, `basis`, `share_percent` (shared only),
  `rationale`, `source` (catalogue_default | edited), `confirmed_by/at`, soft `risk_item_ids[]` (LINK to
  `oe_risk_register` rows; never copies probability, impact, owner).
- `ContractPackage` (the package plan, the single source modules 4/7/8 read): `code`, `title`, `kind`
  (design | construction | design_and_construction | supply | supply_and_install | management_services |
  operation | project_agreement), responsibility flags `designs`, `builds`, `supplies`, `manages`,
  `party_role`, `price_basis`, `standard_form` (string, optional), parent package (trade under CM/GMP), scope
  text, soft refs (WBS / BOQ section), `state`: `planned -> in_procurement -> awarded -> closed` (+ `cancelled`)
  where `in_procurement/awarded` are READ from the linked procurement entity, not set by hand. Soft links:
  `bid_package_id` / `tender_package_id` / `rfq_id` / `subcontract_agreement_id` / `contract_id` (one filled).
- `OwnerFurnishedItem` (OFCI/OFOI, bauseitige Leistung): description, item kind (equipment | material | design
  | service | utility), `install_by` (owner | package), target `ContractPackage` that installs, `procurement_route`
  (rfq | purchase_order | requisition | framework | existing_stock | none_yet), soft link to
  `rfq_id` / `purchase_order_id` / `requisition_id`, need-by date (soft link to schedule activity), lead time and
  enquiry date (module 4), state `identified -> route_set -> ordered -> delivered -> handed_to_installer`.

## 4. Rules (each is a test)
1 Proposing a decision needs at least 2 options scored on every criterion, weights summing to 100, and a
rationale; a single-option "decision" is rejected (`single_option_decision`).
2 Approval needs an entitled decider through `approval_routes` (`entitled_deciders`); proposer != approver when
four-eyes is on (governance setting reused).
3 Every risk category in the pinned catalogue has an allocation with a party; a category without party blocks
`proposed -> approved` (`risk_unallocated`). Not-applicable needs rationale.
4 `shared` allocation needs share_percent summing to 100 across sharing parties and a basis (pain/gain or GBR).
5 An allocation that deviates from the catalogue default for the chosen form needs a rationale.
6 An allocation inconsistent with the form is an error, not a warning, for hard attributes: design_errors on
owner under design_build (contractor designs) or on contractor under design_bid_build; operation_availability
on anyone but operator/concessionaire under ppp. Soft mismatches warn.
7 Package consistency: under `design_bid_build_*` no package has `designs=true` with `builds=true`;
under `design_build`/`turnkey_epc` exactly one design_and_construction package covers the works scope;
under `cm_at_risk` trade packages hang under the GMP package; under `cm_agency`/`management_contracting`
the owner holds trade contracts (cm_agency) or the manager does (MC); `alliance_ipd` has one project agreement.
8 Package `price_basis` must be in the form's `compatible_contract_types`; a linked `contracts.Contract` with a
`contract_type` outside it raises `contract_type_inconsistent_with_form` (catches `design_build` used on a
DBB project, `CONTRACT_TYPES` at `contracts/schemas.py:32`).
9 Changing the selected form when packages exist: allowed only via a new decision; packages already
`in_procurement` or `awarded` are listed as impacted and each needs a disposition (keep / re-scope / cancel)
before approval (`form_change_impacts_packages`). After the governance frame document is binding, the change
starts a governance `FrameChangeRequest`; this module never edits a binding decision.
10 An owner-furnished item must have a procurement route and an installing package before the gate that
releases procurement; `none_yet` past that gate is an error (`ofi_without_route`).
11 An owner-furnished item whose linked PO/RFQ need-by date is after the installing package's need date warns
(`ofi_late_for_installer`).
12 Seeding risks: confirming an allocation may create risk register entries through `risk.service.create_risk`
(`risk/service.py:160`) with category from `register_category`, `metadata_.delivery_model_allocation_id`;
the link is stored on the allocation. Re-confirming never duplicates (idempotent on allocation id).
13 A linked risk item deleted in the register drops the soft link and flags the allocation `link_missing`, it
is not recreated silently.
14 Decision snapshot is frozen: later catalogue version or weight edits do not change an approved decision.
15 Catalogue pin change on a project needs a code mapping for forms and categories (same pattern as
governance rule 7); unmapped allocations become `unconfirmed`.
16 Module 4/7/8 query: "which party designs/builds/supplies X" resolves from ContractPackage only; tests assert
no other table carries the delivery form (grep gate in tests/unit).
17 Every label i18n, export PDF + XLSX via `core/register_export` (decision record, matrix, package plan).

## 5. API (`/api/v1/delivery-model/projects/{project_id}/...`, envelope `{items,total,offset,limit}`)
model (get, set catalogue pin with mapping), options (CRUD), criteria (list, patch weights), scores (bulk put),
decision (propose, get, history, export), allocations (list matrix, put, confirm, seed-risks), packages (CRUD,
link procurement entity, consistency report), ofi (CRUD, set route), catalogue (list available via resolver),
readiness (read-only evidence for governance). Permissions registered on startup: `delivery_model.read`,
`delivery_model.edit` (manager or m02 area owner), `delivery_model.approve` (route-entitled only).
`verify_project_access` on every handler; cross-project ids 404.

## 6. Screens (project tab under `/projects/:id/delivery`, no new top segment)
1 Comparison: options as columns, criteria rows with weights, scores with rationale, weighted totals, owner
capability panel; "Propose" opens decision dialog (rationale required).
2 Risk allocation matrix: categories x parties, cell = allocation with basis and rationale tooltip, defaults
shown greyed until confirmed, link count to risk register, "seed register" action with preview (human confirms).
3 Package plan: tree of packages with D/B/S/M flags, price basis, standard form, link status to bid / tender /
RFQ / subcontract / contract; consistency banner from rules 6-8.
4 Owner-furnished items register with route, lead time, need-by, installer.
5 Decision record (read-only, printable) = what the governance m02 frame document shows.
Strings in all locales in the same commit.

## 7. Validation rule set `delivery_model`
decision_has_alternatives, weights_sum_to_100, every_risk_allocated, shared_risk_sums_to_100,
deviation_has_rationale, allocation_consistent_with_form, packages_consistent_with_form,
contract_type_consistent_with_form, ofi_has_procurement_route, ofi_need_date_feasible,
decision_approved_by_entitled_user. Registered via `validators.py` + `on_startup` (funding pattern).
Readiness evidence for governance: area m02 check reads `delivery_model.readiness()` (approved decision,
zero error-level violations); governance must not import this module (provider registry, see INTEGRATION 2.1).

## 8. Tests first (order)
1 Unit pure: FSMs (table-driven); form-attribute consistency (rules 6-8 as cases per form); weighted scoring
with Decimal; catalogue loader (every shipped catalogue validates; every default allocation names known form,
category, party; every `register_category` in the risk regex; every `contract_party_role` in PARTY_ROLES;
every `compatible_contract_types` in CONTRACT_TYPES; every alias has source_url).
2 Service + PG (tests/pg): propose/approve via approval_routes; form change with awarded packages; risk seeding
idempotent; deleted risk link; OFI route gate; snapshot frozen after catalogue edit; concurrent approval 409.
3 Security (tests/pg + IDOR list in ci-postgres.yml): other tenant cannot read/approve; editor cannot approve.
4 API contract: envelope, 404 vs 403, error codes. 5 Migration up/down/up on PG, tables only.
6 Frontend vitest: matrix states, comparison totals, consistency banner, role gating, i18n keys.
7 E2E: compare 3 forms, approve design_build, confirm matrix, seed 3 risks, derive packages, add OFI with route.

## 9. Build order
tests 1 -> resolver extension (kind) in governance -> catalogue JSON (neutral first, then de/uk/us/fidic/ppp)
-> models + migration -> service + FSM -> router + permissions -> integrations (approval_routes kind, risk
seeding, governance evidence provider, contracts consistency, procurement links) -> frontend -> i18n -> E2E ->
cloud CI -> browser check. Modules 4/7/8 consume ContractPackage / OwnerFurnishedItem afterwards.

## 10. Open questions (resolved in Decisions below)
1 `contracts.CONTRACT_TYPES` mixes a delivery form (`design_build`) into price forms. Keep and validate
(rule 8), or deprecate it in favour of delivery_model + price basis?
2 Approval: own approval_routes instance for the decision, or only the governance gate decision on m02 (one
signature, less ceremony)? Proposal: governance gate only, when the project uses governance; own route otherwise.
3 Risk categories: map to the 7 closed register categories (lossy) or widen `risk/schemas.py:119`
(shared module edit, affects filters and dashboards)? Proposal: map in v1.
4 DE lot-splitting: fetched GWB §97(4) at gesetze-im-internet.de shows only the SME sentence; the lot rule
(Fach- und Teillose) needs a verified source (GWB §97 version or VOB/A §5) before it ships as a country rule.
5 Which package entity is module 8's target: `bid_management.BidPackage`, `tendering.TenderPackage`,
`rfq_bidding.RFQ` or all via soft link? Four package tables already exist.
6 FIDIC Emerald (GBR): separate form or an overlay flag on any form for underground works?
7 Catalogue kind column: `oe_governance_catalogue` has no `kind`. If governance is unreleased, add it now;
if released, kind lives in the body and `code` namespace (create_all skips existing tables).
8 Is v1 content neutral + DE + UK + US + FIDIC + PPP, or neutral + DE only?

## 11. Typical allocation by form (catalogue defaults, abridged)
| risk | DBB split / single | D&B / TU | EPC turnkey | CMAR (GMP) | CM agency / MC | Alliance / IPD | PPP |
|---|---|---|---|---|---|---|---|
| design errors | owner (via designer) | contractor | contractor | owner pre-GMP, then shared | owner | shared pool | concessionaire |
| ground conditions | owner | owner (unforeseeable) or contractor if surveys handed over | contractor | owner | owner | shared | concessionaire, unless excluded |
| interfaces between packages | owner (split) / contractor (single) | contractor | contractor | CM at risk | owner | shared | concessionaire |
| price escalation | contractor (lump) / owner (remeasure) | contractor | contractor | contractor within GMP | owner | shared pain/gain | concessionaire, indexation |
| scope change by owner | owner | owner | owner | owner | owner | owner (outside target) | public authority |
| change in law | owner | owner | owner (FIDIC) | owner | owner | owner | shared per contract |
| operation availability | n/a | n/a | n/a | n/a | n/a | n/a | concessionaire |
Principle: allocate to the party best able to manage the risk at least cost (World Bank PPP guidance).

## 12. Sources
- FIDIC book selection (Red = employer designs, Yellow = contractor designs to Employer's Requirements,
  EPC/Silver = contractor total design and construction risk, fixed price, no Engineer):
  https://fidic.org/bookshop/about-bookshop/which-fidic-contract-should-i-use
- FIDIC Emerald, GBR as single source of ground risk allocation: https://www.ibanet.org/clint-june-2022-feature-1 ,
  https://cms.law/en/srb/legal-updates/introducing-the-fidic-emerald-book
- UK routes (traditional, D&B single/two-stage, MC, CM, two-stage tendering):
  https://www.designingbuildings.co.uk/wiki/Common_procurement ,
  https://lexisnexis.co.uk/legal/construction-law/procurement-in-construction/construction-procurement-routes
- US DBB / DB / CMAR (secondary; DBIA page not retrieved): https://www.archtoolbox.com/construction-project-delivery-methods/ ,
  https://learn.aiacontracts.com/articles/choosing-the-best-construction-project-delivery-method-a-comprehensive-guide/
  (AIA primer PDF https://www.aia.org/sites/default/files/2025-12/AIA_BestPractices_Aprimeronprojectdeliveryterms.pdf
  fetched but not text-extractable; definitions not taken from it).
- IPD multi-party / SPE, shared risk and reward: https://learn.aiacontracts.com/contract-doc-pages/27166-integrated-project-delivery-ipd-family/
- DE GU / GÜ / TU (glossary level, terms vary by source, contract text prevails):
  https://www.ibau.de/akademie/glossar/totalunternehmer-tu/ , https://bau.de/presse/thema-generalunternehmer
- DE §97 GWB (checked: Abs. 4 = SME consideration only on this page): https://www.gesetze-im-internet.de/gwb/__97.html
- PPP risk allocation principle and sector matrices: https://ppp.worldbank.org/public-private-partnership/allocating-risks ,
  https://ppp.worldbank.org/structuring-ppp-projects
- Not yet sourced (needs_review in catalogue): NEC4 option structure, JCT MP/CM suites, CMAA CM-agency
  definition, DBIA definitions, German partnering models (PPA/Allianz), HOAI LPH for novation stage.
- Decision methods: weighted multi-criteria scoring and owner-capability screening are platform method, not
  sourced; risk-based selection = allocation matrix + register exposure per option (EMV from `risk`
  `cost_p50` where linked).

## Decisions on the open questions (binding for implementation)
1. `contracts.CONTRACT_TYPES` keeps `design_build` (existing data). A validation rule warns when a contract's type contradicts the project's chosen delivery form. No deprecation.
2. One approval path for users: the delivery decision is the content of the governance frame document of the contracts area; it is approved and becomes binding through governance (gate + change requests). No second approval route.
3. The allocation catalogue keeps fine-grained risk categories; each maps to exactly one of the risk register's 7 categories (`register_category`). The register is not widened; detail lives in the allocation, the link keeps them consistent.
4. Every legal statement (GWB lot splitting, VOB/A) is verified on gesetze-im-internet.de before it ships; otherwise `review_status: unconfirmed`.
5. `ContractPackage` holds a typed soft link `(kind, id)` to any of the existing package tables; module 8 decides which it creates. v1 creates none itself.
6. FIDIC Emerald is a FLAG `underground_risk_sharing` usable on any form, plus its alias on the design-build and build-only forms.
7. Governance is unreleased: the catalogue table gets a `kind` column now (`phase_model`, `delivery_forms`, later modules add kinds). The lead tells the governance core agent.
8. v1 content: neutral forms with aliases for DE, UK, US and FIDIC; others later as data.
