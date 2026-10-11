# Module `procurement_concept`: award concept, procedures, prequalification, award schedule, frameworks (spec v1, 2026-10-11)

Framework module 8 (Einkauf, `elf/SPEC.md` section 8). Sources: `mod6/INTEGRATION.md` (platform, file:line,
worktree `wt-gates`), `gates/SPEC_v1.md` (module 1), `mod3/SPEC.md` (module 3, delivery model and the package
plan this module applies). Research URLs in section 12.

## 1. Purpose
One project-level answer to "what do we buy, in which packages, by which procedure, from whom, and when".
The procurement manager takes module 3's package plan (`ContractPackage`), refines it into award packages
(by trade, section or system; advance packages; design, works, supply), sets a procedure per package with the
public procurement threshold check, runs prequalification and market sounding to a short list, and plans
award dates backwards from the frame schedule and lead times. Framework agreements are registered once and
called off by packages. The result IS the content of governance frame document `m08_procurement_frame`
(`elf_module_framework.json:1402`, required at gate `development_to_execution`), folders `dev_award_concept`,
`dev_design_awards`, `dev_construction_awards`, `dev_material_awards`, `dev_procedure`, `dev_prequalification`,
`dev_award_schedule` (`:882-928`). After the gate the concept is binding; execution (invitations, bids,
evaluation, award) happens in the existing bidding stack, which this module links to and reads back.

The module is a planner and a router, not a fourth bidding engine. It writes no bids, no invitations, no POs.

## 2. Catalogue data (kind `procurement_procedures`, governance catalogue store)
Registered with `register_catalogue_kind` (`project_governance/catalogue_kinds.py:107`), shipped JSON in
`procurement_concept/catalogues/`: `neutral` (default), `eu`, `uk`, `us_federal`, `de_national`. Tenant clones,
edits, publishes a version; project pins `(source, id, version)`. Every legal fact: `source_url`,
`review_status` (`confirmed` | `unconfirmed`), `valid_from`, `valid_to`.

- `procedures[]`: `code`, `name_key`, neutral attributes `competition` (open | restricted | negotiated |
  dialogue | innovation_partnership | direct | framework_call_off | mini_competition), `stages` (1 | 2),
  `has_prequalification` (bool), `negotiation_allowed`, `tender_basis_allowed` ([detailed, functional]),
  `min_bidders` (int, null), `min_period_days` (submission, null), `aliases[]` ({jurisdiction, term,
  source_url}). Neutral v1: open, restricted, competitive_negotiated, competitive_dialogue,
  innovation_partnership, two_stage_negotiated (private two-stage with PCSA), direct_award, framework_call_off,
  mini_competition, request_for_quotation (private, materials), sealed_bid (US), negotiated_best_value (US).
  National names (Offenes Verfahren, Öffentliche Ausschreibung, competitive flexible procedure, FAR Part 14
  sealed bidding, Part 15 negotiation) are aliases.
- `jurisdictions[]`: `code` (eu | uk | us_federal | de_national | none), `client_types` (central | sub_central |
  utility | private), `thresholds[]` {`contract_kind` (works | supplies | services | design_services |
  concession | light_touch), `client_type`, `amount` (Decimal string), `currency`, `vat_basis` (net | gross),
  `effect` (above_requires_publication | below_allows_direct | below_allows_simplified), `allowed_procedures`
  above / below, `source_url`, `review_status`, `valid_from`, `valid_to`}, `lot_rules[]` (aggregation of lots,
  small lots exemption, splitting preference; each sourced), `min_periods[]`.
- `package_kinds[]`: design (architect, engineer, consultant, surveyor), works, supply, supply_and_install,
  services; each maps to `ContractPackage.kind` (mod3) and to threshold `contract_kind`.
- `prequal_criteria[]`: library with `code`, `group` (financial | technical | experience | hse | quality |
  legal | sustainability | capacity), `kind` (pass_fail | scored), default weight, evidence type
  (document | reference | certificate | rating), optional `certificate_type` (subcontractors `Certificate`).
- `lead_time_defaults[]`: per procedure: prep, publication, bid period, evaluation, standstill, award days
  (sourced where statutory, else platform default `review_status: unconfirmed`).

