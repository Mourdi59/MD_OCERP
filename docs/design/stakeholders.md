# Module `stakeholders`: stakeholders, communication, project organisation and mandates (spec v1, 2026-10-11)

Sources: `mod8/INTEGRATION.md` (platform, file:line), `gates/SPEC_v1.md` (module 1 `project_governance`, which this plugs
into), `mod2/SPEC.md` (authority schedule, linked not copied), `elf/SPEC.md` module 1 "Projektmanagement"
(frame document "Projekthandbuch mit Mandaten"; dev folders `dev_project_organisation`, `dev_mandates`,
`dev_stakeholders`, already in `project_governance/catalogues/elf_module_framework.json:119-151`).
Name: `oe_stakeholders`, dir `stakeholders`, API under `/v1/projects/{id}/stakeholders/...` and
`/v1/projects/{id}/organisation/...`.

## 1. Purpose
Two questions every project must answer before the development-to-execution gate, in one place:
1. **Who outside the core team matters, what do they want, how do we talk to them, what did we promise them?**
   Register, analysis, communication plan, participation formats and events, commitments with follow-up.
2. **Who inside decides what?** Roles (investor, client/Bauherr, user, operator, PM, ...), governance bodies
   (steering committee, user board, design board) with their members and quorum, and the mandates matrix: per decision
   type (orders, design decisions, user changes, ...) which role or body proposes, decides, must be consulted or informed.
   Money limits are NOT stored here: a mandate row for a commitment type points to module 2's authority schedule.

What the module does NOT own: people and companies (the contacts directory and users), letters (correspondence),
meetings and minutes (meetings), risks (risk register), approvals (approval_routes), money authority (module 2),
project access (teams). It references them by id and adds only the stakeholder layer on top.

