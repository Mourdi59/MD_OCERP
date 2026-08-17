// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Raise a change order with proof, not argument" (US).
//
// The objection is "our change orders get settled by relationships, not
// paperwork", and it is usually true right up to the one that does not. The
// case is built so the paperwork costs nothing on the changes that settle
// easily and is already complete on the change that does not.
//
// The US-specific weight is the notice clock. On US contracts the entitlement
// itself is conditioned on notice given within a stated number of days, so a
// late notice can extinguish a claim that was otherwise good. Deadlines are
// stated here as facts with their source named; clause text is never
// reproduced. Content strings are key plus inline English default and live
// only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "raise-a-change-order-with-proof",
  order: 1062,
  region: "US",
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor", "project-manager", "cost-consultant"],
  roles: ["project-manager", "commercial-manager", "quantity-surveyor"],
  icon: "FileSignature",
  titleKey: "cases.raise_a_change_order_with_proof.title",
  titleDefault: "Raise a change order with proof, not argument",
  descKey: "cases.raise_a_change_order_with_proof.desc",
  descDefault:
    "Serve notice inside the contract clock, describe the change against the scope it departs from, attach the evidence, price it in the categories the contract recognises, and take it through to an executed change order.",
  longDescKey: "cases.raise_a_change_order_with_proof.longdesc",
  longDescDefault:
    "Most changes are agreed in a phone call, and that works until the one that is not. The difference between a change order that gets paid and one that gets argued is almost never the merits: it is whether notice was given inside the days the contract allows, whether the change is described against the scope it departs from, and whether the cost is broken down the way the contract asks rather than presented as a total. This case runs that sequence as ordinary work rather than as a dispute posture, so that the record exists before anyone needs it and the conversation stays about the number instead of about whether the entitlement survived.",
  estMinutes: 18,
  steps: [
    {
      id: "notice",
      icon: "CalendarClock",
      inputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.notice.in.event", label: "The event and the day it happened" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.notice.in.clause", label: "The notice period your contract sets" },
      ],
      outputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.notice.out.served", label: "Notice served and dated" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.notice.out.clock", label: "Entitlement preserved" },
      ],
      titleKey: "cases.raise_a_change_order_with_proof.step.notice.title",
      titleDefault: "Serve notice before you know what it is worth",
      whatKey: "cases.raise_a_change_order_with_proof.step.notice.what",
      whatDefault:
        "Record the event in correspondence and send the notice the same week, naming the event and the date it occurred. You do not need the cost yet, and waiting for it is the most common way the notice goes late.",
      whyKey: "cases.raise_a_change_order_with_proof.step.notice.why",
      whyDefault:
        "US contracts condition the entitlement itself on the notice, not merely the payment for it. The period is short, it runs from when you should have recognised the event rather than from when you finished pricing it, and it is not the same on private and federal work. Miss it and a claim that would have been paid can be gone on the date alone, so read the period out of your own contract before you need it.",
      moduleLabel: "Correspondence",
      moduleLabelKey: "correspondence.title",
      to: "/projects/:projectId/correspondence",
    },
    {
      id: "scope",
      icon: "GitCompare",
      inputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.scope.in.contract", label: "Contract scope as awarded" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.scope.in.instruction", label: "The instruction or condition that changed it" },
      ],
      outputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.scope.out.delta", label: "The change stated as a difference" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.scope.out.origin", label: "What caused it, on record" },
      ],
      titleKey: "cases.raise_a_change_order_with_proof.step.scope.title",
      titleDefault: "Describe the change against the scope it departs from",
      whatKey: "cases.raise_a_change_order_with_proof.step.scope.what",
      whatDefault:
        "Raise the variation and write it as a difference: what the contract documents required, what is now required instead, and which instruction, drawing revision or site condition moved it. Keep the description to the change itself and leave the pricing to the next step.",
      whyKey: "cases.raise_a_change_order_with_proof.step.scope.why",
      whyDefault:
        "A change described on its own reads as a request for more money. The same change described as a departure from a named scope item reads as a fact, and the argument moves from whether it is a change to what it costs. That is the whole move.",
      moduleLabel: "Variations",
      moduleLabelKey: "nav.variations",
      to: "/projects/:projectId/variations",
    },
    {
      id: "evidence",
      icon: "FileSearch",
      inputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.evidence.in.diary", label: "Daily reports for the affected days" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.evidence.in.records", label: "Photos, instructions, correspondence" },
      ],
      outputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.evidence.out.bundle", label: "Evidence attached to the change" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.evidence.out.gaps", label: "Missing records identified early" },
      ],
      titleKey: "cases.raise_a_change_order_with_proof.step.evidence.title",
      titleDefault: "Attach the proof while the people who made it are still on site",
      whatKey: "cases.raise_a_change_order_with_proof.step.evidence.what",
      whatDefault:
        "Pull the daily reports covering the affected days into the evidence bundle along with the instruction, the drawing revision and the photographs, and note what is missing so it can be captured now rather than looked for later.",
      whyKey: "cases.raise_a_change_order_with_proof.step.evidence.why",
      whyDefault:
        // Do not name a season in user-facing copy. One of them is a single
        // everyday word across the Romance languages, and that word is also a
        // denied product name, so a faithful translation of the English put a
        // brand-gate hit into seven locale files at once for a sentence that
        // was never about a brand. The trigger has to die in the English
        // source: the denylist cannot tell the season from the product, and
        // loosening it for the ordinary word would blind it to the real one.
        // This comment deliberately does not spell the word either, because the
        // gate reads comments as well as strings.
        "The gap you find today is one somebody can still fill. The same gap found during the final account is a hole in your case, and the only person who could have closed it left the job months ago.",
      moduleLabel: "Claims Evidence",
      moduleLabelKey: "nav.claims_evidence",
      to: "/projects/:projectId/claims-evidence",
    },
    {
      id: "cost",
      icon: "Calculator",
      inputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.cost.in.hours", label: "Booked labor and plant hours" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.cost.in.quotes", label: "Subcontractor and supplier quotes" },
      ],
      outputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.cost.out.breakdown", label: "Cost broken into its categories" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.cost.out.markup", label: "Markup applied at the contract rate" },
      ],
      titleKey: "cases.raise_a_change_order_with_proof.step.cost.title",
      titleDefault: "Price it in the categories the contract asks for",
      whatKey: "cases.raise_a_change_order_with_proof.step.cost.what",
      whatDefault:
        "Build the cost as separate lines for labor, materials, equipment, subcontract work and the additional supervision the change caused, then apply the overhead and profit percentages the contract sets rather than a round number.",
      whyKey: "cases.raise_a_change_order_with_proof.step.cost.why",
      whyDefault:
        "A lump sum invites a lump sum counter-offer. A breakdown can only be argued line by line, and most lines are not worth arguing about, so the negotiation narrows to the one or two that are. Where the contract lets the owner direct the work before the price is agreed, this breakdown is also what the eventual settlement gets measured against.",
      moduleLabel: "Change Orders",
      moduleLabelKey: "nav.change_orders",
      to: "/changeorders",
    },
    {
      id: "execute",
      icon: "FileCheck",
      inputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.execute.in.priced", label: "The priced change" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.execute.in.approvals", label: "Who has to approve it" },
      ],
      outputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.execute.out.executed", label: "Executed change order" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.execute.out.time", label: "Time impact agreed or reserved" },
      ],
      titleKey: "cases.raise_a_change_order_with_proof.step.execute.title",
      titleDefault: "Take it through the stages your job actually uses",
      whatKey: "cases.raise_a_change_order_with_proof.step.execute.what",
      whatDefault:
        "Move the change through its stages to execution, and settle the time impact in the same document as the money: either an agreed extension, or an explicit reservation where the delay cannot be assessed yet.",
      whyKey: "cases.raise_a_change_order_with_proof.step.execute.why",
      whyDefault:
        "A change order that settles the cost and stays silent on time is usually read later as having settled both. If the schedule effect is not yet knowable, saying so in the document is what keeps it open.",
      moduleLabel: "Change Orders",
      moduleLabelKey: "nav.change_orders",
      to: "/changeorders",
    },
    {
      id: "bill",
      icon: "Landmark",
      inputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.bill.in.executed", label: "Executed change orders" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.bill.in.contract", label: "Current contract sum" },
      ],
      outputs: [
        { labelKey: "cases.raise_a_change_order_with_proof.step.bill.out.revised", label: "Revised contract sum" },
        { labelKey: "cases.raise_a_change_order_with_proof.step.bill.out.billable", label: "Change billable on the next application" },
      ],
      titleKey: "cases.raise_a_change_order_with_proof.step.bill.title",
      titleDefault: "Carry the executed change into the money",
      whatKey: "cases.raise_a_change_order_with_proof.step.bill.what",
      whatDefault:
        "Let the executed change orders adjust the contract sum so the next payment application bills them as their own lines, with the work completed to date against each one, rather than folding them into the original scope lines.",
      whyKey: "cases.raise_a_change_order_with_proof.step.bill.why",
      whyDefault:
        "A change buried inside an original line is a change that gets questioned every month for the rest of the job. Billed as its own line against its own executed change order, it is approved once and stops coming up.",
      // `finance.title` because that is what the sidebar itself puts on this
      // route (navCatalog.ts, `to: '/finance'`). The two keys both render
      // "Finance" in English and disagree in five locales (da, hi, ky, nl, no),
      // so the chip has to match the destination rather than match whichever
      // key more playbooks happen to use.
      moduleLabel: "Finance",
      moduleLabelKey: "finance.title",
      to: "/projects/:projectId/finance",
    },
  ],
};

export default playbook;
