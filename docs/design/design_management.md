# Module `design_management`: PSP/WBS, design schedule, design organisation, drawing numbering, register, distribution, reports, permit design (spec v1, 2026-10-11)

Sources: `mod7/INTEGRATION.md` (platform, file:line, worktree `wt-gates`), `gates/SPEC_v1.md` (module 1),
`elf/SPEC.md` module 7 (Gestaltungskonzept, Planungsorganisation, Datenstandard; exec: PSP, Planungsvergaben,
Planungsterminplan, Planverteiler, Plannummern, Datenablage, Pläne und Statik, Prüfberichte und Gutachten).
Research URLs in section 12.

## 1. Purpose
The owner's design manager steers design from concept to permit and construction issue in one place:
1 one project breakdown structure every module references; 2 a design schedule of deliverables per design phase
of the project's phase model; 3 who designs what (roles, interfaces, approval points); 4 a data standard: a drawing
numbering scheme held as data, a generator that fills numbers and a validator that refuses wrong ones; 5 a drawing
register with revision status and a distribution matrix that turns a release into a transmittal; 6 design reviews
and expert reports (acoustics, fire, energy, ground, environment, structural proof) with states; 7 the permit
design package steered until submission and through authority review.

It owns no file, no revision, no transmittal, no schedule date and no approval engine: those stay in CDE,
transmittals, schedule, review_authority / authority_submission and approval_routes. Its frame documents in
governance area `m07_design_management` (`dev_wbs`, `dev_design_organisation`, `dev_design_schedule`,
`dev_data_standard`, `dev_permit_design`, `dev_proofs_reports`) are generated records of its own data; approval
at a gate makes them binding, later changes go through governance change control (governance rule 4).

Country-neutral: phases come from the pinned governance phase model (HOAI LPH, RIBA, AIA or neutral); numbering
schemes, report kinds and permit steps are catalogue data with national variants.

## 2. Catalogue data (shipped JSON + pack + tenant versions, one resolver)
Two kinds registered with `register_catalogue_kind` (`project_governance/catalogue_kinds.py:107`), shipped in
`design_management/catalogues/<kind>/*.json`; tenants clone, edit, publish; a project pins `(source, id, version)`.

### 2.1 Kind `drawing_numbering`
- `fields[]` ordered: `code` (project, originator, functional, spatial, form, discipline, number, plus optional
  `phase`, `sheet_size`, `custom_*`), `label_key`, `required`, `pattern` (regex, e.g. `^[A-Z0-9]{2,6}$`),
  `length_min/max`, `code_list` (inline `[{code, label_key}]` or `free`), `pad` (number zero padding),
  `source_field` (where the value comes from: `project.code`, `container.originator_code`, ..., or `wbs.code`).
- `separator` ("-"), `case` (upper), `max_length`, `allowed_chars` (ISO 19650: A-Z 0-9 and hyphen).
- `metadata_fields[]` NOT part of the name: `status` (suitability), `revision`; their code lists default to CDE
  (`cde/suitability.py:23`), the scheme may only narrow them.
- `drawing_forms[]`: which `form` codes count as drawings for the register (e.g. `DR`, `M2`, `M3`).
- `number_scope`: which fields together make the counter key (default: originator+functional+spatial+form+discipline).
- Shipped v1: `iso19650_generic` (Project-Originator-Functional-Spatial-Form-Discipline-Number, fields free with
  regex only), `iso19650_uk_na` (UK National Annex code lists for form, discipline, status; `review_status:
  unconfirmed` until the code lists are checked against the BSI annex text), `us_ncs_sheet` (discipline designator
  1-2 letters, sheet type digit 0-9, sequence 2 digits, e.g. `A-101`; NCS v6), `de_planschluessel` (Projekt-
  Planart-Leistungsphase-Gewerk-Geschoss-Laufnummer; company practice, no statute; `review_status: unconfirmed`),
  `simple_sequential` (Discipline-Number for small projects).

### 2.2 Kind `design_reports`
- `report_kinds[]`: `code`, `name_key`, `discipline`, `typical_phase` (spine key), `independent_check`
  (none | optional | required_by_rule), `country_rules[]` ({country, region, condition_key, text_key,
  source_url, review_status}).
- v1 kinds: `structural_design`, `structural_proof_check` (Prüfstatik / independent structural check),
  `fire_safety_concept`, `fire_proof_check`, `acoustics`, `thermal_energy` (GEG / Part L / energy code),
  `geotechnical`, `environmental`, `sound_insulation`, `vibration`, `daylight`, `traffic`, `drainage`,
  `survey`, `contamination`, `uxo`.
