// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Answer a GAEB inquiry as a subcontractor" (DE).
//
// The other side of the GAEB handshake: a Nachunternehmer takes the general
// contractor's X83 inquiry in as it was issued, keeps only their own trade,
// prices it with their own rates, separates the Hauptangebot from a
// Nebenangebot and returns X84 before the Abgabefrist. Content strings are key
// plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "answer-a-gaeb-inquiry-as-a-subcontractor",
  order: 1058,
  category: "tendering",
  companyTypes: ["subcontractor"],
  roles: ["estimator", "quantity-surveyor", "commercial-manager"],
  region: "DE",
  icon: "FileOutput",
  titleKey: "cases.answer_a_gaeb_inquiry_as_a_subcontractor.title",
  titleDefault: "Answer a GAEB inquiry as a subcontractor",
  descKey: "cases.answer_a_gaeb_inquiry_as_a_subcontractor.desc",
  descDefault:
    "Take the contractor's GAEB inquiry into your own LV, price your trade with your own rates, decide between Hauptangebot and Nebenangebot, and send the X84 back before the deadline.",
  longDescKey: "cases.answer_a_gaeb_inquiry_as_a_subcontractor.longdesc",
  longDescDefault:
    "A Nachunternehmer who retypes the general contractor's LV into an old calculator answers last and wins least. This case takes the X83 in exactly as it was issued, keeps the position numbering the contractor will compare against, prices only your trade with rates you can defend, and hands back X84 files - the Hauptangebot, and the Nebenangebot where you know a better way - in time to be read.",
  estMinutes: 11,
  steps: [
    {
      id: "intake",
      icon: "Gavel",
      inputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.intake.in.inquiry",
          label: "Inquiry from the contractor",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.intake.in.x83",
          label: "GAEB X83 file",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.intake.out.logged",
          label: "Logged inquiry",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.intake.out.deadline",
          label: "Abgabefrist on record",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.intake.out.rules",
          label: "Nebenangebot rule",
        },
      ],
      titleKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.intake.title",
      titleDefault: "Log the inquiry and its deadline",
      whatKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.intake.what",
      whatDefault:
        "Log the inquiry the general contractor sent you: which trade package it covers, the Abgabefrist and the Bindefrist you are held to, and whether the letter admits Nebenangebote at all.",
      whyKey: "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.intake.why",
      whyDefault:
        "Whether an alternate is allowed is decided by the inquiry, not by you. Reading that together with the deadline on day one is what stops a good idea being set aside on a formality, or a finished price arriving an hour late.",
      moduleLabel: "Bid Management",
      moduleLabelKey: "nav.bid_management",
      to: "/bid-management",
    },
    {
      id: "import",
      icon: "FileInput",
      inputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.import.in.x83",
          label: "GAEB X83 file",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.import.in.project",
          label: "Your project",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.import.out.lv",
          label: "LV with positions",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.import.out.numbering",
          label: "Original OZ numbering",
        },
      ],
      titleKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.import.title",
      titleDefault: "Import the X83 into your own LV",
      whatKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.import.what",
      whatDefault:
        "Drop the X83 on the import tab, check the parsed positions in the preview and take them into a fresh LV in your own project. Ordinal numbers, quantities, units and Langtext arrive exactly as the contractor issued them.",
      whyKey: "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.import.why",
      whyDefault:
        "Retyping the contractor's LV is where a transposed quantity or a dropped position becomes a loss you carry to site. Importing keeps your price tied to their numbering, so every line answers the line they asked about.",
      moduleLabel: "GAEB Exchange",
      moduleLabelKey: "nav.gaeb_exchange",
      to: "/gaeb-exchange",
    },
    {
      id: "scope",
      icon: "Split",
      inputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.scope.in.lv",
          label: "Imported LV",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.scope.in.trade",
          label: "Your trade scope",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.scope.out.package",
          label: "Your trade package",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.scope.out.exclusions",
          label: "Exclusions noted",
        },
      ],
      titleKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.scope.title",
      titleDefault: "Cut the bill down to your trade",
      whatKey: "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.scope.what",
      whatDefault:
        "Work through the imported LV and keep the titles and positions that belong to your trade, whether that is Trockenbau or TGA, and mark what is outside your scope. Check the quantities against your own take before you price a line.",
      whyKey: "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.scope.why",
      whyDefault:
        "A Nachunternehmer prices one trade out of a bill written for the whole building. Drawing that boundary first keeps your offer comparable, and checking the quantity is what stops you carrying the planner's undermeasure at your own risk.",
      moduleLabel: "Bill of Quantities",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "price",
      icon: "Calculator",
      inputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.price.in.positions",
          label: "Unpriced positions",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.price.in.rates",
          label: "Your own rates",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.price.out.priced",
          label: "Priced Hauptangebot",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.price.out.notes",
          label: "Qualifications noted",
        },
      ],
      titleKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.price.title",
      titleDefault: "Price it with your own rates",
      whatKey: "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.price.what",
      whatDefault:
        "Price every position from your own rates and assemblies instead of somebody else's guide price: labour, material, plant and the surcharge you actually carry, each line read against its Langtext as you go.",
      whyKey: "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.price.why",
      whyDefault:
        "Your own rate is the only number you can defend when the contractor asks how you got there. Reading the Langtext while you price is where you find the scaffold, the working hours or the tolerance that would otherwise be free work.",
      moduleLabel: "Resource Catalog",
      moduleLabelKey: "catalog.title",
      to: "/catalog",
    },
    {
      id: "alternate",
      icon: "GitBranch",
      inputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.alternate.in.priced",
          label: "Priced Hauptangebot",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.alternate.in.idea",
          label: "Your better method",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.alternate.out.haupt",
          label: "Hauptangebot LV",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.alternate.out.neben",
          label: "Nebenangebot LV",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.alternate.out.reason",
          label: "Reason per changed position",
        },
      ],
      titleKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.alternate.title",
      titleDefault: "Separate Hauptangebot from Nebenangebot",
      whatKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.alternate.what",
      whatDefault:
        "Keep the priced LV as your Hauptangebot, line for line as asked. Where your method really is better, copy the bill into a second LV, change only the positions your solution touches and write the reason next to each one.",
      whyKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.alternate.why",
      whyDefault:
        "A Nebenangebot wins work when it is a clean second offer the contractor can compare position by position. Mixing the better idea into the main bill instead risks the whole offer being set aside as not answering the tender.",
      moduleLabel: "Bill of Quantities",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "validate",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.validate.in.haupt",
          label: "Hauptangebot LV",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.validate.in.neben",
          label: "Nebenangebot LV",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.validate.out.report",
          label: "Validation report",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.validate.out.fixed",
          label: "Gaps closed",
        },
      ],
      titleKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.validate.title",
      titleDefault: "Validate both bills before they go out",
      whatKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.validate.what",
      whatDefault:
        "Run both LVs through validation: no position left at zero, no quantity that no longer ties back to the X83, and the structure the return file has to honour still intact.",
      whyKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.validate.why",
      whyDefault:
        "A single unpriced position can void the whole submission, and nobody reads several hundred lines twice at four in the afternoon on the deadline day. Validation is the second pair of eyes that takes a minute.",
      moduleLabel: "Validation",
      moduleLabelKey: "validation.title",
      to: "/validation",
    },
    {
      id: "submit",
      icon: "Send",
      inputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.submit.in.validated",
          label: "Validated bills",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.submit.in.deadline",
          label: "Abgabefrist",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.submit.out.x84haupt",
          label: "X84 Hauptangebot",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.submit.out.x84neben",
          label: "X84 Nebenangebot",
        },
        {
          labelKey:
            "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.submit.out.record",
          label: "Submission on record",
        },
      ],
      titleKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.submit.title",
      titleDefault: "Export the X84 and submit on time",
      whatKey:
        "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.submit.what",
      whatDefault:
        "Export each priced LV on the export tab as its own X84, name the files so the contractor sees at a glance which one is the Hauptangebot and which the Nebenangebot, and send them with your covering letter before the Abgabefrist.",
      whyKey: "cases.answer_a_gaeb_inquiry_as_a_subcontractor.step.submit.why",
      whyDefault:
        "An X84 reads straight into the contractor's bid comparison, so your prices land in the evaluation without anybody rekeying them. Two clearly named files are what let your alternate be judged rather than put aside.",
      moduleLabel: "GAEB Exchange",
      moduleLabelKey: "nav.gaeb_exchange",
      to: "/gaeb-exchange",
    },
  ],
};

export default playbook;
