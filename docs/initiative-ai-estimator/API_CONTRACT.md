# AI Estimate Builder - API Contract (oe_ai_estimator)

The frontend (`frontend/src/features/ai-estimator/`) builds against this
contract. It is the authoritative field-level spec for the REST surface the
backend service + router expose. Source of truth for shapes:
`backend/app/modules/ai_estimator/schemas.py`.

## Conventions

- Base path: `/api/v1/ai-estimator/` (auto-mounted by the module loader from the
  module slug `oe_ai_estimator`; the slash form `ai-estimator` is the route).
- Auth: every endpoint requires a bearer token. Every project-scoped endpoint
  runs `verify_project_access`, which returns `404` (not `403`) on deny so UUID
  existence is not leaked.
- Money: all monetary fields are emitted as plain decimal **strings** (e.g.
  `"1234.50"`), never floats. They are accepted as string or number on input.
  `null` means "no value" (for example, no grounded rate found - an honest "no
  rate", never a fabricated number).
- Confidence: a real retrieval/model-derived float in `[0, 1]`, or `null`. There
  is never a `0.5` placeholder. `confidence_band` is one of
  `high | medium | low | none`. Band thresholds (`high` >= 0.78, `medium` >=
  0.62) are also returned on the group list so the UI never hardcodes them.
- Currency: totals are never blended across currencies. Aggregate responses
  carry `currency_subtotals` (a `{currency: amount-string}` map) alongside a
  base-currency `grand_total`.
- IDs are UUID strings. Timestamps are ISO-8601 with timezone.

## Run FSM

`status`: `draft -> analyzing -> grouping -> matching -> review -> applied`,
plus terminal `failed` (carries `failure_reason`) and `cancelled`. Each stage
ends in a human-confirm checkpoint that must be accepted (via
`POST /runs/{id}/confirm`) before the next stage runs. `current_stage` is one of
`source | grouping | matching | assembly` (the four wizard steps).

## Graceful degradation

- No AI key: the run still works. Stages 1/2 skip the AI classification /
  refinement and use the deterministic extractor + signature grouping; stage 3
  falls back to top-1 of `rank()`. `ProgressResponse.degraded_reason =
  "no_ai_key"`; the UI shows a "AI not connected" banner linking to settings.
- No vectors (Qdrant absent or empty): `rank()` degrades to lexical matching;
  scores are honestly low. `degraded_reason = "no_vectors"`.
- No catalogue for the currency/region: `degraded_reason = "no_catalogue"`; the
  groups list returns rows with `null` rates and a "no rates loaded" empty
  state.
- Undecryptable key (JWT rotation): the run does not 500; it degrades to the
  deterministic path and `ReadinessResponse.message` says to re-enter the key.

---

## Endpoints

### POST `/runs`
Create a run and start stage 1 (source understanding).

Request - `RunCreate`:
| field | type | notes |
|---|---|---|
| `project_id` | uuid | required |
| `name` | string \| null | auto-derived from source when omitted |
| `source` | enum | `text \| excel \| gaeb \| bim \| dwg \| pdf \| photo \| documents` (default `text`) |
| `agent_name` | string \| null | user-selected agent slug; `null` = deterministic path |
| `text_input` | string \| null | read when `source=text` |
| `file_refs` | string[] | already-uploaded refs (`excel`/`gaeb`/`pdf`/`photo`) |
| `rows` | object[] | pre-parsed BoQ/line rows (`{description, qty?, unit?, code?, category?}`) |
| `bim_model_ids` | uuid[] | read when `source=bim` |
| `document_ids` | uuid[] | read when `source=documents` |
| `catalogue_id` | string \| null | optional hint; AI suggests at checkpoint #1 |
| `region` | string \| null | optional hint |
| `currency` | string \| null | optional hint |
| `construction_stage` | enum \| null | one of the 12 OmniClass stages |

Response `201` - `RunRead` (see below). `status` is `analyzing` once stage 1 starts.

### GET `/runs?project_id=&limit=&offset=`
List runs for the resume picker, newest-first.

Query: `project_id` (uuid, optional - scopes to project), `limit` (default 50),
`offset` (default 0).

Response `200` - `RunListResponse`:
| field | type |
|---|---|
| `total` | int |
| `runs` | `RunSummary[]` |

`RunSummary`:
| field | type | notes |
|---|---|---|
| `id` | uuid | |
| `project_id` | uuid | |
| `name` | string \| null | |
| `source` | enum \| null | |
| `status` | RunStatus | |
| `current_stage` | StageName | |
| `group_count` | int | |
| `confirmed_count` | int | |
| `applied_count` | int | |
| `model_used` | string \| null | |
| `grand_total` | money-string \| null | |
| `currency` | string \| null | |
| `created_at` / `updated_at` | datetime | |

### GET `/runs/{id}`
Read full run state.

Response `200` - `RunRead`:
| field | type | notes |
|---|---|---|
| `id` | uuid | |
| `project_id` | uuid | |
| `user_id` | uuid | |
| `name` | string \| null | |
| `agent_name` | string \| null | |
| `status` | RunStatus | |
| `current_stage` | StageName | |
| `checkpoints` | object | per-stage `{accepted_at, by}` |
| `source_inputs` | object | raw source refs |
| `detected_source` | object | `{type, confidence, disciplines[], summary}` (stage 1) |
| `suggested_config` | object | `{catalogue_id, region, currency, group_by[], construction_stage}` |
| `catalogue_id` | string \| null | confirmed config |
| `region` | string \| null | |
| `currency` | string \| null | |
| `group_by` | string[] | |
| `construction_stage` | enum \| null | |
| `provider` | string \| null | provider that actually ran |
| `model_used` | string \| null | model that actually ran |
| `total_tokens` | int | |
| `cost_usd_estimate` | float | |
| `duration_ms` | int | |
| `validation_report` | object \| null | last report envelope |
| `grand_total` | money-string \| null | |
| `currency_subtotals` | `{currency: money-string}` | never-blend totals |
| `completeness_score` | float \| null | CHECK_SCOPE advisory |
| `boq_id` | uuid \| null | set on apply |
| `failure_reason` | string \| null | |
| `created_at` / `updated_at` | datetime | |

### POST `/runs/{id}/sources`
Attach more sources to a `draft` run before analysis.

Request - `AddSourcesRequest` (`source` + the same source-bearing fields as
`RunCreate`). Response `200` - `RunRead`.

### POST `/runs/{id}/analyze`
Run stage 1: normalise sources to envelopes + AI source classification.

Request - `AnalyzeRequest`: `{ "use_ai": bool (default true) }`. Response `200`
- `RunRead` with `detected_source` + `suggested_config` populated and
`status=analyzing` complete (awaiting checkpoint #1).

### POST `/runs/{id}/confirm`
Accept a stage checkpoint, optionally editing the stage outputs, and advance.

Request - `StageConfirmRequest`:
| field | type | notes |
|---|---|---|
| `stage` | StageName | the checkpoint being accepted |
| `edits` | object | stage `source`: `{catalogue_id?, region?, currency?, group_by?, construction_stage?}`; other stages accept as-is |

Behaviour: accepting `source` writes the confirmed config and runs stage 2
(grouping); accepting `grouping` advances to stage 3 readiness; accepting
`matching` builds the stage 4 preview; accepting `assembly` is the precondition
for `apply`. Response `200` - `RunRead`.

### GET `/runs/{id}/progress`
Poll target (the frontend polls on an interval while a stage runs).

Response `200` - `ProgressResponse`:
| field | type | notes |
|---|---|---|
| `run_id` | uuid | |
| `status` | RunStatus | |
| `current_stage` | StageName | |
| `stages` | `StageState[]` | `{stage, title, status: pending\|active\|complete\|error, accepted_at}` |
| `group_count` | int | |
| `matched_count` | int | groups with a chosen candidate |
| `confirmed_count` | int | |
| `failure_reason` | string \| null | |
| `ai_connected` | bool | |
| `vector_ready` | bool | catalogue has > 100 vectors |
| `degraded_reason` | string \| null | `no_ai_key \| no_vectors \| no_catalogue \| null` |
| `provider` | string \| null | |
| `model_used` | string \| null | |
| `recent_steps` | `StepOut[]` | most-recent N timeline steps |

### GET `/runs/{id}/steps?limit=`
Full run timeline (ReAct / pipeline events).

Response `200` - `StepOut[]`:
| field | type | notes |
|---|---|---|
| `id` | uuid | |
| `stage` | StageName | |
| `step_idx` | int | monotonic |
| `role` | enum | `thought \| tool_call \| observation \| answer \| error \| stage_complete` |
| `content` | object \| array \| string \| null | role-specific payload |
| `token_count` | int | |
| `took_ms` | int \| null | |
| `created_at` | datetime | |

### GET `/runs/{id}/groups?status=`
List the run's quantity groups (stage 2/3 grid). Optional repeated `status`
query to filter.

Response `200` - `GroupListResponse`:
| field | type | notes |
|---|---|---|
| `run_id` | uuid | |
| `total` | int | |
| `groups` | `GroupSummary[]` | |
| `summary` | `{status: count}` | |
| `confidence_high_threshold` | float | 0.78 |
| `confidence_medium_threshold` | float | 0.62 |

`GroupSummary`:
| field | type | notes |
|---|---|---|
| `id` | uuid | |
| `group_key` | string | |
| `description` | string \| null | clean human label |
| `trade` | string \| null | taxonomy bucket |
| `signature` | string \| null | |
| `element_count` | int | |
| `quantities` | `{unit: number}` | rolled-up canonical quantities |
| `chosen_unit` | string \| null | |
| `primary_quantity` | float | the quantity for the chosen unit |
| `chosen_code` | string \| null | grounded rate code (null until matched) |
| `unit_rate` | money-string \| null | |
| `currency` | string \| null | |
| `score` | float \| null | raw retrieval score |
| `confidence` | float \| null | derived confidence |
| `confidence_band` | enum | `high\|medium\|low\|none` |
| `match_method` | string \| null | `vector\|lexical\|resources\|llm\|manual\|auto` |
| `status` | GroupStatus | `unmatched\|suggested\|confirmed\|overridden\|skipped\|tbd\|needs_human\|applied` |
| `boq_position_id` | uuid \| null | |
| `sort_order` | int | |

### GET `/runs/{id}/groups/{gid}`
Full group detail for the per-group match-review card / slide-over.

Response `200` - `GroupDetail` (all `GroupSummary` fields plus):
| field | type | notes |
|---|---|---|
| `run_id` | uuid | |
| `element_ids` | string[] | |
| `envelope` | object | serialised ElementEnvelope |
| `resources` | `ResourceOut[]` | chosen candidate breakdown |
| `candidates` | `CandidateOut[]` | top-K considered, for override |
| `confirmed_by` | uuid \| null | |
| `confirmed_at` | datetime \| null | |
| `notes` | string \| null | |

`CandidateOut`: `{candidate_id, code, description, unit, unit_rate (money-string),
currency, score, confidence_band}`.
`ResourceOut`: `{name, code, unit, factor, quantity, unit_rate (money-string),
type}` where `type` is `labor\|material\|equipment\|operator\|electricity\|other`.

### PATCH `/runs/{id}/groups/{gid}`
Edit a group (stage 2 quantities/unit) or override its match (stage 3).

Request - `GroupUpdate`:
| field | type | notes |
|---|---|---|
| `chosen_unit` | string \| null | stage 2 |
| `description` | string \| null | stage 2 |
| `quantities` | `{unit: number}` \| null | stage 2 |
| `candidate_id` | string \| null | stage 3 override; MUST be an id already in `candidates` (no fabricated codes) |
| `status` | GroupStatus \| null | e.g. `skipped` |
| `notes` | string \| null | |

Response `200` - `GroupDetail`.

### POST `/runs/{id}/groups/merge`
Merge several groups into one (stage 2). Request - `GroupMergeRequest`:
`{group_ids: uuid[], new_description?: string}`. Response `200` -
`GroupListResponse`.

### POST `/runs/{id}/groups/split`
Split elements out of a group (stage 2). Request - `GroupSplitRequest`:
`{element_ids: string[], new_description?: string}`. Response `200` -
`GroupListResponse`.

### POST `/runs/{id}/groups/{gid}/rematch`
Re-run matching for a single group (e.g. after editing its description).

Request - `RunMatchRequest` (see below; `group_ids` ignored, the path id wins).
Response `200` - `GroupDetail`.

### POST `/runs/{id}/match`
Run stage 3 - find a grounded rate per group.

Request - `RunMatchRequest`:
| field | type | notes |
|---|---|---|
| `group_ids` | uuid[] \| null | null = pick the N largest groups |
| `top_k` | int | 1-50, default 10 |
| `use_reranker` | bool | default true (BGE cross-encoder) |
| `use_agent` | bool | default true; false forces deterministic top-1 |
| `max_groups` | int | 1-500, default 25 |

Response `200` - `GroupListResponse`. Matching never raises for normal input;
groups that find no grounded rate come back `status=needs_human` with `null`
rate, never silently dropped.

### POST `/runs/{id}/groups/{gid}/confirm`
Confirm one group's chosen candidate as the human decision.

Request - `ConfirmGroupRequest`:
`{candidate_id?: string, confidence?: float, save_to_template_library?: bool}`.
Response `200` - `GroupDetail` with `status=confirmed`.

### POST `/runs/{id}/bulk-confirm`
Confirm every suggested group at/above a confidence threshold.

Request - `BulkConfirmRequest`: `{threshold: float (default 0.8), group_ids?:
uuid[]}`. Response `200` - `BulkConfirmResponse`: `{confirmed: int, skipped:
int, group_ids: uuid[]}`.

### GET `/runs/{id}/preview`
Build/return the stage 4 assembly preview - NOT yet written to a BOQ.

Response `200` - `PreviewResponse`:
| field | type | notes |
|---|---|---|
| `run_id` | uuid | |
| `positions` | `PreviewPositionRow[]` | proposed positions, `confirmed:false` |
| `grand_total` | money-string | base currency |
| `currency` | string \| null | |
| `currency_subtotals` | `{currency: money-string}` | never-blend |
| `validation` | `ValidationReportOut` \| null | traffic-light |
| `completeness_score` | float \| null | |
| `missing_items` | string[] | CHECK_SCOPE advisory |
| `can_apply` | bool | false when any ERROR-severity rule fails |

`PreviewPositionRow`: `{group_id, group_key, section_path[], description, unit,
quantity, unit_rate (money-string), currency, line_total (money-string),
confidence, confidence_band, resources: PreviewResourceRow[], confirmed}`.
`PreviewResourceRow`: `{description, factor, quantity, unit, unit_rate
(money-string), type}`.
`ValidationReportOut`: `{status: passed|warnings|errors|skipped, score (float|null
- null when skipped, never 1.0), rule_set, passed[], warnings[], errors[]}` where
each result is `{rule_id, status, severity, message, element_ref}`.

### POST `/runs/{id}/apply`
Write the assembled estimate to a BOQ. Never auto-applies; requires the
`assembly` checkpoint accepted and `can_apply=true`. ERROR-severity validation
rules block the write.

Request - `ApplyRequest`:
| field | type | notes |
|---|---|---|
| `target_boq_id` | uuid \| null | null = create a new BOQ |
| `boq_name` | string \| null | name for a new BOQ |
| `append` | bool | append to an existing BOQ |
| `organize_by_classification` | bool | DIN276/etc. hierarchy (default true) |
| `group_ids` | uuid[] \| null | restrict to a subset of confirmed groups |

Response `200` - `ApplyResponse`: `{run_id, boq_id, positions_created,
grand_total (money-string), currency, currency_subtotals}`. Written positions
carry `source='ai_precise_estimate'`, `confidence` = the group's real float
(or null), `validation_status='pending'`, `cad_element_ids` = the group's
element ids, and resources in `metadata_['resources']`.

### POST `/runs/{id}/cancel`
Cancel a run. Response `200` - `RunRead` with `status=cancelled`.

### GET `/runs/{id}/readiness`
Pre-flight check before starting (or while configuring) a run.

Response `200` - `ReadinessResponse`:
| field | type | notes |
|---|---|---|
| `ai_connected` | bool | |
| `provider` | string \| null | |
| `model_used` | string \| null | |
| `vector_ready` | bool | catalogue has > 100 vectors |
| `vector_count` | int | |
| `catalogues_available` | int | |
| `message` | string \| null | plain-prose guidance when something is missing |

### GET `/catalogues`
Reuse of the CWICR v3 region registry for the source-config step.

Response `200` - `CatalogueOption[]`: `{id, label, currency, region,
default_classification_standard}`.

### GET `/qdrant/health`
Reuse of the shared Qdrant health probe so the wizard can show vector-DB status
without coupling to the match-elements feature. Response `200` - the shared
Qdrant health envelope (`{status, collections, vector_counts, ...}`).
