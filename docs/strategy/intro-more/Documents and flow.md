## file-manager
KEY: file-manager.intro_more

You land on a folder-card grid with one card per file category: documents, photos, sheets, BIM models, DWG drawings, takeoffs, reports and markups. Press Upload files (or drag files in) to add them, then click a category card to drill into its grid or list view, where you can search, sort, filter by extension or tag, star favorites and preview a file in the side pane. Double-clicking a file opens it in the tool that handles it: PDFs go to Takeoff, IFC and RVT to the BIM viewer, DWG to DWG Takeoff.

Files here are the shared library every other module reads from. Photos open in the Site Photos gallery, drawings flow into Takeoff and BIM, and the same files appear as attachments in RFIs, submittals and transmittals. Project owners can lock a folder category to specific roles.

**Getting the most out of it:**
- Use Search all projects in the top bar to find a file when you are not sure which project it is in.
- Open the Transmittal log from the top bar to record formal document issues.
- Star the files you reference daily, then filter to Favorites only.
- Deleted files are recoverable for 30 days in the Recycle Bin.

---

## documents
KEY: documents.intro_more

Click Upload Photos and either drag images in or pick them from your device. Set a category (site, progress, defect, delivery, safety or other) and type tags once and they apply to every photo in that batch, so you classify the whole upload at once instead of editing each shot. As each image loads, the gallery reads its EXIF capture date and GPS when present and marks those photos with a small badge. Switch between the grid and the timeline, which groups photos by the day they were taken, and click any photo to open the full-screen lightbox with its date, location and tags.

Photos live alongside the rest of the project files in the File Manager and can be opened from there. Use Select to multi-select and delete in bulk.

**Getting the most out of it:**
- Shoot with location services on so EXIF GPS sorts site shots correctly.
- When the gallery suggests a category such as a likely defect, click the badge to apply it; nothing is changed automatically.
- Add type tags like foundation or rebar at upload time to make later searches fast.

---

## file-trash
KEY: file-trash.intro_more

When you delete a file in the File Manager it is not destroyed; it moves here, scoped to the project you are working in. Each row shows the file name, its type, its size, when it was trashed and a countdown of how many days remain before it is removed for good. Rows expiring within three days are flagged in red. Click Restore to put a file back where it was, or Delete forever to purge it immediately after a confirm step.

This page reads from the active project you opened in the File Manager, so there is no project picker here. Restored files reappear in their original category in the File Manager.

**Getting the most out of it:**
- Check the days-left badge before a deadline; once the retention window closes the file is gone.
- Restore is the fast undo for an accidental delete, so reach for it before re-uploading.
- Use Delete forever only when you are certain, since a purge cannot be reversed.

---

## markups
KEY: markups.intro_more

Click Add Markup, pick a type (cloud, arrow, text, rectangle, highlight, stamp, polygon, or a distance, area or count measurement), choose the source document and page, set a color and optionally an assignee, then create it. Each markup tracks through active, resolved and archived using the inline action buttons, and you can switch between a list and a grid view. Open a row and press Open in document to jump to that markup on its source PDF in the inline annotator, where it pulses so you can find it. Use the All annotations tab to see markups gathered from across the project, not just hub entries.

Markups attach to documents from the File Manager, can be assigned to people from your user list, and can carry a BOQ position link. An approval route can be applied to any markup when one is configured.

**Getting the most out of it:**
- Filter by assignee or status to clear your own open items first.
- Export to CSV to hand a punch-style markup list to a reviewer.
- Jump to Compare to check an old drawing revision against a new one.

---

## markups_compare
KEY: markups_compare.intro_more

Pick the old revision in the document A dropdown and the new one in document B, then choose a compare mode. Overlay draws B over A as an onion skin with an opacity slider you drag to fade between them. Difference renders the old in red, the new in blue and everything unchanged in grey, and reports a percent-changed figure. Side by side shows both drawings in synced panes that pan and zoom together. Zoom controls, page navigation and a swap-A-and-B button sit in the toolbar.

