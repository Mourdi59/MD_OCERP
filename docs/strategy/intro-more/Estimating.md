## boq
KEY: boq.intro_more

This page is your shelf of estimates across every project. Use **New Estimate** to start one, or open an existing card to work in the grid. Each row shows the project, position count, status (draft, in review, final) and the grand total in that project's own currency. Search by name, filter by project or status, and sort by name, value or date. The stat cards at the top stay in sync with whatever filter you have applied.

What flows here:

- Each estimate's grand total is built from the unit rates you pull from the **Cost Database** and the quantities you bring from **Takeoff**, **Quantities** or **BIM**.
- A finished estimate feeds **Validation**, the **Finance** budget and tender packages in **Tendering** and **Bid Management**.

**Getting the most out of it:** Use **Duplicate** to spin off a what-if version before you change rates, then use **Compare** to set the two side by side. Comparison only subtracts totals when both estimates share a currency, so a EUR job is never blended with a USD one. Sort by value to find your biggest estimates fast.

---

## boq_editor
KEY: boq_editor.intro_more

This is the working grid where the estimate actually gets built. Add a position or a section from the toolbar, type a description, unit, quantity and rate, and the line total and grand total recompute as you go. You can nest sections, renumber a whole branch with the Renumber dialog, paste rows straight from Excel, and use formulas in the quantity cell. Undo and redo are there for every change, and Version History lets you look back at earlier states.

Pull pricing in without leaving the grid:

1. Open the **Cost Database** search to drop a priced item onto a position.
2. Apply an **Assembly** to auto-fill a composite rate from its components.
3. Link rows to **BIM** model elements so quantities track the model.

Import and export from the toolbar cover Excel, CSV, PDF and GAEB. The Validate button checks the estimate against the project's rule sets, and the AI panels can find rates or flag anomalies.

**Getting the most out of it:** Build the section skeleton first, then fill positions under it so ordinals stay clean. Recalculate after a big paste, and run Validate before you call an estimate final.

---

## templates
KEY: templates.intro_more

Use this when you do not want to type a structure from a blank grid. The page shows a card per building type (residential, office, warehouse, school, hospital, hotel, retail, infrastructure), each with its section and position count and a benchmark cost per square metre. Click one, pick the target project, enter the floor area, and an estimated total previews instantly from the benchmark rate.

How it works step by step:

1. Select a building-type card.
2. Choose the project the BOQ will belong to.
3. Set the area and, optionally, rename the BOQ.
4. Create it, and you land in the **BOQ** editor on that project.

The generated structure carries sections and positions with starting rates that you refine against the **Cost Database** like any other estimate.

**Getting the most out of it:** Treat the benchmark rate as a sanity-check starting point, not a final price. Set a realistic area before you generate so the preview total is meaningful, then replace the template rates with real ones from your installed regional catalogue.

---

## costs
KEY: costs.intro_more

This is your searchable price book. Search by keyword or code, filter by region, browse a cost item to see its component breakdown of material, labour and equipment, and note that every rate carries its own ISO currency code. Star the items you use often and the Favourites and Recent filters bring them back quickly. You can also export the catalogue to Excel.

Where it connects:

- Install or upload price books from **Cost Database Import**, and the rates land here ready to search.
- The same atomic items are maintained in **Catalog**, bundled into recipes in **Assemblies**, and pulled into estimates in **BOQ**.

**Getting the most out of it:** Select several items and use **Add to BOQ** to push them into an estimate in one move, with each rate keeping its source currency so the FX rollup converts correctly. Use the regional adjust and escalation tools to bring an older or out-of-region rate up to today's price, and check the certainty badge before you trust a number.

---

## costs_import
KEY: costs_import.intro_more

This is where price books arrive. Pick a country from the CWICR list, each one tied to a metro, language and currency, and install it. Most regions download on first use from the DDC CWICR repository and then stay available offline. You can also upload your own Excel or CSV cost file, and the importer reports how many rows were imported, skipped or errored.

What you get and where it goes:

- An installed database fills the **Cost Database** with searchable priced items and their resource breakdowns.
- Those rates then become matchable across **Catalog**, **Assemblies** and **BOQ**.

**Getting the most out of it:** Install the database that matches your project's region and currency so rates arrive in the right denomination instead of needing conversion later. Mark one database active so search defaults to it. When you upload your own file, check the skipped and errored counts before relying on the import, and fix the flagged rows at the source.

---

## catalog
KEY: catalog.intro_more

The catalog holds the atomic building blocks behind every estimate: individual materials, labour rates, equipment and operators. Use the type tabs to switch between them, search and filter by region or category, and open an item to see its price band (base, min, max) and usage count. Items come from your installed CWICR regional databases or your own imports, and you can add or edit entries by hand.

How prices change in bulk:

1. Open **Adjust Prices**.
2. Choose the basis, a published construction inflation index, a regional factor or a group factor.
3. Preview how many items are affected, then apply.

