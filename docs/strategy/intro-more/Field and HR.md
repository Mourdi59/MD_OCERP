# Field and HR - "Show more" expansion copy

Long-form expansion text revealed by the "Show more" button under each module's
DismissibleInfo / SectionIntro block. These do NOT repeat the intro_title /
intro_body in MODULE_INTRO_COPY.md; they expand on the workflow, the data flow
and practical tips. Renderer is IntroRichText (paragraphs, bullet/numbered
lists, bold only).

---

## safety
KEY: safety.intro_more

Open the Incidents tab and press Report Incident to log something that already happened. Pick the type with the colored cards (injury, near-miss, property damage, environmental, fire), enter the date and a description, then set the treatment (first aid, medical, hospital), and days lost appears when the treatment is medical or hospital. On the Observations tab, Report Observation captures a hazard you spotted; you choose severity and likelihood and the page multiplies them into a live risk score, color-banded low to critical. The Trends tab charts incidents over time and lets you set a threshold alert.

What flows where:

- The four summary tiles at the top pull live counts from Inspections, NCR and Punch List as well as Safety, so the page is a small quality dashboard.
- A serious incident is the starting point for a 5-Whys investigation in HSE Advanced, and a flagged hazard can be turned into an inspection or a punch item.

**Getting the most out of it:** Log near-misses, not just injuries, since they feed the same trend line and cost nothing to record. Keep incident dates accurate, the days-without-incident metric is marked unreliable if any date cannot be read. Use Export Excel on either tab to hand a clean register to a client or auditor.

---

## hse-advanced
KEY: hse-advanced.intro_more

This is the formal, auditable side of safety, organized into tabs you work as the situation demands. Start a 5-Whys, fishbone or timeline investigation off a logged safety incident and record findings and recommendations. Run a Job Safety Analysis through its states (draft, under review, approved, active, archived) before high-risk work. Raise a Permit to Work and drive it requested to approved to active, gated by prerequisite checks such as JSA approved, supervisor present and fire watch assigned. Record toolbox talks with attendance, issue PPE, and conduct a site audit by scoring pass/fail findings that roll up into the audit score.

What flows where:

- Investigations and permits key off incidents from the Safety module, so the two work as a pair.
- Corrective and preventive actions (CAPAs) track to close-out with target dates, 5-Whys root cause and an effectiveness check.
- Everything feeds the KPI strip (open investigations, overdue CAPAs, active permits, days since LTI) and exports to an OSHA Form 300 log as CSV.

**Getting the most out of it:** Approve the JSA before you raise the permit, since the permit will not go active until its prerequisites are ticked. Watch the overdue-CAPA count, it is the single best signal that findings are being logged but not closed.

---

## fieldreports
KEY: fieldreports.intro_more

Press New Report, pick the type (daily, inspection, safety or concrete pour) and a date, then fill the structured form: weather, workforce by trade with headcount and hours, equipment on site, work performed, delays with delay hours, deliveries, visitors and notes. You can fetch live weather to prefill the conditions, attach photos and link existing documents, and capture a signature on the pad. A finished report moves draft to submitted to approved, and you can export it to PDF or the whole project to Excel.

What flows where:

- Workforce hours and counts roll up into the summary tiles and become the labour basis that Payroll aggregates into pay entries.
- Per-report workforce and equipment logs can carry a WBS and cost category, tying field effort back to the budget.
- Unlike the Daily Diary, which is a legally sealed contemporaneous record, field reports are templated forms you can edit, re-template and bulk import from a spreadsheet.

**Getting the most out of it:** Build a custom template once with Manage Templates so every foreman captures the same fields. Record delay hours honestly and in detail, they are your first evidence if a delay claim arrives later. Use the calendar view to spot the days nobody filed.

---

## daily-diary
KEY: daily-diary.intro_more

Each site day, create the diary for that date, then build it up: fetch or enter weather, log labour and equipment counts, and add timed entries (visitors, deliveries, events, completions, incident and inspection summaries). Attach photos, which can have their GPS pulled from EXIF, and link drone surveys or reality-capture scans. A completeness meter shows which blocks are still missing. When the day is done you close the diary and sign it, which seals it with a sha256 fingerprint so any later change is detectable.

What flows where:

- Photos, drone surveys and reality captures attached here sit with the rest of the project files and the site photo library.
- Labour and equipment counts feed schedule progress and a workforce summary.
- A signed diary can be re-opened only through an audited unlock that preserves the original signature, and a date range can be exported as a hash-sealed SCL Protocol bundle for delay analysis.

**Getting the most out of it:** Close and sign the same day while memory is fresh, an unsigned diary is just notes, a signed one is evidence. Let the GPS extraction tag your photos so they map to real locations. Reach for the SCL bundle export when a dispute is brewing, it packages a defensible contemporaneous record across the whole period.

---

## equipment
KEY: equipment.intro_more

Add a machine with its code, name, type, ownership (owned, rented or leased) and purchase details. Open an asset to see its dashboard: utilization, month-to-date fuel cost, open maintenance work orders and how many inspections are expiring. From there you raise maintenance work orders and mark them complete, record inspections with a pass, fail or conditional result and a valid-until date, log damage reports, and feed telemetry readings for hour meter, fuel and location.

What flows where:

- An asset that is not active, or whose required inspection has lapsed, is automatically blocked from new resource assignments in the Resources module, so unsafe plant cannot be dispatched.
- Running and maintenance cost flows through to Finance.
- Telemetry powers the health-analytics and failure-forecast views and the fleet optimization screen that flags underutilized units.

**Getting the most out of it:** Keep inspection valid-until dates current, that single field is what gates a machine on or off site. Set each equipment type's service intervals so work orders can be scheduled against real hours and kilometers. Check fleet optimization monthly to surface idle kit you are paying for but not using.

