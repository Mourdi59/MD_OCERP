# Top-block alignment audit (consolidated)

Synthesis of five per-cluster alignment passes (estimating, overview, commercial, comms-quality, field-docs, planning-misc) into one actionable plan. This is the founder's "poorly positioned / poorly aligned top blocks" feedback, traced to root causes.

The headline finding: the shared components (PageHeader, DismissibleInfo, Breadcrumb, Card, Button) are mostly correct. What is wrong is how ~90 pages compose them. The same four or five mistakes repeat across the whole app. Fix the central components once, then run a mechanical page-local cleanup, and the cluster-specific defects mostly disappear.

Verified against source while writing this doc:
- `frontend/src/shared/ui/PageHeader.tsx` line 37 carries a built-in `mb-4`. The component is otherwise correct (items-center midline, min-h-9).
- `frontend/src/shared/ui/DismissibleInfo.tsx` lines 114-116 default the wrapper margin to `mb-5` via `className ?? 'mb-5'`. The translucent card itself is correct (border-l-2 border-l-oe-blue/70, bg-oe-blue-subtle/25, h-7 w-7 chip).
- `frontend/src/app/layout/Header.tsx` line 216 puts Zone-1 (project pill + module name) in `min-w-0 shrink`; line 255 wraps the module name in `truncate`.
- `frontend/src/features/schedule/PlanningCrossLinks.tsx` line 86 carries a built-in `mb-4` on its nav.

---

## 1. Systemic issues (shared components / conventions)

These are deduped across all clusters. Each is a single central fix. Do these first; they retire dozens of page-local findings.

### S1. PageHeader owns a built-in `mb-4` (double-margin generator)

PageHeader renders `mb-4` on its root row. Every page that also wraps its content in `space-y-5` (or `space-y-6`) gets a compounded gap directly under the header: `space-y` flex gap PLUS PageHeader's own `mb-4`, around 36px, while the breadcrumb-to-header gap is only the `space-y` gap (around 20px). The result is an uneven, oversized gap right under the header on every space-y page (contracts, bid-management, subcontractors, carbon, qms, and the corrected estimating pages once they adopt space-y-5).

Central fix: remove `mb-4` from the root className in `frontend/src/shared/ui/PageHeader.tsx` line 37. Spacing then comes only from the page-level `space-y-5` root.

### S2. DismissibleInfo defaults to `mb-5` (second double-margin generator)

DismissibleInfo defaults its wrapper margin to `mb-5` (`className ?? 'mb-5'`). On a space-y page this stacks the same way S1 does, and on hand-margin pages it is yet another value to reconcile.

Central fix: in `frontend/src/shared/ui/DismissibleInfo.tsx` lines 114-116 change `className ?? 'mb-5'` to `className ?? ''` so the page-level `space-y-5` owns the rhythm.

Note: S1 + S2 together are the single biggest lever. They are also a precondition for the page-local "switch root to space-y-5 and drop per-element margins" cleanup below. Land S1 and S2, then convert page roots; doing it in the other order briefly tightens the gaps but leaves them fragile.

### S3. No single page-root rhythm convention (space-y vs hand-margins)

Pages disagree on how to space the top block: `space-y-5` (canon, used by validation, qms, carbon, schedule-advanced, takt, reporting, punchlist), `space-y-6` (analytics, reports, collaboration, settings on the loose side), `space-y-4` (crm, photos, accommodation, safety on the tight side), `space-y-8` (quantities, too large), and `w-full animate-fade-in` with hand-set `mb-*`/`mt-*` everywhere (boq, costs, assemblies, catalog, ai-estimator, projects, tasks, procurement, tendering, changeorders, rfi, submittals, transmittals, meetings, markups, finance, 5d, equipment cluster, ncr, inspections). Sibling pages even pick different KPI-grid margins (rfi `mb-4` vs submittals/transmittals `mb-6`), so the header-to-KPI gap visibly differs between pages that should look identical.

Central decision (apply cluster-wide, page by page): every module page root = `space-y-5 animate-fade-in`, and every per-element `mb-*`/`mt-*` inside the top block is dropped (Breadcrumb, PageHeader, DismissibleInfo, KPI grid, PlanningCrossLinks). This is mechanical and identical on every page. It depends on S1 and S2 landing first.

### S4. PlanningCrossLinks built-in `mb-4` + injected above the header

`frontend/src/features/schedule/PlanningCrossLinks.tsx` line 86 carries `mb-4`, and the strip is rendered BETWEEN the breadcrumb and the PageHeader on the planning pages (schedule, schedule-advanced, tasks, transmittals has its own variant). That breaks the canonical breadcrumb > PageHeader > info order and pushes the real header down (header top measured at 104px vs 75px on peers). The uppercase "PLANNING & CONTROL" group label (lines 88-90) also echoes a sidebar GROUP name, which the style guide forbids in the trail.

