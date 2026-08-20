// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Review what the AI read off the drawing".
//
// The estimator triages the plan reader's proposals before any of them reach
// the bill: band first, scale provenance second, acceptance last. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "review-ai-takeoff-proposals",
  order: 1037,
  category: "estimating",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  roles: ["estimator", "quantity-surveyor"],
  icon: "ListChecks",
  titleKey: "cases.review_ai_takeoff_proposals.title",
  titleDefault: "Review what the AI read off the drawing",
  descKey: "cases.review_ai_takeoff_proposals.desc",
  descDefault:
    "Take what the plan reader proposed on a PDF sheet and decide, proposal by proposal, what deserves to reach the bill. Triage by confidence band, check where each measurement got its scale, then accept only what you can defend.",
  longDescKey: "cases.review_ai_takeoff_proposals.longdesc",
  longDescDefault:
    "Running the read takes seconds. The review is the work, and it is the part that decides whether the machine saved you an afternoon or cost you a tender. Proposals sit in their own layer until you accept them, they are banded high, medium, low or not scored against the same thresholds the server scores with, and each one records where its scale ratio came from. Nothing here is about trusting the model more; it is about being able to say which lines you checked and why.",
  estMinutes: 12,
  steps: [
    {
      id: "read",
      icon: "Sparkles",
      inputs: [
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.read.in.sheet",
          label: "PDF sheet",
        },
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.read.in.scale",
          label: "Sheet scale",
        },
      ],
      outputs: [
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.read.out.proposals",
          label: "Measurement proposals",
        },
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.read.out.scores",
          label: "A score on each one",
        },
      ],
      titleKey: "cases.review_ai_takeoff_proposals.step.read.title",
      titleDefault: "Run the plan read",
      whatKey: "cases.review_ai_takeoff_proposals.step.read.what",
      whatDefault:
        "Open the sheet in Takeoff and run the plan read across it. The model comes back with proposed areas, lengths and counts, each carrying a score and a note of where its scale came from, and none of it has touched the bill yet.",
      whyKey: "cases.review_ai_takeoff_proposals.step.read.why",
      whyDefault:
        "The read is cheap and the acceptance is not. Keeping proposals in a layer you can throw away means a badly scanned sheet costs you a rerun, rather than leaving you with quantities in a bill that you cannot account for a fortnight later.",
      moduleLabel: "PDF Measurements",
      moduleLabelKey: "nav.pdf_measurements",
      to: "/takeoff",
    },
    {
      id: "triage",
      icon: "Gauge",
      inputs: [
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.triage.in.proposals",
          label: "Measurement proposals",
        },
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.triage.in.thresholds",
          label: "Published thresholds",
        },
      ],
      outputs: [
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.triage.out.count",
          label: "Low-band count",
        },
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.triage.out.cleared",
          label: "Proposals cleared to accept",
        },
      ],
      titleKey: "cases.review_ai_takeoff_proposals.step.triage.title",
      titleDefault: "Triage by confidence band",
      whatKey: "cases.review_ai_takeoff_proposals.step.triage.what",
      whatDefault:
        "Read the review bar before you go anywhere near Accept all. Every proposal sits in a band, high, medium, low or not scored, drawn from the cut points the server publishes. The bar tells you how many are in the low band. Work that band first, one at a time, and either fix it on the drawing or throw it out.",
      whyKey: "cases.review_ai_takeoff_proposals.step.triage.why",
      whyDefault:
        "A bare percentage beside a suggestion is not a decision, because nobody can tell you whether sixty-two is good. A band means the same thing to you as it does to the machine that scored it. Accept all over a pile of weak proposals is how a plan read turns into an over-order that nobody notices until the material lands.",
      moduleLabel: "PDF Measurements",
      moduleLabelKey: "nav.pdf_measurements",
      to: "/takeoff",
    },
    {
      id: "scale",
      icon: "Ruler",
      inputs: [
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.scale.in.measurement",
          label: "A proposed measurement",
        },
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.scale.in.provenance",
          label: "Where its scale came from",
        },
      ],
      outputs: [
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.scale.out.verified",
          label: "Verified scale ratio",
        },
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.scale.out.narrowed",
          label: "Rows on a bad sheet narrowed",
        },
      ],
      titleKey: "cases.review_ai_takeoff_proposals.step.scale.title",
      titleDefault: "Check where the scale came from",
      whatKey: "cases.review_ai_takeoff_proposals.step.scale.what",
      whatDefault:
        "Open a measurement and read its scale-from line. It says whether the ratio was calibrated on this sheet, taken from the document scale, inherited from the sheet, read out of the drawing text, recovered by OCR, read off the drawing by the model, or is simply Unknown. Recalibrate anything you would not defend out loud.",
      whyKey: "cases.review_ai_takeoff_proposals.step.scale.why",
      whyDefault:
        "A wrong scale never looks wrong. It looks like a plausible number that happens to be out by a factor, and it stays plausible all the way to an order. When a sheet does turn out to have been measured at the wrong ratio, provenance is what lets you pull exactly the rows that inherited the bad ratio instead of remeasuring the whole drawing.",
      moduleLabel: "PDF Measurements",
      moduleLabelKey: "nav.pdf_measurements",
      to: "/takeoff",
    },
    {
      id: "accept",
      icon: "Table2",
      inputs: [
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.accept.in.reviewed",
          label: "Reviewed measurements",
        },
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.accept.in.positions",
          label: "Bill positions",
        },
      ],
      outputs: [
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.accept.out.lines",
          label: "Priced bill lines",
        },
        {
          labelKey: "cases.review_ai_takeoff_proposals.step.accept.out.trace",
          label: "Quantities traceable to the sheet",
        },
      ],
      titleKey: "cases.review_ai_takeoff_proposals.step.accept.title",
      titleDefault: "Accept into the bill",
      whatKey: "cases.review_ai_takeoff_proposals.step.accept.what",
      whatDefault:
        "Push the measurements you have signed off into bill positions and attach rates to them. What arrives in the bill is what you reviewed, in the order you reviewed it, not what the model guessed on the first pass.",
      whyKey: "cases.review_ai_takeoff_proposals.step.accept.why",
      whyDefault:
        "The bill is the point of no return, because from here a number goes to a client, a subcontractor or a purchase order. A quantity that got in unreviewed is indistinguishable from one you measured yourself, right up to the moment somebody asks you to prove it.",
      moduleLabel: "Bill of Quantities",
      moduleLabelKey: "boq.title",
      to: "/boq",
    },
  ],
};

export default playbook;
