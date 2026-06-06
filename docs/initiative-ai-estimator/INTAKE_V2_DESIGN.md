# AI Estimate Builder - Conversational Intake v2 (Design)

Status: design, implementation-ready. No source code changed by this document.

This document specifies the v2 conversational intake for the AI Estimate
Builder module (`oe_ai_estimator`). The goal is a single sentence like
"сделай мне смету кухни" or "ремонт дома 120м2" becoming a professional,
vector-DB-grounded estimate, through a short guided dialogue that a human
confirms before any numbers are produced.

It builds strictly on the existing pipeline. v1 already does Understand ->
Group -> Match -> Assemble over an `AiEstimatorRun`. v2 adds a real intake
layer in front of stage 1 that turns a vague free-text request into a
confirmed parameter sheet plus an editable element-group board, so the rest of
the verified pipeline (grouping, grounded matching, FX rollup, validation,
human-confirmed apply) runs unchanged.

Everything below is grounded in the real code paths and in live samples taken
from the running backend (`http://localhost:8000`, version 6.10.0, 120 modules)
and Qdrant (`http://localhost:6333`).

---

## 0. Founder-locked decisions (carried verbatim)

1. Max 3 clarification rounds in the AI dialogue.
2. No AI key configured -> curated parameter questionnaires per project type
   (the offline path goes through the same state machine).
3. Hybrid checklists: curated work-package checklists PLUS vector-DB-grounded
   group shaping. We probe our vector DB hard and pull as many real positions
   into the final estimate as we honestly can (maximize recall of real DB
   positions).
4. AI proposes, human confirms: element groups are visible, editable,
   deletable and addable by the user before estimation.
5. Works decompose into stages, like a professional estimator or foreman.

None of these are reopened here.

---

## 1. What exists today (grounded inventory)

### 1.1 The module

Backend: `backend/app/modules/ai_estimator/`

- `models.py` - three tables: `oe_ai_estimator_run`, `oe_ai_estimator_group`,
  `oe_ai_estimator_step`
  (`backend/app/modules/ai_estimator/models.py:50`, `:224`, `:357`).
- `service.py` - the orchestrator (`AiEstimatorService`,
  `backend/app/modules/ai_estimator/service.py:178`). The four-stage FSM:
  `analyze` (`:244`), `confirm_stage` (`:607`), `_build_groups` (`:659`),
  `run_matching` (`:804`), `build_preview` (`:1487`), `apply` (`:1695`).
- `extractors.py` - source normalisers, including the deterministic free-text
  parser `parse_text_scope` (`backend/app/modules/ai_estimator/extractors.py:639`).
- `taxonomy.py` - the deterministic 12-trade keyword classifier
  `classify_trade` (`backend/app/modules/ai_estimator/taxonomy.py:150`).
- `prompts.py` - the three LLM passes: SOURCE_CLASSIFY, GROUP_REFINE,
  MATCH_REASONING (`backend/app/modules/ai_estimator/prompts.py:33`, `:69`, `:94`).
- `schemas.py`, `router.py`, `repository.py`, `events.py`, `tools.py`,
  `permissions.py`, `validators.py`, `manifest.py`.

Frontend: `frontend/src/features/ai-estimator/`