Central fix: in PlanningCrossLinks.tsx drop the `mb-4` from the nav (line 86) so the page space-y owns the gap, and move the strip BELOW PageHeader (render it as a TabBar under the header, not above it) so canonical order is preserved. Reconsider the uppercase group label. This is one component used by ~5 planning pages, so it is a single fix that clears findings on /tasks, /schedule, /schedule-advanced.

### S5. Top-bar module name truncates on every route

`frontend/src/app/layout/Header.tsx`: the module-name h1 (lines 242-256, `<span className="truncate">`) lives in Zone-1 `flex ... min-w-0 shrink` (line 216) next to the ProjectSwitcher pill capped at `max-w-[260px]`. At 1280-1440px the project pill placeholder plus the search box squeeze the module name to "4D Sch...", "Advan...", "Carbo...", "Takt Pl...". Canon says the module name is the only visible name, so truncating it defeats the whole top-bar contract.

Central fix: in Header.tsx give the project pill a smaller max-w (around `max-w-[200px]`) or let the module-name win the shrink contest (wrap the pill in `shrink min-w-0` and give the title `shrink-0` up to a sane max). One file, fixes the truncation on every route.

### S6. Three info-card treatments where there should be one

The canonical translucent DismissibleInfo (icon chip, bg-oe-blue-subtle/25, pain-named title, link pills) is correct and already used by validation, ncr, qms, inspections, punchlist, collaboration, contracts, tendering, bid-management, subcontractors, supplier-catalogs, carbon. But other pages ship non-canonical info chrome:

- Raw-blue alert banner (banned raw tailwind tokens `bg-blue-50 / dark:bg-blue-950/30 / border-blue-200 / text-blue-800`, inline Info icon with no chip, absolute X): rfi, submittals, transmittals.
- Legacy `InfoHint` "How it works" disclosure pill: procurement, changeorders, reports, tasks, schedule-advanced, takt, 5d, risks, schedule.
- Bespoke `PipelineBanner` (crm), `FinanceWorkflowGuide` gradient card (finance), hand-rolled `WorkflowIntro` Card (daily-diary, equipment, resources, using bg-oe-blue-subtle/10 + sessionStorage instead of the canon /25 + localStorage + top-bar reopener).
- No info card at all: quantities, analytics, projects, bi-dashboards, notifications, meetings, accommodation.

Central direction: converge everything on `DismissibleInfo` (with the SectionIntro thin wrapper where already in use). Per-page swaps are listed in the page-local tables below, but the convention itself is systemic: one info component, translucent style, localStorage + top-bar reopener.

### S7. Hand-rolled headers that bypass PageHeader

Some pages re-implement the header row instead of using the shared PageHeader, so they do not inherit the items-center one-midline behavior (the exact fix made for the 2026-06-06 founder feedback) and they drift on button height. Seen on: supplier-catalogs (`items-start`, reintroduces the misalignment), reporting (raw flex div, default-md button), punchlist (hand-rolled header with a hand-rolled "View on map" control), photos (eyebrow + count pill), markups (PageHeader + bare intro `<p>`).

Central direction: route these through the shared PageHeader (subtitle + actions slot). Listed per page below.

### S8. KPI-tile token + baseline inconsistency

The canonical KPI tile is the shared Card with label `text-2xs uppercase tracking-wide text-content-tertiary` and value `text-lg font-semibold`. Several pages diverge: boq hand-rolls tiles (`text-xl font-bold` value), safety uses `text-xl font-bold`, and analytics/boq multi-currency tiles wrap to a different number of lines so value baselines do not align across the row (single-value tile sits at a different vertical position than a 3-line multi-currency tile, because the grid stretches all tiles to equal height and the content is vertically centered).

Central direction: standardize KPI tiles on the shared Card tokens, and top-align (justify-start) the label+value block so single-line and multi-line tiles share a top baseline. The multi-currency tile needs a reserved/consistent height (fixed min-height or a "+N more" affordance). Per-page entries in the high/medium tables.

---

## 2. Double-margin findings (mechanical)

These are the pure "page root has no space-y so spacing is hand-built with mb-*/mt-*, AND/OR a per-element margin stacks on top of a space-y parent" findings. The fix is identical and mechanical on every one: after S1/S2/S4 land, set the page root to `space-y-5 animate-fade-in` and delete the listed per-element margins. No visual judgement needed.

