## projects
KEY: projects.intro_more

Click **New project** to add work, then watch each project appear as a card showing its BOQ count, total value in its own currency, region, classification standard and chips for the file types you have uploaded. Use the search box to find a project by name or description, narrow the grid with the status and region filters, and reorder by name, newest, oldest or value. Star a project to pin it to the top, and flip on the Map and Weather toggles to see each site's location and forecast right on its card.

The four summary cards roll up your whole portfolio: total projects, total BOQs, total value and average project size. Values are never blended across currencies, so a EUR job is always kept separate from a USD one. The card numbers come from each project's BOQ work, and the same totals feed the cross-project table in Analytics and the role dashboards in Reporting.

**Getting the most out of it:**

- Pin your two or three live jobs so they stay at the top no matter how you sort.
- An amber triangle on a card means open variations need attention.
- Use the per-card On map link to jump straight to the project on the globe.
- Duplicate, archive or delete a project from its card menu, and Undo an accidental archive from the toast.

---

## projects_new
KEY: projects_new.intro_more

When you start a project you first pick a path. **Quick create** puts every setting on one screen and asks only for a name; region, currency, classification standard, address, client, dates and budget are all optional and editable later. **Guided setup** walks you through five short steps: basics, region and currency, project type, scope, then site and review. As you answer, the wizard pre-selects the modules that match the work you do and turns on a focused sidebar, so the project opens ready to estimate instead of crowded with tools you will not use.

Your region and currency are not cosmetic. They drive cost-database matching and the prices you see in BOQ and Costs, and the classification standard you choose (DIN 276, NRM, MasterFormat and others) shapes how the estimate is structured. The setup can be re-run any time from Project Settings.

**Getting the most out of it:**

- New to the platform or unsure which modules you need? Take the guided setup.
- Know exactly what you want? Quick create gets you working in one screen.
- Set region and currency early so cost matching and pricing line up from the start.

---

## project_detail
KEY: project_detail.intro_more

