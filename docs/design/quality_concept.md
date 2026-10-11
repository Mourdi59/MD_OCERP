# Module `quality_concept`: quality requirements, certification targets, proof concept, commissioning stages, acceptance concept (spec v1, 2026-10-11)

Sources: `mod9/INTEGRATION.md` (platform, file:line, worktree `wt-gates` HEAD 4059f178c), `gates/SPEC_v1.md`
(module 1), `mod3/SPEC.md` (`ContractPackage`, the package every proof and acceptance hangs on), `mod5/SPEC.md`
(`PlantItem`, delivery limits), `elf/SPEC.md` section 10 (Qualitaetsmanagement). Research URLs in section 12.
Name: dir `quality_concept`, tables `oe_qconcept_*` (`oe_qc_` is too close to construction_control's `oe_cc_` and
QMS "qc" party role), API `/api/v1/projects/{project_id}/quality-concept/...`, UI tab "Quality & acceptance".

## 1. Purpose
The development-phase PLAN that execution-phase quality modules are measured against. It answers, per project:
which standards and quality requirements apply; which certifications are targeted and at what level; which tests,
protocols, records and certificates each designer and contractor must deliver, per package and by when; how
commissioning runs as staged levels from delivery limit to proof of operation, with preconditions, release and owner
per stage; how acceptance works (partial per package, total, handover to operation) and what legal effect each act
has in the contract's jurisdiction; which documentation and FM data must be handed over; which existing conditions
must be preserved as evidence; and which material testing and calibration evidence is needed.

The platform already holds the EXECUTION evidence in seven modules (construction_control material passports, tests,
hold gates, handover packages; qms ITP plans and calibration; commissioning systems and checklists; closeout slots;
daily_diary photos and reality capture; defects_liability warranties with limitation regimes; requirements with
verification methods). This module adds no second copy of any of them. It owns the plan (what is required), and
computes COVERAGE: required vs delivered, by reading the linked evidence. That is the main user value: one screen
that shows "package Electrical: 41 of 52 proofs delivered, stage L4 blocked by 2 open functional items, acceptance
not yet possible because L5 is not released".

The approved concept IS the content of governance frame document `m10_quality_frame` (`elf_module_framework.json:1420`,
required at `development_to_execution`), folders `dev_quality_requirements` .. `dev_construction_reports` (`:1078-1134`);
execution folders `exec_qa_plans`, `exec_material_testing_*`, `exec_calibration`, `exec_as_built`,
`exec_evidence_preservation`, `exec_expert_reports` (`:1141-1232`) are fed by evidence links. No parallel approval engine.

## 2. Catalogue data (kind `quality_concept`, governance resolver)
Registered with `register_catalogue_kind` (`project_governance/catalogue_kinds.py:107`). Shipped files
`quality_concept/catalogues/neutral.json` (default; stages, evidence types, regimes for DE, UK, US, FIDIC) and later
pack overrides; tenant versions through `CatalogueStore`. Project pins `(source, id, version)`. Every statutory or
scheme fact carries `source_url` + `review_status` (`confirmed | unconfirmed`); thresholds and frequencies that were
not read from the primary text ship `unconfirmed` and render with a badge.

- `standard_families[]`: `code`, `name_key`, `examples[]` (open strings "EN 206", "DIN 1045-2", "EN 13670", "ACI 318",
  "BS 8500"), `discipline`. Reference only, never an enum on evidence rows (construction_control keeps `standard_ref`
  free text, `models.py:72`).
- `requirement_categories[]`: `quality.standards_basis`, `quality.availability`, `quality.energy`, `quality.user`,
  `quality.material`, `quality.durability`, `quality.acoustics`, `quality.fire`, `quality.fm_data`; each with a default
  `verification_method` from `requirements/lifecycle.py:142` VERIFICATION_METHODS (no new vocabulary).
