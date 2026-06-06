# Corporate and configuration - intro_more expansion copy

Long-form "Show more" expansion copy for the Corporate and configuration cluster.
Each entry is the text revealed when a user clicks "Show more" under the module's
DismissibleInfo card. Rendered through IntroRichText (paragraphs, bullet lists,
numbered lists and **bold** only).

---

## crm
KEY: crm.intro_more

The CRM gives you five tabs across the top: Pipeline, Deals, Leads, Activities and Insights. Most of the work happens on the Pipeline board, where each stage is a column and each deal is a card you drag from one column to the next. Dragging a card moves its stage in one click. Open a deal to see its value, weighted value and probability, click a stage in the stepper to advance it, log a quick note, or close it with the Win and Lose buttons. New enquiries start on the Leads tab; qualify a lead and convert it into a deal.

A deal links out to the rest of the platform rather than storing its own copies of anything:

- People and companies are resolved live from **Contacts** through the deal's primary contact; the picker pulls your live contacts list.
- A deal links to its delivery **Projects** record and deep-links straight to it.
- A won deal points you on to **Bid Management** to issue packages and to **Contracts** to formalize the award.

**Getting the most out of it:**

- Drag-and-drop is the fastest way to keep the board honest, do it after every call.
- Use the Win and Lose buttons to close deals, the final stages on the board are intentionally not droppable.
- Pick a loss reason when you lose a deal so the Insights tab can show you why you are dropping work.

---

## contacts
KEY: contacts.intro_more

Contacts is one shared address book for every party on your projects. Click New Contact, pick a type (client, subcontractor, supplier, consultant, internal, lead or customer), fill in the company or person, country, payment terms and a prequalification status, then save. You can bulk-import from Excel or CSV with the supplied template, export the whole directory, search by name or email, and filter by type, country or the CRM tag chips above the search bar. The KPI strip shows your total directory size and counts by type at a glance.

Each record is reused everywhere instead of being re-typed:

- A prequalification status (approved, pending, expired, rejected) gates who can be invited to bid in **Subcontractors** and **Bid Management**.
- The same record surfaces as ball-in-court on **RFI** and submittals, as a transmittal recipient, and as a correspondence party.
- Open a contact's detail drawer to convert it into a Property Development lead, when that module is enabled.

**Getting the most out of it:**

- Keep prequalification status current; an expired certificate is what stops an award before it happens.
- Import your existing supplier list once rather than adding firms one at a time.
- Set realistic payment terms on each company so downstream invoicing and procurement read the right number.

---

## finance
KEY: finance.intro_more

Finance is organized in five tabs: Budgets, Invoices, Payments, EVM Dashboard and Connectors. Start on Budgets by adding budget lines against your WBS categories, or import them from Excel. Each line tracks original, revised, committed, actual and forecast side by side, with the variance colored green when under budget and red when over. Log invoices as payable or receivable, record payments against them, and watch the summary cards and the budget-consumption bar update. The EVM Dashboard turns it into cost and schedule performance once a project has cost data.

Finance pulls from and pushes to the cost side of the platform:

- Lock a **BOQ** estimate and click Create Budget from Estimate to seed your budget lines automatically.
- The **5D Cost Model** and Finance share the same budget and actuals so the numbers stay aligned.
- Purchase orders raised in **Procurement** flow in as committed spend, and invoices roll up into Actual once paid.

**Getting the most out of it:**

- Seed budgets from a locked BOQ instead of typing them, it keeps the WBS and the estimate in step.
- Every record carries its own currency; when a project spans several, set FX rates so totals convert cleanly rather than reading as approximate.
- Watch the budget-consumed bar, it flags over 80 percent as watch and over 95 percent as critical.

---

## portal
KEY: portal.intro_more

The portal is the controlled outside door of the platform. Work it in four tabs: Users, Access Rules, Audit Log and Progress Reports. Invite a client, investor, consultant or subcontractor by email and the system generates a magic-link token, shown once for you to copy and send (email delivery is not wired up yet). Then open Grant Access and create one rule at a time: pick the user, choose a resource (a project, document, development, service ticket or invoice), and set a single permission of view, comment, submit or sign. Nothing is visible to the outsider until you explicitly grant it.

The portal scopes external people against your real project data:

- Grant access to a single project picked by name from **Projects**, or to specific documents in your **Files**.
- Internal staff manage the contractor-facing side of payment applications as progress claims under **Contracts**; the portal payments surface is external only.
- Every view, download and signature an invited user makes is recorded in the Audit Log with IP address and timestamp.