This is the project hub. The tab bar across the top moves you between the **Dashboard** (live widgets and key stats), **Overview** (the project's BOQs), the **4D Schedule**, the **5D Budget**, **Tendering**, **Photos** and **Compliance**, all without leaving the page. The dashboard surfaces RFIs, change orders, daily diary, HSE incidents, variations, budget burn, quality NCRs and recent files as widgets you can rearrange, and a setup checklist tracks whether the BOQ is created, priced and validated.

Open a BOQ from the Overview tab to start estimating, or jump to the budget and schedule tabs to see cost and time. The numbers shown here are pulled live from the modules that own them, so a change in BOQ pricing or budget flows straight back into the totals on this page and into Analytics and Reporting.

**Getting the most out of it:**

- Use the checklist tiles as a fast way to spot what is missing before a deadline.
- Open **Project Settings** from here to change region, currency, VAT or active modules.
- Click a budget or schedule widget to jump directly into that tab.

---

## project_settings
KEY: project_settings.intro_more

Settings is where you fix a project's ground rules once. Set the base currency and add FX rate rows for any other currencies the project touches, set a default VAT rate (or let the regional default apply), and add custom units beyond the standard m, m2, m3, kg, pcs and lsum. The compliance rule packs section lets you pick which jurisdiction standards the project is checked against, and a **Re-run setup** action reopens the guided wizard so you can change region, classification standard or which modules are active.

These choices are the single source of truth that the rest of the platform reads. BOQ pricing uses the currency and VAT, Validation enforces the compliance rule packs you select, and reports inherit the same settings, so correcting a value here keeps every downstream number consistent instead of fixing it in five places.

**Getting the most out of it:**

- Add an FX rate row for every foreign currency before you import priced data in it.
- Leave the VAT field blank to inherit the regional rate, or type a percent to override it.
- Re-run setup when a project's scope grows and you need more modules switched on.

---

## dashboards
KEY: dashboards.intro_more

This page freezes your model data so changes become provable. Pick the active project, then click **New snapshot** to turn its uploaded IFC, RVT, DWG or DGN files into a dated parquet dataset that captures every element and category at that moment. Each snapshot is listed with its entity count, category count and creation time. Switch to the **Timeline** view to see how the model has grown over revisions, or the **Diff** view to pick an older snapshot (A) and a newer one (B) and see exactly what was added, removed or changed between them.

Snapshots are scoped to the project you have active and are built from the CAD and BIM files managed through the BIM module and File Manager. Once frozen, a snapshot becomes the dataset that the Data Explorer queries and that later charts read from, so analysis always runs against a fixed, citable revision rather than a moving target.

**Getting the most out of it:**

- Take a snapshot at each major model issue so you always have a baseline to diff against.
- Use the Diff view before accepting an incoming model revision to catch unexpected changes.
- Send a snapshot to the Data Explorer when you want to slice the frozen data like a spreadsheet.

---

## reporting
KEY: reporting.intro_more

Reporting gives each role the numbers it cares about the moment the page opens. Switch between the **Executive**, **PM**, **Estimator**, **Site** and **Finance** tabs to see live CPI and SPI, budget consumption, schedule progress, open RFIs and submittals, safety stats and risk scores, each carrying a traffic light so anything off track stands out. A managers-only Recalculate action refreshes the portfolio KPIs on demand.

Every figure is pulled live from the module that owns it: finance, schedule, safety, RFIs and the rest. KPIs only appear once a project has its first cost snapshot, so a dash means a metric has not been measured yet, not that something is broken. For the cross-project budget-versus-actual table use Analytics, and to hand someone a document use Reports.

**Getting the most out of it:**

- Start a project's first cost snapshot to light up the KPI cards.
- Watch the traffic lights rather than the raw numbers for a fast health read.
- Use the role tabs to give each stakeholder exactly the view they need.

---

## reports
KEY: reports.intro_more

Reports turns project data into a file you can hand over. Pick a project and a BOQ, then choose the deliverable: detailed BOQ as PDF or Excel, a cost breakdown by category, GAEB X83 XML for tender exchange, validation results, a schedule summary or a 5D budget-versus-actual report. Click a format and the file downloads in the structure your client or authority expects. A history panel keeps the reports you have already generated so you can find an earlier export without rebuilding it.

The numbers in every export come straight from the BOQ and cost data, so what you send matches what you see on screen. Reporting holds the live role dashboards and Analytics the cross-project comparison, while Reports is the place you come to when the output needs to be a document rather than a screen.

**Getting the most out of it:**

- Export GAEB X83 when a DACH client or tender platform expects native LV data.
- Use the Excel BOQ export when the recipient wants to work the numbers themselves.
- Check the history panel before regenerating, the file you need may already be there.

---

## analytics
KEY: analytics.intro_more

Analytics rolls every project's budget against its actual cost into one sortable table and a bar chart, so you can see at a glance which jobs are running over and by how much. Sort by name, budget, actual cost, variance or variance percent, filter by region or status, and search by name. Currencies are kept strictly separate, with per-currency subtotals, so a EUR project is never blended into a USD figure. Export the comparison to CSV when you need it outside the app.

The data comes from each project's budget and BOQ work, the same source the project cards and Reporting read from. Click any row to open that project directly, or move to Reporting when you want the role-by-role KPI view instead of the portfolio cost table.

**Getting the most out of it:**

- Sort by variance to put the projects bleeding money at the top of the list.
- Filter by region to compare like markets without mixing currencies.
- Export to CSV for a board pack or a finance review.

---

## bi-dashboards
KEY: bi-dashboards.intro_more

BI Dashboards saves you from rebuilding the same board every week. The fastest start is the one-click **starter pack**, which installs five role-based dashboards (CEO, CFO, PM, Site, Safety), the full library of system KPIs with twelve weeks of history, three reports, two schedules and four alert rules, and is safe to re-run. The tabs across the top split the work into Dashboards, KPIs, Reports, Schedules and Alerts, and you can build your own dashboard from the KPI library instead of using the pack.

On the **Schedules** tab, set any report to deliver itself to recipients on a cadence. On the **Alerts** tab, create a rule that fires when a KPI crosses a threshold. Every KPI is computed live from your project data, so the boards stay current without manual refreshing, and alerts that fire feed through to the Notifications inbox.

**Getting the most out of it:**

- Install the starter pack first, then prune or customize rather than starting blank.
- Schedule the executive report so stakeholders get it without asking.
- Set threshold alerts on CPI or budget consumption so problems reach you early.

---

## notifications
KEY: notifications.intro_more

The Notifications page is the full inbox behind the header bell. The **Inbox** tab collects every alert the platform raises, finished imports, validation results, safety events, approvals and system messages, each with a colored icon for its category. Filter by all, unread or read, page through the history, mark items read, mark everything read at once, and click a notification to jump straight to the record that triggered it.

The **Preferences** tab is a matrix of event types down the side and channels across the top, in-app, email and webhook, where each cell is a toggle so you decide exactly which events reach you on which channel. Threshold alerts you set in BI Dashboards arrive here, and the outbound rules configured under Notification Webhooks are driven by the same engine.

**Getting the most out of it:**

- Turn off in-app noise for low-priority event types and keep email for the ones that matter.
- Use the unread filter to clear a backlog fast.
- Click through from a notification rather than hunting for the source record by hand.

---

## tasks
KEY: tasks.intro_more

Tasks captures the lightweight action items, topics, information notes, decisions and personal to-dos that keep a project moving. Click **New task** to add one with an assignee, due date, priority and a checklist, and create your own colored categories and Kanban status columns to match how your team works. A task pinned to BIM elements shows a View in BIM button, and tasks created from a meeting or another source carry a tag back to where they came from. Export the list whenever you need it outside the app.

This is deliberately separate from the 4D Schedule, which plans the build timeline, and it complements the weekly commitments in Last Planner rather than replacing them. Flip on **My Tasks** for a cross-project list of everything assigned to you, which is resolved from your login and does not need a project selected.

**Getting the most out of it:**

- Use My Tasks first thing to see everything on your plate across every project.
- Add a checklist to bigger tasks so progress is visible at a glance.
- Pin coordination tasks to BIM elements so the next person can open them in the model.

---
