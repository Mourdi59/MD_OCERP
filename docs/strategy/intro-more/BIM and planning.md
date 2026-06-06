# BIM and planning - "Show more" expansion copy

Long-form expansion copy revealed by the "Show more" button beneath each module's DismissibleInfo block. These do not repeat the intro_title/intro_body in MODULE_INTRO_COPY.md; they go a layer deeper into the actual workflow.

---

## bim
KEY: bim.intro_more

When you open the viewer, upload a Revit (.rvt) or IFC (.ifc) file and it is converted into the canonical element data the rest of the platform reads. Once it processes you get a full 3D model you can orbit and section. Click any element to read its properties and quantities in the right panel, and use the filter and groups panels to isolate a storey, a category or a discipline. From a selection you can add the elements to a BOQ position, save a reusable group, or open the same data as a table.

This module is the canonical source for everything downstream. Linked elements push their quantities into the BOQ, those quantities carry into cost and into the 4D schedule when activities are tied to the model. From here you can jump to the Data Explorer to slice the element data, to the map to place the model, or to BIM Rules to link elements in bulk.

**Getting the most out of it:**
- DWG and DXF files are not accepted here, send those to DWG Takeoff instead.
- Use storey and category filters before linking, so a BOQ position picks up exactly the right elements.
- Flag an element as a tracked asset with a manufacturer or serial and it appears in the Asset Register for handover.

---

## bim_federations
KEY: bim_federations.intro_more

Pick the project, then create a federation and give it a name and shared units. Open it and add member models one at a time, tagging each with a discipline (architectural, structural, MEP, landscape, civil or other) so it carries a color swatch. The Members tab manages the set, the Element types tab shows a flat class tree across all members, and the 3D tab lists each member with a link that opens it in the per-model viewer. Members whose geometry is not available are greyed out so you never land on an empty canvas.

A federation groups models that already live in the BIM viewer, it does not duplicate them. Removing a member only breaks the grouping, the model itself stays in the project. Federations are what Clash Detection and the Coordination dashboard read when they check disciplines against each other, and they keep takeoff and BOQ work aligned to one coordinated set.

**Getting the most out of it:**
- Group models that share an origin point, otherwise disciplines will not line up in 3D.
- Tag disciplines consistently so the color coding stays readable across the set.
- The combined federated scene is still being built, for now open members individually from the 3D tab.

---

## bim_rules
KEY: bim_rules.intro_more

On the Quantity Rules tab, start from a preset like Walls by area or Doors by count, or build a rule from scratch. Set an element type filter (wildcards such as Wall*, IfcWall are supported), optional property key/value filters, and the quantity source (area, volume, length, weight or count) with a multiplier and waste factor. Point the rule at an existing BOQ position or let it auto-create one, optionally using Suggest from CWICR to prefill a unit rate. Run a dry-run preview to see matched elements and the quantities before you apply, then apply it to a model to create all the links at once.

The rule reads elements from a BIM model and writes BOQElementLink rows plus, when auto-creating, new BOQ positions, so quantities roll into the BOQ without per-element clicking. The same page also holds the Requirements tab, where you write information requirements as filter, parameter and constraint, and a Rule Library tab of ready-made packs. Requirement sets are what incoming models are validated against.

**Getting the most out of it:**
- Always run the dry-run preview first, it shows how many elements match and what each quantity resolves to.
- Use a waste factor on materials like concrete or paint so the BOQ quantity already includes loss.
- Keep one rule per trade or material so a re-apply after a model revision stays predictable.

---

## assets
KEY: assets.intro_more

Pick a project, then this page shows every BIM element that was flagged as a tracked asset, with its manufacturer, model, serial, operational status and warranty date. Search across manufacturer, model and serial, or filter by status (operational, under maintenance, decommissioned or planned). Click a row to open a detail drawer with the geometry and full properties, click Edit to record operational data, or use the model link to open the element in the 3D viewer with that asset already selected.

Assets are not created here, they originate in the BIM viewer: open a model, pick an element, and set a manufacturer or serial to register it. This page is the operations and handover view of that data. Each row can export a COBie spreadsheet for the whole model, so the facilities team receives a structured register tied back to the canonical model rather than a loose document.

**Getting the most out of it:**
- Set a clear operational status on each asset so the status filter actually separates live plant from planned items.
- Record the warranty date while the data is fresh, it is the column the FM team will sort on first.
- Export COBie per model at handover rather than at the end, so the register stays current as the model updates.