**Getting the most out of it:** Keep these base items clean and well categorised, because they feed **Assemblies**, unit rates in **BOQ** and cost matching across projects, so one good edit here improves every estimate downstream. Use bulk inflation once a year rather than touching items one at a time.

---

## assemblies
KEY: assemblies.intro_more

Assemblies are reusable cost recipes. Instead of pricing a reinforced concrete wall line by line every time, you build it once as concrete plus rebar plus formwork plus labour, and reuse the composite rate everywhere. The list view shows each assembly's category, component count, total rate and how often it has been used, in either a grid or a table, with search, category filter and sorting. You can clone, export to CSV, or generate one with AI.

Where it fits:

- Build atomic components from the **Catalog** and the **Cost Database**.
- Apply a finished assembly to a position in the **BOQ** editor to auto-populate its component costs.

**Getting the most out of it:** Standardise the work you repeat across projects into assemblies so rates stay consistent and nobody re-prices the same wall twice. Sort by usage count to see which recipes earn their keep, and clone a close match rather than starting a new one from scratch.

---

## assemblies_library
KEY: assemblies_library.intro_more

The library is a shared collection of ready-made assembly templates you can pull from instead of building a recipe yourself. Search by keyword, filter by category (concrete, masonry, drywall, steel, roofing, insulation, finishing, MEP, earthwork), and preview a template's components and rates before you commit. Template names are shown in your interface language where a translation exists.

The flow:

1. Find a template that matches the work.
2. Preview its components.
3. Save it into your own assemblies.

Saved templates become regular entries in **Assemblies**, ready to apply to positions on any project in the **BOQ** editor.

**Getting the most out of it:** Start from the library before authoring anything new, since a close template plus a few edits is faster than a blank assembly. Filter by category first to narrow a long list, and save the templates that fit your typical scope so they are one click away next time.

---

## assemblies_new
KEY: assemblies_new.intro_more

This is the quick setup step for a brand-new assembly. You give it a name and a code, choose its unit and category, set the currency (it defaults to your preferred currency from Regional Settings), and optionally attach a classification standard and code such as DIN 276, NRM, MasterFormat, UniFormat or Uniclass. Creating it does not finish the job, it opens the assembly editor.

What happens next and where it connects:

- After create, you land in the **assembly editor** to add the material, labour and equipment lines that build the composite rate.
- If you want a head start instead of a blank recipe, browse the **Assembly Library** for a template to save and adapt.

**Getting the most out of it:** Set the currency correctly here, because it stamps every component you add afterward. Pick the right classification standard up front so the assembly maps cleanly to your project's cost structure and shows up where you expect in reports.

---

## assemblies_editor
KEY: assemblies_editor.intro_more

This is where the composite rate is actually built, component by component. Use the typed Add menu to seed material, labour, equipment, operator and other lines, each with its own quantity factor and unit. Reorder lines by dragging, edit a factor inline, and the total rate plus the material, labour and equipment split recompute as you change things. You can pull components from the **Cost Database** or the **Catalog** picker so the numbers stay grounded in real prices, and tag the assembly for easier searching.

Where it connects:

- Components draw on the **Catalog** and **Cost Database**.
- The finished assembly is reusable across every project, applied to positions in the **BOQ** editor.

**Getting the most out of it:** Think in factors per unit of the assembly, for example the rebar kilograms per cubic metre of wall, so the recipe scales correctly when applied. Build components from catalogue items rather than typing free rates, and keep the line order readable since that is how it will appear when applied.

---

## costmodel
KEY: costmodel.intro_more

This is the 5D budget control surface. Pick a project and its BOQ, and the page shows an earned-value S-curve of planned, earned and actual cost over time, KPI cards for budget and variance, CPI and SPI performance indicators, and a category breakdown of planned, committed, actual and forecast spend. The cost benchmark compares your numbers against references, and you can run what-if scenarios to see the effect of a change before you make it.

What it draws on:

- The **BOQ** estimate, schedule progress and **Finance** data feed the curves and totals.
- It can generate the control-account cost spine that ties the budget back to those sources.

**Getting the most out of it:** Watch CPI and SPI together, since a project can be on cost but behind schedule or the reverse. Set realistic budget-line thresholds so the variance banding flags the lines that actually need attention. Use what-if scenarios to test a material substitution or a regional adjustment before committing it to the estimate.

---

## quantities
KEY: quantities.intro_more

This page is a chooser, not a measuring tool itself. It helps you pick how to collect quantities and makes sure the file converters you need are installed. Three method cards send you to the right place: a written description goes to **Quick Estimate (AI)**, PDF drawings go to **PDF Takeoff**, and CAD or BIM models go to the **Data Explorer**. A "How it works" strip lays out the upload, measure and apply steps.

The converter section is the practical part:

1. See which CAD and BIM converters (DWG, RVT, IFC, DGN) are installed.
2. Install the one your file format needs, with a one-time download and a progress panel.
3. Update or uninstall a converter when a newer build is available.