---

## resources
KEY: resources.intro_more

Register people, crews, equipment and subcontractors, each with a code, cost rate and skills. The core loop is request and fulfill: a foreman raises a Resource Request for a project with required skills, a date window and a quantity, and a dispatcher fulfills it by matching an available resource, which creates an Assignment. You can also propose an assignment directly. Assignments move proposed to confirmed to in progress to completed, and the planning board shows everyone across a date range with overlap conflicts flagged automatically.

What flows where:

- Equipment marked inactive or with a lapsed inspection in the Equipment module cannot be assigned, the conflict check enforces it.
- Confirmed assignments are the source of truth for who and what is on site each day, aligning with the Schedule and Tasks.
- Each resource has a dashboard with active and upcoming assignments, certifications, skills and a 30-day utilization figure.

**Getting the most out of it:** Fulfill requests rather than free-typing assignments, it keeps the demand-and-supply trail intact. Watch the board conflicts row, a double-booking caught here is a crew that does not show up twice. Keep certification expiry dates current so the right people are matched to skilled work.

---

## payroll
KEY: payroll.intro_more

Pick a project and press Generate to create a draft batch that aggregates field labour hours into pay entries for the period you choose. Review the entries (worker, hours, rate, amount), then walk the batch through its states: draft, submitted, approved, posted. Submitting moves no money; approving (finalize) posts the labour cost into the project budget; posting writes it to the finance ledger. Each step is idempotent, so a double-click cannot double-post.

What flows where:

- Hours come from the field-labour sources captured in Field Reports, the reconcile view compares a batch's hours against those live sources line by line and tells you whether it balances.
- Approving a batch posts its labour cost into the project budget and the 5D cost model, so the people on site tie back to the money.
- Any batch exports to CSV or JSON for an outside payroll system.

**Getting the most out of it:** Run reconcile before you approve, a non-zero delta means a report changed after the batch was generated. Approve in period, since posting late distorts the budget month it lands in. Use the labour-cost figure shown on the page as a quick sanity check against your estimate.

---

## accommodation
KEY: accommodation.intro_more

The landing page lists every property as a card, filtered by kind with the All, Worker camps, Rentals and Hotels tabs, each card showing capacity and occupied-versus-total at a glance. Press New Accommodation to add a camp, rental or hotel. Open a card to manage that property in depth, or use HR autobook to suggest a room for an employee. A KPI strip across the top summarizes capacity and bookings.

What flows where:

- HR autobook takes an employee contact and a start date and suggests the best available room with its rate, linking workforce housing to your Contacts directory.
- A property can be bootstrapped from a Property Development block, turning planned units into bookable rooms.
- The calendar view shares the same rooms and bookings you manage on each property.

**Getting the most out of it:** Set a realistic capacity per property so the vacant-room figures stay trustworthy. Use HR autobook instead of hunting for free beds by hand. This module is workspace-wide rather than tied to one active project, so name properties clearly enough to tell sites apart.

---

## accommodation_calendar
KEY: accommodation_calendar.intro_more

The calendar lays rooms down the side and dates across the top so occupancy reads as a grid. A filled cell is a booking, an empty cell is a free bed, and a clash is obvious because two bookings cannot sit in the same cell on the same night. Use it before you place a worker so you assign into genuine vacancy rather than discovering a conflict after the fact.

What flows where:

- Every cell traces back to its underlying booking, and the calendar reads the same rooms and bookings you manage on the accommodation property pages.
- Bookings carry a check-in and check-out date and move through reserved, checked in, checked out and cancelled, which is what fills or frees a cell.

**Getting the most out of it:** Scan the grid for the next free run of nights before committing a longer stay. Keep check-out dates set, an open-ended booking holds a bed indefinitely and hides real vacancy. Cancel rather than delete when plans change so the history stays readable.

---

## accommodation_detail
KEY: accommodation_detail.intro_more

A single property is laid out as Inventory, Occupancy and Billing, with Settings at the end. In Inventory you add and status rooms (available, occupied, maintenance, blocked), including a bulk add for many rooms at once. In Occupancy you create bookings against a room and switch between the booking list and the calendar. In Billing you pick a booking and add charges (base rent, extras, deposits, refunds) without pasting any IDs. The header KPI strip shows capacity, active bookings, rooms and vacant.

What flows where:

- Bookings can name an occupant from Contacts, and charges carry a currency and a status of pending, invoiced, paid or waived.
- The Settings tab can link the property to its BIM model and bootstrap rooms from a Property Development block.
- Each booking's status transitions (reserved to checked in to checked out, or cancelled) drive what the room and the calendar show.

**Getting the most out of it:** Use bulk add to stand up a whole camp wing in one step instead of room by room. Mark a room as maintenance or blocked rather than deleting it so it leaves the available pool without losing its history. Add the base-rent charge when the booking starts so billing keeps pace with occupancy.

---

## punchlist
KEY: punchlist.intro_more

Press New Item to capture a snag with a title, description, priority, category and trade, optionally pinned to a drawing location and with photos attached. Work the item across its lifecycle, open, in progress, resolved, verified, closed, using the Kanban board to drag items between columns or the list view to triage and bulk-close in one action. The summary strip shows totals by status and priority plus an overdue count and the average days to close.

What flows where:

- Items created from a failed Inspection or an NCR carry their source tag, so you can trace a defect back to where it was found.
- Assignees come from your project's user list, and the open-defect count appears on the Safety and quality dashboards.
- Photos uploaded against an item document the defect and its fix.

**Getting the most out of it:** Add a due date so overdue items surface in the summary instead of drifting. Use bulk-close at handover to clear a verified batch at once. Pin items to the drawing where you can, a located snag is far faster for the trade to find and fix.

---
