## contracts
KEY: contracts.intro_more

Start on the Contracts tab and create an agreement: name it, pick the contract type (lump sum, GMP, cost plus, T and M or unit price), set the currency and a retention percent, then open it to build out its schedule of values line by line. Each contract carries a retention ledger showing what is held and when it releases, plus a running claim history. The Progress Claims tab is where you bill against that schedule, and the Final Accounts tab is where completed or terminated contracts get settled.

Contracts sit at the center of the commercial chain. The schedule of values is what progress claims measure against. Approved variations from the Variations module adjust the contract sum mid-job, and certified claims push their net due into Finance as a payable. A won package in Bid Management can be formalized here as a new contract.

**Getting the most out of it:**
- Set the retention percent and release event up front so every claim withholds the right amount automatically.
- Use the type chip and status filter to find the contract you need fast on a busy job.
- Keep the schedule of values complete before the first claim, since claims bill percent or value complete against these exact lines.

---

## contracts_claim
KEY: contracts_claim.intro_more

This is one progress claim opened in full. Use Populate from progress to pull percent complete straight from progress observations, or edit the claim lines by hand against the contract schedule of values. The header gives you the four numbers that matter: gross, retention, prior claims and net due, all recomputed as you go. Walk the claim through Submit, then Approve, then Certify, then Mark paid using the buttons in the header, with Reject available while it is submitted. Certify and Mark paid are limited to managers and admins.

The claim reads its lines from the parent contract and writes the certified amount back to the contract and into Finance as a payable. On US, Canadian and Australian projects an AIA G702 and G703 application panel appears for formal payment certification.

**Getting the most out of it:**
- Populate from progress instead of typing percentages, so the bill matches what the site actually reported.
- Claim lines are only editable while the claim is draft or submitted, so finish entry before you approve.
- Watch the net due figure, since that is the amount that lands in Finance once the claim is certified.

---

## changeorders
KEY: changeorders.intro_more

Create a change order, set its reason category (client request, design change, unforeseen conditions, regulatory or error and omission), then add line items with original versus new quantities and rates. The system computes the cost delta and you record the schedule impact in days. From the detail view you can draft it with AI from a description, run the what-if impact simulator to see the forecast before committing, then move it through Draft, Submitted, Approved and Executed on the workflow stepper. Approval can run as a single step or as a named, multi-step approval chain in step order.

Approving a change order applies its cost impact to the project budget as a revised commitment, writes a matching budget row that Finance reads, and adds a BOQ section so the change is visible downstream. You can also link related RFIs to the order.

**Getting the most out of it:**
- Enter original and new quantities and rates per line and let the cost delta compute itself, rather than typing a lump figure.
- Use the impact simulator before approval so the budget hit is no surprise to anyone.
- Mark an order Executed only once the work is actually done, so dashboards can tell committed from completed.

---

## variations
KEY: variations.intro_more

Work the five tabs left to right as the change event matures. Raise a Notice first, acknowledge and respond to it, then close it. Promote it into a priced Variation Request, submit it for review and approve it, then convert the approved request into an agreed Variation Order carrying its final cost and schedule days. Daywork sheets capture time and materials work that you sign and bill, and Extension of Time claims track requested versus granted days alongside everything else.

Variations connect site change to the money. Each request and order records its estimated and final cost and schedule impact, the dashboard rolls these into project totals, and an approved order carries its cost and time impact into the contract final account and into Finance, so nothing agreed on site is lost at settlement.

**Getting the most out of it:**
- Start with a Notice the moment a change is spotted, so the paper trail predates any dispute.
- Convert a request to an order only once cost and time are genuinely agreed, since the order is the binding figure.
- Use daywork sheets for T and M work and keep EOT claims current, so time and cost stay defensible together.

---

## tendering
KEY: tendering.intro_more

Create a tender package from a source BOQ, give it a name and scope, then issue it. Each package moves through Draft, Issued, Collecting, Evaluating and Awarded. Open a package to add and compare bids side by side, with the comparison chart showing each bidder against the budget. Three sub-tabs on the package handle the detail: bids and comparison, addenda for mid-tender clarifications, and a leveling matrix for a line by line normalization. An award recommendation flags the suggested winner and warns when a low bid looks suspicious.