- `certification_schemes[]`: `code` (dgnb_new_construction, breeam_new_construction, leed_bd_c, leed_o_m,
  well_building, other), `scope` (building | plant | operation), `versions[]`, `levels[]` (ordered: code, name_key,
  `min_score` + `score_unit` (percent | points), `source_url`, `review_status`), `phases[]` (pre_assessment,
  registration, design_stage, post_construction, certified), `credit_categories[]` optional. All third-party scheme
  content is data; no criteria texts are shipped (licensed), only codes and category names.
- `evidence_types[]`: `code`, `name_key`, `kind` (test | protocol | record | certificate | report | document | dataset),
  `fulfilled_by[]` = allowed evidence link kinds (see INTEGRATION 1.9: `cc_test_result`, `cc_material_record`,
  `cc_inspection`, `cc_asbuilt`, `qms_itp_plan`, `qms_calibration`, `cx_checklist`, `closeout_slot`, `submittal`,
  `cde_document`, `diary_reality_capture`), `default_deliverer` (designer | contractor | supplier | independent_expert |
  owner | authority). v1 set: design_calculation, static_proof_check (Pruefstatik), fire_protection_proof,
  thermal_proof, acoustic_proof, material_certificate_3_1, declaration_of_performance, concrete_conformity_tests,
  concrete_delivery_notes, suspension_tests, steel_mill_certificates, weld_inspection, pile_integrity_test,
  load_test, pressure_test, insulation_resistance_test, functional_test_protocol, integrated_systems_test_protocol,
  performance_test, calibration_certificate, as_built_drawings, as_built_survey, om_manual, warranty_certificate,
  fm_asset_dataset, training_record, authority_acceptance, expert_report.
- `material_test_plans[]`: `material_family` (raw_material | concrete | suspension | reinforcing_steel |
  structural_steel | soil | asphalt), `evidence_type`, `test_method` (open string), `frequency` {`per_quantity`,
  `unit`, `min_per_period`, `period`} or `per_lot`, `source_url`, `review_status` (all `unconfirmed` in v1 unless
  read from the standard text; standards are paid documents).
- `commissioning_stages[]` (LEVELS AS DATA): `code`, `order`, `name_key`, `description_key`, `default_owner_role`,
  `default_release_party` (qc | qa | tpi | ahj, the `HoldGate.required_party_role` vocabulary, construction_control
  `models.py:534`), `default_preconditions[]` (predicate codes, section 4 rule 9), `evidence_types[]`, `aliases[]`
  ({context, term, source_url}). Neutral v1:
  L0 `delivery_limit` (scope and interfaces agreed, from mod5 delivery limits), L1 `factory_test` (FAT, red tag),
  L2 `installation_check` (site acceptance / installation verification, yellow tag), L3 `startup_prefunctional`
  (energisation, start-up, pre-functional checks), L4 `functional_test` (per system), L5 `integrated_systems_test`
  (IST, failure modes across systems), L6 `performance_proof` (proof of operation / trial run / seasonal or
  performance test, handover to operation). Aliases: data-centre "Level 1-5" practice, German
  Inbetriebnahme / Probebetrieb / Leistungsnachweis per VDI 6039 (phases only by title, see 12), ASHRAE Cx
  process terms.
- `acceptance_regimes[]`: `code`, `country_code`, `contract_basis` (statute | standard_form), `name_key`, `act_name`
  (Abnahme, Practical Completion Certificate, Certificate of Substantial Completion, Taking-Over Certificate),
  `partial_allowed` + `partial_term`, `refusal_threshold` (e.g. `material_defect_only`), `deemed_acceptance[]`
  ({trigger: completion_notice | use_start | deadline_set, `working_days` | `reasonable_period`, `consumer_notice_required`,
  `source_url`, `review_status`}), `effects[]` = legal effects as data:
  {`effect`: risk_transfer | limitation_starts | payment_due | retention_release_part | liquidated_damages_end |
  burden_of_proof_shifts | defects_period_starts | occupation_permitted | insurance_responsibility_shifts,
  `detail_key`, `value` (e.g. 50 percent), `source_url`, `review_status`}, `limitation_regime_code` (links
  `defects_liability/limitation.py:83` regimes: `de_bgb`, `de_vob_b`; new regimes added there, not here).
  v1 regimes: `de_bgb` (§640, §641, §644, §634a BGB), `de_vob_b` (§12, §13 VOB/B), `uk_jct_practical`,
  `us_aia_substantial` (A201 §9.8), `fidic_taking_over` (clause 10, unconfirmed). National facts in section 11.
