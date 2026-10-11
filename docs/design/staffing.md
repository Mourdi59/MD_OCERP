# Module `staffing`: staffing plan and project personnel administration (spec v1, 2026-10-11)

Sources: `mod10/INTEGRATION.md` (platform, file:line, worktree `wt-gates`), `gates/SPEC_v1.md` (module 1),
`elf/SPEC.md` module 5 (Personalmanagement), `mod3/SPEC.md` (structure). Research URLs in section 12.

## 1. Purpose
One project-level answer to "which roles does this project need, in which phase, from when, at what FTE, who fills
them, and is every person on it legally and practically able to work here today".
Two halves, one module:
- Staffing plan (development verb FESTLEGEN): positions by role and phase (development, execution, operation),
  owner organisation (project lead, project controls, site supervision), external consultants, operator
  organisation build-up up to commissioning, knowledge handover (who from development stays into execution and
  operation). The approved plan IS the content of the governance frame document `m05_personnel_frame` of area
  `m05_personnel` (`elf_module_framework.json`, document type at :1375, required at gate
  `development_to_execution`). Approval and binding go through governance, no own approval engine.
- Personnel administration (execution verb STEUERN): for each person on the project, the compliance and logistics
  record: employment basis, work permit, passport and visa, qualifications, occupational health check, induction,
  accommodation, travel, leave; expiry tracking with reminders.

Design rule: this module adds the PLAN and the PERSON-ON-PROJECT view. It does not create a second person table,
a second expiry engine or a second accommodation register. A person is a `teams.RosterMember` (site record, grants
no access); validity documents are `credentials.Credential` rows; beds are `accommodation.Booking` rows. The module
owns positions, fills, the document checklist per role, travel and leave, and the privacy envelope around them.

Country-neutral: role families, document kinds and retention rules are catalogue data; national facts carry a
source URL and `review_status`.

## 2. Catalogue data (kind `staffing_model`, one resolver)
Register kind `staffing_model` through `register_catalogue_kind` (`project_governance/catalogue_kinds.py:109`).
Shipped files in `staffing/catalogues/`: `neutral` (default), `de`, `uk`, `us` (retention and document facts only;
role catalogue is shared). Tenant clones, edits, publishes; project pins `(source, id, version)`.
Body:
- `organisations[]`: `owner_project_lead`, `owner_project_controls`, `owner_site_supervision`, `owner_development`,
  `external_consultant`, `operator`, `contractor_key_staff` (only roles the owner contractually approves).
- `roles[]`: `code`, `name_key`, `organisation`, `phases[]` (development | execution | operation),
  `default_fte` (Decimal), `key_role` (bool: must be filled before the gate named in `required_by_gate`),
  `required_document_kinds[]`, `handover_role` (bool), optional `labor_rate_trade` (LINK to labor_rates).
  v1 list: project_director, project_manager, design_manager, cost_manager, scheduler, contract_manager,
  document_controller, hse_manager, quality_manager, site_manager, site_supervisor_civil / _mep, commissioning_manager,
  operator_plant_manager, operator_shift_lead, operator_technician, consultant_legal / _permit / _geotech / _cost.
- `document_kinds[]`: `code` (employment_contract, work_permit, residence_permit, passport, visa,
  qualification, professional_licence, occupational_health_certificate, site_induction, safety_training,
  right_to_work_check, a1_posting_certificate), `credential_type` (maps to `credentials` type registry,
  `credentials/intl.py:83`), `special_category` (bool, GDPR Art. 9), `default_notify_days_before`,
  `store_number` (bool: may a document number be stored at all), `retention_rule` code.
- `retention_rules[]`: `code`, `trigger` (end_of_assignment | end_of_employment | document_expiry),
  `period_months`, `action` (delete | anonymise), `basis_text_key`, `source_url`, `review_status`, `country`.
- `leave_types[]`: annual, public_holiday, rotation_off, sick (no reason stored), training, unpaid, other.

## 3. Entities (project-scoped, FK CASCADE on project, tenant via project access; new tables only)
- `StaffingPlan` (one per project): pinned catalogue, `state` `draft -> in_review -> approved -> binding`
  (+ `revising`). `binding` mirrors the governance frame document; soft `governance_document_id`.
- `StaffingPosition`: `role_code` (catalogue or tenant custom with label), `organisation`, `phase`,
  `title` override, `fte` (Decimal 0.1..1.0 per head) and `headcount` (int), `entry_date`, `exit_date`,
  `required_by_gate` (gate code, optional), `key_role`, `status` `open -> recruiting -> filled`
  (+ `on_hold`, `cancelled`), `recruiting_channel` (internal | agency | direct | framework | consultant_contract),
  soft `resource_request_id` (LINK `resources.ResourceRequest`, models.py:313) when recruiting via the
  resource pool, soft `contract_id` / `rfq_id` for consultant positions (LINK module 8 package), `notes`.