**Getting the most out of it:**

- Grant the narrowest permission that does the job, one rule covers one resource, so create several rules for several projects.
- Set an expiry date on time-limited access rather than leaving it open-ended.
- Suspend or revoke at any time from the user drawer or the access-rules table; nothing the outsider could see survives a revoke.

---

## settings
KEY: settings.intro_more

Settings is laid out as a sidebar of tabs: General, Dashboard, Account, Regional, Converters, AI, Integrations and Advanced. Under General you set your profile name, theme and the Simple/Advanced interface mode that controls how much of the navigation shows. Regional holds language, timezone and number formats. The AI tab is where you pick an LLM provider from the long list, paste its API key, optionally override the model name, and press Test Connection. Converters manages your installed DDC converter versions, and Integrations wires up chat and webhook delivery.

These choices are workspace-wide and flow into the rest of the platform:

- The Advanced tab opens backup, restore and the database setup wizard at **Databases & Resources**.
- Integrations and webhooks set here also live under **Integrations**.
- Which modules appear in your sidebar is governed on the **Modules** page, linked from the Interface Mode card.

**Getting the most out of it:**

- Add an AI provider key and Test Connection before relying on AI features; a saved-but-untested key is the usual cause of a silent failure.
- If a connection fails with a model-not-found error, set the exact current model id in the Model name field rather than waiting for an app update.
- Use Simple mode to declutter the sidebar for focused estimating work, Advanced when you need every module.

---

## setup
KEY: setup.intro_more

This is the fastest way to get a fresh install priced and ready. The page has three sections. In Cost Databases, click a country card to install its CWICR cost database, each card loads both the priced cost items and the matching resource catalogue for that region, in the right currency and language, and kicks off vector indexing in the background. Use Load All to install every region in sequence. The Resource Catalog section confirms what came in with each region. The Demo Projects section drops in a ready-made project with sections, positions and a schedule so you have live data to explore.

What you install here populates the estimating side of the platform:

- Loaded cost items appear in the **Cost Database**, ready to apply to BOQ unit rates.
- The resource catalogue lands in the **Resource Catalog**.
- Installed demo projects show up under **Projects** so you can open and estimate against them straight away.

**Getting the most out of it:**

- Install only the country you actually work in first; Load All is there when you want the full set.
- Each card links straight to its loaded items in Costs and Catalog so you can confirm the import before estimating.
- Demo projects are the quickest way to see the full estimate-to-report chain without building anything yourself.

---

## modules
KEY: modules.intro_more

Modules has four tabs that each shape your workspace a different way. Company Profiles lets you switch on a preset for your company type, which tailors exactly which modules appear in the sidebar; the active profile is shown in a banner and you can fine-tune individual module toggles below it. Partner Packs are ready-made bundles for a country or partner that carry currency, tax, validation standards and branding; press Activate to apply one and Deactivate to revert. Data Packages is the marketplace for installing cost databases, resource catalogues, languages and converters. System Modules lists everything currently loaded.

The page ties into setup and configuration elsewhere:

- Data packages overlap with the one-click installs on **Databases & Resources**.
- To build your own module, the **Developer guide** walks through the full workflow.
- Disabling a module here hides it from the sidebar, the same effect as the toggles surfaced in **Settings**.

**Getting the most out of it:**

- Start from a Company Profile rather than toggling modules one by one, it sets a sensible default for your trade.
- Admins can upload a partner pack as a zip or drop it into the data dir and click Rescan, no restart needed.
- A module cannot be disabled while another enabled module depends on it; the page tells you what is blocking.

---

## modules_developer_guide
KEY: modules_developer_guide.intro_more

The developer guide is a practical, in-app walkthrough for adding your own business features, so you never have to dig through the repository to learn the conventions. It opens with how to create and share a no-code Partner Pack, then covers the prerequisites and a Hello World module you can stand up in a few minutes. From there it works through the full module shape in order:

1. Scaffold from the template and edit the manifest, which sets the name, version and dependencies.
2. Add a router (auto-mounted), then optional models, schemas, services and validators.
3. Ship an Alembic migration if you add tables, declare permissions, and wire events and hooks.
4. Add the frontend manifest, build the React page, register it and add translations.
5. Run the backend, frontend and end-to-end tests, then install and enable it.

When the package is ready you install and enable it from the **Modules** page like any marketplace item, the module loader discovers the folder and mounts the router automatically.

**Getting the most out of it:**

