## compliance
KEY: compliance.intro_more

Type a check the way you would explain it to a colleague, for example "all walls must have a fire-rating property", then pick the language tab (English, German or Russian) and press Generate or Ctrl/Cmd+Enter. The builder shows the resulting validation DSL in the right pane with a confidence badge and the pattern it matched. If nothing matches, it suggests the phrasings it understands. When the rule looks right, click Save as Compliance Rule.

The builder works off a deterministic pattern catalogue, so it runs with no setup. The "Use AI fallback" checkbox is optional and is skipped automatically when no API key is configured. Saved rules join the validation rule sets that run in Validation against your BOQ and imported data, and they are administered alongside the other standards under Governance.

**Getting the most out of it:**

- Start from the example hints on the right rather than a blank box.
- Read the generated DSL before saving. A confidence below 60 percent shows a warning for a reason.
- Keep one rule to one idea so a failure points clearly at what to fix.

---

## gaeb-exchange
KEY: gaeb_exchange.intro_more

On the Import tab, drop a GAEB DA XML file (.x81, .x83 or .xml) onto the upload zone or browse to it. The page parses it, tags it X81 (no prices) or X83 (priced), and previews the positions it found. Pick the target project and BOQ, then click Import to write the positions in. No file handy? Use the "Download a sample GAEB X83" link to try the round trip. On the Export tab, choose a project, a BOQ and a format, preview the lines, and download the GAEB file.

Imports land in a normal BOQ in the BOQ editor, where the result link takes you to review and validate. Exports read straight from the selected BOQ. The same X83 priced file you produce here is the document you hand to a tender, which connects this page to Tendering, while Validation checks the structure once positions are in.

**Getting the most out of it:**

- Legacy DACH files with umlauts are decoded by their declared encoding, so German descriptions stay intact.
- Use X81 to send a priceless Leistungsverzeichnis out for pricing, X83 to return or receive a priced bid.
- After import, open the BOQ and run Validation before sharing.

---

## pdf-takeoff
KEY: pdf_takeoff.intro_more

Open a PDF drawing, then calibrate it: pick two points of a known length and enter the real distance so measurements are true to scale. Choose a tool, distance, polyline, area, volume or count, and click on the drawing to measure. Each measurement gets a label and a group color, and you can add clouds, arrows, text, rectangles and highlights as markup. Undo and redo are supported, and the measurement ledger lists everything you have captured. Zoom, pan and pinch on touch are all available.

Your work saves per drawing and syncs to the active project. From the ledger you can link a single measurement to an existing or new BOQ position, or use Export to push all measurements into a chosen project and BOQ at once. You can also export the takeoff to CSV, Excel or PDF. This feeds your quantity takeoff and your BOQ cost estimate directly.

**Getting the most out of it:**

- Calibrate first. The page warns once if you measure on an uncalibrated drawing.
- Use groups (Structural, Electrical and the rest) so totals roll up by trade.
- Linked measurements keep a badge back to their BOQ position, so quantities stay traceable.

---

## regional-exchange
KEY: regional.intro_more

This one page adapts to your country. The header shows the flag and the native standard, NRM for the UK, MasterFormat for the US, DPGF for France, DIN 276 for the DACH region and others. On the Import tab, drop your Excel, CSV or TSV file (Spain also accepts BC3), preview the parsed positions against the trade-section reference for that standard, pick the target project and BOQ, then Import. On the Export tab, choose a BOQ and export it as a detailed (priced) or summary CSV, or print it to PDF.

The data lands in or is read from an ordinary BOQ, so the same estimate moves between markets without re-keying. Imports run through the country-specific validator pack on the way in, and the result link opens the BOQ for review in Validation.

**Getting the most out of it:**

- Use the "Download a sample file" link to see the exact column layout your country expects.
- The classification reference chips show the trade sections (NRM elements, MasterFormat divisions, DPGF lots) you should be coding against.
- Money travels as exact decimals, so unit rates are not rounded in transit.

---

## property-dev_pricing
KEY: propdev_pricing.intro_more

Pricing works in four tabs. On Price Lists, create a draft list with a currency and effective date, then Activate it to start quoting from it. On Rules, add adjustments on top of the base price, early-bird, view, floor, corner and size premiums, promo codes, friends and family, loyalty and bulk-buy, each with a percentage or fixed amount, a priority and a validity window. Lower priority applies first, and conflicting rules show a badge that explains which one wins. The Simulator quotes a chosen plot (with an optional promo and buyer) and shows the price as a waterfall you can compare with a previous quote. Quote History lists past quotes from reservations.

Rules read plot attributes such as floor, view, area and corner flag, and buyer tags and history, all from this development. The quotes you produce flow into the development's reservations and buyer quotes, and the Inventory Map links here for context.

**Getting the most out of it:**

- The rule form shows a live example calculation, so you can see the effect before saving.
- A currency mismatch between the list and a quote is flagged rather than blended.
- Reorder rules with the up and down arrows to change which discount or premium lands first.

---

## property-dev_inventory_map
KEY: propdev_inventory_map.intro_more

The map lays out every plot as a colored tile, grouped by block and floor. The color is the live status: green available, amber reserved, gray sold, slate handed over, purple held, red blocked. Click the KPI ribbon at the top to filter by status, and narrow further by unit type, floor, price range and area. A plain click on a tile opens its detail drawer (price, area, bedrooms, bathrooms). Cmd or shift-click selects tiles, and shift extends a range. With tiles selected, a floating bar lets you Hold them (with a reason and optional date) or Release them in bulk.

Holding pulls those units off the public board, and releasing puts them back, so this is the daily sales-desk control surface. Status, prices and the rest come from the development's plots, and holds and releases feed straight back into reservations and pricing.

**Getting the most out of it:**

- Filter by status first, then shift-click a whole floor to hold a block of inventory at once.
- This is the workflow view; for phase-grouped analytics use the inventory heatmap dashboard.
- Use the Pricing engine link to check what a held unit would quote at before you release it.

---

## property-dev_bulk_operations
KEY: propdev_bulk_ops.intro_more

This Manager-only console groups five batch actions, each in its own section: change plot statuses, extend reservation expiries, regenerate documents (receipts, sales contracts, certificates, NOCs), import leads from a CSV, and merge duplicate buyers. Every section follows the same safe flow: paste the record UUIDs or pick a file and options, run a Dry run to preview exactly what would change, review the succeeded, skipped and failed counts, then Execute for real. Batches over 50 items make you type EXECUTE to confirm.

Each run is one atomic transaction that rolls back fully on failure, so a large change never leaves the development half-applied. Plot UUIDs come from the Inventory Map (the empty states link straight to it), and outcomes can be downloaded as a CSV log. Status changes and merges are audit-logged with the reason you enter.

**Getting the most out of it:**

- Always read the dry-run result before the live run. Skipped rows tell you why an item was left out.
- Keep batches under the 500-item cap, or the server rejects them.
- Hold and release are not here on purpose. Use the Inventory Map for those.

---
