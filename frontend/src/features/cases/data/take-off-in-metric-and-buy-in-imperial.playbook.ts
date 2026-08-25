// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Take off in metric and buy in imperial" (CA).
//
// Canada measures in metric and buys in imperial, so every bill of materials in
// the country carries the contradiction. The point of the case is that a
// quantity and a product name are two different facts about one row, and that
// there are two different KINDS of nominal name in the same bill: a dressed
// lumber size fixed by standard, where there is no arithmetic between the name
// and the size at all, and a sheet size that is the imperial figure rounded.
// A single conversion factor gets the first catastrophically wrong and the
// second slightly wrong, and slightly wrong is the one that survives review.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "take-off-in-metric-and-buy-in-imperial",
  order: 1105,
  region: "CA",
  category: "estimating",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  roles: ["estimator", "quantity-surveyor"],
  icon: "Ruler",
  titleKey: "cases.take_off_in_metric_and_buy_in_imperial.title",
  titleDefault: "Take off in metric and buy in imperial",
  descKey: "cases.take_off_in_metric_and_buy_in_imperial.desc",
  descDefault:
    "Measure the drawings in metric, keep the quantity metric everywhere it is stored and exported, and carry the imperial product name the yard will actually sell you on the same row, without letting either one rewrite the other.",
  longDescKey: "cases.take_off_in_metric_and_buy_in_imperial.longdesc",
  longDescDefault:
    "This is a metric country whose construction products are named and bought in imperial, so the contradiction is on every bill of materials on every job. What makes it more than a display preference is that a Canadian bill holds two different kinds of nominal name and they behave in opposite directions. A nominal 2x4 is dressed to 38 by 89 mm, a size fixed by standard, and there is no arithmetic between the name and the size: two inches is 50.8 mm and the board is 38 mm, so anyone who converts instead of looking it up is out by a third. A 4x8 sheet is 48 by 96 inches, which is exactly 1219.2 by 2438.4 mm and is conventionally written 1220 by 2440, so here the imperial figure is the real one and the metric is its rounding. One row's metric size cannot be derived from its name at all and the next row's is its name rounded, which is why a single conversion factor gets one of them badly wrong and the other slightly wrong, and slightly wrong is the more dangerous of the two.",
  estMinutes: 15,
  steps: [
    {
      id: "measure",
      icon: "Ruler",
      inputs: [
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.measure.in.drawings", label: "Drawing set at a known scale" },
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.measure.in.scope", label: "Scope to be measured" },
      ],
      outputs: [
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.measure.out.metric", label: "Metric lengths, areas and volumes" },
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.measure.out.tied", label: "Measurements tied to the sheet" },
      ],
      titleKey: "cases.take_off_in_metric_and_buy_in_imperial.step.measure.title",
      titleDefault: "Measure off the drawings in metric",
      whatKey: "cases.take_off_in_metric_and_buy_in_imperial.step.measure.what",
      whatDefault:
        "Set the scale from a known dimension on the sheet and measure lengths, areas and volumes in metric, taking each value from the drawing itself rather than from a figure somebody has already converted.",
      whyKey: "cases.take_off_in_metric_and_buy_in_imperial.step.measure.why",
      whyDefault:
        "The drawings are metric, the model is metric and the specification is metric. Measuring in one system and converting at every step adds a rounding at every step, and roundings compound worst in the quantities that matter most, which are always the biggest ones.",
      moduleLabel: "PDF Measurements",
      moduleLabelKey: "nav.pdf_measurements",
      to: "/takeoff",
    },
    {
      id: "quantities",
      icon: "Table2",
      inputs: [
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.quantities.in.measured", label: "Measurements from the drawings" },
      ],
      outputs: [
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.quantities.out.stored", label: "Metric quantities stored once" },
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.quantities.out.view", label: "A display that does not edit" },
      ],
      titleKey: "cases.take_off_in_metric_and_buy_in_imperial.step.quantities.title",
      titleDefault: "Store the quantity metric and leave it that way",
      whatKey: "cases.take_off_in_metric_and_buy_in_imperial.step.quantities.what",
      whatDefault:
        "Keep the measured quantity in its metric unit as the stored value, and treat an imperial reading of it as a view of that number rather than as a replacement for it.",
      whyKey: "cases.take_off_in_metric_and_buy_in_imperial.step.quantities.why",
      whyDefault:
        "There is only a right answer for one stored number. Storing a converted figure and converting it back is how a quantity acquires a rounding it never had, and nobody catches it, because both versions look entirely reasonable.",
      moduleLabel: "Quantity Takeoff",
      moduleLabelKey: "nav.quantities",
      to: "/quantities",
    },
    {
      id: "nominal",
      icon: "Tags",
      inputs: [
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.nominal.in.quantities", label: "Metric quantities" },
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.nominal.in.names", label: "Product names as they are bought" },
      ],
      outputs: [
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.nominal.out.both", label: "Rows carrying both facts" },
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.nominal.out.dressed", label: "Dressed sizes stated, not derived" },
      ],
      titleKey: "cases.take_off_in_metric_and_buy_in_imperial.step.nominal.title",
      titleDefault: "Carry the product name the yard will sell you",
      whatKey: "cases.take_off_in_metric_and_buy_in_imperial.step.nominal.what",
      whatDefault:
        "Write the nominal product name on the item beside the metric quantity: a 2x4 with its dressed size of 38 by 89 mm stated from the standard, a 4x8 sheet with 1219.2 by 2438.4 mm stated and 1220 by 2440 as the conventional designation. Take each stated size from the standard or the arithmetic that produced it, never from the name.",
      whyKey: "cases.take_off_in_metric_and_buy_in_imperial.step.nominal.why",
      whyDefault:
        "The quantity is what you measured and the name is what you order, and they are two different facts about the same row. A bill carrying only the metric size has to be translated at the counter by whoever answers the phone, and a bill carrying only the name cannot be checked back against the drawings at all.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "check",
      icon: "ShieldCheck",
      inputs: [
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.check.in.bill", label: "The priced bill" },
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.check.in.sizes", label: "Nominal names and stated sizes" },
      ],
      outputs: [
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.check.out.units", label: "Unit mismatches caught" },
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.check.out.verified", label: "Sizes verified against the standard" },
      ],
      titleKey: "cases.take_off_in_metric_and_buy_in_imperial.step.check.title",
      titleDefault: "Check that nothing was converted twice",
      whatKey: "cases.take_off_in_metric_and_buy_in_imperial.step.check.what",
      whatDefault:
        "Validate the bill before it goes out, looking for the two failures this scope produces: a quantity whose unit no longer matches the way it was measured, and a stated size that has been recomputed from the nominal name instead of taken from the standard.",
      whyKey: "cases.take_off_in_metric_and_buy_in_imperial.step.check.why",
      whyDefault:
        "Both failures produce numbers that look right, which is exactly why a read-through does not catch them. A member sized at 50.8 mm where the standard says 38 mm passes every eye in the room and is wrong by a third, and it is wrong in the direction that costs money on site rather than in the estimate.",
      moduleLabel: "Validation",
      moduleLabelKey: "validation.title",
      to: "/validation",
    },
    {
      id: "issue",
      icon: "FileOutput",
      inputs: [
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.issue.in.rows", label: "Bill rows carrying both facts" },
      ],
      outputs: [
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.issue.out.bill", label: "Metric bill for the client" },
        { labelKey: "cases.take_off_in_metric_and_buy_in_imperial.step.issue.out.order", label: "Material order in nominal sizes" },
      ],
      titleKey: "cases.take_off_in_metric_and_buy_in_imperial.step.issue.title",
      titleDefault: "Issue each reader the units they need",
      whatKey: "cases.take_off_in_metric_and_buy_in_imperial.step.issue.what",
      whatDefault:
        "Export the bill with the metric quantities intact for the client and the consultant, and produce the material order carrying the nominal names for the supplier, both from the same rows.",
      whyKey: "cases.take_off_in_metric_and_buy_in_imperial.step.issue.why",
      whyDefault:
        "Two readers need two different things from one set of rows, and neither should be handed a converted version of the other's. Exports staying metric is also what keeps the bill comparable against the drawings it was measured from, which is the only check anybody can run on it later.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