Shipped threshold content v1 (all `confirmed` only after primary-text check, see section 12):
EU 2026-2027: works 5,404,000 EUR, central supplies/services 140,000, sub-central 216,000, utilities
supplies/services 432,000 (net). UK from 2026-01-01: works 5,193,000 GBP, central 135,018, sub-central 207,720,
light touch 663,540, utilities other 415,440, utilities works 5,193,000 (incl. VAT, not Wales). US federal from
2025-10-01: micro-purchase 15,000 USD, simplified acquisition 350,000 USD. DE national (VOB/A, UVgO, BHO direct
award) ships `unconfirmed` until verified on gesetze-im-internet.de.

## 3. Entities (project-scoped, FK CASCADE on project, tenant via project access; new tables only)
- `ProcurementConcept` (one per project): catalogue pin, `jurisdiction`, `client_type`, `public_client` (bool,
  default from mod3 owner capability), `state`: `draft -> in_review -> approved -> binding` (+ `reopened`).
  `binding` mirrored from governance, never set here. Soft `governance_document_id`.
- `AwardPackage` (1:1 extension of mod3 `ContractPackage`, PK = FK `contract_package_id`; no own code/title/
  scope/kind): `split_basis` (trade | section | system | whole), `is_advance` (bool + reason), `estimated_value`
  (Decimal, currency; soft link to cost plan / BOQ section), `aggregated_value` (computed: sum of lots of the
  same works/supply aggregate, never stored), `procedure_code`, `tender_basis` (detailed | functional),
  `stages`, `framework_agreement_id` (null), `evaluation_method` (lowest_price | best_value with weights),
  `need_date` (soft link schedule activity), `lead_time_days`, `state`:
  `planned -> procedure_set -> shortlisted -> in_tender -> awarded` (+ `cancelled`, `on_hold`).
  `in_tender` and `awarded` are READ from the execution link, not set by hand. `execution_link` = typed soft
  link `(kind, id)` stored on mod3 ContractPackage (mod3 Decision 5), never duplicated here.
- `PrequalProfile` (per package or per concept as default): criteria picked from the catalogue with weights
  (Decimal, scored sum = 100), pass mark, validity months.
- `BidderCandidate` (package x company): `subcontractor_id` or `vendor_id` (soft), free name only if neither
  exists yet (must be created before shortlisting), `source` (market_sounding | own_list | framework |
  public_notice), `list` (long | short | excluded), per-criterion `scores` (child rows with evidence refs to
  subcontractors `Certificate` / `PrequalificationApplication` / `SubcontractorRating` / references),
  `total_score` computed, `decision_rationale`, `conflict_of_interest_declared`.
- `ProjectReference` (on candidate): project name, client, value, year, role, contact, verified_by/at.
- `MarketSounding` (per package or group): date, method (survey | meeting | rfi | notice), participants
  (candidates), findings, `capacity_signal` (ample | adequate | tight | insufficient), `price_signal`, lead time
  signal; feeds rule 9.
- `FrameworkAgreement` (tenant-scoped, NOT project-scoped; projects link): supplier (vendor/subcontractor),
  scope, lots, `max_value`, `call_off_value` (computed from linked packages and POs), `start/end`, `call_off_mode`
  (direct | mini_competition), source procedure ref, `state`: `draft -> active -> expired | exhausted | terminated`.
- `AwardScheduleItem` is NOT an entity: award milestones are schedule activities created in `schedule` with
  `metadata_.award_package_id`; this module computes backward dates and proposes them (human confirms).