Award the winning bid and the platform runs the full transaction: it writes the agreed rates back to the BOQ, marks the package awarded, accepts the winning bid, rejects the rest, and drafts a purchase order in Procurement. That rate write-back and PO are what set this apart from Bid Management.

**Getting the most out of it:**
- Build the package from a finished BOQ so the rates you get back land on real positions.
- Use the leveling matrix before awarding, since headline totals can hide scope gaps.
- Read the recommendation warnings, since the lowest number is not always the safe award.

---

## bid-management
KEY: bid-management.intro_more

Create a bid package and add its scope lines, since bidders price these and they become the rows of the leveling matrix. Publish the package, invite bidders, and open bidding to collect their priced submissions, handling clarifications on the Q and A tab. Late, currency mismatched or incomplete submissions are flagged invalid and excluded from the comparison. Close bidding, run Compute Leveling to normalize the offers side by side, then award the best qualified bidder, which auto rejects the rest with a recorded reason.

Bid Management draws on Subcontractors and Contacts for the bidders you invite. Once a package is awarded it becomes read only, and a Formalise as Contract action takes you to Contracts to set up the awarded scope. Use Tendering instead when you want a formal BOQ-driven tender that writes rates back and raises a PO.

**Getting the most out of it:**
- Add complete scope lines before publishing, since they drive both pricing and the leveling matrix.
- Only valid submissions are awardable, so chase bidders to fix late or currency mismatched offers early.
- Level the bids before you award, so you are comparing like for like rather than headline totals.

---

## subcontractors
KEY: subcontractors.intro_more

Add each subcontractor, then run the prequalification questionnaire to record a status and score. The list shows an insurance traffic light driven by the certificate expiry date, plus a star rating from performance scores. Open a subcontractor to work four drawer tabs: scope of subcontract work, payment applications, performance ratings and retention. You can block a subcontractor, and the eligibility banner explains exactly why an award would be stopped.

This is the supply chain record the commercial modules trust. Prequalification status and lien waivers gate who can be invited to bid packages in Bid Management and who can be paid, so an expired certificate or a missing waiver stops an award before it happens. Awarded scopes flow on to Contracts and purchasing flows on to Procurement.

**Getting the most out of it:**
- Keep insurance and certificate expiry dates current, since the traffic light and the award gate both read them.
- Re-run prequalification when status changes, so the score reflects the firm you are about to use.
- Watch the retention tab so held money is released on the right event, not forgotten.

---

## supplier_catalogs
KEY: supplier_catalogs.intro_more

Use this as your reference library for buying. Add vendors with a status, build out their catalog items, and set up warehouses with stock balances. Open the price comparison on any catalog item to see how vendors line up on price for the same thing. The page has six tabs: Vendors, Catalog, Warehouses each own a real create flow, while the PRs, POs and 3-Way Match tabs are read only summaries that hand off to Procurement, where the live purchasing actually happens.

The split is deliberate. Supplier Catalogs stays focused on the vendor and item reference data that purchasing draws from, and deep links across to Procurement for raising requisitions, issuing purchase orders and matching invoices. It also links to Costs for unit rates.

**Getting the most out of it:**
- Keep vendor catalogs priced and current, since price comparison is only as good as the data behind it.
- Use the comparison view before committing to a supplier, so you are not paying more for the same item.
- Track warehouse balances here so you know what is on hand before you raise a new order in Procurement.

---

## procurement
KEY: procurement.intro_more

Raise a purchase order on the Purchase Orders tab: pick the vendor from Contacts, choose the PO type (standard, blanket or service), and add line items with quantities and rates. The PO moves through Draft, Issued, Partially received and Completed on the status pipeline. When a delivery arrives, record a goods receipt on the Goods Receipts tab. Each PO line carries a three-way match status comparing order, receipt and invoice, and a retainage panel lets you withhold against a PO.

Once a PO is issued you create an invoice from it, which posts a payable into Finance. PO totals roll up into the project budget as committed spend and become actual once the invoice is paid, so you see your exposure before the bill arrives. Vendor and item reference data comes from Supplier Catalogs.

**Getting the most out of it:**
- Raise the PO before the work or delivery, so committed spend shows up in the budget early.
- Record goods receipts as deliveries land, since the three-way match needs them to clear an invoice.
- Only issued, partially received or completed POs can be invoiced, so advance the status before billing.

---