- `PositionFill`: (position, `roster_member_id` soft ref to `teams.RosterMember`, `fte_share`, `from_date`,
  `to_date`, `state` `proposed -> confirmed -> ended`). Several fills = job share or succession. Position
  `filled` is DERIVED: sum of confirmed `fte_share` on the entry date >= position fte*headcount.
- `HandoverLink`: (from_fill, to_position, `overlap_days`, `scope` text, `state` planned | done). Knowledge handover.
- `PersonnelFile` (one per roster member per project, the privacy envelope): `roster_member_id`,
  `employer_organisation`, `employment_basis` (employee | posted_worker | contractor_staff | consultant | agency),
  `nationality_required` (bool, only true if a work permit check applies; nationality itself NOT stored),
  `lawful_basis` (contract | legal_obligation | legitimate_interest), `retention_due_at` (computed),
  `state` `active -> ended -> retention_hold -> anonymised`.
- `DocumentRequirement` (computed on read from role + catalogue, not stored) vs `PersonnelDocument`:
  (`personnel_file_id`, `document_kind`, soft `credential_id` LINK -> `credentials.Credential` which holds
  `valid_until`, status, `notify_days_before`), `number_last4` (only when `store_number`), `verified_by/at`,
  `waived` + rationale. Files live in the CDE / documents module via `credentials.document_url` with
  `EntityVisibility` restriction; no file copies.
- `TravelRecord`: personnel file, kind (mobilisation | rotation | business | demobilisation), from/to place
  (city level), depart/return dates, `booking_ref`, `cost` (Decimal, currency), `state` planned | booked | done | cancelled.
- `LeaveRecord`: personnel file, `leave_type`, from/to, `state` requested | approved | taken | cancelled,
  `approved_by`; no medical reason field ever.
- Accommodation: NO table. `PersonnelFile` reads `accommodation.Booking` rows (`accommodation/models.py:165`)
  linked by a new nullable `roster_member_id` column on `Booking` (EXTEND), shown on the file.

## 4. Rules (each is a test)
1 Position FTE in (0, 1] per head, headcount >= 1; `exit_date` >= `entry_date`; Decimal only.
2 `filled` is computed from confirmed fills; setting it by hand is rejected (`status_is_derived`).
3 A fill needs a roster member on the same project (cross-project roster id -> 404).
4 Sum of a person's confirmed `fte_share` across all positions of the project on any day <= 1.0
  (`person_overallocated`, error). Across projects: warning only (reads `resources.Assignment.allocation_percent`).
5 Key role with `required_by_gate = G` not filled (or filled from a date after the gate planned date) -> readiness
  evidence `not_ready` for area `m05_personnel` at G.
6 Plan `in_review -> approved` needs every development and execution key role to exist as a position, every
  operation key role to have an entry date before the commissioning gate/milestone, and every handover role to have
  a `HandoverLink` with overlap_days > 0 (`handover_missing`).
7 After the governance frame document is binding, edits to approved positions create a revision; the binding plan
  stays in force until a governance `FrameChangeRequest` is approved. This module never edits a binding snapshot.
8 Document requirements per person = union of `required_document_kinds` of the roles filled, plus country kinds
  where `employment_basis` triggers them (posted_worker -> a1_posting_certificate; `nationality_required` ->
  work_permit). Missing or expired required document on the confirmed fill's `from_date` -> `not_cleared_to_work`.
9 Expiry: status is the credential's status (`credentials/service.py:75`), never recomputed here. The new daily
  sweep (section INTEGRATION 3) calls `refresh_statuses` so expiry alerts fire without a write.
10 Reminders go to: the person's line manager in the plan (position owner), the m05 area owner, and the person
  if they are a platform user. Never to all project members. Notification body carries kind and date, never the
  document number or health detail.
11 Health check stores ONLY: kind occupational_health_certificate, date done, next due, `fit_for_role` yes/with
  restrictions/no. No diagnosis, no free-text medical field exists in the schema (test asserts columns).
12 Document numbers: only last 4 characters if `store_number`; full numbers are rejected by the API.
13 Access: list and plan endpoints (`staffing.read`) return names, roles, FTE, dates, cleared-to-work flag only.
  `PersonnelFile` detail, documents, travel, leave need `staffing.personnel.read` (MANAGER) AND either m05 area
  owner, the position owner of a fill of that person, or the person themself. Every read of a file writes an
  access audit row (`log_activity`, action `personnel_file.read`).