---

## cad-explorer
KEY: cad-explorer.intro_more

Open the Data Explorer with a converted model loaded and you land on the Data Table tab: filter, sort and search the element rows, toggle a heatmap on numeric columns, and export the visible set to CSV. The Pivot tab groups and aggregates by any column (sum, average, min, max, count or count unique). The Charts tab visualizes distributions, and the Describe tab gives a statistical summary of every numeric column. A missing-data panel and threshold rules flag rows that are empty or out of range.

The element data comes from a model converted in the BIM module. You can save a filtered selection back as a new BIM model that opens in the 3D viewer, so a slice of the data becomes its own working set. Cleaned, measured quantities here feed back into the quantity takeoff and BOQ flow.

**Getting the most out of it:**
- Use the Describe tab early to spot columns that are mostly empty before you trust a quantity.
- Set threshold rules on key dimensions so unrealistic values turn red instead of slipping into a takeoff.
- Pivot by category or storey to sanity-check element counts against what you expect on site.

---

## dwg-takeoff
KEY: dwg-takeoff.intro_more

Upload a DWG or DXF drawing and it renders as 2D entities on a canvas. Toggle layers in the right panel to clear the clutter, then pick a measurement tool from the toolbar to measure distances, areas and counts directly on the plan. Calibrate the scale first if the drawing units are unknown, so measurements come out in real metres. Each measurement you keep can be linked to a BOQ position, and you can compare two revisions of a drawing side by side in the compare drawer.

This is the 2D CAD counterpart to the BIM viewer: it handles the .dwg and .dxf files that the BIM Hub turns away. Measurements linked here flow into the BOQ alongside quantities from BIM models and PDF takeoff, so a job that mixes 2D drawings and 3D models still rolls up into one estimate. You can also export the marked-up canvas to PDF.

**Getting the most out of it:**
- Calibrate the scale before measuring anything, an uncalibrated drawing produces meaningless lengths.
- Turn off layers you are not measuring so snapping lands on the right line.
- Use the revision compare to re-measure only what changed instead of redoing the whole sheet.

---

## geo-hub
KEY: geo-hub.intro_more

The hub opens on a shared 3D globe with every anchored project pinned. Use the scope control to switch the view and the overlay panel to see the list of anchored projects, collapsing it to reveal the full globe. To place a project, type its address into the autocomplete or drop a coordinate, and it is geocoded and pinned. From a pin you jump straight into that project's BOQ, BIM models and the rest of its data.

This is the portfolio-level map. Pins are anchored projects from the Projects module, and the address-to-coordinate lookups are cached by the geocode service that the Geo Hub admin page maintains. From here you move into a single project's map for site overlays, or into any project hub for the cost work.

**Getting the most out of it:**
- Anchor projects by full street address for the most accurate pin, coordinates are the fallback.
- Switch to 2D or Columbus view when you want a flatter read of a dense region.
- Use the hub as a launchpad, click a pin to drop straight into the project rather than navigating the sidebar.

---

## geo_admin
KEY: geo_admin.intro_more

This page is limited to administrators. It shows aggregate statistics for the geocode cache that powers every address-to-coordinate lookup across the Geo Hub: how many results are stored and when they were last touched. A clear action purges stale entries (30 days and older) so the cache does not grow without bound and lookups stay fast.

The cache sits behind the address autocomplete and the auto-anchor flow used on the global map, the project map and the development map. Clearing it forces fresh lookups on the next anchor, which is the right move if an upstream geocoder corrected a result. Access is enforced both on the route and on every backend call.

**Getting the most out of it:**
- Only purge when addresses are resolving to the wrong place, normal use does not need maintenance.
- A purge slows the next few lookups while the cache refills, so run it during quiet hours.
- The stats are a quick health check, a stale last-touched date usually just means nobody anchored recently.

---

## geo_project
KEY: geo_project.intro_more

This is one project on the 3D globe. If the project has no anchor yet, place it by address or coordinate using the place-on-map picker, and adjust the anchor if the pin drifts. Once anchored, the tileset sidebar lists the imagery and 3D tilesets available for the site, and the overlay panel turns on site data pinned at its real-world location: daily-diary photos, HSE incidents and punch-list items. The HUD shows live cursor coordinates, altitude and a scale bar.

The map reads its anchor, imagery and tilesets from this project's map config, and the overlays pull from the Daily Diary, Safety and Punch List modules so what happened on site appears where it happened. It shares the same map chrome as the development map. Empty states explain clearly whether the project lacks an anchor, lacks tilesets, or whether every tileset failed to load.

