// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Take off a plan in feet and inches" (US).
//
// The first thing a US estimator tests on any new tool is whether it can read
// a drawing the way the drawing is dimensioned: feet and inches, fractions,
// square feet, cubic yards. This case runs that test end to end - set the job
// to imperial, calibrate the sheet off a dimension printed on it, measure,
// carry the quantities into the bill and price them per square foot. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "take-off-a-plan-in-feet-and-inches",
  order: 1059,
  region: "US",
  category: "estimating",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  roles: ["estimator", "quantity-surveyor"],
  icon: "Ruler",
  titleKey: "cases.take_off_a_plan_in_feet_and_inches.title",
  titleDefault: "Take off a plan in feet and inches",
  descKey: "cases.take_off_a_plan_in_feet_and_inches.desc",
  descDefault:
    "Set the job to imperial, calibrate a PDF sheet against a dimension printed on it, measure in feet and inches, and carry square feet and cubic yards into a priced bill.",
  longDescKey: "cases.take_off_a_plan_in_feet_and_inches.longdesc",
  longDescDefault:
    "A US drawing is dimensioned in feet and inches and a US bid is priced per square foot, per linear foot and per cubic yard. That is not a display preference, it is the unit the quantity is agreed in, and a takeoff that rounds it through metres and back is a takeoff nobody will check against the plan. Here the measurement system is set once on the job, the sheet is calibrated against a dimension the drawing itself states, and every quantity from that point on is read, entered and priced in the units the drawing and the bid already use.",
  estMinutes: 14,
  steps: [
    {
      id: "units",
      icon: "Gauge",
      inputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.units.in.job", label: "The job you are pricing" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.units.in.market", label: "Market the bid is for" },
      ],
      outputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.units.out.system", label: "Imperial measurement system" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.units.out.money", label: "US number and currency format" },
      ],
      titleKey: "cases.take_off_a_plan_in_feet_and_inches.step.units.title",
      titleDefault: "Put the job on feet and inches before you measure anything",
      whatKey: "cases.take_off_a_plan_in_feet_and_inches.step.units.what",
      whatDefault:
        "Open the regional settings and set the measurement system to imperial, the number format to US and the currency to USD. From here on every quantity you are shown is in feet, square feet, cubic yards, pounds and short tons.",
      whyKey: "cases.take_off_a_plan_in_feet_and_inches.step.units.why",
      whyDefault:
        "Setting this after the takeoff means re-reading every quantity you already checked. Setting it first is the difference between a bill you can hold against the drawing and one you have to convert in your head while the client is on the phone.",
      moduleLabel: "Settings",
      moduleLabelKey: "nav.settings",
      to: "/settings",
    },
    {
      id: "sheets",
      icon: "FolderInput",
      inputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.sheets.in.set", label: "Drawing set as issued" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.sheets.in.date", label: "Issue date and revision" },
      ],
      outputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.sheets.out.filed", label: "Sheets filed on the project" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.sheets.out.revision", label: "Revision you measured on record" },
      ],
      titleKey: "cases.take_off_a_plan_in_feet_and_inches.step.sheets.title",
      titleDefault: "File the sheet set you are going to measure",
      whatKey: "cases.take_off_a_plan_in_feet_and_inches.step.sheets.what",
      whatDefault:
        "Upload the architectural and structural sheets into the project files exactly as they were issued, with the revision letter and the issue date recorded alongside them.",
      whyKey: "cases.take_off_a_plan_in_feet_and_inches.step.sheets.why",
      whyDefault:
        "Drawings get reissued during a bid period. When the scope argument comes, the only thing that settles it is being able to say which revision your quantities were measured on, and to open it.",
      moduleLabel: "Documents",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
    {
      id: "calibrate",
      icon: "Crosshair",
      inputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.calibrate.in.sheet", label: "PDF sheet" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.calibrate.in.dimension", label: "A dimension printed on the sheet" },
      ],
      outputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.calibrate.out.scale", label: "Scale set from a stated dimension" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.calibrate.out.origin", label: "Where the scale came from, on record" },
      ],
      titleKey: "cases.take_off_a_plan_in_feet_and_inches.step.calibrate.title",
      titleDefault: "Calibrate the sheet against a dimension it states itself",
      whatKey: "cases.take_off_a_plan_in_feet_and_inches.step.calibrate.what",
      whatDefault:
        "Open the sheet in PDF measurements, draw the calibration line across a grid bay or an opening the drawing dimensions, and type that dimension in feet and inches. A bay called out at 24 feet 6 inches is entered as 24 feet and 6 inches, not as 7.468 metres.",
      whyKey: "cases.take_off_a_plan_in_feet_and_inches.step.calibrate.why",
      whyDefault:
        "A PDF that has been printed to fit, rotated or reissued at a different sheet size no longer honours the scale in its title block. Calibrating against a dimension the drawing states is the only scale you can defend, and the product records where it came from so a later reader does not have to guess.",
      moduleLabel: "PDF Measurements",
      moduleLabelKey: "nav.pdf_measurements",
      to: "/takeoff?tab=measurements",
    },
    {
      id: "measure",
      icon: "PencilRuler",
      inputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.measure.in.calibrated", label: "Calibrated sheet" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.measure.in.scope", label: "Scope you are bidding" },
      ],
      outputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.measure.out.areas", label: "Areas in square feet" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.measure.out.lengths", label: "Lengths in linear feet" },
      ],
      titleKey: "cases.take_off_a_plan_in_feet_and_inches.step.measure.title",
      titleDefault: "Measure the areas, lengths and counts you are bidding",
      whatKey: "cases.take_off_a_plan_in_feet_and_inches.step.measure.what",
      whatDefault:
        "Work the sheet trade by trade: area for slabs, roofing and finishes, polyline for footings, curb and partitions, count for doors, fixtures and columns. Name each measurement after the scope it belongs to rather than after the shape you drew.",
      whyKey: "cases.take_off_a_plan_in_feet_and_inches.step.measure.why",
      whyDefault:
        "Named measurements are what let a second estimator check your numbers, and what lets you re-measure only the part that changed when the sheet is reissued. An unnamed pile of shapes has to be redone from scratch.",
      moduleLabel: "PDF Measurements",
      moduleLabelKey: "nav.pdf_measurements",
      to: "/takeoff?tab=measurements",
    },
    {
      id: "quantities",
      icon: "ListTree",
      inputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.quantities.in.measurements", label: "Named measurements" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.quantities.in.assumptions", label: "Thicknesses and depths" },
      ],
      outputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.quantities.out.rollup", label: "Quantities rolled up by scope" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.quantities.out.volumes", label: "Volumes in cubic yards" },
      ],
      titleKey: "cases.take_off_a_plan_in_feet_and_inches.step.quantities.title",
      titleDefault: "Roll the measurements up into the quantities you will price",
      whatKey: "cases.take_off_a_plan_in_feet_and_inches.step.quantities.what",
      whatDefault:
        "In the takeoff register, group the measurements by scope and turn areas into the quantities a rate is actually against: slab area times thickness gives concrete in cubic yards, wall length times height gives the square feet of framing and board.",
      whyKey: "cases.take_off_a_plan_in_feet_and_inches.step.quantities.why",
      whyDefault:
        "This is where a takeoff either stays a set of shapes or becomes a quantity a subcontractor can bid. Doing it in the register rather than in a side spreadsheet keeps the thickness you assumed attached to the number that used it.",
      moduleLabel: "Quantity Takeoff",
      moduleLabelKey: "nav.quantities",
      to: "/quantities",
    },
    {
      id: "bill",
      icon: "Calculator",
      inputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.bill.in.quantities", label: "Rolled-up quantities" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.bill.in.rates", label: "Your unit rates" },
      ],
      outputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.bill.out.priced", label: "Priced bill in USD" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.bill.out.units", label: "Rates per SF, LF and CY" },
      ],
      titleKey: "cases.take_off_a_plan_in_feet_and_inches.step.bill.title",
      titleDefault: "Carry the quantities into the bill and price them per foot",
      whatKey: "cases.take_off_a_plan_in_feet_and_inches.step.bill.what",
      whatDefault:
        "Send the quantities to the bill and price each line in the unit the trade quotes in: square feet for slab finish and drywall, linear feet for curb and base, cubic yards for concrete, pounds or tons for reinforcing. Where a quantity is a dimension rather than a total you can type it the way the drawing writes it, as 12'-6 3/4\", and the line takes the value.",
      whyKey: "cases.take_off_a_plan_in_feet_and_inches.step.bill.why",
      whyDefault:
        "A rate you can compare against last job and against the sub's quote is a rate in the unit both of them used. Pricing per square metre and converting at the end is how a bid loses an argument it should have won.",
      moduleLabel: "Bill of Quantities",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "check",
      icon: "ShieldCheck",
      inputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.check.in.priced", label: "Priced bill" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.check.in.plan", label: "The sheet you measured" },
      ],
      outputs: [
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.check.out.report", label: "Validation report" },
        { labelKey: "cases.take_off_a_plan_in_feet_and_inches.step.check.out.cleared", label: "Unit and quantity findings cleared" },
      ],
      titleKey: "cases.take_off_a_plan_in_feet_and_inches.step.check.title",
      titleDefault: "Check the units before the bid goes out",
      whatKey: "cases.take_off_a_plan_in_feet_and_inches.step.check.what",
      whatDefault:
        "Run validation over the priced bill and clear what it finds: a line still at zero, a quantity that does not tie back to a measurement, a weight priced against a ton where the quote was per pound.",
      whyKey: "cases.take_off_a_plan_in_feet_and_inches.step.check.why",
      whyDefault:
        "A short ton is 2000 pounds and a metric tonne is about 2205, so a steel line that quietly swapped one for the other is out by nine percent before anyone has argued about the rate. This pass is where that gets caught.",
      moduleLabel: "Validation",
      moduleLabelKey: "validation.title",
      to: "/validation",
    },
  ],
};

export default playbook;