- `documentation_sets[]`: per project type the default closeout slot definitions (ALIGNS with
  `closeout/checklist_templates.py:76-110`; the catalogue references slot keys there and adds new ones, it never
  redefines existing keys) and FM data requirement defaults (`deliverable_type` cobie | pset | dataset, `loi`).
- `preservation_subjects[]`: neighbour_building, own_existing_structure, public_road, utility, heritage, trees,
  watercourse, with default `influence_trigger` (excavation, piling, dewatering, vibration, crane oversail, demolition)
  and default survey methods (photo, crack_mapping, level_survey, vibration_monitoring, reality_capture).

## 3. Entities (project-scoped, FK CASCADE on project, tenant via project access; new tables only unless marked)
- `QualityConcept` (one per project): pinned catalogue, `governance_document_id` (soft), `requirement_set_id`
  (soft link to the project's quality `RequirementSet`), `state`: `draft -> in_review -> approved -> binding`
  (+ `revising` -> `in_review`); `approved/binding` MIRRORED from the governance frame document, never set here alone.
- Quality requirements: REUSE `requirements.Requirement` rows (category `quality.*`, `verification_method`,
  `source_ref` = standard) in one `RequirementSet` with `metadata.purpose="quality_concept"`. No new table.
- `AppliedStandard`: code (open string), edition/year, scope (discipline / package ids), `source_url`, mandatory flag
  (statute | contract | voluntary), note. The standards basis list; requirements cite it by `source_ref`.
- `CertificationTarget`: scheme code + version, `scope` (building | plant | operation), `target_level`, assessor
  (contact soft id), registration no., `state`: `planned -> registered -> design_assessed -> post_construction_assessed
  -> certified` (+ `abandoned` needs rationale, `level_missed` with achieved level), achieved level + certificate
  (CDE soft link), dates.
- `CreditTarget` (optional, only when the user wants credit tracking): target, credit code (open string),
  category, `points_targeted` (Decimal), `points_achieved`, owner user, evidence links (same typed link as proofs),
  state `targeted -> evidence_submitted -> achieved | not_achieved | dropped`. Totals computed on read.
- `ProofRequirement` (the proof concept, one row per required proof): `package_ref` (soft link to mod3
  `ContractPackage`, nullable only for project-wide proofs), optional `plant_item_id` (mod5) / `cx_system_id`,
  `evidence_type`, `deliverer_role` + optional party (contact soft id), `required_by` (one of: commissioning stage code,
  acceptance unit, schedule activity soft id, date), `quantity_rule` (from material_test_plans for counted tests,
  e.g. "1 per 150 m3"), `review_by` role, `source` (catalogue_default | edited), `state` computed:
  `open | partly_delivered | delivered | accepted | waived` (waive needs rationale + approver).
- `EvidenceLink` (one table, used by ProofRequirement, CreditTarget, StageProgress, PreservationSurvey):
  `(owner_kind, owner_id, link_kind, link_id)`; `link_kind` is a closed list of existing evidence tables; never copies
  their content. Delivery state is read from the linked row (e.g. TestResult `result=pass`, MaterialRecord
  `accepted`, CxChecklist all items pass, closeout binding `is_verified`).
- `CommissioningStageDef` (project copy of the catalogue levels, copy-on-write): code, order, name override,
  `owner_user_id`, `release_party_role`, `release_user_ids[]` (optional named releasers), preconditions (predicate
  codes + params), required evidence types, `applies_to` (all systems | system types | named systems).
- `StageProgress` (cx unit x stage): unit = `commissioning.CxSystem` (REUSE as the commissioning unit; plant items
  link to a system), `state`: `blocked -> ready -> in_test -> passed -> released` (+ `failed` -> `in_test`,
  `not_applicable` with rationale). `ready` = preconditions met (computed); `passed` from linked evidence;
  `released` ONLY through a construction_control `HoldGate` (`attached_kind="cx_stage"`, EXTEND) released e-signed by
  the stage's release party. Stores `hold_gate_id`; no own signature columns.
- `AcceptanceUnit` (acceptance concept + record pointer): `kind` (partial_package | partial_section | total |
  handover_to_operation | authority), `package_refs[]`, section/area ref, `regime_code`, planned date (schedule
  activity soft link), preconditions (stage codes that must be released, proof sets that must be delivered, documentation
  slots), `handover_package_id` (soft link to construction_control `HandoverPackage`, the ACT with gate and e-signed
  certificate), state `planned -> requested -> inspection_scheduled -> accepted_with_reservations | accepted | refused`
  (+ `deemed_accepted`), `completion_notice_at`, `use_started_at`, `reservations[]` (punch item / defect soft ids,
  §640(3) BGB reserved defects), `effects_applied[]` (which effect was confirmed by whom, see rule 15).
- `PreservationSurvey`: subject kind, address / parcel, owner contact, influence triggers, `phase` (before | during |
  after | on_complaint), method(s), surveyor (party / expert), planned date, survey date, invitation sent date,
  attendance / acknowledgment by the owner (signed yes/no + CDE doc), evidence links (diary photos, reality capture,
  CDE report), `state`: `planned -> invited -> surveyed -> report_issued -> closed` (+ `access_refused` with record),
  `paired_with_id` (after-survey points to its before-survey).
- `ExpertReportPlan` (baubegleitende Gutachten): subject, expert, trigger / frequency, due dates, evidence link to the
  CDE report. Small table, not folded into ProofRequirement because it is commissioned by the owner, recurring, and
  has its own budget line (soft link to commitment, mod2).
- Documentation and FM data: REUSE `closeout` (slots seeded from the concept's documentation set into the project's
  CloseoutPackage) and `requirements.RequirementDeliverable` (`deliverable_type` cobie / pset, `loi`, due milestone)
  for FM data. No new table; the concept stores only the chosen documentation set code.
- Material testing, calibration: REUSE construction_control `MaterialRecord`, `TestResult`, qms `QMSCalibration`;
  EXTEND `TestResult` with nullable `calibration_id` (soft) so a test can name its instrument certificate (AsBuilt has
  `instrument_calibration_ref` already, `models.py:445`).

## 4. Rules (each is a test)
1 Concept to `in_review` needs: a standards basis (>= 1 AppliedStandard), every applicable package from mod3 with
  >= 1 ProofRequirement or an explicit "no proofs" rationale, a stage model with an owner per stage, an acceptance unit
  per package plus one `total` and one `handover_to_operation`, each with a regime (`concept_incomplete` + list).
2 Every ProofRequirement names a deliverer role and a `required_by`; `required_by` stage code must exist in the
  project's stage model.
3 Evidence link kind must be in the evidence type's `fulfilled_by`; link to a row of another project -> 404 at write,
  never stored (IDOR).
4 Delivery state is derived: a test proof is delivered only by TestResult `status=recorded` and `result=pass`;
  a material proof only by MaterialRecord `accepted` and not expired at use; a counted proof (quantity_rule) needs the
  computed number of passing results for the placed quantity (quantity read from linked MaterialRecord / BOQ soft ref);
  partial -> `partly_delivered`.
5 A TestResult or AsBuiltRecord linked as evidence whose instrument calibration was expired on `tested_at` /
  `survey_date` does not count, and raises `evidence_with_expired_calibration` (error).
6 A failed linked test keeps the proof `open` even if a later pass exists for a DIFFERENT sample; a re-test must
  reference the failed result (metadata) or the NCR closure.
7 Waiving a proof needs rationale and an approver != requester (four-eyes from governance setting).
8 Stage order is strict per unit: stage n cannot be `ready` while stage n-1 is not `released` or `not_applicable`.
9 Precondition predicates (catalogue codes, evaluated, never free code): `previous_stage_released`,
  `proofs_delivered(evidence_types)`, `no_open_cx_issues(severity>=high)`, `hold_gates_released(scope)`,
  `plant_item_delivered` (mod5 state), `delivery_limit_agreed` (mod5), `authority_acceptance_present`,
  `systems_released(stage, systems)` (for IST across systems), `documentation_slots_delivered(keys)`.
10 Release of a stage only via HoldGate release by a user whose asserted party role satisfies the stage's
  `release_party_role` (`gating_service.party_role_satisfies`); `released` without a released gate is impossible.
11 `commissioning.CxSystem` may become `commissioned` only when the project's final stage for that system is
  released (EXTEND `commission_system` with a guard that calls this module's provider when the project has a concept;
  without concept, today's behaviour stays).
12 A failed stage test raises a CxIssue (existing table) and returns the stage to `in_test`; released stages of
  dependent units (IST) go `stale` and need re-release when a system they depend on re-enters testing.
13 Acceptance unit `requested` needs every precondition met, or an explicit "accept with reservations" path that lists
  each unmet precondition as a reservation (only for preconditions flagged `reservable` in the regime; BGB/VOB:
  non-material defects; JCT/AIA: punch / snag items).
14 Deemed acceptance clock: when the regime has `deemed_acceptance` and the unit records `completion_notice_at` or
  `use_started_at`, the deemed date is computed (VOB/B: 12 working days after written completion notice, 6 working days
  of use; BGB: deadline set by contractor, refusal must name >= 1 defect) and shown as a warning with source; the
  module never sets `deemed_accepted` itself, a user confirms (AI/automation proposes, human confirms).
15 Issuing the HandoverPackage certificate (existing e-signed path) moves the unit to `accepted*` via event; each
  regime effect is then PROPOSED, applied only on confirm: limitation_starts -> sets `warranty_start_date` and
  `limitation_regime` on the linked DlpWarranty rows (through defects_liability service); defects_period_starts -> same;
  retention_release_part / payment_due -> notification + LINK to mod2 commitment, no money written here;
  risk_transfer / insurance -> notification to area m09 owner. Idempotent per (unit, effect).
16 Partial acceptance counts open NCRs and unreleased hold gates of ITS packages only (fix: today
  `_open_ncr_count` is project-wide, `handover_service.py:456`); requires NCR / gate package scope (INTEGRATION 2).
17 `total` acceptance needs all partial units accepted or explicitly included; `handover_to_operation` needs the
  final stage released for every in-scope system and FM data deliverables accepted.
18 Certification target: `certified` needs an achieved level >= target or the state `level_missed`; credit totals
  (when credits are tracked) below the target level's `min_score` warn (`certification_target_at_risk`), with the
  threshold's review_status shown.
19 Preservation: every subject with an influence trigger matching a planned activity (excavation, piling, demolition,
  dewatering; soft link to schedule activity) needs a `before` survey `surveyed` before that activity starts
  (`preservation_missing_before_start`, error at the hold gate if the user attached one); an `after` survey pairs
  with its `before`.
20 Neighbour survey without owner acknowledgment or recorded refusal warns (evidence value weaker); refusal is recorded,
  never edited later.
21 Material test plan: placed quantity vs passing results per family below the catalogue frequency warns
  (`material_test_frequency_short`, review_status shown since frequencies are unconfirmed).
22 Snapshot: concept approval snapshots proofs, stages, acceptance units; later edits create a revision; after binding,
  changes go through governance `FrameChangeRequest` (governance rule 4).
23 All labels i18n; exports PDF + XLSX via `core/register_export`: proof matrix (package x evidence type), stage
  matrix (system x stage), acceptance plan with legal effects and sources, preservation register, certification sheet.

## 5. API (`/api/v1/projects/{project_id}/quality-concept/...`, envelope `{items,total,offset,limit}`)
concept (get, pin catalogue, submit, revisions, export), standards (CRUD), requirements (proxy list/create into the
quality RequirementSet via requirements service, no own storage), certifications (CRUD, transitions) + credits (CRUD,
bulk), proofs (CRUD, bulk generate from package + catalogue preview -> confirm, coverage report, waive), evidence-links
(add/remove, candidates search per link kind), stages (list/patch model, apply catalogue), stage-progress (matrix,
open test, request release -> creates HoldGate, mark n/a), acceptance-units (CRUD, request, record completion notice /
use start, deemed-date preview, confirm effects), preservation (CRUD, invite, record survey, pair), expert-reports
(CRUD), readiness (read-only evidence for governance). Permissions: `quality_concept.read`, `quality_concept.edit`
(manager or m10 area owner), `quality_concept.waive` (route-entitled), stage release stays
`construction_control` gate permission. `verify_project_access` on every handler; cross-project ids 404.

## 6. Screens (project tab `/projects/:id/quality`, no new top segment)
1 Overview: concept state, governance badge, coverage bars per package (proofs), stage funnel L0..L6, acceptance
  timeline, certification target card, preservation status; "what blocks the next acceptance" list.
2 Proof matrix: packages x evidence types; cell = required / delivered / accepted, click opens linked evidence.
  "Generate from catalogue" shows a preview, user confirms rows.
3 Commissioning stages: systems x levels board; cell shows preconditions (green/red with reason), evidence, release
  gate; level model editor (rename, owner, release party, add/remove level).
4 Acceptance plan: units with regime, legal effects with source links and review badges, deemed-date countdown,
  link to the HandoverPackage act; effects confirmation dialog.
5 Standards and requirements (list + quality RequirementSet table), certification targets and optional credits.
6 Evidence preservation register with map pins (address), before/after pairs, photos from diary.
Strings in all locales in the same commit.

## 7. Validation rule set `quality_concept`
concept_complete, proof_has_deliverer_and_due, evidence_kind_allowed, evidence_with_expired_calibration,
stage_has_owner_and_release_party, stage_order_respected, stage_released_via_gate, acceptance_unit_per_package,
acceptance_regime_set, acceptance_preconditions_met, partial_acceptance_scoped, deemed_acceptance_due (warning),
certification_target_at_risk (warning), preservation_before_start, preservation_acknowledged (warning),
material_test_frequency_short (warning), commissioned_without_final_stage (error, catches CxSystem commissioned
outside the stage model). Registered via `validators.py` + `on_startup`.
Readiness for governance area `m10_quality` at `development_to_execution`: concept approved, zero error violations,
rules 1-2 satisfied, preservation surveys planned for every triggered subject. Provider registry, governance never
imports this module.

## 8. Tests first (order)
1 Unit pure: FSMs (concept, stage progress, acceptance unit, preservation, certification) table-driven; precondition
  evaluator (each predicate, stage order); delivery derivation (rule 4-6 cases incl. counted tests and expired
  calibration); deemed-date calculator (VOB/B working days incl. Saturdays as Werktage, holidays as data; BGB);
  catalogue loader (every shipped catalogue validates; every `fulfilled_by` is a known link kind; every
  `release_party` in the HoldGate vocabulary; every `limitation_regime_code` in `ALL_LIMITATION_REGIMES`; every
  `verification_method` in VERIFICATION_METHODS; every legal effect has source_url; closeout slot keys referenced exist).
2 Service + PG (tests/pg): generate proofs for a package; link evidence across modules and see coverage change; stage
  release via HoldGate; CxSystem commission guard; IST stale after system re-test; acceptance with reservations;
  effects confirm writes DlpWarranty start once (idempotent); partial acceptance counts only its packages' NCRs;
  preservation before-start error; snapshot frozen after binding; concurrent release 409.
3 Security (tests/pg + IDOR list in ci-postgres.yml + `test_idor_router_guards.py`): other tenant cannot read or link;
  evidence link to another project's TestResult 404; editor cannot waive; non-matching party role cannot release.
4 API contract: envelope, 404 vs 403, error codes. 5 Migration up/down/up on PG (new tables + 7 nullable EXTEND columns: TestResult.calibration_id, CxChecklist.stage_code, CxSystem.plant_item_id, HoldGate.package_ref, HandoverPackage.regime_code + package_refs, NCR package ref).
6 Frontend vitest: proof matrix states, stage board preconditions, effects dialog shows sources and review badges,
  role gating, i18n keys. 7 E2E: pin neutral catalogue, generate proofs for 2 packages, link a test + material
  record, run HVAC through L2-L4 with releases, partial acceptance (VOB/B) with one reservation, confirm limitation
  start, check warranty date.

## 9. Build order
tests 1 -> catalogue kind + neutral.json -> models + migration (incl. EXTEND columns: TestResult.calibration_id,
CxChecklist.stage_code, HoldGate attached_kind `cx_stage`, HandoverPackage regime + package scope) -> service +
FSMs + evaluator -> router + permissions -> integrations (governance provider + frame doc, requirements set, closeout
seeding, construction_control gate + handover events, commissioning guard, defects_liability effects, daily_diary
evidence, notifications, export) -> frontend -> i18n -> E2E -> cloud CI -> browser check.

## 10. Open questions
No open questions; all decided below. Items needing a human legal read are marked `unconfirmed` in data.

## 11. Acceptance regimes v1 (catalogue content, abridged)
| regime | act | partial | deemed acceptance | key effects |
|---|---|---|---|---|
| de_bgb | Abnahme (§640 BGB) | by agreement | contractor sets reasonable deadline; deemed unless refused naming >= 1 defect; consumer needs text-form notice (§640(2)) | risk passes (§644), payment due (§641), limitation 5 y from Abnahme (§634a), reserve known defects or lose §634 Nr.1-3 rights (§640(3)); refusal not for insignificant defects |
| de_vob_b | Abnahme (§12 VOB/B) | yes, self-contained parts (§12(2)) | 12 Werktage after written completion notice; 6 Werktage after start of use; use to continue works is not use (§12(5)) | as BGB plus limitation 4 y default (§13(4)); refusal for material defects (§12(3)) |
| uk_jct_practical | Practical completion certificate | sectional completion | none | rectification period starts, half retention released, LDs stop, client occupies (unconfirmed against JCT text) |
| us_aia_substantial | Certificate of Substantial Completion (A201 §9.8) | designated portion | none | owner can occupy or utilize for intended use; punch list; warranties and responsibilities fixed in certificate (unconfirmed against A201 text) |
| fidic_taking_over | Taking-Over Certificate (clause 10) | sections / parts | deemed if engineer does not respond (unconfirmed) | DNP starts, delay damages stop (unconfirmed) |

## 12. Sources
- §640 BGB Abnahme, deemed acceptance, reservation: https://www.gesetze-im-internet.de/bgb/__640.html (fetched)
- §644 BGB risk until Abnahme: https://www.gesetze-im-internet.de/bgb/__644.html (fetched)
- §634a / §641 BGB: https://www.gesetze-im-internet.de/bgb/__634a.html , https://www.gesetze-im-internet.de/bgb/__641.html
  (not fetched in this session; §634a already cited by `defects_liability/limitation.py:104`)
- VOB/B §12 (text, 2016): https://lxgesetze.de/vob-b-2016/12 ; commentary https://www.bauprofessor.de/fiktive-abnahme/
  (secondary; VOB/B is a private standard form, no official free text)
- §485 ZPO independent evidence proceeding (condition of a thing, cause of defect): https://www.gesetze-im-internet.de/zpo/__485.html
  (fetched; basis for the evidence-preservation register's legal value, info text only)
- UK practical completion, rectification period, retention: https://www.designingbuildings.co.uk/wiki/Rectification_period ,
  https://c-link.com/?p=15550 (secondary, unconfirmed)
- US substantial completion A201 §9.8.1: https://learn.aiacontracts.com/?p=13891 ,
  https://www.floridaconstructionlegalupdates.com/what-is-substantial-completion/ (secondary, unconfirmed)
- Commissioning levels 1-5 (FAT, installation / SAT, pre-functional, functional, IST): https://www.hioki.com/id-id/industries-solutions/facilities/data-center-commissioning-levels.html ,
  https://archdesk.com/blog/data-center-commissioning-levels (practice, naming varies, hence levels are data)
- VDI 6039:2011 commissioning management for buildings (TOC only): https://www.dinmedia.de/de/technische-regel/vdi-6039/142074819 ,
  https://www.staedtetag.de/files/dst/docs/Dezernat-6/2020/energiemanagment-hinweise-inbetriebnahmemanagement-november-2020.pdf
- Certification schemes (levels unconfirmed until read on the scheme sites): https://www.dgnb.de/en ,
  https://bregroup.com/products/breeam , https://www.usgbc.org/leed ; overview https://en.wikipedia.org/wiki/Green_building_certification_systems
- Material evidence vocabularies already in code: EN 10204, EU CPR DoP, ISO/IEC 17025 (`construction_control/models.py:14-20`).

## Decisions (agent, 2026-10-11; binding unless the lead overrides)
1. Plan vs evidence split. This module owns only requirements-to-deliver and coverage; every test, certificate,
   inspection, checklist, calibration and handover act stays in its existing module and is linked. Reason: seven
   modules already hold the evidence; a second copy would be a parallel island the design rules forbid.
2. Quality requirements are `requirements.Requirement` rows in one quality RequirementSet, not a new table. Reason:
   requirements already has category, verification method, source and phase; one place for "what must be true".
3. One `EvidenceLink` table with a closed list of link kinds for proofs, credits, stages and surveys. Reason: one
   resolver, one IDOR check, one coverage query; matches the UER pattern in construction_control.
4. Commissioning levels are catalogue data with a neutral L0-L6 default; projects rename, drop or add levels. Reason:
   sources disagree on level names (L2 = SAT vs installation check); a fixed enum would be wrong for someone.
5. The commissioning unit is the existing `CxSystem`; checklists get a nullable `stage_code`. Reason: commissioning
   already has systems, checklists, issues and a readiness gate; levels are a sequence over them, not a new tree.
6. Stage release is a construction_control `HoldGate` (new attached kind `cx_stage`), not a new signature. Reason:
   HoldGate already has party-role checks and e-signature; qms hold point release stays for ITP items. One release
   mechanism per stage.
7. The acceptance ACT stays `HandoverPackage` (e-signed certificate, gating); this module adds the PLAN
   (`AcceptanceUnit`) and the regime with legal effects. `HandoverPackage.completion_regime` is extended by a nullable
   `regime_code` from our catalogue (DE Abnahme was missing: pattern has only taking_over|substantial|practical) and a
   package scope. Reason: one certificate path; legal effects as data, not hard-coded.
8. Legal effects are proposed, never auto-applied; the warranty start is written through defects_liability service on
   confirm, money effects are notifications plus links to mod2. Reason: principle 7 and single source for money.
9. Deemed acceptance is computed and warned, never set automatically. Reason: whether a notice was "written" or use was
   "uninterrupted" is a legal finding.
10. Certification: targets and levels as data; credit tracking optional and points-only (no scheme criteria texts).
    Reason: "credit tracking only as far as useful"; scheme manuals are licensed.
11. Evidence preservation is a NEW register (`PreservationSurvey`) whose photos and scans stay in daily_diary / CDE.
    Reason: nothing models neighbours, invitations, acknowledgment or before/after pairs today.
12. Material testing and calibration reuse construction_control and qms; only `TestResult.calibration_id` is added.
    Test frequencies ship `unconfirmed` because the standards are paid texts.
13. Documentation and FM handover reuse closeout slots and RequirementDeliverable (COBie, LOI); the concept picks a
    documentation set. Reason: closeout already builds the dossier and COBie.
14. Expert reports during construction get a small own table (owner-commissioned, recurring, budgeted); not proofs.
15. Partial acceptance must scope NCRs and hold gates to its packages; this needs a package soft link on NCR and
    HoldGate (EXTEND, nullable). Without it, partial acceptance would be blocked by unrelated defects.
16. v1 content: neutral levels + regimes DE BGB, DE VOB/B, UK JCT, US AIA, FIDIC; DE facts confirmed from
    gesetze-im-internet.de where fetched, all others `unconfirmed`.
