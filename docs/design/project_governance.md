# Module `project_governance`: phases, gates and frame documents

Design document. The first consumer is an eleven-area project management framework with a development and an execution phase.

## 1. Purpose
A country-neutral backbone every later module plugs into. A project runs through a phase model with gates.
Management areas (configurable catalogue) each have an owner and, per gate, required frame documents and a
readiness check. A gate decision is taken by an authorised person, freezes what it approved and may carry
conditions. After the gate, approved frame documents become binding and change only through change control.

## 2. Catalogues (data, not code)
Shipped inside the module as versioned JSON (one active pack per installation cannot carry them):
`neutral` (default), `hoai_lph` (DE), `riba_2020` (UK), `aia_b101` (US), `aho_heft9` (DE PM, areas A-E x stages 1-5),
`elf_module_framework` (11 areas, Development / Execution). Country default via `regional_packs`; a pack may
name its default catalogue. Each phase carries `spine_key` into `requirements/lifecycle.py` PHASE_SPINE, the one
neutral phase vocabulary (extended where a phase has no spine key, for example AIA procurement).
Catalogue = phases (ordered), gates (between phases), areas (code, i18n name, default required documents per
gate), document types (code, i18n name, area). Statutory facts in a catalogue carry source URL and review status.

## 3. Entities (all project-scoped, CASCADE on project, tenant isolated)
- `GovernanceModel`: project pins catalogue id + version (one per project). Changing it needs an explicit
  phase mapping; decided gates are kept.
- `GovernanceArea`: code, name override, `owner_user_id`, `deputy_user_id`, applicable flag + rationale.
- `GovernanceGate`: from/to phase, planned date via soft link to a schedule activity (schedule owns the date),
  state: `not_started -> in_preparation -> in_review -> decided` (+ `reopened` as a new attempt).
- `FrameDocument`: (project, area, document type). Soft link `container_id` to a CDE container; versions ARE CDE
  revisions, no file copies. `release_state`: `draft -> in_review -> approved_at_gate -> binding -> superseded`.
  `bound_revision_id`, `bound_content_hash`.
- `ReadinessCheck`: (gate attempt, area): status `not_assessed / ready / ready_with_risks / not_ready / not_applicable`,
  RAG, note, confirmed_by/at, `stale` flag. Automatic evidence items read from linked modules (CDE published,
  site_prep gate items, requirements GateResult, closeout, commissioning, hold points).
- `GateDecision` (immutable): attempt no., outcome `go / go_with_conditions / hold / recycle / stop`, decided_by,
  rationale, snapshot (JSON: document revision ids + hashes, check states), `proceed_at_risk_areas`.
- `GateCondition`: decision, area, text, owner, due date, severity, state `open / cleared / waived / overdue`
  (waive needs rationale + authority).
- `FrameChangeRequest`: the only path to change a binding document; approval through `approval_routes`.

Reuse: `core/fsm.EntityFSM` for both state machines; `approval_routes` new `target_kind="phase_gate"` and
`"frame_change"` with a subscriber (pattern `submittals/approval_subscribers.py`); `Project.phase` stays a mirror
written ONLY by this module; `ProjectMilestone` not written; audit log, event bus, notifications, activity feed.
Not used: `tasks.checklist` (no signer), `enterprise_workflows`, `core/workflow_engine.py` (dead).

## 4. Rules (the 15 behaviours; each is a test)
1 go blocked while a required document is not approved, unless turned into a condition. 2 area without owner
blocks the gate. 3 decision snapshots exact revisions and checks. 4 editing a binding document creates a draft;
the binding revision stays in force until a change request is approved. 5 overdue conditions escalate and block
the next gate; waiver needs rationale. 6 reopen keeps the old decision, starts attempt n+1. 7 model change needs a
mapping, keeps decided gates. 8 not-applicable needs rationale and the decider's acceptance. 9 decider must be
entitled by the route; four-eyes optional per project (owner != decider). 10 recycle marks checks stale; hold
freezes with resume date. 11 stop makes open documents read-only. 12 owner change resets that area's readiness.
13 a check goes stale when its document changes after confirmation. 14 proceed-at-risk is explicit and limited to
named areas. 15 full trail exportable (PDF + XLSX via `core/register_export`), all labels i18n.

## 5. API (under `/v1/projects/{id}/governance/...`, envelope `{items,total,offset,limit}`)
model (get, set with mapping), areas (list, patch owner/deputy/applicable), gates (list, get with readiness
matrix, submit for review, decide, reopen), documents (list, attach CDE container, submit, history), checks
(confirm, mark n/a), conditions (create, clear, waive), change requests, export (pdf/xlsx). Permissions
registered on startup: `governance.read`, `governance.edit` (owner of the area or manager), `governance.decide`
(entitled via route only). `verify_project_access` on every handler.

## 6. Frontend
Project tab "Governance" (route nested under `/projects/:id`, no new top segment):
1 Matrix: areas x phases, each cell = document state + readiness, owner avatar, next gate banner.
2 Gate page: readiness per area with evidence, blockers list, decision dialog (outcome, conditions, rationale),
history of attempts with snapshots.
3 Area page: owner, documents with CDE revisions, binding badge, change requests.
4 Conditions register. Project header ribbon reads phases from the model (fix for HOAI keys).
Strings in all locales in the same commit.

## 7. Validation rule set `project_governance`
area_has_owner, required_documents_defined, binding_document_unchanged (hash), conditions_not_overdue,
gate_date_after_previous, decision_by_entitled_user, not_applicable_has_rationale.

## 8. Tests first (written before code, in this order)
1 Unit, pure: state machines (every allowed and forbidden transition, table driven); gate evaluator (the 15
behaviours as cases); catalogue loader (schema, every catalogue loads, spine keys valid, i18n keys exist).
2 Service with DB (tests/pg): decide go / conditions / hold / recycle / stop; snapshot frozen after document
change; reopen; binding + change request through approval_routes; stale checks; owner change; model change
with mapping; concurrent decisions (one wins, 409 for the other).
3 Security (tests/pg, IDOR lane + tenant_isolation marker): other tenant cannot read or decide; editor cannot
decide; non-entitled manager cannot decide; owner cannot decide own area under four-eyes.
4 API contract: envelope, 404 vs 403, validation errors with codes.
5 Migration: up, down, up on PG; fresh DB has zero schema repairs.
6 Frontend vitest: matrix renders states, blockers listed, decision dialog requires rationale for stop / waiver,
role gating of buttons, i18n keys resolve.
7 E2E (Playwright, one scenario): set model, assign owners, attach documents, decide gate with condition, clear it.
Gate CI: ruff, build, all repo hygiene gates, both cloud lanes green before merge.

## 9. Build order
tests 1 -> catalogue + models + migration -> service + FSM (tests 1-2 green) -> router + permissions (3-4) ->
integrations (approval_routes, CDE, events, notifications, audit, validation, export) -> frontend (6) -> i18n ->
E2E -> cloud CI -> browser check -> merge.