- DE Prüfstatik is a Land rule (Bauordnung + Prüfverordnung, varies by building class and Sonderbau): shipped as
  `country_rules` per Land with `review_status: unconfirmed` until each Land text is read; never enforced, shown as
  a hint "independent check likely required".
- `permit_steps[]` per jurisdiction profile: ordered steps (pre-application, application, completeness check,
  remarks, approval, partial approval, start notice) each with `spine_key`, mapped to `review_authority` cycle
  states. v1: `neutral`, `de_bauantrag`, `uk_planning_building_regs`, `us_building_permit` (all unconfirmed
  where they name statutory deadlines).

## 3. Entities (project-scoped, FK CASCADE on project, tenant via project access)
Existing tables EXTENDED: `oe_projects_wbs` (service rules only, no DDL in v1, see Decision 2).

- `DesignSetup` (one per project, NEW): pinned numbering scheme (source, id, version), pinned reports catalogue,
  `four_eyes_release` bool, `default_distribution_purpose`, `lead_designer_role_id`.
- WBS = `ProjectWBS` (EXISTING): nodes gain `metadata_.kind` (`location | system | package | phase | cost`) and
  `metadata_.discipline`; rules 1-4 enforce unique codes and a closed tree.
- `DesignRole` (NEW): `code`, `title`, `party_kind` (owner | lead_designer | discipline_designer | specialist |
  checker | authority | contractor_designer), `discipline_code` (scheme discipline list), `contact_id` /
  `user_id`, `originator_code` (scheme originator), soft `contract_package_id` (delivery_model ContractPackage,
  the design award), `responsible_wbs_ids[]`, `state`: `planned -> appointed -> active -> released`.
- `DesignApprovalPoint` (NEW): where design needs a decision (owner sign-off of a phase, user sign-off, cost
  check): `code`, `title`, `phase_code` (from pinned phase model), `kind` (owner_approval | user_signoff |
  cost_check | authority | internal_review), soft `governance_gate_id`, approver role, state `open ->
  in_review -> approved | rejected` via approval_routes `target_kind="design_approval_point"`.
- `DesignDeliverable` (NEW, the design schedule line): `phase_code`, `role_id`, `discipline_code`,
  `form_code`, `title`, `wbs_node_id`, `planned_count` (drawings), soft `schedule_activity_id` (dates owned by
  schedule), `required_for` (approval point ids / permit package), state `not_started -> in_progress ->
  issued_for_review -> accepted` computed from linked drawings' CDE states, never set by hand except `waived`
  (rationale).
- `Drawing` (NEW 1:1 extension of a CDE container, `oe_design_drawing`, unique `container_id`): `title`,
  `scale`, `sheet_size`, `phase_code`, `deliverable_id`, `wbs_node_id`, `role_id`, `planned_first_issue`,
  `forecast_issue` (soft schedule link optional), `superseded_by_container_id`. Number = container code,
  revision/status = CDE revision/suitability (read, never copied).
- `NumberCounter` (NEW): `(project, scope_key) -> next_value`, row-locked on allocate; reserved numbers are
  containers in state wip with no revision (`reserved`).
- `DistributionRule` (NEW, the Planverteiler matrix row): recipient (`file_distribution` list id OR design role
  id), filter (`discipline_codes[]`, `form_codes[]`, `phase_codes[]`, `wbs_node_ids[]`, min suitability),
  `purpose` (transmittals purpose code), `format` (pdf | native | both), `copies_paper` int, `ack_required`.
- `Release` (NEW): a set of container revisions released together (`title`, `purpose`, `revision_ids[]`
  snapshot), state `draft -> ready -> issued` (+ `cancelled`); `issued` creates one `transmittals` row per
  recipient via service call and stores `transmittal_ids[]`.
- `DesignReview` (NEW, internal phase review, e.g. end of LPH 3): `phase_code`, `scope` (deliverable ids),
  reviewers (role ids), `state: planned -> open -> comments_closed -> concluded`, outcome `accepted |
  accepted_with_comments | rework`, comments as `DesignReviewComment` (container revision id, text,
  `severity`, state `open -> answered -> closed | rejected`, `answered_by_role`).
- `DesignReport` (NEW, expert reports and proofs): `kind_code` (catalogue), `title`, `author_role_id`,
  `container_id` (the report is a CDE container), `checker_role_id` (independent checker), soft
  `review_cycle_id` (review_authority) for external checks, `required` + `required_reason` (catalogue rule or
  manual), state `required -> commissioned -> in_progress -> submitted -> under_check -> remarks ->
  accepted | rejected` (+ `not_required` with rationale), `conditions_text` (Auflagen), soft
  `governance_condition_ids[]`.