## 4. Rules (each is a test)
1 Every mod3 `ContractPackage` of kind other than `project_agreement` has an `AwardPackage` before `in_review`
(`package_without_procedure_plan`); every AwardPackage maps to exactly one ContractPackage (FK).
2 Procedure must be allowed for the jurisdiction, client type, contract kind and value: public client above
threshold cannot use `direct_award` or private procedures (`procedure_not_allowed_above_threshold`).
3 Threshold test uses the aggregated value of all lots of the same works (or same supply kind) on the
project, not the single lot; small-lots exemption only where the catalogue rule allows it, with its own cap
(`lot_splitting_avoids_threshold`).
4 Threshold applied is the one valid on the planned procedure start date (`valid_from/to`); VAT basis
converted per `vat_basis`; currency other than the threshold currency needs the catalogue's conversion rate
entry, else `threshold_currency_unresolved` (warning, blocks approval for public clients).
5 An `unconfirmed` threshold or rule is shown with a banner and never produces a hard error, only a warning.
6 Procedure consistency with mod3 form: design_build forms need a functional or mixed tender basis for the D&B
package; cm_at_risk / partnering need a two-stage procedure for the main package; split forms need one package
per trade group (warn otherwise).
7 Design packages (architect, engineer, consultant) use procedures and thresholds of `services` /
`design_services`, never works; fee estimate is required.
8 Shortlist: at least `min_bidders` of the procedure (default 3 for restricted / negotiated) on the short
list before `shortlisted`; every excluded candidate has a rationale; candidates on the short list pass all
pass/fail criteria and reach the pass mark.
9 Market sounding with `capacity_signal` tight / insufficient requires a mitigation note or re-split
before approval (`capacity_unmitigated`).
10 Prequal evidence expired (certificate or insurance expiry before planned award date) warns
(`prequal_evidence_expires_before_award`).
11 Award schedule backward pass: award date = need date minus lead time (mod4 for equipment); procurement start
= award minus sum of procedure durations. A start date in the past or before the gate that releases
procurement is an error unless the package `is_advance` with an approved reason (`award_schedule_infeasible`).
12 Advance packages must be released by a governance gate decision or condition; an advance package without
reason is rejected.
13 A package calling off a framework needs an `active` framework whose scope covers the package kind, end date
after planned award, and remaining value >= estimated value (`framework_exhausted`, `framework_expired`).
14 Changes after binding go through governance `FrameChangeRequest`; this module never edits a binding concept.
15 Execution link: creating execution from an AwardPackage creates ONE `bid_management.BidPackage` (works,
design, services) or ONE `rfq_bidding.RFQ` (supply / materials), copies scope lines from BOQ, sets
`ContractPackage` link; never both, never a `tendering.TenderPackage` (link only, existing data).
16 State read-back: BidPackage published -> `in_tender`, BidAward -> `awarded`, RFQAward -> `awarded`; via events,
idempotent.
17 Every label i18n; export PDF + XLSX via `core/register_export` (concept, package list, shortlist, schedule).

## 5. API (`/api/v1/procurement-concept/projects/{project_id}/...`, envelope `{items,total,offset,limit}`)
concept (get, pin catalogue, set jurisdiction), packages (list joined with ContractPackage, patch, threshold
check, consistency report), prequal (profiles CRUD, candidates CRUD, score, shortlist), market-soundings (CRUD),
schedule (compute, propose activities, confirm), execution (create bid package / RFQ), readiness (governance
evidence), export. Tenant-level: `/api/v1/procurement-concept/frameworks` (CRUD, call-off ledger).
Permissions on startup: `procurement_concept.read`, `.edit` (manager or m08 owner), `.frameworks.manage`.
`verify_project_access` on every handler; cross-project / cross-tenant ids 404.

## 6. Screens (project tab `/projects/:id/procurement-concept`)
1 Package board: tree from mod3 plan grouped by design / works / supply, columns split basis, advance, value,
threshold badge (above / below / unconfirmed), procedure, tender basis, framework, state, execution link.
2 Package detail: procedure picker filtered by rule 2 with the reason shown, threshold explanation with source.
3 Prequalification: criteria weights, candidate matrix (long / short / excluded), evidence chips from
subcontractors, references.
4 Market sounding log with capacity heat per trade.
5 Award schedule: Gantt slice of schedule activities with backward-pass proposals and conflicts.
6 Frameworks register (company level) with call-off ledger.
7 Concept record (read-only, printable) = governance m08 frame document.

## 7. Validation rule set `procurement_concept`
package_has_procedure_plan, procedure_allowed_for_value, lots_aggregated_for_threshold,
threshold_source_confirmed (warn), procedure_consistent_with_delivery_form, design_package_uses_services_rules,
shortlist_min_bidders, excluded_candidate_has_rationale, capacity_risk_mitigated, prequal_evidence_valid,
award_schedule_feasible, advance_package_released, framework_call_off_valid. Registered via `validators.py` +
`on_startup` (`rfq_bidding/validators.py:914-960` pattern). Readiness provider for area `m08_procurement`.

## 8. Tests first
1 Unit pure: FSMs; threshold resolver (table: jurisdiction x client x kind x value x date incl. boundary equal
to threshold, VAT basis, expired version); lot aggregation; backward schedule; scoring with Decimal; catalogue
loader (every procedure alias sourced, every threshold has source_url + valid_from, codes unique).
2 Service + PG: concept approve through governance; execution creates exactly one BidPackage / RFQ; read-back on
award event idempotent; framework call-off ledger and exhaustion; shortlist rule; schedule proposal confirm.
3 Security: other tenant cannot read concept or framework; IDOR on candidate, sounding, framework ids (add to
IDOR list in `ci-postgres.yml`); editor without m08 ownership cannot approve.
4 API contract, 5 migration up/down/up, 6 vitest (board badges, procedure picker filtering, role gating, i18n),
7 E2E: public client, 3 lots aggregated above EU threshold -> open procedure forced, shortlist 4, schedule,
create bid package.

