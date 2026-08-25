// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Adjust a material price with a cost index" (CN).
//
// Chinese contracts name the method by which steel, concrete and the other
// volatile materials get adjusted when prices move. This case walks the
// price-index method: the adjustment is the ratio of a published index series
// between the base period the contract names and the period the work was done
// in, applied on the bill rather than beside it.
//
// The point worth the estimator's attention is not the arithmetic, it is that
// the escalation line does not carry a percentage anybody typed. It names a
// series and two periods, and the increase is whatever the index did between
// them. That is a document rather than a number, which is what makes the
// monthly conversation short. Where the series has no value for a period, the
// bill refuses to produce a total rather than quietly pricing the line at
// nothing, and that refusal is the feature. Content strings are key plus inline
// English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "adjust-a-material-price-with-a-cost-index",
  order: 1127,
  region: "CN",
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  roles: ["quantity-surveyor", "commercial-manager", "estimator"],
  icon: "TrendingUp",
  titleKey: "cases.adjust_a_material_price_with_a_cost_index.title",
  titleDefault: "Adjust a material price with a cost index",
  descKey: "cases.adjust_a_material_price_with_a_cost_index.desc",
  descDefault:
    "Read the adjustment clause, load the index series it names, put an escalation line on the bill that names the series and the two periods, and issue the adjustment as a document that shows its own working.",
  longDescKey: "cases.adjust_a_material_price_with_a_cost_index.longdesc",
  longDescDefault:
    "Every month somebody rebuilds this in a spreadsheet, and every month the other side rebuilds it differently. The reason is that a spreadsheet stores the answer rather than the question: a cell holding 6.4 percent cannot tell you which series it came from, which two periods were compared, or whether the person who typed it used the same base date the contract did. An escalation line on the bill stores the question instead - this series, this base period, this current period - and recomputes the answer from the published values, so two parties running it get the same number or find out exactly where they disagree. Your contract decides the rest: which materials are adjustable, what movement has to happen before adjustment is due at all, and whether the whole movement or only the part beyond the threshold is adjusted. Those are terms to read and apply, not defaults to assume.",
  estMinutes: 16,
  steps: [
    {
      id: "clause",
      icon: "BookOpen",
      inputs: [
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.clause.in.contract", label: "The contract" },
      ],
      outputs: [
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.clause.out.method", label: "The method named" },
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.clause.out.base", label: "Base date and adjustable materials" },
      ],
      titleKey: "cases.adjust_a_material_price_with_a_cost_index.step.clause.title",
      titleDefault: "Read the clause before you compute anything",
      whatKey: "cases.adjust_a_material_price_with_a_cost_index.step.clause.what",
      whatDefault:
        "Open the contract and write down four things: which method it names, which materials are adjustable, what the base date is, and what movement has to occur before an adjustment is due. This case walks the price-index method; if your contract names the published-price method instead, the base data and the arithmetic are different and the clause will say so.",
      whyKey: "cases.adjust_a_material_price_with_a_cost_index.step.clause.why",
      whyDefault:
        "An adjustment computed correctly under the wrong method is worth nothing, and it is the sort of error that survives several months before anybody checks. Getting the four terms out of the contract once, in writing, saves rereading it every month and stops each month's calculation being a fresh interpretation.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "series",
      icon: "LineChart",
      inputs: [
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.series.in.published", label: "Published index values" },
      ],
      outputs: [
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.series.out.series", label: "Series with its periods" },
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.series.out.gaps", label: "Periods you are missing" },
      ],
      titleKey: "cases.adjust_a_material_price_with_a_cost_index.step.series.title",
      titleDefault: "Load the series the contract names, period by period",
      whatKey: "cases.adjust_a_material_price_with_a_cost_index.step.series.what",
      whatDefault:
        "Enter the index series with a value for each period, and keep it current as the publication comes out. The values you load are the published ones for your region; the product ships the mechanism and generic vocabulary rather than anybody's published book.",
      whyKey: "cases.adjust_a_material_price_with_a_cost_index.step.series.why",
      whyDefault:
        "The series is the evidence. Loading it as data means the adjustment can be recomputed and audited a year later against the same values, instead of resting on a screenshot somebody took of a bulletin that has since been superseded.",
      moduleLabel: "Price Index",
      moduleLabelKey: "nav.price_index",
      to: "/price-index",
    },
    {
      id: "escalate",
      icon: "Percent",
      inputs: [
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.escalate.in.bill", label: "The bill and its quantities" },
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.escalate.in.periods", label: "Base period and current period" },
      ],
      outputs: [
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.escalate.out.line", label: "Escalation line on the bill" },
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.escalate.out.refusal", label: "A refusal instead of a wrong total" },
      ],
      titleKey: "cases.adjust_a_material_price_with_a_cost_index.step.escalate.title",
      titleDefault: "Put the adjustment on the bill as a named series and two periods",
      whatKey: "cases.adjust_a_material_price_with_a_cost_index.step.escalate.what",
      whatDefault:
        "Add an escalation line to the bill's markup stack and give it the series and the two periods: the base period the contract names, and the period the work was done in. The factor comes from what the index did between them; you do not type a percentage.",
      whyKey: "cases.adjust_a_material_price_with_a_cost_index.step.escalate.why",
      whyDefault:
        "Where the series has no value for one of the two periods, the bill refuses rather than guessing, and a refusal is the right answer: an interpolated index value is a number nobody published and nobody can defend. It also means an adjustment that looks complete really is complete, instead of quietly containing a line that priced at zero.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "document",
      icon: "FileBarChart",
      inputs: [
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.document.in.adjusted", label: "The adjusted bill" },
      ],
      outputs: [
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.document.out.statement", label: "Adjustment statement" },
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.document.out.working", label: "Series, periods and factor shown" },
      ],
      titleKey: "cases.adjust_a_material_price_with_a_cost_index.step.document.title",
      titleDefault: "Issue it as a document that shows its working",
      whatKey: "cases.adjust_a_material_price_with_a_cost_index.step.document.what",
      whatDefault:
        "Report the adjustment with the series it used, the two periods, the factor and the base value it was applied to, so the reader can follow the arithmetic without asking you for the spreadsheet.",
      whyKey: "cases.adjust_a_material_price_with_a_cost_index.step.document.why",
      whyDefault:
        "An adjustment presented as a single figure gets queried every time. The same adjustment presented with its inputs gets checked once and accepted, because the person checking it can do the multiplication themselves and stop.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
    {
      id: "agree",
      icon: "Handshake",
      inputs: [
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.agree.in.statement", label: "The adjustment statement" },
      ],
      outputs: [
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.agree.out.submitted", label: "Submitted and dated" },
        { labelKey: "cases.adjust_a_material_price_with_a_cost_index.step.agree.out.agreed", label: "Agreed amount for the period" },
      ],
      titleKey: "cases.adjust_a_material_price_with_a_cost_index.step.agree.title",
      titleDefault: "Submit it for the period and get the amount agreed",
      whatKey: "cases.adjust_a_material_price_with_a_cost_index.step.agree.what",
      whatDefault:
        "Send the statement to the other party as correspondence for the period it covers, and record the agreed figure against it. Carry the agreed amount into the period's payment application yourself, on its own line, so it can be seen and queried separately from the valuation.",
      whyKey: "cases.adjust_a_material_price_with_a_cost_index.step.agree.why",
      whyDefault:
        "An adjustment buried inside a valuation total is one that gets renegotiated at settlement, because nobody can find it. On its own line, submitted with its working and agreed period by period, it is closed each month rather than accumulated into an argument about two years of steel.",
      moduleLabel: "Correspondence",
      moduleLabelKey: "nav.correspondence",
      to: "/projects/:projectId/correspondence",
    },
  ],
};

export default playbook;