- `PermitPackage` (NEW): `profile_code` (permit_steps), `title`, contents: drawing container ids + report ids
  (`PermitItem` rows: kind drawing | report | form, `required`, `included_revision_id` pinned on submit),
  soft `authority_submission_id`, soft `review_cycle_id`, `target_submission_date` (schedule activity link),
  state `assembling -> ready -> submitted -> under_review -> remarks -> approved | partially_approved |
  refused | withdrawn`; states from `submitted` on are READ from the linked review_authority cycle.

## 4. Rules (each is a test)
1 WBS codes unique per project; a duplicate code is rejected (`wbs_code_duplicate`), existing duplicates are listed.
2 WBS child code starts with its parent code plus separator when the project enables `hierarchical_codes`
  (default on); renumbering a node renumbers its subtree in one transaction.
3 A WBS node referenced anywhere (resolver over the 10 known columns) cannot be deleted; it can be closed
  (`metadata_.closed`), closed nodes refuse new references.
4 Resolver accepts an id or a code; an unresolved `wbs_id`/`wbs_code` in boq, finance, procurement, fieldreports,
  inspections, cvr, field_time, schedule is a warning `wbs_reference_unresolved` with module and row.
5 Generator: with a pinned scheme, `next_number(fields)` fills each field from its `source_field`, pads, joins,
  and allocates the counter under row lock; two concurrent allocations never return the same number.
6 Validator: a container code (generated or typed) must match the scheme: order, separator, per-field regex and
  code list, length, allowed characters, case; error lists the failing field (`numbering_field_invalid`).
7 The container's ISO parts and the code agree: parsing the code yields exactly the stored parts.
8 A number is unique in the project and never reused after the container is archived or deleted
  (counter only increases).
9 Changing the pinned scheme: existing numbers are kept and flagged `legacy_scheme`; optional renumber with a
  mapping preview, applied only after confirmation, old numbers stored as aliases searchable.
10 Revision and status metadata stay out of the number; a typed number containing a suitability or revision
  segment is rejected.
11 Title block check: when sheet fields are read (`documents/sheet_fields.py`), sheet number != container code
  raises `title_block_number_mismatch`.
12 Distribution: issuing a Release creates exactly one transmittal per matching recipient, items = the pinned
  revisions; a revision whose suitability is below a rule's minimum is excluded with a reason.
13 A Release cannot include a wip (S0) revision; `for_construction` purpose needs published (A-codes).
14 Re-issuing the same revision to the same recipient is flagged `duplicate_issue` (allowed with reason).
15 A deliverable is `accepted` only when all its drawings reached the target suitability for the phase and
  `planned_count` is met or reduced with rationale.
16 A design phase gate (governance) is not ready for area m07 while a required deliverable of that phase, a
  required report, or an open review comment of severity `major` exists (readiness evidence).
17 A report marked `independent_check` required cannot become `accepted` without a checker role different from
  the author's party (four-eyes by party) and, when external, a linked review cycle in state approved.
18 A report `not_required` needs rationale; a catalogue hint overridden needs rationale.
19 Permit package `ready` needs every required item present with a shared/published revision; `submit` pins the
  revision ids; later revisions of those containers mark the package `superseded_content` warning.
20 Permit conditions (Auflagen) recorded on approval become governance conditions or tasks with owner and due date
  (human confirms each, no auto-create).
21 Design role with `discipline_designer` must have an originator code unique in the project; a drawing's
  originator must belong to an active role (`originator_unknown`).
22 Approval point approval only by an approver entitled by approval_routes; four-eyes when enabled.
23 Frame documents: generating `dev_data_standard` etc. writes a CDE revision; once binding, editing scheme,
  roles or matrix creates a draft and requires a governance change request (governance rule 4).
24 Tenant isolation and IDOR: every id from another project is 404; counters and catalogues tenant-scoped.
25 All labels i18n; register, matrix, report list and permit package export PDF + XLSX via `core/register_export`.