**Getting the most out of it:**
- Anchor the project accurately first, every overlay and tileset positions relative to that point.
- Use the phase or block filters where available to paint just one part of a large site.
- If the canvas looks empty, read the empty-state message, it tells you which piece is missing rather than failing silently.

---

## geo_development
KEY: geo_development.intro_more

This shows a single property development on the same 3D globe used elsewhere, scoped to that development. In most cases the development is already placed: the create-development flow drops it on the project map automatically, so opening this page just frames the site with its imagery and tilesets. The tileset sidebar lists what is available, and optional phase or block filters narrow the view to one part of the scheme.

It shares the map chrome and the collapse-panel preference with the project map, so the two feel like one tool. The development location comes from the property-dev create event, so you reach this view from inside the property pages as a quick way to see the site in context rather than as a place to set things up.

**Getting the most out of it:**
- This is the fastest route to see a development on the ground, open it from the property-dev pages.
- Use the phase filter to review one release at a time on a multi-phase scheme.
- If the development is not placed, set its location from the property-dev pages, this map follows that anchor.

---

## schedule
KEY: schedule.intro_more

Create a schedule and set its start and end dates. Add activities by hand, or use Generate from BOQ to turn an estimate's structure into a starting activity list, then refine durations and draw dependencies. The timeline renders as a Gantt with the critical path highlighted; click Calculate critical path to flag the activities that drive the finish, and run the risk analysis for a probabilistic finish-date view. Activities can be marked as tasks, milestones or summaries.

The schedule pulls its structure from a project BOQ and writes nothing back to it. Link an activity to BIM elements to drive a 4D sequence, with a View in BIM button once models exist. For deeper critical-path work open the CPM view, and for Last Planner phase plans, look-aheads and weekly commitments move up to Advanced Scheduling.

**Getting the most out of it:**
- Generate from a BOQ to skip the blank start, then prune the activities you do not need to track.
- Set dependencies before running CPM, the critical path is only as honest as the links you draw.
- Link activities to BIM elements early so the 4D sequence is ready when you need to show progress.

---

## schedule_cpm
KEY: schedule_cpm.intro_more

This view runs the Critical Path Method over one schedule and lays out every activity with its early start, early finish, late start, late finish and total float, with the critical activities flagged. Press recompute after editing durations or dependencies to refresh the forward and backward pass. The result tells you which activities have slack and which cannot move without pushing the finish date.

When crews or kit are over-committed, open the resource-leveling step: it reads the distinct resources on the activities, lets you set a limit per resource, and shifts non-critical activities to ease the overload while protecting the finish date. The shifts are shown as before-and-after early starts so you can see exactly what moved. It works on the schedule built in the 4D Schedule module.

**Getting the most out of it:**
- Float is your buffer, the activities with zero total float are the ones to protect first.
- Level resources only after the network is stable, leveling a half-linked schedule produces noise.
- Recompute after every duration or dependency change so the dates you read are current.

---

## schedule-advanced
KEY: schedule-advanced.intro_more

Work the tabs in order. Start a master schedule, then break the work into phase plans (apply a phase template to skip the setup) and pull, start and complete each phase as the work flows. Build a look-ahead and clear its constraints before they bite. Each week, create a weekly work plan and capture commitments from the trade foremen, then mark each commitment committed, completed or missed; a missed commitment records a reason for non-completion. Capture baselines to track variance against the plan.

This is the Last Planner layer on top of a master schedule, distinct from the 4D Schedule's Gantt and CPM. The reasons for non-completion feed root-cause analysis so recurring blockers surface. For location-based flow scheduling, the Takt page sits alongside it and shares the same master schedules.

**Getting the most out of it:**
- Clear constraints in the look-ahead before a commitment is made, that is the whole point of the six-week window.
- Be honest about missed commitments, the reason codes are what drive the improvement, not the percent complete.
- Capture a baseline at the start of each phase so the variance you report later means something.

---

## takt
KEY: takt.intro_more

Pick a project and a master schedule, then create a takt schedule and define its sequence of locations (zones, floors or areas). Import trade activities into the schedule, then press Compute line of balance. You get the marching diagram where each trade is a diagonal line moving location to location, a crew-flow view, and a list of any takt-rhythm violations where a trade falls behind or collides with the one ahead. Export the result when you need to share it.