**Getting the most out of it:** Install the converter that matches your incoming files before you start a takeoff, so the model route works the first time. Whichever method you pick, the measured quantities end up in your **BOQ**. For a few numbers you do not need any of this, jump straight to the BOQ editor with Quick Manual Entry.

---

## takeoff
KEY: takeoff.intro_more

Upload a PDF drawing and measure right on it. Open a document and use the on-screen tools to measure areas, lengths and counts by hand, or let the AI analysis extract elements with quantities and a confidence score for each. Extracted elements list by category with totals, and you choose which ones to keep. There is also a compare drawer to set two drawing revisions against each other.

How measurements travel:

- Selected measurements and accepted elements flow into your **BOQ** as positions with quantities.
- They stay linked to the project, so the quantities tie back to project cost and schedule, and you can switch between this and the other routes on the **Quantities** page.

**Getting the most out of it:** Review the AI confidence on each element before accepting it, since low-confidence items deserve a manual check against the drawing. Use the compare drawer when a new revision lands so you re-measure only what changed. Confirm the unit on each measurement so it lands in the BOQ as the quantity you expect.

---

## validation
KEY: validation.intro_more

Validation runs your estimate against rule sets and shows where it falls short before a client or authority does. Pick a project and BOQ and press run. The rule sets applied are derived from the project's classification standard: boq_quality is universal and always runs, DIN 276 projects add din276 and gaeb, NRM and MasterFormat projects add their own. Results come back as a traffic-light report with a score and counts of errors, warnings, info and passes.

Reading and acting on the results:

- Filter by errors, warnings, info or passed to focus.
- Each finding links back to the exact BOQ position via its element reference, so you fix it at the source.
- Findings cover missing quantities, missing or out-of-range unit rates, missing descriptions, duplicate ordinals and classification-code checks.

It checks the **BOQ** and its linked **BIM** elements, and you can export the report.

**Getting the most out of it:** Run validation before marking an estimate final and again after any large import or paste. Clear errors first, then work the warnings. Use the rule tooltips to understand exactly what each check expects.

---

## advisor
KEY: advisor.intro_more

The advisor lets you ask, in plain language, what something should cost, and it answers from your installed regional cost databases rather than guessing. Type a question, pick the region, and the reply comes back as a short answer with the source rates, units and regions it drew on shown underneath. It reads as a chat, so you can follow up to refine the question.

Where the numbers come from:

- Answers are grounded in the same **Cost Database** you install and maintain, with each cited source carrying its own currency.
- For a full structured estimate rather than a single sanity-check, move to **Quick Estimate (AI)**.

**Getting the most out of it:** Use it to pressure-test a number before you commit it to an estimate, and always read the cited sources rather than just the headline figure. Be specific about scope and region in your question so the retrieved rates are relevant. Quality depends on having the matching regional database installed, so install it first if a region returns thin results.

---

## ai_estimate
KEY: ai_estimate.intro_more

This is the fast lane from a rough brief to a first number. Choose an input tab, plain text, a photo or scan, a PDF, an Excel or CSV file, or a paste from any app, give a little context such as building type, and the engine turns it into a structured estimate with descriptions, units, quantities and rates. The lines are matched against your cost database for you to review, edit and trim.

The shape of a run:

1. Pick the input and provide your source.
2. Let the engine produce estimate lines.
3. Review the matched rates and adjust.
4. Save the result as a BOQ on any project.

Saved estimates open in the **BOQ** editor; rates come from the **Cost Database**. For a guided, stage-by-stage version where you confirm each step, use the **Estimate Builder (AI)**.

**Getting the most out of it:** Give the building type and a sense of scale so matching has something to work with, then treat the output as a draft to review, not a final price. This is the quick one-shot path; reach for the Estimate Builder when you want more control over each stage.

---

## ai_estimator
KEY: ai_estimator.intro_more

The Estimate Builder is the guided, four-stage version of AI estimating, run as a tracked job you can return to. The runs list keeps your past estimates; New estimate opens a stepper with a left rail and a run monitor on the right. You bring any source, a BIM or CAD model, a DWG or PDF takeoff, an Excel or GAEB import, photos or a written description, and you confirm each stage before it moves on.

The four stages:

1. Understand the source, with the format auto-detected.
2. Group quantities, AI-derived and editable.
3. Match rates, grounded in catalogue rates with resource breakdowns.
4. Review and apply, with totals and validation, then an explicit confirm.

Every rate comes from the **Cost Database**, never invented, and the result writes into a **BOQ**, with checks aligned to **Validation**. It degrades gracefully when no AI key or vector database is present.

**Getting the most out of it:** Use this over the one-shot Quick Estimate when accuracy matters, because confirming each stage catches grouping and matching mistakes early. Pick the catalogue that fits your region so matched rates are relevant, and review the match scores before applying.

---