14 Retention: on `ended`, `retention_due_at` = max over the file's documents of their retention rule end. A daily
  job moves due files to `anonymised`: roster link cut, travel/leave kept as counts by month, documents deleted
  via credentials delete, `retention_hold` (legal hold, rationale required) blocks it.
15 Erasure request (Art. 17) by an admin with rationale: anonymises immediately unless a retention rule with
  `trigger=legal obligation` is still running; then refuses with `retention_obligation_active` and the end date.
16 Leave overlapping the person's own travel `mobilisation` or a key-role gate date warns (`leave_conflicts_gate`).
17 Travel with return after the fill `to_date` warns; demobilisation missing on `ended` warns.
18 Accommodation: confirmed fill on a remote site (project flag `requires_accommodation`) without a Booking
  covering the from_date warns (`no_accommodation`).
19 Planned vs actual: FTE-days planned per position vs hours from `field_time` lines of the linked resource
  (read only) shown as a variance; never written back.
20 Export PDF + XLSX via `core/register_export`: staffing plan (no personal data beyond names), organisation chart,
  compliance matrix (role x document kind, status only). Personnel files are not exportable in bulk; the
  person's own file is exportable to them (Art. 15/20).
21 Catalogue pin change needs a role-code mapping; unmapped positions become `custom`.

## 5. API (`/api/v1/staffing/projects/{project_id}/...`, envelope `{items,total,offset,limit}`)
plan (get, set catalogue pin with mapping, submit), positions (CRUD, bulk from catalogue phase), fills (create,
confirm, end), handovers (CRUD), org-chart (read), compliance (matrix, statuses only), personnel-files (list
restricted, get, create from roster member, end, hold, erase), documents (list, link credential, verify, waive),
travel (CRUD), leave (CRUD, approve), readiness (evidence for governance), export, catalogue. Permissions:
`staffing.read` (viewer), `staffing.edit` (editor; plan, positions, fills), `staffing.personnel.read` /
`staffing.personnel.edit` (manager + rule 13), `staffing.personnel.erase` (admin). `verify_project_access`
(`dependencies.py:856`) on every handler; foreign ids 404.

## 6. Screens (project tab `/projects/:id/staffing`)
1 Staffing plan: timeline (rows = positions grouped by organisation, bars from entry to exit coloured by status,
  phase bands, gate markers); FTE histogram by phase; side panel to create positions from catalogue.
2 Organisation chart per phase (owner org, consultants, operator), vacancies visible.
3 Compliance matrix: people x document kinds, cell = valid / expiring (days) / expired / missing / waived;
  "cleared to work" column. Opens the personnel file only for entitled users.
4 Personnel file: header (role, fills, dates), documents with expiry, health certificate (date + fit flag only),
  accommodation (from accommodation module), travel, leave, access log, retention status.
5 Upcoming: expiring in 30/60/90 days, mobilisations next 14 days, leave calendar.
All strings i18n, all locales same commit; privacy notice text keys per screen 4.

## 7. Validation rule set `staffing`
position_fte_valid, position_dates_valid, key_roles_present, key_roles_filled_before_gate, person_not_overallocated,
handover_roles_linked, required_documents_present, documents_not_expired_on_start, health_record_minimal (no
extra fields in metadata), document_number_masked, retention_rule_assigned, accommodation_for_remote_site.
Registered via `validators.py` + `on_startup`. Readiness provider for `m05_personnel` at
`development_to_execution` through the governance readiness-provider registry (EXTEND, mod3 INTEGRATION 2.1):
plan approved, rule 5 clean, zero error violations.

## 8. Tests first
1 Unit pure: FSMs (plan, position, fill, file); derived filled status; overallocation by day with Decimal;
  requirement union (rule 8); retention date calculation; catalogue loader (every role's document kinds exist,
  every `credential_type` in credentials registry, every retention rule has source_url or `unconfirmed`).
2 Service + PG: fill and derive; binding plan + change request; expiry sweep fires `credentials.expiry.alert` with
  no write; reminder recipients exactly rule 10; anonymisation job; legal hold blocks it; erasure refusal.
3 Privacy: schema test that no medical/diagnosis/nationality/full number column exists; API rejects full passport
  number; list endpoint payload contains no document fields; notification body has no number; access audit row
  written per file read.
4 Security (tenant_isolation marker + ci-postgres IDOR list + `test_idor_router_guards.py`): other tenant 404;
  project editor without `staffing.personnel.read` 403 on file; manager who is not area/position owner 403;
  person reads own file 200; cross-project roster id in fill 404.