| Route | File | Margins to drop | Root change |
|---|---|---|---|
| /boq | frontend/src/features/boq/BOQListPage.tsx | Breadcrumb mb-4 (694), DismissibleInfo mb-4 (748), KPI grid mb-6 | line 693 -> `space-y-5 animate-fade-in` |
| /costs | frontend/src/features/costs/CostsPage.tsx | PageHeader mb-5 (864) + per-block margins | line 856 -> `space-y-5 animate-fade-in` |
| /assemblies | frontend/src/features/assemblies/AssembliesPage.tsx | PageHeader mb-3 (362), DismissibleInfo mb-3 (478) | line 356 -> `space-y-5 animate-fade-in` |
| /quantities | frontend/src/features/quantities/QuantitiesPage.tsx | Breadcrumb mb-4, PageHeader mb-4 | line 943 `space-y-8` -> `space-y-5` |
| /ai-estimator | frontend/src/features/ai-estimator/AiEstimatorPage.tsx | implicit PageHeader margin reliance | lines 603 (list) + 630 (wizard) -> `space-y-5 animate-fade-in` |
| /validation | frontend/src/features/validation/ValidationPage.tsx | Breadcrumb mb-1 (1007) | already space-y-5 |
| /projects | frontend/src/features/projects/ProjectsPage.tsx | Breadcrumb mb-4 (386), PageHeader mb-6 (390), stats grid mb-6 (415) | line 385 -> `space-y-5 animate-fade-in` |
| /tasks | frontend/src/features/tasks/TasksPage.tsx | per-element mb-4/mb-3 | -> `space-y-5` |
| /analytics | frontend/src/features/analytics/AnalyticsPage.tsx | Breadcrumb mb-4 (288) | line 282 `space-y-6` -> `space-y-5` |
| /reports | frontend/src/features/reports/ReportsPage.tsx | Breadcrumb mb-4 | lines 962 + 975 `space-y-6` -> `space-y-5` |
| /bi-dashboards | frontend/src/features/bi-dashboards/BIDashboardsPage.tsx | n/a (clean) | add DismissibleInfo, keep rhythm |
| /tendering | frontend/src/features/tendering/TenderingPage.tsx | Breadcrumb mb-4, PageHeader mb-6, DismissibleInfo mb-6 (~1337-1378) | wrap root in `space-y-5` |
| /changeorders | frontend/src/features/changeorders/ChangeOrdersPage.tsx | PageHeader mt-4, InfoHint mt-4 mb-2, summary grid mt-6 | line 1626 -> wrap in `space-y-5` |
| /crm | frontend/src/features/crm/CRMPage.tsx | n/a | line ~340 `space-y-4` -> `space-y-5` |
| /contracts | frontend/src/features/contracts/* | header->info gap | covered by S1/S2 (already space-y-5) |
| /ncr | frontend/src/features/ncr/NCRPage.tsx | per-element mb-* | `w-full animate-fade-in` -> `space-y-5 animate-fade-in` |
| /inspections | frontend/src/features/inspections/InspectionsPage.tsx | per-element mb-* | -> `space-y-5 animate-fade-in` |
| /daily-diary | frontend/src/features/daily-diary/DailyDiaryPage.tsx | Breadcrumb mb-2 (~404) | already space-y-5 |
| /collaboration | frontend/src/features/collaboration/* | n/a | `space-y-6` -> `space-y-5` |
| /5d | frontend/src/features/costmodel/CostModelPage.tsx | manual mb-4/mb-6 (~2632-2724) | `w-full animate-fade-in` -> `space-y-5` |
| /risks | frontend/src/features/risk/RiskRegisterPage.tsx | per-child mt-3/mt-4/mt-4/mt-6 (613-665) | single `space-y-5` (or space-y-6) root |
| /carbon | frontend/src/features/carbon/CarbonPage.tsx | header->info gap (166-237) | covered by S1 |
| /settings | frontend/src/features/settings/SettingsPage.tsx | phantom UpdateNotification mb-6 (1206-1208) | -> `space-y-5` root; render wrapper only when an update exists |
| /safety | frontend/src/features/safety/SafetyPage.tsx | Breadcrumb mb-4 (523), KPI grid mb-6 (409), tab-bar mb-6 (586) | line 515 `w-full animate-fade-in` -> `space-y-5 animate-fade-in` |
| /markups | frontend/src/features/markups/MarkupsPage.tsx | PageHeader mt-3 (~1472) | line ~1456 -> `space-y-5 animate-fade-in` |
| /accommodation | frontend/src/features/accommodation/AccommodationListPage.tsx | BetaBanner mt-3 (156) | line ~154 `space-y-4` -> `space-y-5` |

---

## 3. Page-local findings (by severity)

### Covered by the unified-top-block rollout wave (do NOT double-fix)

These are content/anatomy items the rollout wave fixes by design: in-page H1s, in-page project pickers, module-name-as-info-title, missing info cards, subtitle copy, and legacy info-chrome swaps. List them so nobody patches them ahead of the wave; track them with the wave, not with the systemic/page-local fixes above.

| Route | Item | Where | Notes |
|---|---|---|---|
| /costs | Info title is the module name "Cost Database" | CostsPage.tsx:949 | replace with pain-named MODULE_INTRO_COPY title via `costs.intro_title` |
| /catalog | Info title is the module name "Resource Catalog" | CatalogPage.tsx:1704 | pain-named title |
| /takeoff | Info title is the module name "PDF Takeoff" | TakeoffPage.tsx:1816 | pain-named title |
| /takeoff | In-page project AND BOQ pickers | TakeoffPage.tsx:694, 841 | remove project picker, read useProjectContextStore; keep only a BOQ-target selector |
| /qms | Leftover in-page project picker (raw slug) | QMSPage.tsx:387-393 | remove, rely on global useProjectContextStore |
| /boq | Generic count-based info title "About estimates" | BOQListPage.tsx:747 | pain-named title when copy wave reaches it |
| /reporting | Subtitle is the module name "Reporting Dashboards" | en.ts:6461 + other locales | use the descriptive sentence; data bug not a component change |
| /quantities | No DismissibleInfo card at all | QuantitiesPage.tsx | add `storageKey="quantities"` card under PageHeader |
| /analytics | No DismissibleInfo card | AnalyticsPage.tsx | add card between PageHeader and KPI grid |
| /reports | Legacy InfoHint instead of DismissibleInfo | ReportsPage.tsx:995 | swap to DismissibleInfo |
| /tasks | Legacy InfoHint | TasksPage.tsx | swap to DismissibleInfo |
| /procurement | Legacy InfoHint + separate Finance/Contacts row | ProcurementPage.tsx | fold into one DismissibleInfo with links pills |
| /changeorders | Legacy InfoHint | ChangeOrdersPage.tsx | swap to DismissibleInfo |
| /crm | Bespoke PipelineBanner | CRMPage.tsx:340-385 | swap to DismissibleInfo (pipeline steps as links) |
| /finance | Bespoke FinanceWorkflowGuide gradient card | FinancePage.tsx:534-593 | swap to DismissibleInfo |
| /rfi, /submittals, /transmittals | Raw-blue hand-rolled alert banner | RFIPage.tsx ~1848-1894, SubmittalsPage.tsx ~957-992, TransmittalsPage.tsx ~1124-1145 | swap to DismissibleInfo |
| /meetings | No DismissibleInfo (action-items-flow strip instead) | MeetingsPage.tsx:2200-2213 | replace strip with DismissibleInfo under PageHeader |
| /daily-diary, /equipment, /resources | Hand-rolled WorkflowIntro Card (sessionStorage) | DailyDiaryPage.tsx ~210-285, EquipmentPage.tsx ~143, ResourcesPage.tsx ~242 | delete local WorkflowIntro, call DismissibleInfo |
| /photos | Eyebrow header + count pill + bare `<p>` intro (Variant C candidate) | PhotoGalleryPage.tsx ~1280-1331 | adopt PageHeader + DismissibleInfo; drop literal "Dashboard" breadcrumb item |
| /markups | Bare `<p>` intro instead of card | MarkupsPage.tsx ~1577-1582 | swap to DismissibleInfo |
| /bi-dashboards | No DismissibleInfo card | BIDashboardsPage.tsx | add card |
| /project-controls | Variant B (header wrapped in card) | ProjectControlsPage | founder is choosing a variant; resolve with the variant decision, not now |

### High severity

| Route | Issue | Exact fix (file + classes) | Screenshot |
|---|---|---|---|
| /catalog | Worst in-row height mismatch: region `<select>` is h-9 (36px) next to four `size="sm"` (h-7, 28px) header buttons, an 8px midline difference. Subtitle uses a literal double-hyphen separator "France -- 7,184 resources" (no-em-dash / clean typography rule). | CatalogPage.tsx:1634 change the region select from `h-9` to `h-7` (or wrap in a shared sized control). Line 1618 replace ` -- ` with a comma or middot. Consider moving the region selector out of header actions into the toolbar/tab row (selection lives in the toolbar, not header actions). | crop-catalog.png |
| /takeoff | PageHeader rendered with srTitle only (no subtitle/actions) -> empty header row before the info card, reads as a blank midline. | TakeoffPage.tsx:1812 give PageHeader a real subtitle (what PDF takeoff does) or remove the empty header so there is no blank midline. (Info-title rename + picker removal are in the rollout-wave subsection.) | takeoff.png |
| /procurement | Worst-aligned top block in the cluster: PageHeader subtitle alone with empty right side, then four stacked rows with mismatched margins (mb-6/mb-4/mb-4/mb-6/mb-6) - lone "How it works" InfoHint, Finance/Contacts ghost-button row, yellow no-project warning, tab bar - with no shared rhythm and no canonical card. | ProcurementPage.tsx ~199-246: wrap root in `space-y-5` (currently `w-full` only) and drop per-element mb-* (Breadcrumb mb-4, PageHeader mb-6, InfoHint mb-4, links div mb-4, warning mb-6). Replace the InfoHint + Finance/Contacts row with a single `<DismissibleInfo storageKey="procurement" ...>` carrying the workflow text as children and Finance/Contacts as `links` pills (matching supplier-catalogs). Keep the no-project warning as one rhythm child. | procurement.png, procurement-crop.png, procurement-dark.png |

### Medium severity

| Route | Issue | Exact fix (file + classes) | Screenshot |
|---|---|---|---|
| /assemblies | Header action row mixes button heights: four secondary buttons are `size="sm"` (h-7) but primary "New Assembly" defaults to md (h-8); ~2px midline mismatch. "AI Generate" carries bespoke violet color classes. | AssembliesPage.tsx ~462 add `size="sm"` to the "New Assembly" Button so all five share one h-7 midline. Line 458 drop the inline violet-300/violet-600 on AI Generate; use a standard secondary or a single accent token. | crop-asm.png |
| /boq | KPI strip diverges from canon and is internally unbalanced: hand-rolled tiles (`rounded-xl bg-surface-elevated border p-3`, value `text-xl font-bold`, label `text-2xs uppercase tracking-wider`) instead of shared Card; multi-currency Total Value tile wraps per-currency chips to a second line at `text-sm` so baselines do not align and tile heights differ. | BOQListPage.tsx:771-815 rebuild tiles on the shared Card with canon tokens (label `text-2xs uppercase tracking-wide text-content-tertiary`, value `text-lg font-semibold`). For multi-currency Total Value, reserve a consistent tile height (fixed min-height, or dominant currency + "+N more") so the four tiles stay equal-height with aligned baselines. | crop-boq.png |
| /changeorders | Header action buttons mixed heights: "Export CSV" is `size="sm"` (h-7) while "AI Draft" and "New Change Order" are default md (h-8); right-aligned row is ragged. | ChangeOrdersPage.tsx ~1635-1655 give Export CSV `size="md"` (or remove `size="sm"`) so all three actions are h-8. (Root space-y-5 + InfoHint swap covered above.) | changeorders.png, changeorders-crop.png |
| /supplier-catalogs | Header is hand-rolled (`<div className="flex items-start justify-between">`) using `items-start`, so the subtitle top-aligns with the New Vendor button instead of sitting on a shared midline - reintroduces the exact misalignment PageHeader's items-center fixed. | SupplierCatalogsPage.tsx ~174-186 replace the hand-rolled flex header with shared `<PageHeader subtitle={...} actions={canCreateHere && <Button.../>}/>` (add PageHeader import). If kept hand-rolled, change `items-start` to `items-center` and add `min-h-9`. | supplier-catalogs.png, supplier-crop.png |
| /analytics | KPI value baselines not aligned across the row: single-line "Total Projects" value vs 3-line multi-currency valueNode; grid stretches tiles to equal height so headline figures sit at different vertical positions. | AnalyticsPage.tsx in KPICard wrap label+value in a flex-col with `justify-start` (anchor the value row to the top instead of vertical-centering), or cap the multi-currency valueNode to a fixed first-line position so single- and multi-line tiles share a top baseline. | analytics--topcrop.png |
| /tasks | Most cluttered top block: PlanningCrossLinks strip (group label + 6 pills) injected between Breadcrumb and PageHeader, four manually-margined chrome rows before content, action buttons `size="sm"` h-7 smaller than sibling primaries. | Component fix in PlanningCrossLinks.tsx (S4): move the switcher below PageHeader or demote the uppercase group label, drop its mb-4. In TasksPage.tsx set root `space-y-5`, drop per-element mb-4/mb-3, normalize the three header Buttons to the cluster default height. | tasks--topcrop.png |
| /schedule-advanced | No PageHeader title, orphan subtitle with no actions, and PlanningCrossLinks renders ABOVE the subtitle (canon = breadcrumb > header > info). Four stacked rows ~47px apart from compounding mb-4 + space-y-5. | ScheduleAdvancedPage.tsx:324-352 rely on the S1 mb-4 removal; move `<PlanningCrossLinks>` below `<PageHeader>` (or drop its mb-4). Pass an `actions` prop to PageHeader so the header row is not a floating sentence. (InfoHint swap covered above.) | schedule-advanced-top.png |
| /takt | Orphan subtitle, no actions, big empty top gap; subtitle contains an em-dash ("repetitive work - cycle a crew"). | TaktSchedulePage.tsx:185-198 replace the em-dash in `takt.subtitle` default with a comma/period; add an `actions` slot to PageHeader (e.g. New Takt Schedule). (InfoHint swap covered above.) | takt-top.png |
| /5d | Header-less orphan subtitle; "Viewing all projects (29)" scope strip is very low contrast (`border-border-light bg-surface-secondary/60`) and nearly disappears. | CostModelPage.tsx:2632-2724 root to `space-y-5`; raise scope-strip contrast (2706-2710) to e.g. `bg-oe-blue-subtle/30 + text-content-secondary`; give PageHeader an action. | 5d-top.png |
| /risks | Top block double-margins: PlanningCrossLinks (built-in mb-4) wrapped in mt-3, PageHeader (built-in mb-4) gets mt-4, InfoHint mt-4, KPI strip mt-6 - explicit mt-* stacks on each component's mb-4. | RiskRegisterPage.tsx:613-665 drop the per-child mt-3/mt-4/mt-4/mt-6 wrappers and use a single `space-y-5` (or space-y-6) root; relies on S1/S4. | risks-top.png |
| /finance | No project selected: orphan subtitle, then bespoke gradient card, then a separate amber "Select a project" banner (mb-6) that duplicates the empty-state shown below - two stacked banners push content far down. | FinancePage.tsx:670-700 drop one of the duplicated no-project banners (line 696-700 duplicates the RequiresProject empty state); move to a `space-y-5` root. (Card swap covered above.) | finance-top.png |
| /settings | Large empty gap above the orphan subtitle: a hidden UpdateNotification wrapper `<div className="-mx-4 sm:-mx-7 mb-6">` stays in the DOM with mb-6 even though UpdateNotification returns null on the current version, reserving ~24px of phantom margin. | SettingsPage.tsx:1206-1208 render the wrapper only when an update exists (lift the null-check up, or let UpdateNotification own its margin); switch the page to a `space-y-5` root. | settings-top.png |
| /schedule | Same family as schedule-advanced (PlanningCrossLinks strip > orphan subtitle > How-it-works pill); subtitle restates the top-bar placeholder verbatim. | SchedulePage.tsx S4 fix (strip placement + drop double margins), give PageHeader an action, and use a description of what the module does instead of repeating the top-bar placeholder. | schedule-top.png |
| /meetings | Mixed header button heights: "Import Summary" has no `size="sm"` so it is h-9 while "Create recurring series" and "New Meeting" are `size="sm"` (h-8) - three buttons, two heights. | MeetingsPage.tsx:2164-2171 add `size="sm"` and `icon={<FileUp size={14}/>}` to Import Summary so all three match. (Info-card add + root space-y-5 covered above.) | meetings.png |
| /transmittals | A "Document flow" stage strip is inserted BETWEEN the breadcrumb and the PageHeader (lines 1086-1101), breaking canonical order and pushing the header to top=104 (vs 75 on peers), leaving New Transmittal floating beside an empty line. | TransmittalsPage.tsx move the document-flow strip OUT of the top block (fold into DismissibleInfo body/links, or render below the KPI strip). (Banner swap + root space-y-5 covered above.) | transmittals.png |
| /photos | Breadcrumb passes a literal "Dashboard" text item -> renders [Home] > Dashboard > Project Photos, duplicating the dashboard link (the Home icon IS the dashboard link). Variant C candidate (wave-pending overall). | PhotoGalleryPage.tsx ~1280-1331 drop the literal Dashboard breadcrumb item so `items=[{ label: t('photos.title') }]` (single item auto-hides); root to `space-y-5`. | photos.png |
| /safety | KPI tiles use `text-xl font-bold` values and `uppercase` labels; canon is `text-lg font-semibold` value + `text-2xs uppercase tracking-wide` label, so safety numbers are bolder/larger than the canonical strip elsewhere. | SafetyPage.tsx QualityDashboardSummary 409-467 change tile value class from `text-xl font-bold` to `text-lg font-semibold` and add `tracking-wide` to the label. (Root space-y-5 + KPI/tab-bar mb-6 drops covered above.) | safety.png |
| /accommodation | Full-width yellow BetaBanner inserted between the (hidden) breadcrumb and PageHeader with `mt-3` while inside the space-y-4 parent -> double margin, becomes the visually-first element. At 1280px the subtitle wraps to 2 lines while four right-side actions crowd the row. | AccommodationListPage.tsx ~154-199 drop `mt-3` from BetaBanner (156) or move it below PageHeader; root to `space-y-5`. De-crowd the header: shorten "Suggest room for employee" or move the Calendar link + ModuleHelpButton into a secondary group so the subtitle does not wrap. | accommodation.png |
| /markups | Root `animate-fade-in` (no space-y), PageHeader `mt-3`, intro is a bare `<p className="mt-2 text-xs">` so subtitle and intro merge into one muted block; an in-header document `<select>` reads as a disabled "No docs" pill wedged into the action group. | MarkupsPage.tsx root ~1456 -> `space-y-5 animate-fade-in`; remove PageHeader `mt-3` (~1472). Give the "No docs" select a min-width/placeholder so it does not read as disabled when empty. (Bare-p -> DismissibleInfo covered above.) | markups.png |
| /qms | Single "New ITP Plan" Button has no `size="sm"` so it is h-9 where the cluster norm is h-8; no in-row mismatch (it is alone) but inconsistent across the cluster. | QMSPage.tsx:266 add `size="sm"` to New ITP Plan. (In-page project picker removal covered in rollout-wave subsection.) | qms.png |

### Low severity

| Route | Issue | Exact fix (file + classes) | Screenshot |
|---|---|---|---|
| /validation | Breadcrumb `className="mb-1"` double-manages spacing on top of the space-y-5 parent. | ValidationPage.tsx:1007 remove `className="mb-1"` from the Breadcrumb. | validation.png |
| /ai-estimator | List-view root is bare `animate-fade-in`, no space-y, no breadcrumb; an AiStatusBanner sits between PageHeader and the info card so the header-to-info gap is 59px (largest in cluster). | AiEstimatorPage.tsx:603 (list) and 630 (wizard) -> `space-y-5 animate-fade-in`; AiStatusBanner + IntroBanner then sit on the uniform 20px rhythm. | ai-estimator.png |
| /reporting | Header row is hand-rolled (raw flex div at 531) not the shared PageHeader, so it misses min-h-9/midline rules and its Button is default-md (h-8) vs sibling sm (h-7). | ReportingPage.tsx:531-548 replace the hand-rolled `<div className="flex ... justify-between">` with `<PageHeader subtitle actions srTitle />`. | reporting--topcrop.png |
| /projects | New Project button is default-md (h-8) vs sm (h-7) on /analytics and /tasks. | ProjectsPage.tsx normalize the New Project button height to the cluster default. (Root space-y-5 covered above.) | projects--topcrop.png |
| /bi-dashboards | Subtitle contains an em-dash ("... alert rules - all in one place."); New Dashboard is default-md height while siblings use sm. | BIDashboardsPage.tsx:290 replace the em-dash in `bi.subtitle` default and in the locale files with a comma/period; align the button height to the cluster. | bi-dashboards--topcrop.png |
| /notifications | Subtitle is left-aligned with NO right-side action on its midline, leaving a large empty right half; real actions live one row lower in the Inbox tab. | NotificationsPage.tsx ~202 promote a header-level action (e.g. "Mark all read") into the PageHeader `actions` slot, or accept the subtitle-only header but keep the toolbar below on the canon rhythm. | notifications.png |
| /contracts | Inherits the systemic header->info double-margin and the slightly-low DismissibleInfo icon chip; otherwise canonical. | Resolved by S1 + S2 (and the chip nit below). No page-local change. | contracts.png, contracts-crop.png, contracts-dark.png |
| /bid-management | Canonical and correct; only inherits the systemic PageHeader mb-4 gap and slightly-low icon chip. | No page-local change; resolved by S1/S2. | bid-management.png |
| /subcontractors | Canonical and correct; inherits the systemic gap and icon chip. Slow mount (~3s spinner) noted, not an alignment defect. | No page-local change; resolved by S1/S2. | subcontractors.png |
| /carbon | Reference page; PageHeader mb-4 compounds slightly with space-y-5; info body uses em/en dashes (A1-D). | Covered by S1. Replace em-dashes in `carbon.intro_body` (235) with commas to honor the no-em-dash style. | carbon-top.png |
| /finance (dark) | Numbered-step body text contains em-dashes ("BOQ estimate - budget lines", "paid - payment records"). Dark rendering itself is fine. | FinancePage.tsx FinanceWorkflowGuide step copy: replace em-dashes with commas/periods. | finance-dark.png |
| /ncr | Root `w-full animate-fade-in` not space-y-5; rhythm currently leans on baked-in component margins. | NCRPage.tsx root -> `space-y-5 animate-fade-in`, drop per-element mb-*. (Hardens once S1/S2 land.) | ncr.png |
| /inspections | Same as ncr: root not space-y-5. | InspectionsPage.tsx root -> `space-y-5 animate-fade-in`. | inspections.png |
| /punchlist | Header mixes a hand-rolled "View on map" button (border + px-2.5 py-1.5, ~h-7) next to the shared "New Item" Button (~h-8) - two heights and two styles on one midline. | PunchListPage.tsx ~911-921 render "View on map" as a shared `Button variant="secondary" size="sm"` (icon MapPin); optionally adopt the shared PageHeader for the header row. | punchlist.png |
| /collaboration | Root `space-y-6` rather than canonical `space-y-5` (cosmetic). | collaboration page root `space-y-6` -> `space-y-5`. (Slug-in-body is a label-polish item out of scope.) | collaboration.png |
| /daily-diary | Breadcrumb `className="mb-2"` on top of the space-y-5 parent -> double gap above the header. | DailyDiaryPage.tsx ~404 remove `className="mb-2"` from the Breadcrumb. | daily-diary.png |
| /schedule-advanced | PageHeader subtitle rendered alone with no actions, so the header reads as a floating sentence; primary actions live inside tab bodies. | ScheduleAdvancedPage.tsx:338-344 pass an `actions` prop to PageHeader (a context-relevant Create button). | schedule-advanced-top.png |
| /risks | Info treatment above the KPI grid is the small InfoHint pill while siblings use a full card, so the gap above the 4-up grid reads larger than below the header. | Normalizes after the spacing unification (previous risks finding); no tile-internal change. | risks.png |
| /project-controls | Variant B: the whole top block is wrapped in a translucent card (PageHeader is not card-wrapped in canon); Portfolio chip is inline at the end of the subtitle rather than right-aligned. Founder is choosing this variant. | Resolve with the variant decision. If B is not chosen, unwrap the header and move the Portfolio chip / refresh into the actions slot. If B is chosen, use items-start for the multi-line subtitle and align meta chips to the panel padding. | project-controls-top.png |
| DismissibleInfo chip | Across contracts, supplier-catalogs, subcontractors, bid-management: the icon chip (h-7 w-7, mt-0.5) on an items-start row with a text-base leading-snug title sits ~4-6px below the title cap height, reading slightly low. | DismissibleInfo.tsx: tighten with items-center on the title line or reduce the chip `mt-0.5`. One central tweak. | contracts-crop.png |
| / (dashboard) | Bespoke home landing (custom banner, gradient greeting H1, KPI strip). Intentional exception (home page, not a module page). Dark theme verified clean. | No change. Justified exception per style guide section 1 (full-bleed/bespoke surfaces). | root-dashboard.png |
| /files, /documents | Full-bleed file-manager workspace; documented canon exception (manages its own chrome). /documents redirects to /files. | No change. Confirm /documents -> Navigate to /files (App.tsx:876). | files.png |

---

## 4. Prioritized fix order

Systemic first, because each systemic fix retires many page-local rows and the page-root cleanup depends on the central margin removals landing first.

1. S1 - remove `mb-4` from PageHeader (PageHeader.tsx:37). One line, clears the header->next double margin app-wide.
2. S2 - change DismissibleInfo default `mb-5` to `''` (DismissibleInfo.tsx:114-116). One line, second half of the double-margin fix.
3. S5 - fix top-bar module-name truncation (Header.tsx:216/255 + project pill max-w). One file, fixes every route at 1280-1440px.
4. S4 - PlanningCrossLinks: drop nav `mb-4` and move the strip below PageHeader (PlanningCrossLinks.tsx:86). Clears /tasks, /schedule, /schedule-advanced order + double-margin findings.
5. Double-margin mechanical pass (section 2) - set every page root to `space-y-5 animate-fade-in` and delete the listed per-element margins. Pure mechanical, depends on steps 1-2.
6. DismissibleInfo chip vertical nit (items-center / reduce mt-0.5) - one central tweak, clears the low-severity chip rows.
7. High-severity page-local: /catalog (select h-7 + " -- " separator), /takeoff (empty header), /procurement (top-block rebuild).
8. Medium-severity page-local: button-height normalization (assemblies, changeorders, meetings, qms), KPI baseline/tokens (boq, analytics, safety), hand-rolled-header -> PageHeader (supplier-catalogs), strip placement (transmittals), contrast (5d), banner dedup (finance), phantom margin (settings), breadcrumb dedup (photos), header de-crowd (accommodation).
9. Low-severity page-local cleanups (section 3 low table), em-dash copy fixes (bi-dashboards, carbon, finance, takt).
10. Rollout-wave items (section 3 first subsection) - run with the unified-top-block + MODULE_INTRO_COPY wave, not in this pass, so info-title/copy/picker/info-card-swap work is not duplicated.
11. Variant decision (project-controls Variant B, photos Variant C) - blocked on the founder's style choice; resolve when chosen, then roll the picked variant app-wide.
