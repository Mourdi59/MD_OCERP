# Module `permits`: permit roadmap and consolidated permit-condition register (spec v1, 2026-10-11)

Sources: `mod4/INTEGRATION.md` (platform, file:line), `gates/SPEC_v1.md` (module 1, `project_governance`),
`elf/SPEC.md` modules 2 ("Baurecht und Genehmigungsfahrplan", special permits) and 11 ("Genehmigungsauflagen:
consolidation of all conditions from module 2 as requirement for execution"). Siblings: `mod2` (commitment matrix),
`mod3` (delivery model). Name `oe_permits`, dir `permits`, API `/v1/projects/{id}/permits/...`.

UI vocabulary (fixed, i18n keys `permits.*`): "Authority permit" (this module) vs "Permit to work"
(`hse_advanced.PermitToWork`, a site safety permit) vs "Gate condition" (governance `GateCondition`, an internal
condition attached to a gate decision) vs "Permit condition" (this module). The word "permit" is never shown alone.

## 1. Purpose
Answer three questions for owner, PM and site manager on one screen. (1) Which authority approvals does this project
need, who applies, when, in what order, and by when must each decision arrive so the schedule holds (the roadmap)?
(2) Where does each application stand, and what did the authority decide (granted, granted with conditions, partial,
refused)? (3) What has every decision obliged us to do, who owns it, when is it due, and what evidence discharges it
(ONE register of all conditions from all permits)? Before-start conditions feed the start gate and site mobilisation;
before-occupation conditions feed handover; ongoing conditions feed HSE and the operation phase.

Not owned here: the authority's document review rounds and remarks (`review_authority`), the machine-readable
e-submission payload (`authority_submission`), the route classification (`project_route`), dates of construction
activities (`schedule`), site inspections (`inspections`), safety work permits (`hse_advanced`), funding obligations
(`funding`). The module links them; it does not copy them.

Domain basis (fetched 2026-10-11 = `review_status: confirmed`; everything else ships `unconfirmed`):
- DE, conditions: VwVfG §36 Abs. 2 types Befristung, Bedingung, Widerrufsvorbehalt, Auflage, Auflagenvorbehalt
  (https://www.gesetze-im-internet.de/vwvfg/__36.html, confirmed). A Bedingung is suspensive (effect depends on the
  event), an Auflage is an enforceable duty. This difference drives rule 12.
- DE, BImSchG: decision within 7 months (formal) / 3 months (simplified, §19), from receipt of the application AND
  complete documents, one extension by up to 3 months by the authority with reasons, further only with applicant consent
  (§10 Abs. 6a, https://www.gesetze-im-internet.de/bimschg/__10.html, confirmed). Early start (§8a, revocable at any
  time, may require security and an undertaking to restore, https://www.gesetze-im-internet.de/bimschg/__8a.html,
  confirmed). Water law early start WHG §17 (https://www.gesetze-im-internet.de/whg_2009/__17.html, unconfirmed),
  Erlaubnis/Bewilligung WHG §8 (unconfirmed).
- DE, building law is Land law: the MBO is a model only, paragraph numbers differ per Land. Worked example NRW: BauO NRW
  2018 §75, Baugenehmigung lapses if work does not start within 3 years or pauses more than 1 year, extendable by up to
  1 year per request (https://lexmea.de/de/gesetz/bauo-2018-nrw/75, secondary, unconfirmed); BW extends by up to 3 years
  (same search, unconfirmed). Bauvoranfrage/Vorbescheid, Teilbaugenehmigung, vorzeitiger Baubeginn, Genehmigungsfiktion
  and decision periods: per-Land data rows, all `unconfirmed` until read in the Land statute.
- UK (England): determination 8 weeks, major 13 weeks, from the day after receipt, longer by written agreement
  (DMPO 2015 art. 34, https://www.legislation.gov.uk/uksi/2015/595/article/34, confirmed); EIA period referenced to
  separate regulations (unconfirmed). Discharge of conditions: 8 weeks from the day after receipt, extendable by
  agreement (art. 27, https://www.legislation.gov.uk/uksi/2015/595/article/27, confirmed); deemed discharge regime
  (art. 28-29, unconfirmed). Default time limit to begin: 3 years England, 5 years Wales (TCPA 1990 s.91,
  https://www.legislation.gov.uk/ukpga/1990/8/section/91, confirmed). Pre-commencement conditions need the applicant's
  written agreement (TCPA s.100ZA, unconfirmed). s.73 variation and s.96A non-material amendment (unconfirmed).
  Building regulations: Building Act 1984 s.16 (full plans period) was omitted from 1.10.2023 by the Building Safety
  Act 2022 (https://www.legislation.gov.uk/ukpga/1984/55/section/16, confirmed); the current periods and the
  higher-risk-building gateways 2 and 3 ship `unconfirmed`.
- US: permits, inspections and certificate of occupancy follow the adopted model code (IBC ch. 1: 105 permits,
  105.5 expiration, 110 inspections, 111 certificate of occupancy; https://codes.iccsafe.org/content/IBC2021P1,
  fetch refused 403, unconfirmed) as amended locally; decision periods are set per jurisdiction, so US rows carry no
  statutory period unless a jurisdiction row supplies one. Zoning (variance, special use) is local. Federal
  environmental: NEPA, CWA §404, NPDES construction general permit (unconfirmed).
- Generic: EU EIA Directive 2011/92/EU as amended by 2014/52/EU (unconfirmed); utility connection agreements (grid,
  water, sewer, telecom) are contractual, not statutory, modelled as permit types of category `utility`.

## 2. Catalogue (data, not code): kind `permit_type`
Registered with one call in module 1's kind registry (`project_governance/catalogue_kinds.py:107`
`register_catalogue_kind`): shipped JSON in `permits/catalogues/`, tenant drafts and immutable published versions in
the shared governance catalogue store, one resolver; a project pins `(source, id, version)`. Shipped catalogues:
`neutral`, `de` (with per-Land overlays `de_nw`, `de_bw`, others empty skeletons), `uk_england`, `uk_wales`, `us_ibc`
(jurisdiction rows added by tenants or packs). Country default via `core/regional_packs.py` as in module 1.

Catalogue body:
- `permit_types[]`: `code`, i18n `name_key`, `category` (`planning_zoning` | `building` | `environmental` | `water` |
  `immission` | `heritage` | `traffic_road` | `utility` | `occupancy` | `discharge` | `early_start` | `other`),
  `authority_kind` (reuses `review_authority` AUTHORITY_KINDS plus `planning_authority`, `environmental_agency`,
  `utility_operator`), `default_applicant_role` (`owner` | `designer` | `contractor` | `operator`), `typical_documents[]`
  (i18n keys), `scope`: `full` | `partial` | `preliminary` (Vorbescheid binds only on asked questions) | `early_start`,
  `requires[]` (type codes that must be granted, or `submitted`, first), `enables[]` (spine phase or milestone codes:
  `site_start`, `construction`, `occupation`, `operation`), `triggered_by_route[]` (`project_route` ROUTE_OPTIONS
  values, e.g. `full_permit`, `notification`), `revocable` (bool, e.g. BImSchG §8a), `security_possible` (bool).
- `clock`: `period` (int), `unit` (`calendar_days` | `working_days` | `weeks` | `months`), `start_event`
  (`receipt` | `day_after_receipt` | `complete`), `stop_on_rfi` (bool), `extension` (`none` | `by_authority_once`
  {max, unit, reason_required} | `by_agreement`), `deemed_outcome` (`none` | `granted` | `discharged`) and
  `deemed_requires_notice` (bool), plus `variants[]` (e.g. `major` 13 weeks, `simplified` 3 months).
- `validity`: `lapse_if_not_started` {period, unit}, `lapse_if_paused` {period, unit}, `extension_per_request`.
- `condition_kinds[]`: national labels mapped onto the neutral kinds of section 3 (DE: Bedingung -> `suspensive`,
  Auflage -> `obligation`, Befristung -> `time_limit`, Widerrufsvorbehalt -> `revocation_reserve`,
  Auflagenvorbehalt -> `reserved_obligation`; UK: pre-commencement / prior-to-occupation / compliance conditions;
  US: conditions of approval, special inspections).
- Every statutory figure: `source_url`, `review_status` (`confirmed` | `unconfirmed`), `as_of`, `effective_from/to`.

## 3. Entities (project-scoped, FK CASCADE on project, tenant via project access, new tables only)
- `PermitRoadmap` (one per project): pinned catalogue `(source,id,version)`, `jurisdiction` (ISO 3166-2, e.g.
  `DE-NW`), `route_assessment_id` (soft, `project_route`), `delivery_model_id` (soft, mod3), `governance_document_id`
  (soft, frame document), `state` `draft -> agreed` (agreed = approved at the governance gate, mirrored, rule 18).
- `PermitRequirement` (a roadmap row: "we need X"): `permit_type_code`, title override, `applicable` + rationale,
  `applicant_role` + `applicant_party` (free text or `contact_id`) + `responsible_user_id` (internal owner),
  `depends_on[]` (other requirement ids, typed `granted` | `submitted`), `planned_submit_date`, `needed_by_activity_id`
  (soft schedule activity, the activity that cannot start without it) or `needed_by_date`, `clock_variant`,
  `schedule_activity_id` (soft, optional milestone in the schedule), `governance_area_code` (default m02).
- `PermitApplication`: `requirement_id`, `attempt` (resubmission after refusal = n+1), `kind` (`new` | `variation`
  (s.73) | `amendment_non_material` | `extension_of_validity` | `discharge_of_conditions` | `early_start`),
  `parent_permit_id` (for variation / extension / discharge), `discharges_condition_ids[]` (discharge kind only),
  `authority_name`, `authority_reference`, `submitted_at`, `received_at`, `validated_at` (complete), clock events
  (`ClockEvent` rows: `stop`, `resume`, `extension_agreed`, `extension_by_authority` with reason),
  `review_cycle_id` (soft, `review_authority`), `submission_id` (soft, `authority_submission`),
  `cde_container_id` (application documents as CDE revisions), `approval_instance_id` (internal release, optional),
  `state` (below).
- `PermitDecision` (immutable, one per application; corrections create a new decision with `supersedes_id`):
  `outcome` `granted` | `granted_with_conditions` | `partially_granted` | `refused` | `deemed_granted` | `withdrawn`,
  `decision_date`, `served_date`, `reference`, `scope_note` (what a partial covers), `valid_until` (computed from
  `validity` and the start notice, rule 9), `appeal_deadline` (data, optional), `document_revision_id` (CDE, the
  notice itself), `content_hash`.
- `Permit` (the granted right, one per non-refused decision; read model the rest of the platform links to):
  `state` `in_force` | `suspended` | `lapsed` | `revoked` | `superseded` | `expired`, `start_notified_at`,
  `superseded_by_id`.
- `PermitCondition` (THE register, every condition from every decision): `permit_id`, `number` (as in the notice,
  e.g. "N 12", "Condition 7"), `text` (verbatim), `kind` (`suspensive` | `obligation` | `time_limit` |
  `revocation_reserve` | `reserved_obligation` | `information`), `trigger` (`before_application_x` | `before_start`
  | `before_stage` (+ `stage_ref`: activity or WBS) | `before_occupation` | `ongoing` | `by_date` | `on_event`
  (+ text) | `after_completion`), `due_date` (computed or fixed), `topic` (`hse` | `environment` | `noise` |
  `traffic` | `heritage` | `structural` | `fire` | `drainage` | `ecology` | `design` | `admin` | `other`),
  `owner_user_id`, `responsible_party` (contractor etc.), `requires_authority_approval` (bool: discharge is itself an
  application, UK style), `evidence_required` (text), `requirement_id` (soft, `requirements`, for measurable
  technical limits), `hse_relevant` (derived from topic, overridable), `state` (below), `source`
  (`manual` | `ai_extracted` with `confidence`, rule 15).
- `ConditionEvidence`: `condition_id`, `kind` (`cde_revision` | `inspection` | `commissioning_item` | `report` |
  `photo` | `external_url` | `discharge_decision`), `ref_id`, note, `added_by/at`.
- `ConditionDischarge` (immutable): `condition_id`, `mode` (`self_certified` | `authority_discharged` |
  `deemed_discharged` | `not_triggered` | `waived_by_authority`), `decided_by` (user) or `discharge_application_id`,
  `verifier_user_id` (four-eyes, rule 13), `date`, snapshot of evidence ids + hashes.

States (all via `core/fsm`):
- Application: `planned -> preparing -> internal_review -> submitted -> validated -> under_review -> decided`;
  side `info_requested` (clock stopped if the type says so) `-> under_review`, `withdrawn`. `decided` is entered only
  by recording a `PermitDecision`.
- Requirement (derived, never stored): `not_started` | `in_progress` | `granted` | `partially_granted` | `refused`
  (with no newer attempt) | `not_applicable` | `blocked` (dependency not met).
- Condition: `open -> evidence_submitted -> discharged`; `open -> discharge_applied -> discharged | rejected -> open`;
  `ongoing` conditions sit in `in_compliance` / `breach`; `not_triggered`, `waived` (authority only, with document),
  `superseded` (permit varied). Overdue = computed flag, not a state.

## 4. Rules (each is a test)
1 Roadmap seeding: confirming a `project_route` assessment proposes requirements from `triggered_by_route` of the
  pinned catalogue; a human accepts each proposal (no auto-apply); `exempt` proposes nothing and says so.
2 Default applicant per requirement comes from mod3 allocations `permits_approval` (and `permit_conditions_change`
  for discharge/variation); without a delivery model the catalogue `default_applicant_role` applies; override allowed
  with rationale.
3 Dependencies: an application cannot move to `submitted` while a `requires` dependency is not met (`granted` or
  `submitted` as typed); cycles in `depends_on` are refused at write (`dependency_cycle`).
4 Clock: forecast decision date = start event (`receipt` / `day_after_receipt` / `validated_at`) + period in its unit
  (working days use the project calendar from `schedule`), + stopped days when `stop_on_rfi`, + agreed or authority
  extensions (authority extension only once and only up to the catalogue max, reason required). Table-driven test per
  shipped clock incl. BImSchG 7 months + 3, DMPO 8/13 weeks, discharge 8 weeks.
5 Unknown clock (no period in data, e.g. US): forecast is `null` with reason `no_statutory_period`, the user may enter
  an expected date marked `estimate`; never a silent default.
6 Schedule link: `needed_by` = linked activity `late_start`, else `early_start`, else `constraint_date`, else fixed date
  (`date_basis` returned). Latest submit date = needed_by - clock - dependency chain - buffer. Forecast > needed_by ->
  `schedule_conflict` flag with days; optional "push to schedule" creates/updates a milestone activity through the
  schedule API, only on explicit user action.
7 Deemed outcome: when the clock passes with no decision and the type has `deemed_outcome`, the module proposes a
  `deemed_granted` / `deemed_discharged` decision; it becomes effective only when a user confirms (and records the
  notice if `deemed_requires_notice`). Never automatic.
8 Decision recording: `granted_with_conditions` requires at least one condition or an explicit "conditions to follow"
  flag that keeps the register incomplete (`conditions_pending`); `partially_granted` requires `scope_note` and creates
  a follow-up requirement for the rest on confirmation; `refused` closes the attempt and offers resubmission (attempt
  n+1) or appeal note.
9 Validity: `valid_until` computed from `validity` and the start notice; no start notice by lapse date -> permit
  `lapsed` warning 90/30/7 days before; extension application (kind `extension_of_validity`) resets it on decision.
10 Early start (`early_start` scope, e.g. BImSchG §8a, WHG §17, vorzeitiger Baubeginn): the permit is `revocable`;
  conditions of kind `obligation` for restoration and security are mandatory fields; the start gate reads it as
  "start at risk", never as the full permit.
11 Partial / Teilbaugenehmigung: enables only the stages in `scope_note` mapped to activities; activities outside the
  scope stay `blocked_by_permit` in the readiness view.
12 Suspensive conditions block: a permit with an open `suspensive` condition whose trigger is `before_start` is not
  effective for start; site start readiness is `not_ready` and names the condition. `obligation` conditions do not
  suspend the permit; when overdue they raise `breach_risk`.
13 Discharge: `self_certified` needs evidence + owner, and a verifier != owner (four-eyes always on for discharge);
  `requires_authority_approval` conditions can only be discharged by a decided `discharge_of_conditions` application
  (one application may discharge several conditions; partial discharge per condition).
14 Variation / amendment: a decided variation supersedes the listed conditions (`superseded`) and copies forward the
  unchanged ones with a link to the original; discharged evidence survives on the new condition when the text is
  unchanged (hash equality), else it reopens.
15 AI extraction (optional, `ai` module present): from the decision notice the module proposes conditions with
  confidence, number, text span, kind and trigger; each needs confirmation; unconfirmed proposals never count in
  readiness (principle 7).
16 Ongoing conditions (noise hours, monitoring): `in_compliance` / `breach`; a breach can be raised from an HSE
  observation or inspection link and is listed in the HSE view; it never auto-closes.
17 Overdue: condition due date passed and not discharged -> owner and PM notified, escalation to area owner (m11 for
  HSE topics, m02 otherwise) after the project's escalation days.
18 Governance: frame documents `dev_permit_roadmap` and `dev_special_permits` (area m02) and `dev_permit_conditions`
  (area m11) are CDE revisions of this module's export made at the gate; roadmap `agreed` mirrors the governance
  binding state; after binding, roadmap changes (new requirement, removed requirement, changed dependency) go through
  a governance `FrameChangeRequest`; application progress and conditions are operational and never need it.
19 Readiness providers (registry from mod3 INTEGRATION 2.1): m02 check = all requirements needed for the next phase
  submitted or granted, no `schedule_conflict` unaccepted; m11 check = register complete (no `conditions_pending`), every
  condition has owner and trigger; construction gate = no open `before_start` suspensive conditions and every
  `before_start` obligation discharged or accepted as gate condition; handover gate = no open `before_occupation`
  conditions and occupancy permit (category `occupancy`) granted where required.
20 Site mobilisation: `site_prep` readiness reads `permits.start_readiness(project)` as a computed item in category
  `permits_consents` (`is_gate`); no site_prep items are created or copied.
21 Closeout: `before_occupation` and `after_completion` conditions plus every permit are listed in the closeout
  package as a generated slot (evidence = discharges); a manual duplicate slot is not created.
22 Commitment matrix (mod2): precondition kind `permit` resolves to a `PermitRequirement` state (`granted` or chosen
  scope), replacing the earlier `review_authority` cycle reference.
23 Requirements: a condition with a measurable limit may create a `Requirement` (originator_role `authority`,
  phase from trigger, `source_ref` = permit reference + condition number) and keeps the soft link; the condition text
  stays here, the constraint lives there; no copy back.
24 Tenant isolation and IDOR: every handler `verify_project_access`; links to activities, CDE revisions, review cycles,
  submissions, inspections of another project -> 404.
25 Everything exportable (PDF + XLSX via `core/register_export`), audit (`log_activity`) on every state change,
  decision and discharge; all labels i18n; all dates timezone-aware for clocks (authority timezone = project timezone).

## 5. API (envelope `{items,total,offset,limit}`, under `/v1/projects/{id}/permits/...`)
roadmap (get, pin catalogue, seed from route `POST .../roadmap/propose`, accept proposals), requirements (CRUD,
dependencies, `GET .../timeline` with forecast, latest submit, conflicts), applications (create, transition, clock
events, link review cycle / submission / CDE, record decision), permits (list, start notice, extension), conditions
(list with filters trigger/topic/owner/state/overdue, create, patch, evidence add/remove, discharge, breach, AI
proposals confirm/reject), readiness (`GET .../readiness?gate=`), export (pdf/xlsx per register). Catalogue admin
`/v1/permits/catalogues` through the shared resolver (list, clone, edit draft, publish, diff).
Permissions on startup: `permits.read`, `permits.edit` (owner of requirement/condition or manager), `permits.manage`
(catalogue pin, roadmap, decisions), `permits.verify` (discharge verification), `permits.catalogue` (admin).
Internal release before submission uses `approval_routes` target kind `permit_application` (optional per project).
Events: `permits.application.submitted`, `permits.decision.recorded`, `permits.permit.state_changed`,
`permits.condition.created|discharged|overdue|breach`, `permits.readiness.changed`.

## 6. Screens (project tab `/projects/:id/permits`, no new top segment)
1 Roadmap: Gantt-style timeline (rows = requirements, bars = preparing / under review / forecast decision, needed-by
  marker from schedule, dependency arrows, conflict badge), filter by category; table toggle (AG Grid).
2 Application drawer: state stepper, clock with stop/extension history, linked review cycle remarks count, documents
  (CDE), decision form (outcome, conditions entry or AI proposals with confidence).
3 Condition register (AG Grid): number, permit, text, kind, trigger, topic, owner, due, state, evidence count;
  saved views "before start", "before occupation", "ongoing / HSE", "overdue", "mine"; bulk assign owner.
4 Readiness card per gate (also embedded in governance gate page and site_prep page).
5 Catalogue screen: permit types per jurisdiction with clocks, sources and review status labels.
Strings in all locales in the same commit.

## 7. Validation rule set `permits`
requirement_has_applicant_and_owner, dependency_acyclic, forecast_before_needed_by, application_has_authority_reference
(after submitted), decision_has_notice_document, conditional_grant_has_conditions, condition_has_trigger_and_owner,
condition_due_not_passed, suspensive_condition_blocks_start, discharge_has_evidence_and_verifier,
permit_not_lapsing (90 days), catalogue_figures_have_source (catalogue), unconfirmed_figure_used (warning).

## 8. Tests first (in this order)
1 Unit, pure: clock calculator (every unit, start events, RFI stops, authority extension once/max, agreement,
  deemed outcome proposal, null period); dependency graph (cycle, blocked); timeline (needed_by fallbacks, latest
  submit, conflict); FSMs (table driven); condition readiness per gate (suspensive vs obligation, triggers); validity
  lapse; variation carry-forward with hash; catalogue loader (every shipped file validates, every figure has URL +
  review status, i18n keys exist, route codes valid against `project_route` ROUTE_OPTIONS).
2 Service with DB (tests/pg): route -> proposals -> accept; application to decision with conditions; partial grant
  -> follow-up requirement; refusal -> attempt 2; discharge self-certified with four-eyes; discharge by application
  covering 3 conditions; variation supersedes; deemed proposal needs confirmation; concurrent decision record -> one
  409.
3 Integrations (tests/pg): governance provider readiness per gate; site_prep computed item; closeout slot; mod2
  precondition; schedule link and push; requirement creation from condition.
4 Security (IDOR lane + `tenant_isolation`): foreign project ids in every soft link -> 404; editor cannot record
  decisions; owner cannot verify own discharge. Handlers added to `tests/unit/test_idor_router_guards.py`, file to
  `ci-postgres.yml`.
5 API contract (envelope, error codes). 6 Migration up/down/up on PG, indexes on models. 7 approval_routes kind in
  model tuple and schema Literal. 8 Frontend vitest (timeline conflict badge, register views, decision form rules,
  i18n). 9 E2E: DE-NW project, route full_permit, roadmap Bauvoranfrage -> Baugenehmigung + BImSchG, decision with
  Bedingung + Auflagen, start gate blocked then cleared by discharge.

## 9. Build order
tests 1 -> kind registration in module 1 registry -> catalogues (neutral, de + de_nw, uk_england, us_ibc) -> models +
migration -> clock, graph, readiness pure functions -> service (tests 2) -> router + permissions (4, 5) -> approval
kind -> readiness provider + site_prep + closeout + mod2 + requirements hooks (3) -> export + frame documents ->
frontend -> i18n -> E2E -> cloud CI -> browser check.

## Decisions (binding for implementation)
a. Applications are a new entity; `review_authority.ReviewCycle` is LINKED, not extended. The cycle models review
   rounds with remarks and only knows approved/rejected; the legal decision (conditions, partial scope, validity,
   deemed outcomes, clocks) belongs to the application. One application may link several cycles (resubmission rounds).
b. Discharge of conditions and variations are applications of the same entity (`kind`), not separate tables: the
   UK practice that a discharge is itself an application with its own clock then needs no special code.
c. Conditions are NOT stored as `requirements` rows: they carry legal kind, trigger, discharge and evidence that the
   requirements model lacks. Measurable technical limits optionally spawn a linked requirement (rule 23).
d. `funding.FundingObligation` stays separate (award obligations, not authority permits); the register shows a
   read-only "other obligations" link, no merge.
e. `hse_advanced.PermitToWork` is untouched and distinct; HSE sees permit conditions through the `hse_relevant`
   filter and the HSE view, nothing is copied into HSE tables.
f. Governance `GateCondition` stays the internal gate instrument; a before-start permit condition may be accepted at
   a gate as a gate condition (linked by id), never duplicated.
g. Clocks are data with units, start events, stops and extensions; no national period appears in code. US ships no
   periods (jurisdiction-specific) rather than invented ones.
h. Deemed approvals and AI-extracted conditions are proposals only and need human confirmation.
i. DE data keyed by Land (`DE-NW`), MBO used only as fallback with `unconfirmed`; paragraph numbers vary per Land.
j. Default four-eyes on condition discharge (owner != verifier), because a discharged condition releases site start
   and occupation; a project may not turn it off for `suspensive` conditions.
k. Internal approval before submission is optional (project setting), default off, to keep small projects simple.