- Copy the Hello World loop first; it proves the discover-mount cycle end to end before you write real logic.
- Prefix every table name with your module slug to avoid collisions, and guard every mutating endpoint with a permission.
- Route every user-visible string through translation; raw English strings are caught in review.

---

## users
KEY: users.intro_more

User Management is the admin panel for your team. The table lists each member with their role, status and last login, plus a stat strip of totals, active users, admins and managers. Click the role chip on any row to change someone between admin, manager, editor and viewer. Use the Access button to open the per-user module matrix, where you toggle which modules each person can see and set their access level (none, view, edit or full) per module, with one-click presets for all, viewer or minimal. Admins can invite a new user with a name, email, role and a strong starting password.

Access set here governs the whole platform:

- The role you assign decides what every user can see and do across all modules.
- For the rules behind the roles and the approval steps that use them, open **Governance**.
- Every role change and activation is recorded; review it in the **Audit Log**.

**Getting the most out of it:**

- Use the minimal or viewer preset as a starting point, then grant up rather than starting everyone at full.
- Deactivate a leaver instead of deleting them, it keeps their history intact in the audit trail.
- Creating users is admin-only; managers can view the page but will not see the invite control.

---

## admin_audit_log
KEY: admin_audit_log.intro_more

The audit log is a read-only timeline of every recorded change across the platform. Each row shows when it happened, a derived severity, who did it (with email and IP address), the action, the target record and a preview. Use the filter bar to narrow by user, by module or entity type, by action, and by date with the quick-preset chips (Today, Last 7d, Last 30d or a custom range), plus a free-text search across actor, entity, IP and payload, and severity chips for info, warning and critical. Click any row to open a drawer with the full payload and a side-by-side before-and-after diff. Sort by timestamp and page through with adjustable row counts.

It draws on the rest of the platform and feeds your investigations:

- Actor names are resolved from **User Management** so you read who, not a raw id.
- Pair it with **Governance** to confirm who was allowed to do what at the time.
- Export the filtered view to CSV or JSON to attach to a dispute file or hand to an auditor.

**Getting the most out of it:**

- Start with the date presets, then layer a user or action filter to find a specific event fast.
- Open the row drawer for the before-and-after diff, the preview column only hints at the change.
- Access is limited to Manager and above; the export reflects exactly the filters you have applied.

---

## admin_webhook_targets
KEY: admin_webhook_targets.intro_more

This page registers outbound HTTP endpoints that receive your notification events as they happen, so your own systems can react without polling. Click New webhook and give it a name, the receiving URL, an event filter (a pattern, with an asterisk matching everything), and an optional HMAC secret used to sign the payload so the receiver can verify it. Each row shows the URL, the event filter, and a live status badge: inactive, active but never fired, OK with the last HTTP status, or failed with the status and a failure count, so a broken endpoint is visible without reading server logs. You can toggle a target active or inactive and delete it.

It is the raw, programmable end of the notification system:

- The events it forwards are the same ones surfaced in **Notifications**.
- For chat or email delivery without writing a receiver, use the friendlier prebuilt connectors on **Integrations** instead.

**Getting the most out of it:**

- Set an HMAC secret and verify the signature on your end so you can trust the payload is really from the platform.
- Watch the failure count and last status on the row; a target that keeps failing is pointing at a dead or wrong URL.
- Use a narrow event filter rather than the catch-all asterisk so your receiver only handles what it cares about.

---

## requirements
KEY: requirements.intro_more

The EIR matrix tracks ISO 19650 information requirements for the active project and proves each one is delivered. First create a requirement set to group them, then add requirements as rows, each written as an Entity, an Attribute and a Constraint (for example exterior wall, fire rating, equals F90), with a priority of must, should or may. The columns are the six deliverable types that can prove a requirement: model, drawing, schedule, report, COBie and property set. Click any cell to attach a deliverable, record its level of detail and information, and its submitted and accepted dates. The cell turns green when accepted, amber when submitted and red when still missing, and a live coverage score sits in the header.

The matrix sits alongside the BIM coordination work:

- It pairs with **Rule Packs**, where the EIR and information-requirement checks that incoming models are tested against are defined.
- Read the project's overall model health on the **Coordination Hub**.

**Getting the most out of it:**

- Write requirements as Entity, Attribute and Constraint so they are testable, not as prose.
- Set the submitted and accepted dates as deliverables move through review; that is what drives the green, amber and red coverage.
- Filter by deliverable type, status or requirement set to find the gaps fast on a large matrix.

---

## coordination
KEY: coordination.intro_more