## 9. Build order
tests 1 -> catalogue kind + JSON (neutral, eu, uk, us_federal; de_national unconfirmed) -> models + migration
-> service -> router -> integrations (mod3 ContractPackage, bid_management / rfq execution, subcontractors
evidence, schedule activities, governance provider, events) -> frontend -> i18n -> E2E -> cloud CI.
Depends on mod3 `ContractPackage` landing first.

## 10. Decisions (binding for implementation)
1 Canonical package = mod3 `ContractPackage`. It is the single identity (code, title, scope, kind, who designs/
builds/supplies). `AwardPackage` is a 1:1 extension (PK=FK) holding only procurement attributes. Reason: one
package plan, modules 4/7/8 read it; a second package table would be a second source of truth.
2 Canonical execution vehicle = `bid_management.BidPackage` for works, design and services; `rfq_bidding.RFQ` for
supply quotes. Reason: BidPackage has the richest model (bidders, Q&A, leveling, award, `award_contract.py`) and
10 events; RFQ already has award validation rules and fits material quotes. `tendering.TenderPackage` is not
created by this module (no budget, no procedure, string amounts) but existing rows can be linked; no migration of
its data in v1. Fix the dead `BidPackage.tender_id` comment pointing at a non-existent table as a separate small bug.
3 Thresholds are catalogue data with validity dates, never constants. Threshold checks only warn when the fact is
`unconfirmed`. Reason: thresholds change every two years (EU, UK) or five (US).
4 Procedures are neutral codes with national aliases, same pattern as mod3 forms.
5 Prequalification extends, not replaces, subcontractors: candidates point to `Subcontractor` / `Vendor`;
evidence is read from `Certificate`, `PrequalificationApplication`, `SubcontractorRating`. Project-specific
criteria and scoring live here because the existing prequal is one integer per company, not per package.
6 Framework agreements are tenant-level (they outlive projects) with a call-off ledger; projects link.
7 Award schedule lives in `schedule` as activities; this module computes and proposes, the human confirms.
8 Market sounding is a light log with a capacity signal, not a survey tool.
9 Private clients use the same module with jurisdiction `none`: thresholds off, procedures from the private set.
10 Approval is the governance gate on m08, no own approval route (consistent with mod3 Decision 2).

## 11. Procedure overview (catalogue defaults, abridged)
| neutral code | EU 2014/24 | UK PA 2023 | US federal | private |
|---|---|---|---|---|
| open | open (Art. 27) | open procedure | sealed bidding (FAR 14) | open tender |
| restricted | restricted (Art. 28) | competitive flexible | two-phase design-build (FAR 36.3) | selective tender |
| competitive_negotiated | Art. 29 | competitive flexible | negotiation (FAR 15) | negotiated |
| direct_award | below threshold / Art. 32 | direct award (s.41) | below micro-purchase | direct |
| framework_call_off | Art. 33 | framework (s.45) | IDIQ task order | call-off |

## 12. Sources
- EU thresholds 2026-2027, Delegated Reg. (EU) 2025/2152: https://inenuitvoer.sdu.nl/content/CELEX-32025R2152-20251112-ENG ,
  https://www.arthurcox.com/insights/public-procurement-thresholds-for-2026-2027/ (primary EUR-Lex text to be
  checked before `confirmed`).
- UK thresholds from 2026-01-01: https://www.blakemorgan.co.uk/new-public-procurement-thresholds-from-1-january-2026 ,
  https://www.trowers.com/insights/2025/december/procurement-act-2023-threshold-changes (SI not fetched: unconfirmed).
- US FAR thresholds from 2025-10-01: https://centrelawgroup.com/blog/inflation-updates-to-far-thresholds-what-changed-on-october-1-2025/ ,
  https://smallgovcon.com/?p=29648 (FAR 2.101 text to be checked).
- DE national direct award limits (conflicting sources, unconfirmed): https://vergabeblog.de/2026-01-13/bund-verlaengert-befristete-auftragswertgrenze-von-15-000-eur-fuer-direktauftraege/ ,
  https://www.bundestag.de/resource/blob/1170342/WD-7-015-26.pdf
- Not yet sourced: EU procedure articles and minimum periods, UK s.41/s.45 numbering, FAR 36.3, VOB/A §3a limits,
  GWB §97(4) lot splitting (mod3 Q4).