Takt builds on the master schedules from Advanced Scheduling and turns them into location-based flow. Where the Gantt answers when an activity happens, the line of balance answers whether trades hand off cleanly zone to zone at a steady beat instead of bunching up.

**Getting the most out of it:**
- Order your locations the way crews actually move through the building, the diagram is only as right as the sequence.
- Aim for parallel diagonal lines, lines that converge are crews about to collide.
- Read the violations list as your early-warning system, fix the rhythm before it shows up on site.

---

## carbon
KEY: carbon.intro_more

Open an inventory for a project, then assign material carbon factors to its BOQ positions, drawing from EPD sources such as Okobaudat, ICE and EC3 or entering a manual override. The embodied total rolls up across lifecycle stages A1 to D. Separate tabs hold the EPD records you reuse, the Scope 1, 2 and 3 operational carbon entries, and the reduction targets you track progress against. When the numbers are ready, generate a report in GHG Protocol, GRI or ISSB format.

Embodied carbon is driven by the BOQ: each priced position carries a quantity that the carbon factor multiplies. This is the full corporate inventory, with scopes, targets and standards reporting. For a quick position-by-position footprint of a single BOQ, the Sustainability page covers that lighter view and shares the same EPD factor library.

**Getting the most out of it:**
- Reuse EPD records across positions rather than re-keying factors, it keeps the inventory consistent.
- Set reduction targets up front so the progress view has something to measure against.
- Use a manual override only when no EPD fits, and note the source so the report stands up to scrutiny.

---

## risk
KEY: risk.intro_more

On the Register tab, log each risk with a category, probability, cost impact, schedule impact in days and an owner, and the system scores it. The probability-by-impact matrix shows where your exposure clusters, and totals are kept per currency rather than blended, so a euro risk is never silently added to a dollar one. Risks that cross an escalation threshold or pass a lapsed review date are flagged automatically. The Monte Carlo tab runs a simulation across the whole register.

This is the qualitative risk register for a project. The planning cross-links carry the project context into the schedule and cost work so a risk is not assessed in isolation. For probabilistic cost contingency driven by a BOQ rather than the register, use Risk Analysis; for schedule-driven cost-time uncertainty, the 5D simulation covers that.

**Getting the most out of it:**
- Fill in both cost and schedule impact, the score and the matrix both depend on them.
- Assign a real owner to every risk, an unowned risk is one nobody is closing.
- Trust the per-currency totals, a blended single number across currencies would mislead.

---

## sustainability
KEY: sustainability.intro_more

Select a project and one of its BOQs, then enrich it with EPD material factors and press Calculate. You get the total CO2 for that bill, a per-square-metre benchmark with a letter rating, a compliance read, and a breakdown by material category drilling down to each individual position. A donut chart shows where the emissions sit by category. Export the CO2 report as PDF or CSV when you need to hand it over.

This is the per-BOQ footprint view, the quick answer to what one estimate's carbon looks like, position by position. It shares the same EPD material factor library as the Carbon module. When you need full inventories, operational scopes, reduction targets and standards-format reporting, the Carbon module is where that lives.

**Getting the most out of it:**
- Enrich with EPD factors before calculating, an un-enriched BOQ has nothing to multiply.
- Read the per-square-metre benchmark, it compares far better between projects than a raw total.
- Use the category breakdown to find the few materials driving most of the footprint, that is where reduction pays off.

---

## risk-analysis
KEY: risk-analysis.intro_more

Pick a project and a BOQ, generate the default parameters or tune the distribution on each position, then run the Monte Carlo simulation. The result is a probability distribution of total project cost shown as a histogram with the P50 and P80 markers drawn in, the band below P50 in green and above P80 in red. The recommended contingency is the gap between the P80 and P50 outcomes. A Top 10 Risk Drivers table ranks the positions contributing most to the uncertainty.

This focuses on cost uncertainty position by position, reading directly from a BOQ, so the contingency you set rests on the spread of likely outcomes rather than a flat percentage. It is the canonical cost Monte Carlo. For the qualitative register use Risks, and for schedule-driven cost-time uncertainty use the 5D simulation.

**Getting the most out of it:**
- Set the P80-minus-P50 gap as your contingency, it is the buffer the simulation says you actually need.
- Work the Top 10 drivers, narrowing the range on those few positions tightens the whole distribution.
- Re-run after pricing firms up, the contingency should shrink as uncertainty leaves the estimate.

---
