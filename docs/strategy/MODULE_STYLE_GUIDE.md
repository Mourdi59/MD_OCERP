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

1. `Breadcrumb` - first element where it has DEPTH. The shared component
   hides single-item trails itself (founder decision 2026-06-06): a lone
   module label duplicates the top app bar (project pill + module icon +
   module name) and renders nothing. Pages still PASS their canonical trail;
   the component decides visibility.
   - The shared component already renders the Home icon (-> `/`). Never add a
     "Dashboard" text item - the icon IS the dashboard link.
   - Non-project page: `[Module label]` (current, unlinked; hidden at runtime).
     Label = the same i18n `nav.*` key as the sidebar item.
   - Project-scoped page: `[Project name -> /projects/:id] -> [Module label]`.
     The project comes from the shared project context, never a page-local
     guess; omit the project item while no project is selected.
   - Detail page: `[Project] -> [Module label -> list route] -> [item name/number]`.
   - Never include sidebar GROUP names in the trail; never link the last item;
     never invent intermediate levels that have no real page behind them.
2. Header row - use the shared `PageHeader` component
   (`frontend/src/shared/ui/PageHeader.tsx`). One line on desktop, wraps on
   mobile. FOUNDER DECISION 2026-06-06: the module NAME renders ONCE - in the
   top app bar (AppLayout title), accompanied by the module ICON
   (`frontend/src/app/layout/routeIcons.ts`). Pages must NOT repeat the module
   name as a visible in-page H1 (pass `srTitle` for screen readers).
   - Left: optional one-line subtitle - one sentence, what the module does
     (i18n), `text-content-tertiary`.
   - Right: actions, in this order: primary action (`Button` variant primary),
     secondary actions (outline/ghost), then `ModuleHelpButton` where a tour
     exists.
   - NO in-page project picker. Project selection happens ONCE, globally, in
     the top bar; pages read the shared project context
     (`useProjectContextStore`). Local per-module project selects are removed.
3. `DismissibleInfo` immediately under the header row (see section 3).

## 3. Info block (DismissibleInfo)

One per page, `storageKey` = route slug. Canonical behavior (2026-06-06 spec):

FOUNDER DECISION 2026-06-06 (content): the expanded TITLE is never the module
name and never a generic "Information" - it names the PAIN the module closes,
in the user's language ("Nothing slips through at handover", not "Punch
list"). The BODY explains HOW the module works in 1-3 plain sentences (what
you put in, what you get out, where the result goes next). The collapsed
state keeps the neutral `common.module_info` label. Canonical copy deck:
`docs/strategy/MODULE_INTRO_COPY.md` - every page's intro title/body comes
from there via i18n keys (`<feature>.intro_title` / `<feature>.intro_body`).

- Expanded: translucent light card with a VISIBLE light blue tint:
  `bg-oe-blue/10 dark:bg-oe-blue/[0.14] backdrop-blur-sm`, border
  `border-oe-blue/20` + left accent `border-l-oe-blue/70`. Body
  `text-content-secondary`, title `text-content-primary`.
  WHY these exact classes (2026-06-06): alpha modifiers on var()-based
  Tailwind colors emitted NO css until the channel-triplet fix
  (`--oe-blue-ch` in index.css + function colors in tailwind.config.js) -
  `bg-oe-blue-subtle/25` and friends silently rendered transparent.
  `oe-blue-subtle` deliberately has NO alpha support (its dark value is
  itself an rgba tint) - use `bg-oe-blue/<n>` for translucent blues.
- FOUNDER DECISION 2026-06-06 (collapse target): clicking ANYWHERE on the
  block OR the X removes the card from the page ENTIRELY - no leftover line
  in the content flow. The card registers in `useModuleInfoStore` and the
  TOP APP BAR shows a small info icon right after the module name (project
  pill > module icon + name > info icon). Clicking that icon re-expands the
  card in the page (and the icon disappears). Implemented centrally in
  `DismissibleInfo.tsx` + `Header.tsx` (`ModuleInfoReopener`) - pages need
  no changes.
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