Both documents are pulled from the project files, the same PDFs you annotate in Markups, and you reach this view from the Markups page (or with documents pre-selected when you arrive from a link).

**Getting the most out of it:**
- Use Difference first to spot where a revision changed, then switch to Side by side to read the detail.
- Watch the percent-changed readout to gauge how big a revision really is.
- Catch drawing changes here before the new sheet reaches the field.

---

## cde
KEY: cde.intro_more

Upload your documents in the File Manager first, then organize them here into ISO 19650 containers tagged by discipline. Each container moves its revisions through four states in order: Work in Progress, Shared, Published and Archived. To advance a container, open it and promote it across the next gate; the buttons only appear when your role is allowed to cross that gate, so editors and viewers never hit a dead control. Add a new revision to a container as the document evolves, and open the history drawer to see every state change and revision on the record.

Containers reference the project documents you manage in the File Manager, and a transmittals badge ties published documents back to the formal issues you record under Transmittals.

**Getting the most out of it:**
- Promote to Shared only once a document is ready for coordination, and to Published only when it is approved for use.
- Use the suitability codes to signal exactly what a revision can be used for.
- Keep one container per deliverable so its full revision history stays in one place.

---

## integrations
KEY: integrations.intro_more

Connectors are grouped into Notifications, Automation, and Data and Analytics. For a chat or email connector (Teams, Slack, Telegram, Discord, email or a signed webhook), click Connect, follow the numbered setup steps, paste in the webhook URL or credentials, and press Test Connection to send a live test before you Save. For a webhook you also tick which events to subscribe to, such as task created, RFI answered, invoice approved, document uploaded or BOQ changed. Once saved, the connector shows as Connected and you can test or disconnect it any time.

Events that fire here are the same ones the Notifications inbox collects, and the signed-webhook connector overlaps with the outbound endpoints managed under Webhook targets.

**Getting the most out of it:**
- Always run Test Connection before Save so a wrong URL fails on your screen, not in production.
- Copy the calendar feed URL to see project due dates in Google Calendar or Outlook.
- For anything beyond chat, point n8n, Zapier, Make or a BI tool at the REST API documented at /api/docs.

---

## pipelines
KEY: pipelines.intro_more

The screen is a three-zone canvas: a step palette on the left, the wiring canvas in the middle and an inspector on the right. Drag a step from the palette onto the canvas, or click it to drop it in the center, then drag from one step's output dot to the next step's input to connect them; the dot colors show the data type so mismatches are obvious. Press Run and the canvas plays the run live, lighting each step as it executes and showing progress in the run dock at the bottom. Save the graph to reuse it later. Press Explain for a plain-language summary of the steps, the data flow and any inputs that are still unconnected.

Pipelines are scoped to the project in the page URL, and the steps you wire chain the same data work you do by hand across modules like the Data Explorer and Quantities.

**Getting the most out of it:**
- Run Explain before a run to catch steps that still need an input connected.
- Save once it works so the same flow is one click away next time.
- This module is in beta, so confirm the output before relying on it.

---

## service
KEY: service.intro_more

Work the tabs left to right. Start under Contracts by setting up a service agreement for a customer, then register the equipment it covers under Assets. When something needs attention, log it as a ticket; dispatch the ticket and assign a technician, which turns it into a scheduled work order. When the visit is done, complete the work order with a debrief (problem, cause and solution), and a completed order can then be billed. Each ticket also carries an SLA countdown chip that turns amber as the deadline nears and red once it is breached.

Customers are pulled from Contacts, on-site engineers from Subcontractors, and a billed work order rolls its value into Finance.

**Getting the most out of it:**
- Use the overdue filter to surface tickets that have breached or are about to breach their SLA.
- Fill in the debrief properly, since it becomes the record of what was actually fixed.
- Set up the Recurring tab for planned maintenance so repeat visits raise themselves on schedule.

---
