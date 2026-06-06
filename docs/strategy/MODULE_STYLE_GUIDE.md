# Module Page Style Guide (canonical, v7.0)

Status: adopted 2026-06-06. This is the binding contract for every module page.
Goal: a user landing on ANY of the ~90 module pages sees the same anatomy in the
same order, with the same spacing, tokens and behaviors. Nothing module-specific
about the chrome - only the content differs.

## 1. Page container

- The app shell (`AppLayout`, `frontend/src/app/layout/AppLayout.tsx`) already
  provides `<main className="px-4 pt-6 pb-4 sm:px-7">`. Pages must NOT add their
  own `mx-auto max-w-*` or extra page-level padding.
- Page root: `<div className="space-y-5 animate-fade-in">`.
- Exceptions (full-bleed viewers that manage their own chrome): BIM/CAD/DWG
  viewers, Geo Hub map, takeoff canvas. Everything else follows this guide.

## 2. Header block (always first)

Order top to bottom:

1. `Breadcrumb` - on EVERY module page, always the first element, canonical trail:
   - The shared component already renders the Home icon (-> `/`). Never add a
     "Dashboard" text item - the icon IS the dashboard link.
   - Non-project page: `[Module label]` (current, unlinked). Label = the same
     i18n `nav.*` key as the sidebar item.
   - Project-scoped page: `[Project name -> /projects/:id] -> [Module label]`.
     The project comes from the shared project context, never a page-local
     guess; omit the project item while no project is selected.
   - Detail page: `[Project] -> [Module label -> list route] -> [item name/number]`.
   - Never include sidebar GROUP names in the trail; never link the last item;
     never invent intermediate levels that have no real page behind them.
2. Header row - one line on desktop, wraps on mobile.
   FOUNDER DECISION 2026-06-06: the module NAME renders ONCE - in the top app
   bar (AppLayout title), now accompanied by the module ICON
   (`frontend/src/app/layout/routeIcons.ts`). Pages must NOT repeat the module
   name as an in-page H1.
   - Left: optional one-line subtitle `<p className="text-sm
     text-content-tertiary">` - one sentence, what the module does (i18n).
   - Right: actions, in this order: primary action (`Button` variant primary),
     secondary actions (outline/ghost), then `ModuleHelpButton` where a tour
     exists.
   - NO in-page project picker. Project selection happens ONCE, globally, in
     the top bar; pages read the shared project context
     (`useProjectContextStore`). Local per-module project selects are removed.
3. `DismissibleInfo` immediately under the header row (see section 3).

## 3. Info block (DismissibleInfo)

One per page, `storageKey` = route slug. Canonical behavior (2026-06-06 spec):

- Expanded: translucent light card - background MORE translucent than chrome
  (`bg-oe-blue-subtle/30` over theme surface), text slightly dimmed
  (`text-content-secondary` body, title `text-content-primary/90`).
- Clicking ANYWHERE on the block OR the X collapses it to a bare line: info icon
  + muted label `t('common.module_info')` ("Module information") - NO background,
  NO border. Clicking that line re-expands.
- Collapsed state persists per page (`localStorage oce.intro.<key>`).
- Content: 1-3 sentences max on what the page is for + optional cross-module
  link pills. Never marketing copy.

## 4. KPI strip (where the module has headline numbers)

- Directly under the info block: `grid grid-cols-2 gap-3 sm:grid-cols-4`
  (2-6 tiles). Tile = `Card` with `text-2xs uppercase tracking-wide
  text-content-tertiary` label and `text-lg font-semibold text-content-primary`
  value. Money via `MoneyDisplay`, dates via `DateDisplay` - never hand-formatted.

## 5. Content area

- Cards: shared `Card` (rounded-xl border border-border bg-surface-primary).
- Tabs: shared `TabBar` only - no hand-rolled tab rows.
- Tables/grids: full width; toolbar row above (search input left, filters middle,
  view switches right) using shared `Input`/`ChipBar`.
- Empty states: shared `EmptyState` ALWAYS - icon, one-line explanation of what
  will appear here, and a primary action button that starts the flow (or a deep
  link to the module that produces the data). Never a bare "No data".
- Loading: `SkeletonLoader` mirroring final layout; never a perpetual skeleton -
  resolve to data or `EmptyState` within the query lifecycle.
- Errors: inline retry block (message + retry button), not a toast alone.

## 6. Tokens and language

- Theme tokens only (`text-content-*`, `bg-surface-*`, `border-border*`,
  `oe-blue` accents). No raw hex, no raw `text-gray-*` in new chrome.
- Every string through i18n `t()`. No hardcoded English in headers, tabs,
  stage labels, empty states.
- Currency NEVER defaulted (no hardcoded EUR/USD) - always the project currency.
- Em-dash for empty cells; "N/A" is banned.

## 7. Connective tissue

- Project-scoped pages read/write the shared project context
  (`useProjectContextStore`) - never a page-local default to "first project".
- Each page exposes at least one deep link IN (from related modules) and OUT
  (to where its results are consumed). Result rows link to the consuming module.

## Reference implementation

`/procurement` (header + tabs + empty states) and `/collaboration` (2026-06-06
rework) are the visual reference. When in doubt, copy their classes.