## 5. API (`/v1/projects/{id}/design/...`, envelope `{items,total,offset,limit}`)
setup (get, pin scheme / reports catalogue with mapping); wbs (tree, create, patch, move, close, references,
unresolved report); roles (CRUD); approval-points (CRUD, submit, decision via route); deliverables (CRUD, status);
numbering (preview, allocate, validate, bulk validate, renumber preview/apply); drawings (register list with
filters, create = container + extension, patch, supersede); distribution-rules (CRUD, preview recipients for a
release); releases (CRUD, issue); reviews (CRUD, comments, conclude); reports (CRUD, link review cycle, transition);
permits (CRUD, items, ready check, submit link, sync from review cycle); readiness (read-only evidence for
governance); export (register, matrix, reports, permit; pdf/xlsx); catalogue (resolver lists).
Permissions on startup: `design.read`, `design.edit` (manager or m07 area owner or lead designer role),
`design.release` (issue releases), `design.approve` (route-entitled only). `verify_project_access` everywhere.

## 6. Screens (project tab `/projects/:id/design`, sub-tabs, no new top segment)
1 Overview: phase strip from the pinned model, per phase deliverables progress, reports and permit status, blockers.
2 PSP: tree editor (drag, renumber preview, close), reference counts per module, unresolved references list.
3 Organisation: roles table, discipline x role matrix, approval points per phase, interfaces (from
  interface_management, read).
4 Design schedule: deliverables grouped by phase and discipline, dates from schedule, Gantt reuse of schedule view.
5 Data standard: scheme editor (fields, code lists) with live example and validator test box; "new drawing"
  dialog with generated number preview.
6 Drawing register: grid (number, title, revision, status, phase, discipline, last issue, recipients), bulk validate,
  title block mismatch badges.
7 Distribution: matrix (recipients x discipline/form), releases list, issue dialog with per recipient preview.
8 Reviews and reports: kanban by state, independent-check badge, country hint with source link.
9 Permit: package checklist, pinned revisions, authority cycle timeline (from review_authority).
Strings in all locales in the same commit.

## 7. Validation rule set `design_management`
wbs_code_unique, wbs_reference_resolves, drawing_number_matches_scheme, drawing_number_parts_consistent,
drawing_originator_known, title_block_matches_number, release_revisions_suitable, deliverable_complete_for_phase,
report_independent_check, not_required_has_rationale, permit_package_complete, permit_content_current,
approval_by_entitled_user. Registered via `validators.py` + `on_startup` (governance pattern
`project_governance/validators.py:236`). Readiness evidence for governance area m07 via the provider hook
(Decision 9).

## 8. Tests first (order)
1 Unit pure: FSMs (Release, DesignReview, comment, DesignReport, PermitPackage, ApprovalPoint; table driven);
numbering generator + validator over every shipped scheme (valid and invalid cases per field, round-trip parse);
catalogue loaders (every scheme validates, every code list unique, every report kind's spine key valid, every
country rule has source_url or unconfirmed); WBS tree rules (unique, hierarchical prefix, renumber subtree).
2 Service + PG: concurrent allocation (20 parallel, no duplicates); release issue creates transmittals; deliverable
status from CDE states; report with external cycle; permit pin and supersede; scheme change with renumber
mapping; resolver over all 10 wbs columns; frame document binding then change request.
3 Security (tests/pg, IDOR list in ci-postgres.yml, tenant_isolation marker): other tenant cannot read register,
allocate numbers, issue releases; editor cannot approve; cross-project container id in a release = 404.
4 API contract: envelope, 404 vs 403, error codes. 5 Migration up/down/up on PG, new tables only.
6 Frontend vitest: scheme editor live example, register badges, matrix preview, role gating, i18n keys.
7 E2E: pin ISO generic scheme, create WBS, add roles, generate 3 drawing numbers, release to a list, see transmittals.

## 9. Build order
tests 1 -> catalogue kinds + shipped JSON (generic, UK NA, NCS, DE, simple; report kinds) -> models + migration
-> numbering service + CDE hook -> WBS rules + resolver (projects) -> register + deliverables -> distribution +
releases (transmittals) -> reviews + reports (review_authority link) -> permits (authority_submission link) ->
approval routes kind + governance evidence provider + frame document generators -> router + permissions ->
frontend -> i18n -> E2E -> cloud CI -> browser check.

## 10. Open questions
None left open; all decided below.

## 11. Typical scheme examples (shipped, illustrative)
- ISO 19650 generic: `PRJ1-ABC-ZZ-01-DR-A-0001` (status S2 and revision P01 as metadata, not in the name).
- US NCS: `A-101` (A architectural, 1 plans, 01 sequence), `S-501` (details).
- DE company Planschlüssel: `P123-AR-LPH5-GR-EG-0012` (company practice, code lists editable tenant data).
- Simple: `A-012`.

