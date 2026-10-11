# Module `commitment_release`: commitment and release matrix with delegation of authority (spec v1, 2026-10-11)

Sources: `mod2/INTEGRATION.md` (platform, file:line), `gates/SPEC_v1.md` (module 1, `project_governance`, which this
plugs into), `elf/SPEC.md` module 9 (first consumer: "Verpflichtungs- und Freigabematrix").
Name: `oe_commitment_release`, dir `commitment_release`, API nested under `/v1/projects/{id}/commitments/...`.

## 1. Purpose
The owner decides, item by item, when money may be bound and who may bind it. A matrix item is a planned or existing
commitment (a works package, a long-lead supply, a design appointment, a change, a contingency drawdown). Per item the
matrix holds: amount, cost code / cost bearer, approver, preconditions, latest decision date, cancellation or transfer
option and the residual loss if the project aborts now. A delegation-of-authority schedule (DoA) decides which tier of
approver a release needs, by amount and type. Releases go through `approval_routes`; nobody keeps a second approval engine.

What the module does NOT own: amounts of contracts, POs, change orders, variations, budgets. It references those
documents and derives every amount. New data is only: the item, its release decisions, its abort terms, the DoA catalogue.

Domain basis (fetched 2026-10-11 and confirmed: §648 BGB incl. the 5 % presumption, FAR 2.101 SAT USD 350,000; all other URLs come from secondary search and their figures ship with `review_status: unverified`, see INTEGRATION 8):
- DE: Kostensteuerung in AHO Heft 9 action area C (https://thost.de/wp-content/uploads/2026/04/seminar-einladung-aho.pdf,
  secondary); DIN 276:2018-12 cost groups as cost code (paywalled). Owner free termination: contractor keeps the price
  less saved costs, 5 % of the unperformed part presumed (§648 BGB, https://www.gesetze-im-internet.de/bgb/__648.html;
  BGH VII ZR 223/10 https://gesetze.co/urteile/VII_ZR_223-10; burden of proof BGH VII ZR 6/14
  https://rewis.io/urteile/urteil/xob-08-01-2015-vii-zr-614/); §8 Abs. 1 VOB/B same rule. Public owners: commitments
  binding later years need a Verpflichtungsermächtigung (§38 BHO, https://www.gesetze-im-internet.de/bho/__38.html).
  EU thresholds 2026-27, works EUR 5,404,000 (Delegated Reg. (EU) 2025/2152, https://umwelt-online.de/recht/eu/25d/25d_2152.htm).
- UK: delegated authority by amount and novelty (HM Treasury, Managing Public Money, Annex 2.2,
  https://assets.publishing.service.gov.uk/media/684ae4c6f7c9feb9b0413804/Managing_Public_Money.pdf). NEC4 ECC
  termination amounts A1/A2/A4 for the client's own reason
  (https://www.neccontract.com/news/termination-in-an-nec4-engineering-and-construction-contract; CECA bulletin 54,
  https://gmhplanning.co.uk/wp-content/uploads/2025/06/CECA-NEC-Bulletin-Nr-54-Termination-June-2025.pdf; sources
  disagree on A3/A4, verify clause text). JCT SBC has no general owner termination for convenience.
- US: termination for convenience settlement (FAR 49.201, https://www.acquisition.gov/far/49.201); simplified acquisition
  threshold USD 350,000 from 2025-10-01 (FAR 2.101, https://www.acquisition.gov/far/2.101), inflation-adjusted every 5
  years, so dated data; reserve drawdown (AACE RP 75R-13, via https://www.pathlms.com/aace/courses/2928/documents/3853).
- Last responsible moment: decisions scheduled backwards from need (IGLC 2000, Heathrow T5,
  https://www.iglc.net/papers/Details/110); last possible moment definition
  (https://projectproduction.org/glossary/last-possible-moment-lpm/). LRM = need date - lead time - decision buffer.
- Exposure on abort: no single standard; assembled per contract basis from the rules above. Long-lead supply
  cancellation charges scale with fabrication progress (general practice, secondary).

## 2. Catalogues (data, not code)
Two catalogue kinds, `authority_schedule` and `abort_basis`, registered with ONE call each in module 1's kind registry
(`project_governance/catalogue_kinds.py`, in flight in the worktree, uncommitted; its docstring already names
`authority_schedule`): shipped JSON in this module's `catalogues/`, tenant drafts and immutable published versions in the
shared `oe_governance_catalogue` tables, one resolver; projects pin `(source, id, version)`. No second store.

`authority_schedule` (DoA). Shipped: `neutral` (3 tiers, no statutory numbers), `de_public_owner`, `uk_public_body`,
`us_federal_owner` as examples with source URL + review status per statutory figure. A company clones one into a tenant
version. Body:
- `currency` (ISO 4217) of the bands; `basis`: `net` | `gross` (default net, statutory thresholds are net).
- `commitment_types`: codes + i18n keys: `works`, `services`, `supplies`, `design`, `change`, `contingency_drawdown`,
  `claim_settlement`, `termination_settlement` (extendable).
- `tiers` (ordered): `code`, i18n name, `approver`: one of `role` (platform role), `project_role` (key into a project
  assignment, see 3), `user` (tenant versions only); `steps` mode (`all`/`any`), `four_eyes` (requester != approver).
- `bands`: `(type, tier, max_amount)`; the required tier is the lowest whose `max_amount` >= the evaluated amount;
  above the top band = `escalate_outside` (board / ministry consent, recorded as an external approval document).
- `aggregation`: how an amount is evaluated: `item_total` (cumulative released incl. this request, default) or `request_only`.
  Anti-splitting: items sharing `split_group` are evaluated on the group sum.
- `novelty_flags`: types or flags that force a minimum tier regardless of amount (Managing Public Money "novel or contentious").
- `variation_tolerance`: absolute and percent; a linked document may exceed the release by up to this before re-release.
- `effective_from` / `effective_to` (dated thresholds, FAR SAT moves every 5 years).

`abort_basis`. Shipped: `de_bgb_648`, `de_vob_b_8_1`, `nec4_ecc_client_reason`, `far_49_convenience`, `supply_cancellation_schedule`,
`none_free_cancellation`, `custom`. Body: formula parameters only (e.g. `presumed_unperformed_pct: "0.05"` with source URL
and review status), never code paths keyed on country.

Country default via `core/regional_packs.py` and pack metadata, as in module 1 (`catalogue.py:488` pattern).

## 3. Entities (project-scoped, CASCADE on project, tenant isolated, new tables only)
- `CommitmentMatrix` (one per project): pins authority schedule `(source,id,version)`; `enforcement`: `off` | `warn` | `block`
  (default `warn`, see rule 3); `base_currency` read from project; `fx_policy`: `project_rates` (default, same numbers as
  costmodel) | `fx_service_rate_set`; `tier_routes`: map `tier_code -> route_id` (routes of kind `commitment_release`, one per tier, because
`InstanceCreate` carries only `route_id/target_kind/target_id` and steps come from the route,
`approval_routes/schemas.py:183-188`). The module GENERATES these routes from the schedule tiers plus `AuthorityAssignment`
as user-pinned steps (`approver_user_id`, so `entitled_deciders` and delegation apply; a role step returns None there) and
regenerates them when an assignment changes. A manager may pin a hand-built route per tier instead; optional
  `legal_entity_id` (cost bearer default, `legal_entities/models.py:31`).
- `AuthorityAssignment`: `(project, project_role key, user_id, deputy_user_id, valid_from, valid_to)`: who fills
  `project_role` tiers on this project (e.g. `owner_pm`, `owner_board_member`). Absence is NOT modelled here: it is an
  `approval_routes.Delegation`.
- `CommitmentItem`: `code` (unique per project), title, `commitment_type`, `cost_line_id` (soft, Cost Spine, the cost code),
  `control_account_id` (soft), `cost_bearer_legal_entity_id` (soft, nullable = matrix default), optional
  `funding_application_id` (soft), `risk_id` (soft), `governance_area_code` + `gate_code` (gate it must be released by),
  `split_group`, `owner_user_id` (requester), `planned_source` (`budget_line` | `cost_line` | `boq_position` | `manual`)
  + `planned_source_id`; `planned_manual_amount` + `currency` ONLY when source is `manual` (the one stored estimate, used
  before any budget exists, flagged as such); decision date: `need_activity_id` (soft schedule activity) + `lead_time_days`
  (or soft `requisition_id` to read it) + `decision_buffer_days`, or `latest_decision_date_fixed`; `state` (below).
- `CommitmentLink`: `(item, kind, document_id)`, kind `contract` | `contract_line` | `purchase_order` | `change_order` |
  `variation_order` | `tender_package` | `contingency_drawdown`. Unique `(kind, document_id)` project-wide: a document
  counts in one item only. Amount never stored.
- `Precondition`: `(item, kind, ref_id, text, state, confirmed_by/at)`; kinds `manual`, `gate_decided` (governance gate go),
  `frame_document_binding`, `funding_approved`, `permit` (review_authority cycle), `budget_available` (computed),
  `public_commitment_appropriation` (manual with evidence). Linked kinds are computed on read, only manual ones store a tick.
- `ReleaseDecision` (immutable): `attempt`, `requested_amount`, `currency`, `amount_in_schedule_currency`, `fx_rate_used` + date,
  `cumulative_after`, `required_tier`, `schedule_version` snapshot, `approval_instance_id`, outcome `released` | `rejected`
  | `withdrawn`, `decided_by` (from the instance), `snapshot` JSON (linked doc ids + amounts + content hash at decision,
  precondition states), `conditions` text, `valid_until` (optional).
- `AbortTerms`: per link or per item: `abort_basis` code + version, `cancellation_schedule` (list of `{milestone, from_date
  or progress_pct, charge_amount or charge_pct}`), `transferable` (`no` | `to_project` | `resale`), `transfer_value_estimate`,
  `salvage_value_estimate`, `saved_cost_estimate`, `notice_days`, source note. Estimates carry `entered_by/at`.
- `AbortScenario` (optional, saved snapshot of a computed exposure on a date for reporting; the live figure is computed).

Item state (`core/fsm.EntityFSM`): `planned -> release_requested -> released | partially_released -> committed ->
closed`; side states `rejected` (back to planned with attempt n+1), `re_release_required` (linked amount above release
+ tolerance), `on_hold`, `aborted`, `transferred`, `lapsed` is NOT a state: "decision overdue" is a computed flag.
`committed` and `closed` derive from linked documents (committed = any link counts per costmodel rule; closed = all
links completed/closed), written only by the module's event subscribers.

## 4. Rules (each is a test)
1 Amounts are derived: planned from `planned_source`; committed per linked document through
  `CostSpineRepository.committed_by_document` (new per-document variant of `costmodel/repository.py:1204`, same counting
  rule: PO from issued, subcontractor contracts, terminated = certified) returning NATIVE currency per document; the
  matrix converts under its own FX policy (rule 13). The award-pair rule and the change rule (rule 7) run over the
  item's whole LINK SET, not per document. Reconciliation test: matrix committed per cost line equals
  `committed_by_cost_line` when every rate is present; a separate case with a missing rate expects the matrix to refuse
  while costmodel blends.
1a Net / gross: each link kind has a fixed field map (PO `amount_subtotal` net / `amount_total` gross; contract line
  `total_value`; CO `approved_amount` else `cost_impact`; VO `final_cost_impact`) with its declared tax basis; the
  schedule `basis` picks the field. One test per link kind, including a document whose "net" field already holds tax.
2 Release request evaluates the DoA, then starts the instance on `tier_routes[required_tier]`: amount = cumulative released + request (or group sum for `split_group`), converted to
  the schedule currency; picks the lowest sufficient tier for the item type; novelty flags raise the tier; above top band
  -> `escalate_outside` requires an attached external approval reference.
3 Enforcement (guards the LISTED routes only; a full writer inventory of Contract/PO status and `total_value`, incl.
  clone and import paths, is a build step before `block` may be offered): `off` = register only; `warn` = guard points return a warning payload and an audit entry; `block` = the
  guard raises 409 `commitment_not_released` at every guard point in INTEGRATION 7 (award, contract activate, contract value
  edit/amend, PO approve, PO issue, change order approve, variation approve, contingency drawdown). Each guard point has a
  test in its own module. A document not linked to any item: `block` refuses with `commitment_not_in_matrix` only when
  `require_link` is on (default off).
4 Release above own authority: the approval instance is started with the steps of the required tier; a decider below
  the tier is not in `entitled_deciders` -> 403. Requester == decider refused when the tier has `four_eyes`.
5 Partial release: `release` grants a ceiling below the planned amount (tranche, e.g. design to stage 3); item is
  `partially_released`; a document whose amount exceeds the cumulative ceiling + tolerance is blocked/warned; next
  tranche re-evaluates the tier on the new cumulative amount (a tier can rise between tranches).
6 Linked contract later varied: on `contracts.contract.amended`, `variations.contract_sum.updated`, `changeorder.approved`,
  `procurement.po.updated` the module recomputes; if committed > released + tolerance the item becomes
  `re_release_required` and its owner is notified; under `block` the variation approval itself was the guard point (rule 3).
7 A change order / variation is either its own item (type `change`, own tier and ceiling) or a delta link on the
  contract's item, never both. An approved change is folded into `Contract.total_value`, so a change item's committed
  amount is the delta already inside the contract figure, and the contract's item reports committed net of changes owned
  by change items: counted once project-wide. Same once-only rule for contract vs its contract_line and for
  tender_package / contract / PO from one award. The reconciliation test includes the CO-as-own-item case.
8 Decision date: `latest_decision_date = need date - lead_time_days - decision_buffer_days`, need date = linked activity
  `late_start`, else `start_date`, else fixed date; null CPM -> uses `start_date` and says so (`date_basis` in API). Passed
  and not released -> `decision_overdue` flag, escalation notification to owner and tier approver, and the abort exposure
  view shows the cost of the delay as a manual note (no invented figure).
9 Approver absent: delegation through `approval_routes.Delegation` only (window + project scope); the delegate decides
  under the delegator's tier; `decided_by` records the delegate and `on_behalf_of`. No delegate and SLA passed -> the
  existing SLA escalation. An `AuthorityAssignment` with `valid_to` in the past cannot be snapshotted into a new instance.
10 Schedule version change mid-project: decided releases keep their snapshot tier; new requests use the newly pinned
  version; pinning needs `commitment.manage`.
11 Rejected release: item back to `planned`, attempt n+1, rationale required.
12 Withdrawal: a pending release can be withdrawn by the requester (instance cancelled).
13 Currency (the matrix's own conversion, never `_amount_in_base`): Decimal end to end, quantised only for display. Item, document and schedule may differ in currency. Missing
  FX rate -> release evaluation refuses with `fx_rate_missing` (never 1:1, unlike `_amount_in_base`); the rate and its date
  are frozen in the decision. Display totals in base currency show a `mixed_currency` flag.
14 Abort exposure per item at date D (computed, never clamped, sign shown):
  `sunk = paid + invoiced_unpaid + certified_not_invoiced + received_not_invoiced` (finance/cost_position, claims, GR);
  `committed_not_spent = committed - sunk`; `cancellation_charge` from `AbortTerms` (schedule entry for D or progress,
  else basis formula, e.g. BGB 648: unperformed price - saved costs, default 5 % of unperformed when saved costs not
  documented; NEC4 A1+A2+A4; FAR 49 incurred + settlement + profit on work done); `recoverable = transfer + salvage`;
  `residual_loss = sunk + cancellation_charge - recoverable`. Released-but-uncommitted adds nothing (it is avoidable).
  Unknown terms -> `residual_loss` is `null` with reason `abort_terms_missing`, not 0. Project total = sum with a count of
  unknown items.
15 Abort executed: `aborted` state needs a decision through the release route (type `termination_settlement`, tier by
  residual loss); the module does NOT terminate the contract, it links the contract's own terminate action.
16 Transfer: `transferred` needs target project / item; links move, decisions stay with the source item.
17 Contingency drawdown: release writes the drawdown through the risk/finance API (`risk/contingency.py:284` record
  format) after approval; balance below request -> refused `contingency_insufficient`.
18 Precondition not met: release request allowed in `warn`, refused in `block` with the list of open preconditions;
  a gate precondition reads `project_governance` decisions only.
19 Concurrency: two release requests on one item -> one wins, the other 409; cumulative amounts computed inside the
  transaction with a row lock on the item.
20 Variations high-value constant (`variations/service.py:96`) is fed from the project's DoA when a matrix exists
  (type `change`); without a matrix the constant stays (no behaviour change for projects that do not enrol).
21 Tenant isolation: links to documents of another project are refused 404; every handler `verify_project_access`.
22 Governance: readiness evidence "all items with `gate_code` = G are released or explicitly deferred" feeds module 1;
  the frame document `dev_commitment_matrix` is a CDE revision of the matrix export (PDF/XLSX) made at the gate, so the
  binding version is the snapshot, the live matrix keeps moving.
23 Everything exportable (PDF + XLSX via `core/register_export`), all labels i18n, audit via `log_activity` on every
  state change and every abort-terms edit.

## 5. API (envelope `{items,total,offset,limit}`, under `/v1/projects/{id}/commitments/...`)
matrix (get, set pinned schedule / enforcement / fx policy), authority assignments (list, put), items (list with
derived amounts, flags and exposure; get; create; patch; links add/remove; preconditions confirm), releases (request,
withdraw, history), abort terms (put per link/item), exposure (`?as_of=`), check (`POST .../check` used by guard points:
`{kind, document_id, new_amount, currency}` -> `ok | warn | block` with reasons), export (pdf/xlsx). Catalogue admin:
`/v1/commitments/authority-schedules` (list, clone, edit draft, publish, diff) through the shared resolver.
Guard is also a Python call `core.commitment_guard.check(...)` (registry, no-op when the module is absent).
Permissions registered on startup: `commitment.read`, `commitment.edit` (item owner or manager), `commitment.manage`
(schedule pin, enforcement, assignments), `commitment.catalogue` (admin). Release authority is never a permission:
it is the route's `entitled_deciders`.

## 6. Frontend (project tab, route nested under `/projects/:id/commitments`, no new top segment)
1 Matrix grid (AG Grid): item, type, cost code, cost bearer, planned / released / committed / spent, required tier,
  approver, preconditions (chips), latest decision date with overdue badge, cancellation/transfer option, residual loss.
  Group by cost code, gate, type. Totals in base currency with mixed-currency flag.
2 Item drawer: links to documents (open in their modules), release history with snapshots, abort terms editor with the
  computed exposure explained line by line, preconditions.
3 Release dialog: amount, tranche note, shows the required tier and who will decide before submitting.
4 Decision timeline: items ordered by latest decision date against gates (reads governance gates).
5 Authority schedule screen: bands table per type x tier, versions and diff, test calculator ("who approves 250k works?").
Strings in all locales in the same commit.

## 7. Validation rule set `commitment_release`
item_has_cost_code, item_has_planned_amount_source, release_within_authority (snapshot tier vs schedule),
committed_within_release (tolerance), decision_date_not_passed, abort_terms_present_for_committed,
document_linked_once, fx_rate_available, authority_schedule_bands_monotonic (catalogue), split_group_not_bypassing_tier.

## 8. Tests first (in this order)
1 Unit, pure: DoA evaluator (bands, types, cumulative, split groups, novelty, above top band, dated versions, currency
  conversion with frozen rate, missing rate); abort exposure calculator (each basis, unknown terms -> null, negative
  residual allowed, schedule by date and by progress); decision date (late_start, fallback, fixed); FSM table; catalogue
  loader (every shipped schedule validates, monotonic bands, every statutory figure has URL + review status, i18n keys).
2 Service with DB (tests/pg): request -> instance with tier steps -> completed -> released; rejection; partial tranches
  raising the tier; amended contract -> `re_release_required`; PO approved vs issued counting; reconciliation with
  `committed_by_cost_line`; delegation decides; expired assignment; concurrent requests (one 409); contingency drawdown.
3 Guard points (tests/pg, one per route in INTEGRATION 7, each in `off`/`warn`/`block`), including award subscribers not
  double-checking.
4 Security (tests/pg, IDOR lane + `tenant_isolation`): other tenant reads / links / releases -> 404; below-tier decider 403;
  four-eyes; editor cannot pin schedule. Add handlers to `tests/unit/test_idor_router_guards.py` and file to
  `ci-postgres.yml` list.
5 API contract (envelope, 404 vs 403, error codes). 6 Migration up/down/up on PG, tables only, indexes on models.
7 approval_routes: new kind accepted by model tuple AND schema Literal (plus the governance kinds, see INTEGRATION 0).
8 Frontend vitest: grid states, overdue badge, release dialog shows tier, exposure explanation, i18n keys resolve.
9 E2E: pin schedule, create item from a budget line, release in two tranches by two tiers, award tender, vary contract
  -> re-release flag, compute abort exposure.

## 9. Build order
tests 1 -> register catalogue kinds in module 1's registry (after module 1 commits it) -> catalogues -> models + migration -> evaluator,
exposure, FSM -> costmodel per-document committed + reconciliation test -> service (tests 2) -> approval_routes kind +
subscriber -> router + permissions (4-5) -> guard registry + guard points module by module (3), default `warn` ->
governance evidence hook + frame-document export -> frontend -> i18n -> E2E -> cloud CI -> browser check.

## 10. Open questions (resolved in Decisions below)
a Enforcement default: `warn` (proposed) or `block` for new projects; is `block` acceptable as the guard touches 7 routes
  in 6 modules?
b Commitment point: costmodel counts a PO from `issued`, finance from `approved`. Which one is "committed" for the matrix
  (proposal: release required before `approved`, committed counted from `issued`, and align finance later)?
c Scope of "company" for authority schedules: tenant (today the user id) or `legal_entities` (install-wide)? Proposal:
  tenant catalogue, optionally narrowed to a legal entity.
d Retire `variations.HIGH_VALUE_APPROVAL_THRESHOLD` into the DoA for enrolled projects (rule 20), or leave both?
e Abort statutory formulas (BGB 648 5 %, NEC4 A-amounts, FAR 49) in v1 as shipped bases, or only `custom` +
  `supply_cancellation_schedule` until a domain expert reviews them?
f FX policy default: project rates (matches costmodel) or the fx module's dated rate sets (auditable)?
g Per-tier routes generated by the module from assignments (proposed), or hand-built by managers only?

## Decisions on the open questions (binding for implementation)
a. Enforcement default per project is `warn`: users see the breach and why, nothing they did before stops working. A manager can switch a project to `block`. The guard is implemented once as a service function and called from the listed routes, award first; every call site gets a test for off / warn / block.
b. "Committed" = the point at which the platform's single commitment rule (`committed_by_cost_line`) counts it. One definition only; costmodel and finance must not disagree. If they disagree today, fix the divergence in the shared rule with a test, not in this module.
c. An authority schedule belongs to the tenant and may be narrowed to a legal entity (`legal_entity_id` optional). Most companies have one entity; groups get per-entity schedules.
d. The hidden 100,000 threshold in variations stays as the fallback when a project has no authority schedule; with a schedule, the schedule decides. Documented in both places, tested.
e. v1 ships custom abort terms and supplier cancellation schedules. Statutory abort formulas (BGB § 648, NEC4, FAR) ship as data marked `review_status: unconfirmed`, shown with that label, never applied silently.
f. FX: the fx module's dated rate sets (auditable), falling back to project rates when no dated set covers the date; the source used is shown next to every converted figure. A missing rate refuses, never 1:1.
g. The module generates one approval route per tier from the schedule (named after the tier, editable afterwards by a manager) so it works out of the box; regenerating after a schedule change asks before touching edited routes.