Domain basis (secondary unless stated; every figure or statutory duty ships as data with URL and
`review_status: unconfirmed` until checked against the primary text):
- Analysis methods (no statute, practice): power/interest grid (Mendelow 1991, as used in PMBOK stakeholder chapters);
  salience model power/legitimacy/urgency (Mitchell, Agle, Wood 1997, AMR 22(4) 853-886,
  https://www.jstor.org/stable/259247); engagement assessment matrix current vs desired level
  unaware/resistant/neutral/supportive/leading (PMBOK, secondary https://pmstudycircle.com/stakeholder-engagement-assessment-matrix/).
- Participation levels: IAP2 Spectrum inform/consult/involve/collaborate/empower, each level a promise to the public
  (https://www.dpc.sa.gov.au/responsibilities/community-engagement/documents/IAP2s-participation-spectrum.pdf; wording is
  IAP2 copyright, ship our own text, cite the source).
- DE: early public participation in land-use planning, §3(1) BauGB (https://www.gesetze-im-internet.de/bbaug/__3.html,
  mirror https://lxgesetze.de/baugb/3); authority shall work towards early participation by the project developer,
  §25(3) VwVfG (https://www.gesetze-im-internet.de/vwvfg/__25.html; a draft moved it to §25a, BT-Drs. 20/4525,
  https://bundestag.de/resource/blob/1027236/ad7b258fcd09994fbb907ce8edc8a734/20-4-525-B.pdf, status unconfirmed);
  guideline VDI 7000:2015-01 and draft VDI-MT 7000 (2025)
  (https://vdi.de/richtlinien/details/vdi-7000-early-public-participation-in-industrial-and-infrastructure-projects).
  Governance roles investor / Bauherr / Nutzer / Betreiber and approval levels: AHO Heft 9 action area A (secondary, as module 1).
- UK: Statement of Community Involvement of the planning authority, s18 PCPA 2004
  (https://www.legislation.gov.uk/ukpga/2004/5/section/18); NSIP developer duty to consult the community per a
  Statement of Community Consultation, s47 Planning Act 2008, draft SoCC consultation 28 days
  (https://www.legislation.gov.uk/ukpga/2008/29/section/47; secondary practice
  https://nsip-documents.planninginspectorate.gov.uk/published-documents/EN010153-000010-5.2_Consultation%20Report%20Appendix%201%20Statement%20of%20Compliance.pdf).
- US: public involvement in environmental review (NEPA; agency procedures since the 2025 CEQ rescission vary,
  so shipped as `unconfirmed` with https://ceq.doe.gov as source) and local public hearing notices (municipal codes, project data).
- Responsibility assignment (RACI and the extended form with Approve/Decide): practice, no statute.

## 2. Catalogues (data, not code)
One catalogue kind `stakeholder_framework`, registered with ONE call in module 1's registry
(`project_governance/catalogue_kinds.py`, `register_catalogue_kind(CatalogueKind(...))`), shipped JSON in this module's
`catalogues/`, tenant drafts and published versions in the shared `oe_governance_catalogue` tables, one resolver; a
project pins `(source, id, version)`. Shipped: `neutral` (default), `de_public_participation`
(adds BauGB / VwVfG / VDI 7000 formats and duty references), `uk_planning_consultation` (s47 SoCC, s42/48 references),
`elf_module_framework` (role and body set of the 11-module framework). Country default via `core/regional_packs.py` as in
module 1 (`catalogue.py:488` pattern). Body:
- `stakeholder_categories`: codes + i18n keys + `kind` (`internal` | `external`): `investor`, `client`, `user`, `operator`,
  `municipality`, `permitting_authority`, `specialist_authority`, `grid_operator`, `utility`, `neighbour`, `public`,
  `interest_group`, `media`, `politics`, `funding_body`, `lender`, `insurer`, `landowner`, `designer`, `contractor`,
  `other`. Extendable.
- `analysis_methods`: each a list of dimensions with scale (`code`, i18n, `min`, `max`, `labels`) and a derived
  classification rule as DATA: `power_interest` (2 dims 1-5, quadrant thresholds -> `manage_closely` / `keep_satisfied` /
  `keep_informed` / `monitor`), `salience` (3 booleans -> 7 classes + `non_stakeholder`), `engagement_level` (ordinal
  unaware..leading, current and desired), `attitude` (-2..+2), `influence` (1-5). Classification = lookup table or
  threshold list; no code path per method.
- `participation_levels`: ordered `inform`, `consult`, `involve`, `collaborate`, `empower`, each with an i18n promise text.
- `channels`: `letter`, `email`, `portal`, `newsletter`, `website`, `meeting`, `site_visit`, `public_hearing`,
  `information_evening`, `workshop`, `hotline`, `social_media`, `press_release`, `notice_board`.
- `participation_formats`: code, default level, default channels, `statutory_refs` (list of `{jurisdiction, ref, url,
  review_status}`), e.g. `early_public_participation_baugb_3_1`, `community_consultation_socc`, `neighbour_information`,
  `steering_committee_briefing`.
- `roles`: project roles of the organisation (`investor`, `client`, `client_pm`, `user_representative`, `operator`,
  `project_manager`, `project_controller`, `site_supervisor`, `lead_designer`, ...), each with `holder_kind`
  (`person` | `organisation`), i18n.
- `body_types`: `steering_committee`, `project_board`, `user_board`, `design_board`, `change_board`, `supervisory_board`
  with default decision level (order of escalation).
- `decision_types`: `order_award`, `design_decision`, `user_change`, `scope_change`, `schedule_change`, `budget_release`,
  `claim_settlement`, `gate_decision`, `stakeholder_commitment`, `communication_release`, each with
  `commitment_type` (optional link key into module 2's authority schedule, e.g. `order_award -> works`) and
  `approval_target_kind` (the approval_routes kind that executes such a decision, if any).
- `mandate_template`: default RACI-D rows `(decision_type, role|body, letter)` with letters `P` propose, `D` decide,
  `A` approve/co-sign, `C` consulted, `I` informed.

## 3. Entities (project-scoped, CASCADE on project, tenant isolated, new tables only)
- `StakeholderSettings` (one per project): pinned framework `(source, id, version)`, `analysis_method` code (default
  `power_interest`), `review_interval_days` (default 90), `owner_area_code` (module 1 area that owns the register,
  default `m01_project_management`).
- `Stakeholder`: `code` (unique per project), `display_name`, `category` (framework code), `contact_id` (soft, contacts
  directory, person or organisation; nullable for a group like "residents of X street"), `is_group` + `group_size_estimate`,
  `parent_stakeholder_id` (person inside an organisation), `user_id` (soft, if internal and a platform user),
  `interests` text, `expectations` text, `concerns` text, `relationship_owner_user_id` (must be project member),
  `geo` (optional point / parcel ref, for neighbours), `is_confidential` (personal data of private persons, see rule 17),
  `status` `active | dormant | archived`. Personal data stays in contacts; the register stores only the role in the project.
- `StakeholderAssessment` (append-only, each one dated): `stakeholder_id`, `method_code`, `method_version`, `scores` JSON
  validated against the method dimensions, derived `classification` (computed at write, stored for history),
  `engagement_current`, `engagement_desired`, `attitude`, `rationale`, `assessed_by/at`. The latest per stakeholder is
  the current one; history shows drift.
- `CommunicationPlanItem`: `audience` = stakeholder ids and/or categories and/or a governance body, `purpose` /
  `key_message` (text, i18n not applicable: user content), `participation_level`, `channel`, `frequency`
  (`once` | `rrule` string, RFC 5545 subset) or `trigger` (`gate`, `event_type`), `owner_user_id`, `starts_on/ends_on`,
  `status` `planned | active | paused | completed | cancelled`, `next_due` (computed).
- `EngagementEvent`: one occurrence: `plan_item_id` (nullable for ad hoc), `format_code`, `participation_level`,
  `title`, `held_on`, `location`, `stakeholder_ids`, `attendance_count`, `outcome` text, `feedback_summary`, links:
  `meeting_id` (soft, meetings), `correspondence_ids` (soft), `document_ids` (CDE). State `planned -> held | cancelled`.
  An occurrence of a recurring item is generated lazily (only when due or recorded), never pre-materialised.
- `StakeholderCommitment`: something promised TO a stakeholder: `stakeholder_ids`, `source` (`event_id` | `meeting_id`
  | `correspondence_id` | `permit_condition_ref` | `manual`), `text`, `category` (`noise`, `traffic`, `working_hours`,
  `information`, `compensation`, `design_change`, `access`, `environment`, `other`), `owner_user_id`, `due_date`,
  `verification` text (how we prove it), `decision_ref` (mandate check result id, rule 10), linked follow-up:
  `task_id` / `risk_id` / `requirement_id` (soft); state `proposed -> agreed -> in_progress -> fulfilled -> verified`,
  side `withdrawn` (rationale + decided under mandate), `breached` (computed flag when overdue, explicit state when
  confirmed). `communicated_back_at` (closing the loop: the stakeholder was told it is done).
- `ProjectRole`: `(project, role_code)` from the framework or a custom code with label; holder = `roster_member_id`
  (`teams.RosterMember`, `teams/models.py:171`: the project's one list of people, user OR contact OR name) or
  `holder_contact_id` for an organisation (investor company, operator company), `deputy_roster_member_id`, `valid_from/valid_to`. Several holders
  per role allowed only if the role is marked `multi`. Module 2's `AuthorityAssignment.project_role` keys REFERENCE these
  role codes (one role vocabulary per project, see INTEGRATION 6).
- `GovernanceBody`: `code`, `body_type`, `name`, `chair_role_code`, `quorum` (`min_members` or `majority` | `unanimous`),
  `decision_level` (int, escalation order), `meeting_series_ref` (soft, meetings `meeting_type`), terms of reference
  (CDE document id). `GovernanceBodyMember`: `(body, role_code | user_id | contact_id, voting bool, valid_from/to)`.
- `Mandate`: `(project, decision_type, holder = role_code | body_code, letter P/D/A/C/I, scope_note, limit_ref)`;
  `limit_ref` is `{"authority_schedule": "pinned", "commitment_type": "works"}` when the decision is money-bound, resolved
  live from module 2 (never a stored amount). Uniqueness: exactly one `D` per `(decision_type, scope)`; see rules.
- `MandateConflict` is not a table: multiple-role conflicts are computed (rule 12).

States use `core/fsm.EntityFSM` (commitment, plan item, event).

## 4. Rules (each is a test)
1 A stakeholder needs a category from the pinned framework; unknown code -> 422 `unknown_category`.
2 An assessment validates scores against the method's dimensions (range, all required); classification is derived from
  the method's table, never accepted from the client.
3 Changing the analysis method keeps old assessments (with their method version); the grid shows only assessments of the
  current method; stakeholders without one are listed as `not_assessed`.
4 Review due: a stakeholder whose latest assessment is older than `review_interval_days` (or none and category is
  external) is flagged `review_due`; daily job notifies the relationship owner once per interval.
5 Engagement gap = desired - current level (ordinal); gap > 0 for a `manage_closely` stakeholder with no active
  communication plan item -> validation warning `key_stakeholder_without_plan`.
6 A plan item's `next_due` comes from its rrule / trigger; an overdue item (next_due passed, no event recorded in the
  window) is flagged and notifies its owner; `trigger: gate` items become due when module 1 moves the gate to `in_review`
  (event `governance.gate.submitted`).
7 Recording an event against a recurring item advances `next_due`; recording two events for one occurrence is allowed
  (ad hoc); the occurrence counts as done once.
8 Participation level honesty: an event or plan item at level `consult` or higher requires a `feedback_summary` within
  N days (framework, default 30) after `held_on`, else flag `feedback_not_reported` (IAP2 promise "report back").
9 A commitment created from an event/meeting/correspondence keeps the source link; the source can be deleted only
  softly (commitment keeps a snapshot of source title + date).
10 Agreeing or withdrawing a commitment is a decision of type `stakeholder_commitment`: the mandate check (rule 11)
  resolves who decides; if that holder's decision needs an approval route (framework `approval_target_kind`), the
  transition waits for the approval instance (new kind `stakeholder_commitment`), else the decider confirms directly.
  Commitments with a cost (`cost_estimate` set) additionally require a module 2 release item link before `agreed` when
  the project has a commitment matrix (no matrix -> warning only).
11 Mandate check `who_decides(decision_type, scope, amount?)`: returns the `D` holder resolved to users (role -> holders
  valid today; body -> members + quorum); if the type has `commitment_type` and an amount is given, it delegates the
  tier lookup to module 2 (`commitment_release` evaluator) and returns both (role from here, tier/approver from there).
  Without module 2 installed it returns the role only and `authority_not_evaluated`.
12 Multiple roles: the same user holding roles that are both `P` and `D` (or `D` and `A`) for one decision type is a
  conflict -> listed in the matrix; framework flag `forbid_self_approval` per decision type turns it into a validation
  error; otherwise a warning with mandatory acknowledgement (rationale stored on the role assignment).
13 Exactly one `D` per decision type and scope; zero -> `mandate_missing` (gate blocker via readiness, rule 20); two ->
  422 on write.
14 A role holder must be a project member (teams access rule) or an external contact; `valid_to` in the past -> holder not
  returned by rule 11; a role with no valid holder is flagged `role_vacant`.
15 Body quorum: rule 11 for a body returns members valid today; fewer than quorum -> `body_inquorate` warning.
16 Changing a role holder publishes `stakeholders.role.changed`; module 2 regenerates its tier routes from it (its rule g),
  module 1 area owners are NOT changed automatically (different concept) but a hint is shown when the area owner was the
  old holder.
17 Personal data: stakeholders that are private persons (`neighbour`, `public`) default to `is_confidential`; their list
  and export require `stakeholders.read_personal`; exports mask names otherwise. Erasure of the contact (GDPR) leaves the
  stakeholder as "anonymised" with assessments and commitments intact.
18 Commitment overdue -> `breached` flag, notify owner and relationship owner; confirmed breach needs rationale and creates
  (option) a risk in the risk register via its API (soft link, risk owns the record).
19 Closing the loop: `verified` requires `communicated_back_at` or an explicit `not_required` rationale.
20 Governance readiness evidence for module 1 (area `m01_project_management`): `register_present` (>= 1 external
  stakeholder assessed), `key_stakeholders_planned` (rule 5 clean), `mandates_complete` (every decision type marked
  required has one D), `roles_filled` (no required role vacant), `commitments_tracked` (no breached without rationale).
  Each returns status + counts; module 1 decides how to use them.
21 Frame documents: the export "Project organisation and mandates" (roles, bodies, mandates) and "Stakeholder and
  communication plan" are generated PDF/XLSX and filed as CDE revisions into the module 1 frame document of the area
  (`dev_project_organisation`, `dev_mandates`, `dev_stakeholders`), so the binding version is that revision. After the
  gate, editing roles/mandates of a bound document produces a module 1 `FrameChangeRequest` (warning, not block, in v1).
22 Tenant isolation and IDOR: every handler `verify_project_access`; a contact, meeting, correspondence, risk or user
  from another project/tenant -> 404 on link.
23 Everything exportable (PDF + XLSX via `core/register_export`), all labels i18n, `log_activity` on every state change.

## 5. API (envelope `{items,total,offset,limit}`)
`/v1/projects/{id}/stakeholders/`: settings (get/put pin), stakeholders (CRUD, filter by category/classification/
review_due), assessments (list per stakeholder, create), grid (`GET .../grid` computed positions), plan items (CRUD,
`.../due`), events (CRUD, record occurrence), commitments (CRUD, transition), export (pdf/xlsx).
`/v1/projects/{id}/organisation/`: roles (list, put holders), bodies (+ members), mandates (matrix get / put rows),
`GET .../who-decides?decision_type=&scope=&amount=&currency=`, conflicts, export.
Catalogue admin: `/v1/stakeholders/frameworks` (list, clone, edit draft, publish, diff) through the shared resolver.
Permissions registered on startup: `stakeholders.read`, `stakeholders.edit`, `stakeholders.read_personal`,
`organisation.manage` (roles, bodies, mandates), `stakeholders.catalogue` (admin).

## 6. Frontend (project tabs nested under `/projects/:id/stakeholders` and `/projects/:id/organisation`)
1 Register (AG Grid): name, category, classification chip, engagement current -> desired, attitude, owner, review due,
  open commitments count. 2 Grid view: power/interest quadrants (or salience Venn) with drag-to-reassess (creates an
  assessment, asks rationale). 3 Stakeholder drawer: contact card (from contacts), assessment history, events, letters
  (correspondence filtered by contact), commitments. 4 Communication calendar: plan items and due occurrences.
5 Commitments register with due/breached badges. 6 Organisation: org chart of roles and bodies, mandates matrix
  (decision types x roles/bodies, letters, conflict highlighting, "who decides X for 250k?" calculator that shows the
  module 2 tier). Strings in all locales in the same commit.

## 7. Validation rule set `stakeholders`
stakeholder_has_category, assessment_current (review interval), key_stakeholder_has_plan, feedback_reported,
commitment_has_owner_and_due, commitment_not_breached, mandate_one_decider, mandate_no_self_approval, role_not_vacant,
body_quorate, framework_scales_valid (catalogue).

## 8. Tests first (in this order)
1 Unit, pure: classification per method (quadrant boundaries, salience 7 classes), score validation, rrule next_due
  (incl. DST and month-end), mandate resolver (one D, conflicts, bodies, quorum, validity windows), FSM tables, catalogue
  loader (every shipped framework validates, every statutory ref has URL + review_status, i18n keys).
2 Service with DB (tests/pg): assess -> history; review_due job; plan due and event advance; feedback flag; commitment from
  event through agreed (direct and via approval route) to verified; breach -> risk link; role change event -> module 2
  route regeneration stub; who-decides with module 2 present and absent; GDPR anonymisation keeps history.
3 Security (tests/pg, IDOR + `tenant_isolation`): other tenant read/link 404; editor without `read_personal` gets masked
  names in list and export; viewer cannot edit mandates. Add handlers to `tests/unit/test_idor_router_guards.py` and the
  file to `ci-postgres.yml`.
4 API contract. 5 Migration up/down/up on PG. 6 approval_routes kind `stakeholder_commitment` in model tuple AND schema
  Literal. 7 Governance evidence hook returns the 5 checks. 8 Frontend vitest (grid quadrants, mandate matrix conflicts,
  masked names, i18n). 9 E2E: pin framework, add neighbour + municipality, assess, plan info evening, record it with a
  commitment, set roles and mandates, see readiness at the gate.

## 9. Build order
tests 1 -> register catalogue kind (after module 1 commits the registry) -> catalogues -> models + migration -> classifier,
rrule, mandate resolver, FSM -> service (tests 2) -> router + permissions (3-4) -> approval kind + subscriber -> governance
evidence + frame-document export -> module 2 link (role vocabulary, who-decides delegation) -> frontend -> i18n -> E2E ->
cloud CI -> browser check.

## Decisions (binding for implementation)
a. One module for stakeholders AND organisation/mandates, two API roots. Reason: ELF module 1 treats them as one frame
   document (Projekthandbuch mit Mandaten); splitting creates two role vocabularies.
b. People live in contacts, never in the register. Reason: one source of truth for names, addresses, GDPR erasure; the
   register stores the project relation only. Groups without a contact are allowed (residents of a street).
c. No new CRM. `crm` (accounts, leads, opportunities) is sales pipeline of the contractor; stakeholders are project
   scoped and include non-commercial parties. No reuse beyond the contact link.
d. Assessments are append-only with the method version. Reason: attitude drift over time is the most useful view, and a
   method change must not silently rewrite history.
e. Analysis methods are catalogue data (dimensions + lookup), default power/interest. Reason: users know the 2x2 grid in a
   minute; salience and engagement levels are optional add-ons, same mechanism.
f. Communication plan uses an RFC 5545 rrule subset plus gate/event triggers; occurrences are not pre-generated.
   Reason: no orphan rows when a plan changes; gate triggers tie communication to module 1.
g. Events link to meetings and correspondence instead of copying minutes or letters. Reason: those modules already own
   attendees, minutes, distribution and registers.
h. Commitments to stakeholders are a NEW entity, not meeting action items. Reason: action items are internal tasks with
   free-text owners; a promise to a third party needs verification, closing the loop and breach handling. A commitment
   may spawn a task for execution.
i. Mandates store roles/bodies and letters only; money limits are a live reference into module 2's authority schedule
   (`commitment_type`). Reason: no duplicated thresholds; module 2 already handles currency, tiers and delegation.
j. One project role vocabulary: module 2's `AuthorityAssignment.project_role` keys are this module's `ProjectRole` codes,
   and module 2 reads holders from here (module 2 keeps its table only for deputies/validity it already specified, fed
   from `stakeholders.role.changed`; if both ship, this module is the writer). Reason: one answer to "who is the client PM".
k. Absence/delegation is NOT modelled here: `approval_routes.Delegation` as in module 2.
l. Roles do not grant platform permissions or project access. Reason: access stays in teams/RBAC; roles describe the
   organisation and feed mandates and approval steps. A role holder who is not a member is refused (rule 14).
m. Private persons are confidential by default with a separate read permission. Reason: neighbour lists are personal
   data (GDPR art. 5, 6), the gate export goes to many readers.
n. Post-gate edits of roles/mandates warn and propose a frame change request instead of blocking in v1. Reason: governance
   change control (module 1 rule 4) is still being built; block can be enabled per project later.
o. Statutory participation duties ship as formats with refs and `review_status: unconfirmed`; the module never claims
   legal compliance, it shows the reference.