The Coordination Hub is a single health view for one project's BIM coordination. It rolls up four signals as KPI cards: your federated models, clash results, rule-pack checks and BCF activity, with a status banner above them flagging when an alert threshold is crossed. Below the cards, a trade matrix shows clashes by discipline pair so you can click a cell and drill into the filtered clash list, and a 30-day timeline lists recent clash runs, federation changes, rule-pack checks and BCF topics. A row of quick-action tiles takes you straight to the next task. A timestamp shows how fresh the snapshot is, and Refresh re-pulls it.

Every number traces back to the canonical model, and the quick actions hand off to the working tools:

- Review clashes opens **Clash Detection**, where you triage, suppress and assign to disciplines.
- Federations opens **BIM Federations** to stitch models and view by discipline.
- Rule packs opens **Rule Packs** for LOD and COBie compliance checks.

**Getting the most out of it:**

- Treat this as your morning glance, the banner tells you whether anything crossed a threshold overnight.
- Editors and above can set the alert thresholds from the Thresholds button so the banner reflects your project's tolerance.
- Click a trade-matrix cell rather than scrolling the full clash list, it lands you on exactly the discipline pair that is clashing.

---

## project-controls
KEY: project-controls.intro_more

Project Controls is the executive cross-module dashboard: six domains, cost, schedule, quality, safety, risk and changes, land on one screen, each as a card of status-banded KPI tiles colored green, amber or red. A row of stat chips up top summarizes how many domains and KPIs are tracked, how many are on track, how many are critical, and the currency. When KPIs need attention an alert banner lists them. Click any tile to open the drill drawer, which traces that figure back to the records in the module that owns it. The scope follows your global project selector: a project selected scopes to it, nothing selected gives you the whole portfolio.

The figures are pulled from a single consolidated snapshot and lead back to the source modules:

- Cost and change tiles trace to **Finance** and **Change Orders**.
- The risk tile traces to **Risks**.
- Quality, safety and schedule tiles trace to their owning modules so you never act on a number you cannot verify.

**Getting the most out of it:**

- Leave the project selector empty to see the portfolio, then pick a project to zoom in on a single job.
- Click a red tile straight into the drill drawer rather than guessing why it is red.
- The currency chip shows Mixed when a portfolio spans currencies, a reminder that those totals are not a single blended number.

---

## match-elements
KEY: match-elements.intro_more

Match Elements is a guided wizard that turns a BIM or CAD model into a priced bill of quantities, one stage at a time with a clear explanation at each step. You move through eight stages on a single rail:

1. Confirm the project.
2. Pick the source model whose elements get priced.
3. Confirm the cost catalogue and that the vector database is ready.
4. Set the scope, the construction stage and net or gross quantities.
5. Choose how elements roll up into estimable groups.
6. Run the match, watching live progress as the pipeline ranks candidates.
7. Review the ranked cost-catalogue candidates per group and confirm each match.
8. Apply, which dry-runs the BOQ rollup, then writes it.

It drives the real pipeline end to end and connects the model to your estimate:

- The element data comes from the same converted model you can interrogate in the **Data Explorer**.
- Candidate rates are ranked from the installed regional **Cost Database** using semantic search.
- Confirmed matches are written into the project as real **BOQ** positions with quantities and rates.

**Getting the most out of it:**

- Make sure the region's cost database is loaded and vectorized first; the catalogue stage checks readiness for you.
- Confirm each match in Review rather than trusting the top candidate blindly, the scores tell you how confident the match is.
- The final Apply step dry-runs the rollup before it writes, so you see the bill of quantities before it lands in the project.

---

## about
KEY: about.intro_more

About is where you confirm what build you are running and learn the story behind it. The top of the page shows your installed version, an open-source badge, the AGPL-3.0 licence chip and a list of the most recent releases, with an update notification when a newer version is available. Scroll down for the platform capability stats, the founder's note on why the project exists, the full AGPL-3.0 licence broken into plain "you can" and "you must" lists, documentation links, the changelog, and ways to support the project. It is a read-only information page, nothing here changes your data.

It links out to the wider ecosystem rather than into your project records:

- Jump to **Modules** to see what is installed, or **Settings** to configure the workspace.
- The page links to the DataDrivenConstruction ecosystem, the open-source repositories and the free Data-Driven Construction book.

**Getting the most out of it:**

- Check the version number here before reporting an issue or planning an upgrade.
- The recent-releases list and changelog show the cadence, so you can see what changed between your build and the latest.
- The licence "you can / you must" lists spell out the AGPL trade-off in plain terms before you self-host or fork.

---