- `AiEstimatorPage.tsx`, `api.ts`, `meta.ts`, `helpers.ts`.
- Stage components: `Stage1Source.tsx` (intake + confirm checkpoint #1),
  `Stage2Groups.tsx`, `Stage3Match.tsx`, `Stage4Review.tsx`, plus
  `StageRail.tsx`, `StageTimeline.tsx`, drawers and banners.

### 1.2 The current free-text path and why it is not enough

`RunCreate.source = "text"` carries `text_input`
(`backend/app/modules/ai_estimator/schemas.py:116`). On `analyze`,
`_collect_envelopes` calls `_normalise_sources`, which for text calls
`parse_text_scope` (`service.py:343`).

`parse_text_scope` is a deterministic line-item parser. It splits a scope into
clauses and reads a leading "`<number> <unit>`" off each clause
(`extractors.py:639`). So:

- "120 m2 brick walls, 2 steel doors, 30 m3 C25/30 foundation" becomes three
  honest envelopes (120 m2, 2 pcs, 30 m3). This works well.
- "сделай мне смету кухни" becomes one envelope with description "сделай мне
  смету кухни", no quantity, trade `other`. There is no kitchen scope, no work
  packages, no quantities. The estimate it produces is empty or meaningless.
- "ремонт дома 120м2" becomes one envelope: description "ремонт дома 120м2",
  one number 120 read as `area_m2`, trade `other`. A single 120 m2 line with no
  work decomposition is not an estimate.

The v1 stage-1 LLM pass (`_classify_source`, `service.py:462`) only classifies
the source kind / disciplines / region / currency from a digest. It does NOT
ask the user anything, does NOT extract project type or parameters, and does
NOT decompose a vague request into work. That is the gap v2 fills.

The `analyze` step is also fully synchronous in `create_run`
(`router.py:92` calls `service.analyze(run, use_ai=True)`), so there is no
turn-taking. v2 introduces an explicit dialogue loop before grouping runs.

### 1.3 The grounded retrieval stack (reused unchanged)

`run_matching` (`service.py:804`) builds an `ElementEnvelope`
(`backend/app/core/match_service/envelope.py:32`) per group and calls
`rank(MatchRequest, db)` from `backend/app/core/match_service/ranker_qdrant.py`.

The ranker:

1. Loads `MatchProjectSettings`, resolves the bound catalogue.
2. Builds a `SearchPlan` via `build_search_plan`
   (`backend/app/modules/costs/query_builder.py:464`): a `dense_query`
   (the envelope description, truncated to 512 chars, `query_builder.py:497`),
   `hard_filters` and `soft_boosts`.
3. Hard filters that fire only when the bound collection actually carries the
   field (`_collection_carries`, `query_builder.py:505`): `is_abstract=False`,
   `department_code` (DIN 276 2-digit prefix), `unit_type`
   (`Area`/`Volume`/`Linear`/`Mass`/`Count`, `query_builder.py:113`),
   `ifc_class`, `ifc_predefined_type`, `construction_stage`, and the
   `is_external`/`is_loadbearing`/`is_structural` booleans.
4. One hybrid Qdrant call: dense + sparse (+ optional resources) fused by
   native RRF (`qdrant_adapter.search`, `qdrant_adapter.py:963`).
5. Narrow post-search boost stack: classifier + unit + region
   (`ranker_qdrant.py:82`).
6. BGE-M3 rerank (`reranker_bge.py`) when `use_reranker=True`; optional LLM
   rerank.
7. Confidence band via `confidence_band_for` (`envelope.py:193`); HIGH >= 0.78,
   MEDIUM >= 0.62 (`service.py:58`).

Catalogue routing: `country_to_collection` maps a region to a language
collection (`qdrant_adapter.py:222`); `country_filter_for` pins the ISO head
("MX" out of "MX_MEXICO") as a payload predicate but returns None for a bare
language code so all countries in a language stay reachable
(`qdrant_adapter.py:310`). The match-catalog country-filter bug fixed earlier
was exactly here: pinning a country that does not exist in the US-only
`cwicr_en_v3` collection returned 0 results. Lesson carried into v2 below.

Revit -> IFC keyword fallback: `normalize_to_ifc_class` and
`canonical_ifc_class` (`query_builder.py:236`) collapse Revit OST categories
and IFC refinements onto the catalogue's indexed class.

Net: rates are never invented. A group with no grounded candidate comes back
`needs_human` (`service.py:1037`). v2 keeps this invariant: the dialogue and
group composer only ever shape the QUERY; rates still come solely from the DB.

---

## 2. The vector DB reality (the surprising part that shapes the design)

This is the most consequential research finding and it changes how groups must
be phrased. All facts below are from the live Qdrant.

### 2.1 Collections present

`GET /collections` returned, among the OE app collections:

- `cwicr_en_v3` - 55,719 points, 1024-dim dense + sparse, US-only.
- `cwicr_en_v3_enriched` - 20,000 points, adds `description` / `passage_text`
  natural-language fields and a `construction_stage` payload field.
- `cwicr_mn_v3` - Mongolian.

There is no `cwicr_ru_v3` or `cwicr_de_v3` present on this install. Per
`country_to_collection` (`qdrant_adapter.py:234`), any RU/DE project falls back
to `cwicr_en_v3`. BGE-M3 is multilingual so cross-lang retrieval still works
from a Russian or German query string against English passages, but the rate
DATA is US. This is acceptable for the design (honest "no rate for your
currency" is the fallback), but the intake must not promise local rates it
cannot ground.

### 2.2 The payload has NO free description in the canonical collection

A scroll of `cwicr_en_v3` returns payloads like:

```
rate_code: "RILI_KANE_KAKAME_KAME"        (obfuscated synthetic token)
collection_name: "Motorways"
department_code: "NE"
masterformat_division: "32 10 00"
rate_unit: "100 CY"
category_type: "CONSTRUCTION WORK"
unit_type: "Volume"
material_class: "ReinforcedConcrete"
construction_stage: "13_Sitework"
uniformat_group: "G_Sitework"
is_abstract / is_structural / is_finishing / ... (booleans)
```

There is NO human description field. The searchable text lives only in the
dense/sparse vectors, which were embedded from a SYNTHESISED string. We can see
that synthesised string in the enriched collection's `description` field:

```
"Motorways. Reinforced Concrete. Construction Work. Precast. Sitework.
 Volume (100 CY). MasterFormat 32 10 00 Exterior Improvements"

"Stucco work. Ifc Covering. Cladding. Walls. Repair And Construction Works.
 Demolition. Interiors. Linear (100 LF). MasterFormat 09 24 00 Finishes"

"Brick and block structures. Brick. Ifc Wall. Solidwall. Walls.
 Construction Work. Manual. Envelope. Shell. Volume (CY).
 MasterFormat 04 20 00 Masonry"
```

So the embedded text is a keyword-salad of classification axes: a
collection_name, a material, an IFC class, an OST category, a work type
(Construction Work / Repair And Construction Works / Equipment Installation),
an installation method, a construction stage, a Uniformat group, the unit_type
with the unit, and the MasterFormat division name.

Implication for v2 group phrasing: a query phrased like a natural sentence
("Install ceramic wall tiles in the kitchen, two coats of grout") is NOT the
strongest possible query against this collection. The strongest query mirrors
the synthesised vocabulary: a short noun-led phrase combining the material, the
work type, the element, and the trade, e.g. "Ceramic tiling finishes wall
interior". The element-group composer (section 5) probes the DB to LEARN the
phrasing that scores, rather than assuming the natural sentence is best.

### 2.3 A minority of enriched rows DO carry rich human text

About 0.85 percent of the 2,000 enriched rows sampled (17 of 2,000) carry a
genuinely descriptive `description` using a `|` delimiter:

```
"EXTERIOR FACADE CLADDING | Installation of ventilated curtain walls using an
 aluminum alloy curtain wall system without insulation, fixed to the floor
 slab | Facade cladding with decorative tongue-and-groove products ..."

"Laying of wall sections (cornices, belts, etc.) made of brick and ceramic and
 silicate stones with facing with facing brick | wall thickness 640 mm with
 floor height up to 4 m"

"Installation of steel panel radiators | over 1000 to 1600 mm"
"Masonry of external and internal brick walls of lightweight structures |
 640 mm thick for floor heights over 4 m"
```

These rich rows ARE residential / building-trade flavoured (radiators, brick
walls with floor heights, facade cladding). They confirm residential vocabulary
exists. But they are rare in the canonical collection, so a v2 design that
relies on them would be fragile. We treat them as a bonus, not a foundation.

### 2.4 The catalogue is dominated by heavy civil / industrial work

Faceting `cwicr_en_v3` on `category_type` (full collection):

```
29,616  CONSTRUCTION WORK
19,155  EQUIPMENT INSTALLATION
 3,919  REPAIR AND CONSTRUCTION WORKS
 2,604  COMMISSIONING
   425  MAJOR EQUIPMENT REPAIRS
```

Faceting on `masterformat_division` (top of full collection):

```
5,657  31 70 00  Tunnel Excavation / Earthwork
3,544  41 00 00  Material Processing and Handling Equipment
3,405  33 10 00  Water Utilities
2,878  40 05 00  Process Integration / piping
2,341  31 00 00  Earthwork
2,228  26 00 00  Electrical
2,192  35 00 00  Waterway and Marine Construction
2,008  48 00 00  Electrical Power Generation
1,877  27 00 00  Communications
1,835  34 70 00  Transportation
```

EQUIPMENT INSTALLATION is 34 percent of the catalogue. The top MasterFormat
divisions are tunnels, process plants, utilities, power generation, marine,
railways. This is a civil/industrial cost book, not a residential renovation
price list.

### 2.5 But the residential / fit-out trades DO exist, with usable counts

Faceting `collection_name` to count rows per trade (full collection):

```
2,180  Electrical installations
1,004  Finishing works
  527  Ventilation and air conditioning
  517  Stucco work
  467  Wooden structures
  383  Internal sanitary and technical work
  371  Painting work
  371  Floors
  309  Brick and block structures
```

So a kitchen / bathroom / apartment renovation CAN be grounded: tiling and
plastering map to Stucco work (517) and Finishing works (1,004); painting to
Painting work (371); flooring/screed to Floors (371); plumbing to Internal
sanitary and technical work (383); ventilation to Ventilation and air
conditioning (527); electrical sockets/wiring to Electrical installations
(2,180); partitions to Brick and block structures (309) and Wooden structures
(467). These are the target landing zones the element-group composer aims at.

### 2.6 Empirical retrieval note

A standalone offline encode-and-query loop could not run cleanly in the sandbox
(the BGE-M3 model segfaulted when loaded a second time outside the warm server
process; the int8 ONNX repo is missing weights and falls back to FP32). The
warm backend at :8000 holds the model and serves matching fine. The structural
evidence above (description vocabulary + collection distribution + facet counts)
is sufficient to drive the design, and section 8 specifies a golden-fixture
recall harness that runs IN-process against the live ranker to validate it.

Design consequence (the headline): we must NOT trust a single natural-sentence
probe to find residential work. We must probe with MULTIPLE phrasings per work
package, in the catalogue's own keyword-salad vocabulary, keep the phrasings
that score, and surface the coverage gaps honestly. That is exactly what the
hybrid checklist + live-probe composer does.

---

## 3. Project-type taxonomy and per-type questionnaires

Ten project types. Each is a curated definition consisting of: (a) a label and
synonyms in RU/EN/DE used for free-text type detection, (b) a parameter
questionnaire where every parameter is justified by the quantity it unlocks,
and (c) a curated work-package checklist with default stages (section 4) and
candidate vector probes (section 5).

This taxonomy lives in a new backend module file
`backend/app/modules/ai_estimator/project_types.py` as plain data (no ML), the
same pattern as `taxonomy.py`. UI labels go through i18n
(`aiest.ptype.<key>`); the data file carries English defaults plus the
detection synonyms.

### 3.1 The type registry (shape)

```python
@dataclass(frozen=True)
class ProjectParam:
    key: str                 # "floor_area_m2"
    kind: str                # number | choice | bool | length
    unit: str | None         # "m2" | "m" | None
    required: bool
    choices: tuple[str, ...] | None
    # which quantity formulas this param feeds (section 6), for the
    # "why we ask" tooltip and for skipping a question whose answer is
    # already known from the free text.
    unlocks: tuple[str, ...]
    round_group: int         # clarification round 1, 2 or 3

@dataclass(frozen=True)
class WorkPackage:
    key: str                 # "wall_tiling"
    trade: str               # one of taxonomy.TRADE_KEYWORDS keys
    default_on: bool         # in the curated checklist by default
    stages: tuple[str, ...]  # ordered foreman stages (section 4)
    probes: tuple[str, ...]  # candidate vector phrasings (section 5)
    qty_formula: str         # formula id (section 6)
    unit: str                # m2 | m | m3 | pcs | lsum

@dataclass(frozen=True)
class ProjectType:
    key: str
    synonyms_en / _ru / _de: tuple[str, ...]
    params: tuple[ProjectParam, ...]
    packages: tuple[WorkPackage, ...]
    default_unit_system: str   # metric
```

### 3.2 The ten types and their parameters

For each type the table lists the key parameters and, crucially, what each
unlocks. "Round" is which of the max-3 clarification rounds the question lands
in (round 1 = the few questions that unlock the most quantity; round 3 =
nice-to-have refinements only asked if rounds 1-2 left confidence low).

#### kitchen_reno (Kitchen renovation)
syn: kitchen, кухня, ремонт кухни, Kueche, Kuechenumbau

| param | kind | unlocks | round |
|---|---|---|---|
| floor_area_m2 | number m2 | floor screed/tiling area, ceiling area, paint area base | 1 |
| ceiling_height_m | length m (default 2.7) | wall area = perimeter x height | 1 |
| perimeter_m | length m (derived from area if absent) | wall tiling/paint area | 2 |
| finish_level | choice [economy, standard, premium] | which packages default-on, unit picks | 1 |
| demolition | bool | demo packages on/off, debris volume | 1 |
| wet_zone_tiling | bool (default true) | wall tiling area vs paint | 2 |
| replace_plumbing | bool | sink/supply/drain packages | 2 |
| replace_electrical | bool | sockets/wiring packages | 2 |
| cabinets_lm | length m | casework count/length | 3 |

#### bathroom_reno (Bathroom renovation)
syn: bathroom, санузел, ванная, ремонт ванной, Bad, Badezimmer

Params: floor_area_m2 (1), ceiling_height_m (1), finish_level (1),
demolition (1), full_tiling (bool default true; unlocks wall tiling = full
wall area) (1), waterproofing (bool default true; unlocks tanking m2) (2),
fixtures_count (WC/basin/shower/bath count -> sanitary install pcs) (2),
heated_floor (bool; unlocks underfloor heating m2) (3),
ventilation (bool; extract fan + duct) (3).

#### apartment_reno (Full apartment renovation)
syn: apartment, квартира, ремонт квартиры, Wohnung, Wohnungssanierung

Params: floor_area_m2 (1), room_count (1; drives door count, fixture spread),
ceiling_height_m (1), finish_level (1), demolition (strip-out scope) (1),
wet_rooms_count (1; bathrooms/kitchens drive tiling+plumbing),
reconfigure_partitions (bool; new partition lm) (2),
replace_windows (bool + count) (2), replace_doors (count) (2),
rewire (bool) (2), replumb (bool) (2), hvac (choice [none, radiators,
underfloor, split]) (3), flooring_type (choice) (3).

#### house_new (Single-family house, new build)
syn: house, дом, новый дом, строительство дома, Einfamilienhaus, Neubau

Params: gross_floor_area_m2 (1), storeys (1), footprint_m2 (derived) (1),
wall_construction (choice [masonry, timber_frame, concrete, SIP]) (1; drives
structure + envelope packages), roof_type (choice [pitched, flat]) (1),
foundation_type (choice [strip, raft, piles]) (2), basement (bool) (2),
ceiling_height_m (2), finish_level (2), garage (bool) (3),
mep_scope (choice) (3), site_area_m2 (landscaping/sitework) (3).

#### roof (Roof works)
syn: roof, кровля, крыша, ремонт кровли, Dach, Dachsanierung

Params: roof_area_m2 (1; the dominant driver), roof_type (choice [pitched,
flat]) (1), pitch_deg (length/number; converts plan area to slope area) (2),
covering (choice [tile, metal, membrane, shingle]) (1; drives covering m2 unit
rate), insulation (bool + thickness) (2), structure_replacement (bool;
rafters/sheathing) (2), gutters_lm (3), skylights_count (3),
demolition_existing (bool; strip old covering) (1).

#### facade (Facade / external wall)
syn: facade, фасад, отделка фасада, Fassade, Fassadensanierung

Params: facade_area_m2 (1), system (choice [render_ETICS, ventilated,
cladding, paint_only]) (1; the single biggest unit-rate switch),
insulation_thickness_mm (2), openings_area_m2 (1; subtracted from gross),
scaffolding (bool default true; lump or m2) (1), substrate_prep (choice
[none, repair, full_strip]) (2), storeys (scaffold height) (2),
plinth_treatment (bool) (3), color_coats (number) (3).

#### extension (Building extension / Anbau)
syn: extension, пристройка, расширение, Anbau, Erweiterung

Params: extension_floor_area_m2 (1), storeys (1), wall_construction (1),
roof_type (1), foundation_type (2), connect_to_existing (bool; breakthrough
+ making-good) (1), ceiling_height_m (2), finish_level (2),
mep_extension (choice) (3), excavation_depth_m (3).

#### commercial_fitout (Commercial fit-out)
syn: fit-out, fitout, офис, ремонт офиса, Ausbau, Mieterausbau

Params: floor_area_m2 (1), category (choice [shell_and_core, cat_a, cat_b]) (1),
ceiling_type (choice [suspended, exposed, MF]) (1; ceiling m2 + grid),
partition_lm (1; demountable vs studwork), raised_floor (bool) (2),
hvac_scope (choice [none, vav, fcu, vrf]) (2; m2 or zone count),
small_power_density (choice) (2; sockets per m2),
lighting (choice) (2), sprinklers (bool) (3), data_outlets_count (3),
finishes_level (2).

#### landscaping (Landscaping / external works)
syn: landscaping, благоустройство, озеленение, ландшафт, Garten,
Aussenanlagen

Params: site_area_m2 (1), paving_area_m2 (1; the big driver),
paving_type (choice [block, asphalt, gravel, concrete]) (1),
planting_area_m2 (1), turf_area_m2 (2), fencing_lm (1),
retaining_wall_lm (2), drainage (bool) (2), lighting (bool) (3),
irrigation (bool) (3), earthworks_volume_m3 (3).

#### mep_retrofit (MEP retrofit)
syn: MEP, инженерные сети, замена коммуникаций, Haustechnik, TGA-Sanierung

Params: floor_area_m2 (1), disciplines (multi-choice [electrical, plumbing,
heating, ventilation, cooling]) (1; turns whole package families on/off),
building_type (choice [residential, office, retail]) (1),
heating_system (choice [radiators, underfloor, air]) (2; radiator count or
m2), points_density (sockets/outlets per m2) (2), riser_count (2),
plant_replacement (bool; boiler/AHU as pcs/lump) (1),
ceiling_access (choice [suspended, surface]) (3), commissioning (bool) (3).

### 3.3 Parameter justification principle

Every parameter must map to at least one quantity in section 6. If a parameter
unlocks nothing, it is cut. This is enforced by a unit test that asserts every
`ProjectParam.unlocks` references a real formula id and every `WorkPackage`
references a real `qty_formula`.

The "why we ask" tooltip in the UI reads `param.unlocks` so the user always
sees the payoff of answering, e.g. ceiling_height_m -> "used to compute wall
area (perimeter x height) for tiling and painting".

---

## 4. Work-stage decomposition (the foreman logic)

Founder decision 5: works decompose into stages like a professional estimator
would. We reuse the existing 12 OmniClass-aligned construction stages already
in the schema (`ConstructionStage`, `schemas.py:92`) AND a finer per-package
ordered build sequence. The catalogue carries `construction_stage` as a payload
field on the enriched collection (values like `02_Demolition`, `10_Finishes`,
seen in section 2), so the stage is also a usable hard filter / soft boost.

### 4.1 The universal stage order (foreman sequence)

```
1. demo        Strip-out, remove existing, protect, debris removal
2. structure   Structural alterations, new openings, partitions framing
3. rough       First fix: rough plumbing, rough electrical, rough HVAC,
               substrate prep, screed, plasterboard
4. close       Plaster/render, tanking/waterproofing, insulation
5. finish      Tiling, painting, flooring finish, second fix MEP,
               fixtures, fittings, casework
6. commission  Test, balance, snag, clean
```

Each `WorkPackage` declares which of these stages it spans. The composer emits
one element-group per (package x stage) cell that has work, so a single "wall
tiling" package produces a "demo: remove old tiling" group (if demolition=true)
and a "finish: install ceramic wall tiling" group.

### 4.2 Dependency rules (encoded as a small DAG)

The foreman logic is encoded as stage precedence per package, used for two
things: ordering the group board top-to-bottom, and warning when a confirmed
group set violates a dependency.

Examples (kitchen):
- demo.remove_tiling precedes finish.wall_tiling (cannot tile a wall not
  stripped).
- rough.plumbing_first_fix precedes finish.fixtures (sink) and precedes
  close.plaster on the same wall.
- rough.screed precedes finish.floor_tiling.
- rough.electrical_first_fix precedes close.plaster precedes finish.painting.
- close.plaster precedes finish.painting and finish.wall_tiling.

These are advisory in the UI (a yellow note "tiling is scheduled before its
plaster substrate"), never blocking, consistent with "AI proposes, human
confirms". They also drive the default `sort_order` on
`AiEstimatorGroup.sort_order` so the board reads in build order.

### 4.3 Mapping packages to the existing trade taxonomy

Each package's `trade` is one of the existing `TRADE_KEYWORDS` keys
(`taxonomy.py:28`) so grouping, the per-category summary, and the GROUP_REFINE
LLM label vocabulary all stay consistent with v1. No new trade vocabulary is
introduced.

---

## 5. Element-group composer (hybrid checklist + live vector probes)

This is the heart of founder decision 3. The composer turns a confirmed
parameter sheet into the run's `AiEstimatorGroup` rows BEFORE the existing
`run_matching` stage. It runs as a new internal step inside (or just before)
`_build_groups`, and it does two things at once: it expands the curated
checklist, and it probes the live vector DB to (a) validate that each package
can be grounded, (b) pick the best-scoring phrasing, and (c) flag coverage gaps.

### 5.1 Inputs and outputs

Input: confirmed `ProjectType`, parameter sheet, selected packages (the user
has already toggled them on the board, section 7), the run's `catalogue_id` /
`region` / `currency`.

Output: for each selected (package x stage) cell, one `AiEstimatorGroup` with:
- `description` = the BEST phrasing found by probing (the one that scored
  highest), so the later `run_matching` dense query is already the strong one.
- `quantities` from section 6 formulas.
- `chosen_unit` from `package.unit`.
- `trade` from `package.trade`.
- `envelope` carrying `construction_stage_hint` set to the OmniClass stage that
  the foreman stage maps to (demo -> 02_Demolition, finish -> 10_Finishes,
  rough MEP -> 09_MEP, etc.) so the existing `build_search_plan`
  construction_stage hard/soft filter fires when the collection carries it.
- `metadata_.probe` = the probe report (phrasings tried, their top scores) for
  transparency in the timeline and for the recall test harness.

### 5.2 The probe procedure (per package x stage cell)

For each cell we have a curated tuple of candidate phrasings
(`WorkPackage.probes`). These are written in the catalogue's own keyword-salad
vocabulary (section 2.2), NOT as natural sentences. Concrete examples grounded
in the sampled payloads:

- wall_tiling.finish probes:
  - "Ceramic tiling wall interior finishes" (mirrors "Stucco work ... Walls ...
    Interiors ... Finishes")
  - "Ceramic wall covering cladding interiors"
  - "Tile finishing works wall"
- floor_screed.rough probes:
  - "Cement screed floor leveling"
  - "Floors screed construction work area"
- painting.finish probes:
  - "Painting work walls ceiling interiors"
  - "Paint finishes interior two coats"
- plaster.close probes:
  - "Stucco work plaster walls interiors"
  - "Render plastering finishing works"
- plumbing_rough probes:
  - "Internal sanitary and technical work water supply pipe"
  - "Plumbing pipe drainage services"
- electrical_rough probes:
  - "Electrical installations wiring cable"
  - "Electrical wire conduit services"
- partition.structure probes:
  - "Brick and block structures wall partition" (masonry)
  - "Wooden structures wall interior partitions" (stud)
- ventilation.rough probes:
  - "Ventilation and air conditioning duct"
  - "Air duct galvanized sheet steel installation"

The probe runs each phrasing through the SAME grounded ranker the real match
uses (`ranker_qdrant.rank` via a lightweight `ElementEnvelope` with just
`description`, `unit_hint`, `construction_stage_hint`, project currency/region),
top_k small (5), reranker on. It records the top score per phrasing.

Selection rule:
- Keep the phrasing with the highest top-1 score as the group `description`.
- If the best top-1 score >= MEDIUM (0.62): mark the cell `grounded` (green).
- If between LOW floor and MEDIUM: mark `weak` (amber) - still added, but the
  group will likely land `suggested` with low confidence; the user is told.
- If no phrasing returns any candidate, OR best score is below the LOW floor:
  mark the cell `gap` (red). The group is STILL created (so the user can edit /
  add a manual rate), but the board surfaces it as "no good catalogue match for
  this currency / region" honestly. This is the section 2.6 headline applied:
  we never silently drop a work package; we disclose the gap.

This directly satisfies "maximize recall": curated phrasings give recall a
floor; probing multiple phrasings and keeping the best lifts it; the gap report
tells the user exactly where the catalogue is thin so they can switch catalogue
or add a line manually.

### 5.3 Caps and performance

Probing N packages x up to 3 phrasings each is a vector fan-out. We reuse the
existing per-pass cap discipline (`DEFAULT_MATCH_GROUP_CAP = 25`,
`schemas.py:89`). The composer:
- Probes only the SELECTED packages (the user trimmed the board).
- Caps total probe calls at a configurable ceiling (default 60 = 20 cells x 3),
  beyond which it probes the first phrasing only.
- Runs probes concurrently in bounded batches (asyncio.gather with a semaphore),
  the same pattern the rest of the module already follows.
- Caches the encoder per process (already true: `_encode` warms once).

The probe phase logs a `thought` step "Probing the cost database with N
phrasings across M work packages" and a `stage_complete` "K of M packages
grounded, P weak, Q gaps", mirroring the honest cap disclosure pattern in
`run_matching` (`service.py:833`).

### 5.4 Why not let the LLM write the phrasings freely

The LLM CAN propose extra phrasings (when a key is present), but they are
treated as additional probe candidates and still selected by SCORE against the
real DB. The LLM never decides a group is grounded; the vector score does.
This keeps the "AI proposes, retrieval confirms" invariant and protects against
the LLM inventing a plausible phrase that returns nothing.

---

## 6. Quantity derivation formulas

Formulas are pure functions of the parameter sheet. They live in
`backend/app/modules/ai_estimator/quantities.py` as deterministic functions
keyed by `qty_formula` id, callable on the no-AI path. Every number is derived
from a value the user confirmed; nothing is invented (mirrors the
`parse_text_scope` "only numbers the user wrote" rule).

### 6.1 Core geometric helpers

```
perimeter_m(area_m2, aspect=1.4)        # if perimeter not given:
    side = sqrt(area_m2 / aspect); P = 2*(side + aspect*side)
    # aspect 1.4 is a conservative room proxy; flagged as ESTIMATED so the
    # user sees a hollow confidence and can type the real perimeter.

gross_wall_area_m2(perimeter_m, height_m) = perimeter_m * height_m

net_wall_area_m2(gross, openings_area_m2) = max(gross - openings_area_m2, 0)

openings_area_m2(doors, windows)         # default door 1.8 m2, window 1.5 m2
    = doors*1.8 + windows*1.5            # only when counts are known

slope_area_m2(plan_area_m2, pitch_deg) = plan_area_m2 / cos(pitch_deg)

debris_volume_m3(demo_area_m2, factor)   # strip-out debris proxy
    = demo_area_m2 * 0.05                 # 50 mm equivalent; ESTIMATED
```

### 6.2 Per-package formula table (representative)

| package | qty_formula | unit | formula |
|---|---|---|---|
| floor_screed | floor_area | m2 | floor_area_m2 |
| floor_tiling | floor_area | m2 | floor_area_m2 |
| wall_tiling (wet) | wall_net | m2 | net_wall_area_m2 (wet-zone share if not full) |
| wall_plaster | wall_net | m2 | net_wall_area_m2 |
| painting_walls | wall_net | m2 | net_wall_area_m2 |
| painting_ceiling | ceiling | m2 | floor_area_m2 |
| ceiling_suspended | ceiling | m2 | floor_area_m2 |
| partition_new | partition | m2 | partition_lm * ceiling_height_m |
| plumbing_first_fix | fixtures | pcs | fixtures_count (or rooms-derived) |
| sanitary_install | fixtures | pcs | fixtures_count |
| electrical_points | points | pcs | round(floor_area_m2 * density) |
| roof_covering | slope | m2 | slope_area_m2(roof_area, pitch) |
| facade_system | facade_net | m2 | net of openings_area_m2 |
| scaffolding | facade_gross | m2 | facade_area_m2 (or lump) |
| paving | paving | m2 | paving_area_m2 |
| fencing | fencing | m | fencing_lm |
| demo_strip | floor_area | m2 | floor_area_m2 (the room being stripped) |
| debris_removal | debris | m3 | debris_volume_m3 |

### 6.3 Estimated-vs-confirmed flagging

Any quantity computed from a proxy (perimeter from area, openings from default
sizes, debris factor) is tagged `estimated: true` in the group metadata. The
board shows these with a dashed underline and a tooltip "estimated from {param},
edit to set the real value". A confirmed quantity (user typed area = 12 m2) is
solid. This keeps the human-confirm spirit: the user can always overwrite a
derived number on the existing group-edit path (`GroupUpdate.quantities`,
`schemas.py:389`).

### 6.4 No-AI path uses identical formulas

The formulas are pure and deterministic, so the offline questionnaire path
produces exactly the same quantities as the AI path. The only difference is how
the parameters were collected (curated form vs extracted-then-confirmed), not
how quantities are computed.

---

## 7. Dialogue state machine

The intake is a small FSM that sits in front of the existing run FSM. It is
persisted on the run so it is resumable and pollable like everything else.

### 7.1 New persistence

A new table `oe_ai_estimator_intake` (alembic migration; the current single
head must be confirmed with `python -m alembic heads` before adding it, per the
agent-migration-fork gotcha). One row per run, 1:1.

```
oe_ai_estimator_intake
  id              GUID pk
  run_id          GUID fk -> oe_ai_estimator_run.id (unique, cascade)
  mode            String(16)   # "ai" | "offline"
  raw_request     Text         # the original free text
  detected_type   String(40)   # project_type key, or null
  type_confidence Float|null
  params          JSON         # confirmed/partial parameter sheet
  param_status    JSON         # per-param: known | asked | confirmed | skipped
  round_idx       Integer      # 0..3, how many clarification rounds used
  questions       JSON         # the current round's question batch
  transcript      JSON         # [{role, text, ts}] user/assistant turns
  phase           String(24)   # see 7.2
  packages        JSON         # composed package board state (selected, gap...)
  created_at / updated_at
```

The dialogue transcript also writes `AiEstimatorStep` rows (role `thought` /
`answer` / `observation`) so the existing timeline UI shows it for free.

Why a separate table rather than stuffing `source_inputs`: the intake has its
own lifecycle (rounds, transcript, param status) and a 1:1 row keeps the run
row lean and the migration additive. `source_inputs.text_input` still carries
the raw request for backward compatibility.

### 7.2 Intake phases

```
collect_request   -> user submits free text (or picks a type tile manually)
extract           -> derive project_type + seed params (AI or curated)
clarify_round_1   -> ask round-1 questions (highest-quantity-unlocking)
clarify_round_2   -> ask round-2 questions (only unresolved/required)
clarify_round_3   -> ask round-3 questions (only if confidence still low)
parameter_sheet   -> user reviews and confirms the full sheet (checkpoint A)
compose_groups    -> hybrid checklist + live vector probes (section 5)
group_board       -> user edits/adds/deletes/toggles groups (checkpoint B)
done              -> hand off to existing grouping->matching pipeline
```

Hard rule: at most three of the `clarify_round_*` phases ever run
(founder decision 1). The machine SKIPS a round whose questions are all already
answered (e.g. "ремонт дома 120м2" already gave area, so the area question is
pre-filled and not re-asked). If after round 3 a required param is still
missing, the parameter sheet uses a clearly-labelled sensible default and lets
the user fix it on the sheet, rather than asking a fourth time.

### 7.3 The AI extraction step (key present)

Reuses `resolve_provider_key_model` + `call_ai` + `extract_json`
(the same imports `_classify_source` already uses, `service.py:511`). A new
prompt `INTAKE_EXTRACT_SYSTEM` in `prompts.py`:

- Input: the fenced raw request + the project-type registry summary (keys +
  synonyms + the param keys per type).
- Output JSON:
  ```
  {
    "project_type": "kitchen_reno",         // or "" if unsure
    "type_confidence": 0.0..1.0,
    "params": { "floor_area_m2": 12, "demolition": true, ... },  // only what
                                                                 // the text says
    "language": "ru",
    "summary": "Kitchen renovation, area not stated."
  }
  ```
- The same hard contract as the other prompts: the model EXTRACTS and ASKS, it
  never invents a quantity it was not told and never produces a rate. Confidence
  is a real float or null (`_real_confidence`, `service.py:578`).

A second prompt `INTAKE_QUESTIONS_SYSTEM` turns the unresolved required params
for the current round into a small batch of grouped, human-friendly questions
(with choices where the param is a choice). This is the only place the LLM
phrases questions; the SET of questions is bounded by the curated round
grouping, so the LLM cannot run away with 20 questions.

Degradation: if `resolve_provider_key_model` raises (no key / undecryptable),
or `call_ai` fails, the machine logs `observation {"degraded": "no_ai_key"}`
(exactly as `_classify_source` does, `service.py:525`) and falls through to the
offline path for THIS step. The dialogue still proceeds.

### 7.4 The offline path (no AI key)

Founder decision 2. Same FSM, different question source:

- `extract`: a deterministic detector matches the free text against
  `ProjectType.synonyms_*` (substring match across RU/EN/DE, the same technique
  as `classify_trade`). If exactly one type matches, it is selected with
  `type_confidence = null` (honest: deterministic, not probabilistic). If none
  or several match, the UI shows the 10 type tiles and the user picks one
  (this is the manual entry already half-present in `Stage1Intake`).
- It also runs `parse_text_scope` on the raw text to seed any explicit
  quantities the user wrote ("120 м2" -> floor_area_m2 = 120), so the offline
  path is not dumber than v1 at reading numbers.
- `clarify_round_*`: instead of LLM-phrased questions, the UI renders the
  curated questionnaire for that round directly (the `ProjectParam` list,
  grouped, with units and choices). This is a plain form, not a chat. Still
  capped at 3 logical rounds (rounds map to the param `round_group`).
- `parameter_sheet`, `compose_groups`, `group_board`, `done`: identical to the
  AI path. The composer's vector probes do NOT need an AI key (they use the
  embedding model + Qdrant, which are independent of the LLM provider key), so
  grounded group shaping works fully offline. This is important: the offline
  path still gets DB-grounded groups, only the natural-language conversation is
  replaced by a form.

### 7.5 Confidence-driven round skipping

After each round the machine computes a readiness score: required params
known / required params total, weighted by how much quantity each unlocks. If
readiness >= a threshold (e.g. 0.9) after round 1 or 2, it skips straight to
`parameter_sheet` and does not burn a clarification round. This respects the
3-round cap as a ceiling, not a quota, and keeps simple requests fast
("ремонт ванной 4 м2, под ключ" can reach the sheet in one round).

---

## 8. API design

All new endpoints live under the existing base path
`/api/v1/ai-estimator/` (router auto-mount, `router.py:7`), reuse
`verify_project_access` (404 on deny) and `RequirePermission("ai_estimator.run"
| ".read")`, and follow the money-as-string / confidence-as-real-float-or-null
conventions already enforced by the schemas.

### 8.1 New endpoints

```
POST /api/v1/ai-estimator/intake
  Body: { project_id, text, name?, mode_hint? }   # mode_hint: "ai"|"offline"|null
  Creates a run in a new status "intake" + an intake row, runs `extract`,
  returns IntakeState (below). Does NOT run grouping yet.
  -> 201 IntakeState

GET  /api/v1/ai-estimator/runs/{run_id}/intake
  -> IntakeState   (poll target while a round/extraction runs)

POST /api/v1/ai-estimator/runs/{run_id}/intake/answer
  Body: { answers: { <param_key>: <value>, ... }, advance: bool }
  Records answers for the current round; if advance, computes the next phase
  (next round, or parameter_sheet when ready / round cap hit).
  -> IntakeState

POST /api/v1/ai-estimator/runs/{run_id}/intake/confirm-parameters
  Body: { params: {...} }            # final edits to the sheet (checkpoint A)
  Transitions to compose_groups, runs the hybrid composer (section 5),
  persists AiEstimatorGroup rows, transitions to group_board.
  -> IntakeState (with composed packages + group ids + probe report)

POST /api/v1/ai-estimator/runs/{run_id}/intake/packages
  Body: { add?: [WorkPackageSelection], remove?: [package_key],
          toggle?: { <package_key>: bool } }
  Edits the package board: re-runs the composer only for added/toggled cells,
  deletes groups for removed packages. Honest: editing a package re-probes it.
  -> IntakeState

POST /api/v1/ai-estimator/runs/{run_id}/intake/finish
  Confirms the group board (checkpoint B). Advances the RUN FSM to
  status "grouping" / current_stage "grouping" exactly where the existing
  confirm_stage("source") would land, so the rest of the pipeline
  (match / preview / apply) is untouched.
  -> RunRead

GET  /api/v1/ai-estimator/project-types
  Static registry for the UI (tiles + synonyms + param/questionnaire schema).
  -> [ProjectTypeOut]
```

### 8.2 Response schema: IntakeState

```python
class IntakeQuestionOption(BaseModel):
    value: str
    label_key: str            # i18n key; UI falls back to value

class IntakeQuestion(BaseModel):
    param_key: str
    kind: Literal["number","choice","bool","length"]
    unit: str | None
    required: bool
    options: list[IntakeQuestionOption] = []
    prompt: str               # human question text (LLM- or curated-phrased)
    why: str                  # the "unlocks" justification, i18n-keyed
    current_value: Any | None # prefilled if known from the text

class ComposedPackage(BaseModel):
    package_key: str
    trade: str
    selected: bool
    stages: list[str]
    group_ids: list[uuid.UUID]
    coverage: Literal["grounded","weak","gap"]   # section 5.2
    best_score: float | None                     # real probe score or null
    quantity: float
    unit: str
    estimated: bool                              # any proxy-derived qty

class IntakeState(BaseModel):
    run_id: uuid.UUID
    mode: Literal["ai","offline"]
    phase: Literal["collect_request","extract","clarify_round_1",
                   "clarify_round_2","clarify_round_3","parameter_sheet",
                   "compose_groups","group_board","done"]
    round_idx: int                  # 0..3
    rounds_remaining: int           # max(0, 3 - round_idx)
    detected_type: str | None
    type_confidence: float | None   # null on offline / deterministic
    params: dict[str, Any]
    questions: list[IntakeQuestion] # current round's batch (empty off-round)
    packages: list[ComposedPackage] # populated from compose_groups onward
    transcript: list[dict]          # [{role, text}]
    ai_connected: bool
    vector_ready: bool
    degraded_reason: str | None     # "no_ai_key" | "no_vectors" | "no_catalogue"
    summary: str | None
```

### 8.3 Reused, not rebuilt

- The whole match/preview/apply surface (`/match`, `/preview`, `/apply`,
  `/bulk-confirm`, group edit/merge/split) is unchanged. After
  `intake/finish` the run is a normal grouping-stage run.
- `RunStatus` gains one value `"intake"` (the `oe_ai_estimator_run.status`
  column is `String(24)`, `models.py:87`, so no enum migration is needed, same
  as `Position.source` being a free string per the DESIGN dossier).
- `degraded_reason` / `ai_connected` / `vector_ready` reuse
  `_ai_status` / `_vector_status` (`service.py:1938`, `:1950`).

### 8.4 Status / FSM additions

```
run.status:        draft | intake | analyzing | grouping | matching |
                   review | applied | failed | cancelled
intake.phase:      collect_request .. done   (section 7.2)
```

`intake/finish` is the single bridge: it sets the run to the same state the old
`confirm_stage("source")` produced and records the `source` checkpoint, so the
StageRail shows stage 1 complete and stage 2 (grouping) active. The groups the
composer already wrote ARE the grouping output, so `_build_groups` is skipped
for an intake-originated run (a flag `metadata_.intake_composed = true` tells
`confirm_stage` not to re-derive groups from envelopes and wipe the composed
ones).

---

## 9. Frontend UX

Route stays `/ai-estimator`. The wizard gains a v2 intake mode that precedes
the existing StageRail. The existing `Stage1Intake`
(`Stage1Source.tsx:90`) already has a text tab with a great placeholder; v2
turns the text path into the conversational flow while keeping files / BIM /
documents on the v1 path (those already have real quantities and do not need a
questionnaire).

### 9.1 Stage 1: the dialogue panel

A two-column layout:

- Left: the conversation. The user's free text, then the assistant's grouped
  question cards (one round at a time), then the user's answers inline. A
  progress chip "Round 1 of up to 3". A persistent "I'd rather fill a form"
  link that flips to the curated questionnaire (the offline rendering of the
  same questions) at any time. The detected project-type tile is shown with its
  confidence badge (reusing `scoreColor` / `scorePercent`, `helpers.ts`); the
  user can change the type with one click, which re-seeds the questionnaire.
- Right: a live parameter sheet that fills in as answers arrive, each row
  showing value + unit + a "why we ask" tooltip from `IntakeQuestion.why`.
  Confirmed values solid, estimated/defaulted values dashed.

Questions render by `kind`: number/length -> input with unit suffix; choice ->
segmented control or select from `options`; bool -> toggle. Required unanswered
questions block "Continue" until answered or explicitly skipped.

When no AI key: the left column shows the curated questionnaire form instead of
chat, with the same right-hand sheet. A `DegradedBanner`
(`components/DegradedBanner.tsx`, already exists) explains "AI conversation is
off; using the guided form. Grounded matching still works."

### 9.2 Stage 2: the editable group board

After `confirm-parameters`, the right panel becomes the group board, grouped by
foreman stage (demo -> structure -> rough -> close -> finish -> commission) and
within each stage by trade. Each `ComposedPackage` card shows:

- package label, trade chip, the computed quantity + unit, estimated flag.
- a coverage badge: green "grounded", amber "weak match", red "no catalogue
  match" (from `ComposedPackage.coverage`), with the real `best_score` shown on
  hover.
- toggle (include/exclude), delete, and an "add work" affordance per stage that
  opens a picker of the type's non-default packages plus a free-text "add custom
  work" box (which creates a manual group with a user-typed description that the
  composer probes immediately).

This is founder decision 4 made literal: groups are visible, editable,
deletable and addable before estimation. The board reuses the existing
`Stage2Groups` grid and group endpoints under the hood; the new layer is the
package grouping + coverage badges + the type-aware "add work" picker.

A footer summary: "18 work packages, 14 grounded, 3 weak, 1 gap. Confirm to
match rates." The gap count links to a short explainer: the catalogue for your
currency is thin on this trade; switch catalogue or add a manual rate.

"Confirm group board" calls `intake/finish` and the user lands in the familiar
stage-3 match review.

### 9.3 Confidence display

- Type detection confidence: badge on the type tile (null -> "selected", not a
  fake percentage).
- Per-package coverage: green/amber/red from the real probe score, never a
  placeholder. A gap package honestly shows "no match".
- Downstream, the existing per-group confidence band (HIGH/MEDIUM/LOW/none) is
  unchanged.

### 9.4 Example transcripts

RU (kitchen, AI path):
```
User:      сделай мне смету кухни
Assistant: Это ремонт кухни. Чтобы посчитать объёмы, уточните, пожалуйста:
           - Площадь пола кухни? (м2)            [unlocks: пол, потолок, стены]
           - Высота потолка? (м, по умолчанию 2.7)
           - Уровень отделки: эконом / стандарт / премиум?
           - Нужен демонтаж старой отделки? (да/нет)
User:      8 м2, 2.7 м, стандарт, да
Assistant: Принято. Ещё два уточнения:
           - Менять сантехнику (мойка, подводка, слив)? (да/нет)
           - Менять электрику (розетки, проводка)? (да/нет)
User:      да, да
Assistant: Готово. Собрал 16 работ по этапам: демонтаж, черновые,
           отделка. 13 нашлись в базе, 2 слабые, 1 без точного совпадения.
           Проверьте список работ перед расчётом.
```

EN (bathroom, AI path):
```
User:      bathroom refurb, about 5 square metres, full tiling, turnkey
Assistant: Bathroom renovation, 5 m2, full tiling, turnkey. One thing to
           confirm: how many fixtures (WC, basin, shower, bath) to install?
User:      WC, basin, shower - so 3
Assistant: Got it. Composed 14 packages across demo, first fix, tanking and
           finishes. 12 grounded in the catalogue, 2 weak. Review the work
           list, then I will match rates.
```

DE (facade, offline / no key):
```
User:      Fassadensanierung, 220 m2, WDVS
[no AI key -> guided form]
Form R1:   Fassadenflaeche: 220 m2 | System: WDVS (ETICS) | Geruest: ja |
           Oeffnungsflaeche: ? m2
Form R2:   Daemmstaerke: 140 mm | Untergrund: ausbessern | Geschosse: 2
Board:     Geruest 220 m2 (grounded), WDVS-System 200 m2 netto (weak),
           Sockel (gap) ... bearbeiten / hinzufuegen / entfernen
```

---

## 10. Test plan

### 10.1 Golden fixtures (3 languages x 4 project types)

Twelve fixtures under `backend/tests/fixtures/ai_estimator_intake/`:

```
ru_kitchen.json    en_kitchen.json    de_kitchen.json
ru_bathroom.json   en_bathroom.json   de_bathroom.json
ru_apartment.json  en_apartment.json  de_apartment.json
ru_roof.json       en_roof.json       de_roof.json
```

Each fixture carries: the raw request string, the scripted answers per round,
the expected detected `project_type`, the expected parameter sheet, the
expected set of selected packages, and an expected `golden_positions` list:
the curated set of CWICR `collection_name` / MasterFormat divisions a competent
estimator would expect each package to land in (e.g. kitchen wall_tiling ->
{Stucco work, Finishing works, MF 09 ...}; plumbing -> {Internal sanitary and
technical work, MF 22 ...}).

### 10.2 Deterministic unit tests (no network, no LLM, fast)

- Project-type detection: each fixture's raw string detects the right type
  via the offline synonym matcher.
- Parameter formulas: feed the fixture parameter sheet, assert each package's
  quantity matches the expected value (exact for confirmed, tolerance for
  estimated/proxy quantities).
- Round cap: assert no fixture ever produces more than 3 clarification rounds;
  assert a fully-specified request ("ремонт ванной 4 м2 под ключ") reaches the
  sheet in <= 1 round.
- Integrity: assert every `ProjectParam.unlocks` and `WorkPackage.qty_formula`
  resolves to a real formula; assert every package `trade` is in
  `taxonomy.TRADE_KEYWORDS`.
- Offline parity: assert the offline path and a mocked-AI path produce the same
  parameter sheet and the same package set for the same answers.

### 10.3 Recall metrics vs golden position lists (in-process, live ranker)

A test `test_intake_recall.py` that runs IN the backend process (so the warm
encoder and live Qdrant are available, avoiding the standalone segfault from
section 2.6). For each fixture:

1. Compose the groups (the real composer, real probes).
2. Run `run_matching` over the composed groups against the bound catalogue
   (`USA_USD` on this install).
3. For each package, check whether the top candidate's `collection_name` /
   MasterFormat division is in that package's `golden_positions` set.

Metrics reported (and asserted against floors, not perfection, because the
catalogue is US/civil-heavy per section 2):

- package_grounding_rate = packages with coverage in {grounded, weak} / total.
  Floor: >= 0.7 for kitchen/bathroom/apartment finishes packages.
- top1_in_golden_rate = packages whose top candidate is in golden_positions /
  packages with any candidate. Floor: >= 0.5 (honest, given synthetic US data).
- gap_disclosure_correctness = every package the harness marks as a gap is
  ALSO surfaced as a gap in the UI state (no silent gaps). Must be 1.0.
- recall_at_5 = packages with at least one golden position in their top-5
  candidates / total. Tracked over time as the headline recall number the
  composer is optimised to raise (more/better probe phrasings lift this).

The harness prints a per-package table (probe phrasing chosen, top score, top
collection_name, golden hit yes/no) so a human can read exactly where recall
leaks and add a better curated probe phrasing. This closes the loop on founder
decision 3: the test is literally the "look hard at our vector DB and pull as
many real positions as possible" measurement.

### 10.4 API / FSM tests

- The full happy path: POST /intake -> answer (round 1) -> answer (round 2) ->
  confirm-parameters -> packages (toggle one off) -> finish -> the run is in
  grouping with the composed groups intact.
- Round cap enforcement at the API: a third answer with `advance` always lands
  on `parameter_sheet`, never a fourth round.
- Degradation: with no AI key, POST /intake returns `mode="offline"`,
  `degraded_reason="no_ai_key"`, and the curated questions; the rest of the
  flow still composes grounded groups.
- Auth: every new endpoint 404s on cross-project access and enforces the
  `ai_estimator.run` / `.read` permissions.

---

## 11. Build order (suggested, additive, no v1 regressions)

1. Data: `project_types.py` (registry) + `quantities.py` (formulas) + unit
   tests (10.2). Pure data + functions, zero risk.
2. Persistence: `oe_ai_estimator_intake` table + repository + alembic migration
   (confirm single head first). Add `"intake"` to `RunStatus`.
3. Composer: the hybrid checklist + probe step, reusing `ranker_qdrant.rank`.
   Recall harness (10.3) drives its tuning.
4. State machine + service methods (`extract`, round advance, confirm-params,
   packages, finish) with the AI and offline branches sharing one machine.
5. Prompts: `INTAKE_EXTRACT_SYSTEM`, `INTAKE_QUESTIONS_SYSTEM` in `prompts.py`.
6. Router: the new endpoints + IntakeState schemas. API tests (10.4).
7. Frontend: dialogue panel + editable group board + coverage badges, behind
   the text source tab; files/BIM/documents keep the v1 path.
8. i18n: new keys for questions, why-tooltips, coverage badges, type tiles
   across the 26 locales (the i18n-sweep skill).

Every step is additive: the existing four-stage pipeline, its endpoints, its
tests and the non-text source paths are untouched. v2 only adds a richer way to
ARRIVE at stage-2 groups for the free-text case.

---

## 12. Invariants preserved (the non-negotiables)

- AI proposes, human confirms: two explicit checkpoints (parameter sheet,
  group board) before any rate is matched; groups editable/deletable/addable.
- Rates never invented: the dialogue and composer only shape the QUERY. Every
  rate still comes from `ranker_qdrant.rank` over the cost DB; a package with no
  grounded candidate is an honest gap, not a fabricated number.
- Confidence is real: type confidence and package coverage are real probe
  scores or null, never a 0.5 placeholder.
- Graceful degradation: no AI key -> curated questionnaire through the same
  machine; no vectors / wrong-currency catalogue -> honest gap disclosure; the
  flow never 500s.
- Max 3 clarification rounds, enforced in the machine and the API and tested.
- Single-DB, lightweight: one additive table, pure-Python registry and
  formulas, reuse of the existing encoder + Qdrant + ranker. No new heavy
  dependency.
```