## 12. Sources
- ISO 19650 field structure and UK annex revision (Functional/Spatial/Form/Discipline, no fixed field lengths,
  status and revision as metadata): https://www.symetri.co.uk/insights/blog/iso-19650-file-naming-update ,
  https://viewpoint.com/blog/understanding-bim-in-the-uk-part-2-changes-in-the-uk-naming-convention-and-the-the-uk-annex ,
  CDBB annex guidance (fetched, PDF not text-extractable; code lists therefore unconfirmed):
  https://www.cdbb.cam.ac.uk/files/national_annex_guidance.pdf
- Irish national annex variant: https://www.cita.ie/wp-content/uploads/2021/03/CWO_CitAPresentation_IrishNA19650_2021.03.18.pdf
- US NCS sheet identification (discipline, sheet type digit, sequence): https://www.archtoolbox.com/construction-document-sheet-numbers/ ,
  https://dallascityhall.com:443/departments/sustainabledevelopment/buildinginspection/DCH%20documents/pdf/BI_EPRS%20Filename%20Instructions.pdf
  (primary NCS text not retrieved: unconfirmed).
- DE independent structural check per Land: Bavaria Art. 62a BayBO guidance
  https://stmb.bayern.de/assets/stmi/buw/baurechtundtechnik/24_bautechnischenachweise_20241125.pdf ;
  Schleswig-Holstein PPVO https://umwelt-online.de/recht/bau/laender/sh/ppvo21.htm ; Lower Saxony
  https://umwelt-online.de/recht/bau/laender/nds/bpr.htm (all unconfirmed until read per Land).
- HOAI phases come from module 1 catalogue `hoai_lph.json` (source https://www.gesetze-im-internet.de/hoai_2013/ ,
  carried there).
- Existing CDE suitability set: platform code `cde/suitability.py:23`.

## Decisions (lead of this spec, 2026-10-11; binding for implementation)
1. One canonical PSP = existing `ProjectWBS` in `projects`; no new tree. Reason: every module already depends on
   projects, the table has writers, copy and export; a second tree would be a second source of truth.
2. No DDL on `oe_projects_wbs` in v1 (unique code enforced in the service and by a validation rule). Reason:
   running installs may already hold duplicate codes; `create_all` skips existing tables and a unique index would
   fail on dirty data. A later revision adds the index after a cleanup report shows zero duplicates.
3. Bare `wbs_id` columns are not converted to FKs; one resolver (id or code) plus a rule. Reason: ten columns, four
   types, free text in finance; conversion would break writers. The resolver makes them usable today.
4. A drawing IS a CDE container; module 7 adds only a 1:1 extension table. Reason: number, revisions, states and
   signatures already live in CDE; `Document.drawing_number` and `Sheet.sheet_number` become mirrors checked by rules.
5. Numbering scheme is a catalogue kind, not a free-text field; `naming_convention` stays as a rendered display.
   Reason: a scheme as data can be validated, generated, shipped per country and edited per company.
6. Status and revision never enter the number. Reason: ISO 19650 practice and the existing CDE metadata; avoids
   renaming on every issue.
7. Counter allocation in the DB under row lock, numbers never reused. Reason: two designers creating drawings at the
   same time is normal; a gap is harmless, a duplicate is not.
8. Distribution reuses `file_distribution` lists and the CDE-linked `transmittals`; module 7 adds the matrix and
   releases only. `file_transmittals` is not used. Reason: transmittals items already reference CDE revisions.
9. Governance readiness: module 7 registers an evidence provider `design_management.readiness(project, gate)`
   through a small registry that module 1 must add (same need as mod3; governance must not import modules).
   Until it exists, m07 readiness stays manual and the rule set is the evidence.
10. External checks (authority, Prüfingenieur, third party) use `review_authority` cycles linked from our side;
    permit filing links `authority_submission`. No new remark FSM. Reason: those FSMs exist and are tested.
11. Internal design reviews are new (`DesignReview`) because nothing reviews a phase deliverable set today; comments
    point at CDE revisions, not files.
12. Design phases are the codes of the project's pinned governance phase model; no design-phase vocabulary of our
    own. Deliverable dates are schedule activities (soft link).
13. National statutory facts (Prüfstatik duty per Land, permit deadlines, UK NA code lists, NCS) ship as data with
    `review_status: unconfirmed` and are shown as hints, never enforced, until a source is read.
14. Approval points use approval_routes `target_kind="design_approval_point"` (edit `approval_routes/models.py:50`
    and `schemas.py:25`); releases with `four_eyes_release` use kind `design_release`.
15. Permit conditions become governance conditions or tasks only after a human confirms each one (AI/automatic
    extraction may suggest, never apply).
16. Module name in UI "Design management" / de "Planungsmanagement"; route `/projects/:id/design`.