5 API contract, envelope, error codes. 6 Migration up/down/up (new tables + `Booking.roster_member_id`).
7 Frontend vitest: timeline, matrix states, gating of file link, masked number input. 8 E2E: build plan from
  catalogue, fill 3 positions, link work permit expiring in 20 days, see reminder, approve via gate.

## 9. Build order
tests 1 -> catalogue kind + JSON (neutral, then de/uk/us facts) -> models + migration -> service + FSMs ->
router + permissions -> integrations (credentials types + sweep job in `notification_worker.start_scheduler`,
accommodation column, governance readiness provider, resources request link, field_time read, audit) ->
frontend -> i18n -> E2E -> cloud CI -> browser check.

## 10. Data protection design constraints (cited)
- Minimisation and purpose (GDPR Art. 5(1)(b),(c)): no nationality, birth date, address, religion, family data;
  number last 4 only. Storage limitation Art. 5(1)(e): retention rules + anonymisation job. Integrity Art. 5(1)(f):
  role restriction + access audit. https://gdpr-info.eu/art-5-gdpr/
- Health is special-category (Art. 9(1)); employment/occupational medicine bases Art. 9(2)(b),(h).
  https://gdpr-info.eu/art-9-gdpr/ . DE: employer gets only a certificate "dass, wann und aus welchem Anlass"
  (ArbMedVV §6(3) Nr. 3), findings stay with the physician: https://www.gesetze-im-internet.de/arbmedvv/__6.html
  -> rule 11 shape is mandated, not a preference.
- DE employee data processing basis BDSG §26: https://www.gesetze-im-internet.de/bdsg_2018/__26.html
- Privacy by design / default (Art. 25), erasure (Art. 17), access/portability (Art. 15, 20), records (Art. 30):
  https://gdpr-info.eu/ (articles of the same name; principle-level, not fetched individually).
- UK: right to work check copy kept not less than 2 years after employment ends (Immigration (Restrictions on
  Employment) Order 2016 reg. 5A): https://legislation.gov.uk/uksi/2016/1058/regulation/5A/data.xht
  (`review_status: unconfirmed` until the current text is checked). ICO employment guidance:
  https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/employment/
- US: Form I-9 kept 3 years after hire or 1 year after termination, whichever later (8 CFR 274a.2; secondary:
  https://shrm.org/topics-tools/tools/how-to-guides/how-to-retain-file-9-forms) -> `unconfirmed` (eCFR not fetched).

## 11. Not in scope v1
Payroll, wages, performance reviews, recruiting pipeline beyond a status and channel (ATS category software owns
it), shift rostering (field_time), visa application workflows.

## Decisions (binding for implementation)
1. No new person table: the person is `teams.RosterMember`. Reason: it already carries starts_on, allocation,
   company and grants no access; a second table would split the truth.
2. Expiry lives only in `credentials`. Reason: it has derived status, notify_days and alerts; we add types and the
   missing scheduled sweep (benefits every module) instead of a parallel engine. `resources.Certification`
   (string dates) is not used.
3. `StaffingPosition` is new, not `resources.ResourceRequest`. Reason: a position is a planning object with phase,
   organisation, FTE and gate; a request is a resource-pool booking. A recruiting position may create a request
   (soft link) when the pool is used.
4. Accommodation is read from the accommodation module with one new nullable `Booking.roster_member_id`. Reason:
   bookings exist with charges; only the person link is missing.
5. Health data reduced to date + fit flag; no diagnosis field at all. Reason: Art. 9 and ArbMedVV §6 make the
   certificate the maximum an employer receives; a field that must stay empty is a leak waiting to happen.
6. Nationality is never stored; only "work permit check applies". Reason: minimisation; the rule needs the
   consequence, not the attribute.
7. Two permission tiers plus relationship check, no new global role. Reason: `Role` is global (`core/permissions.py:33`);
   an HR role would grant every project. Relationship (area owner, position owner, self) narrows it.
8. Full document numbers are not stored; scans live in the document module with `EntityVisibility`.
   Reason: last 4 digits suffice for matching; Fernet helper is keyed to the JWT secret and unsafe for long-lived PII.
9. Retention is catalogue data with source and review status; default neutral rule = delete 24 months after
   assignment end. Reason: national periods differ (UK 2 years, US I-9 rule); unconfirmed rules still run but are
   flagged.
10. The plan is the m05 frame document and approval goes through governance only. Reason: one approval path, as
    decided for module 2.
11. Sick leave stores type and dates only. Reason: Art. 9; the reason is not needed for staffing.
12. Operation phase is a position phase attribute, not a new governance phase. Reason: the elf catalogue has
    development/execution only; operator build-up is planned in those phases and keyed to commissioning.
