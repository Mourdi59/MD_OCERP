// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Walk the estimate from Class D to Class A" (CA).
//
// The Canadian class ladder runs D, C, B, A and publishes a design allowance
// per class. It does NOT publish an accuracy range, and the two are different
// quantities: a design allowance is a contingency added to an estimate, an
// accuracy band is a statement about how wrong the estimate might be. A case
// that reports 20 percent as "accurate to plus or minus 20 percent" is asserting
// something nobody has published, so the steps state the allowance and refuse
// the band. Content strings are key plus inline English default and live only
// here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "walk-the-estimate-from-class-d-to-class-a",
  order: 1108,
  region: "CA",
  category: "estimating",
  companyTypes: ["cost-consultant", "developer-client", "project-manager", "general-contractor"],
  roles: ["estimator", "quantity-surveyor", "project-manager"],
  icon: "LineChart",
  titleKey: "cases.walk_the_estimate_from_class_d_to_class_a.title",
  titleDefault: "Walk the estimate from Class D to Class A",
  descKey: "cases.walk_the_estimate_from_class_d_to_class_a.desc",
  descDefault:
    "Say what each estimate was prepared from and which class of the ladder that puts it in, carry the design allowance the class expects separately from risk, roll the cost up by element as well as by trade, and escalate to the mid-point of construction rather than to the day the job finishes.",
  longDescKey: "cases.walk_the_estimate_from_class_d_to_class_a.longdesc",
  longDescDefault:
    "The class ladder used on Canadian public work runs D, C, B, A. Class D rests on a statement of requirements or a functional program, Class C on schematic or conceptual design, Class B on design development drawings and outline specifications, and Class A on completed drawings and specifications prepared before calling tenders, with the first two treated as indicative and the last two as substantive. Each class carries a design allowance of no more than 20, 15, 10 and 5 percent respectively. That allowance is a contingency added to the estimate, and it is not a statement about how wrong the estimate might be: no accuracy range is published for these classes at all. So the honest form of the sentence is that the estimate was prepared from these documents and carries this allowance, which is a fact, rather than that it is accurate to a band, which nobody has published. An estimate that knows how much it does not know is more useful to a client than one that pretends to a precision the drawings cannot support.",
  estMinutes: 20,
  steps: [
    {
      id: "basis",
      icon: "NotebookPen",
      inputs: [
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.basis.in.documents", label: "Design documents at this stage" },
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.basis.in.assumptions", label: "Assumptions and exclusions" },
      ],
      outputs: [
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.basis.out.basis", label: "Basis document stating the class" },
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.basis.out.allowance", label: "Design allowance declared" },
      ],
      titleKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.basis.title",
      titleDefault: "Say what this estimate was prepared from",
      whatKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.basis.what",
      whatDefault:
        "Record the documents the estimate rests on and the class of the ladder they put it in, together with what is included and excluded, the market conditions assumed and the reason for the contingency carried. Name the design allowance the class expects, and do not state an accuracy range.",
      whyKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.basis.why",
      whyDefault:
        "The class is a statement about the documents rather than about the estimator, which is exactly why it is worth writing down. It tells the reader whether they are looking at a number to plan around or a number to commit to, and that is the difference between an estimate that gets superseded and one that gets blamed.",
      moduleLabel: "Basis of Estimate",
      moduleLabelKey: "nav.estimate_basis",
      to: "/estimate-basis",
    },
    {
      id: "allowances",
      icon: "Percent",
      inputs: [
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.allowances.in.class", label: "Class and its design allowance" },
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.allowances.in.risks", label: "Identified project risks" },
      ],
      outputs: [
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.allowances.out.lines", label: "Two allowance lines with reasons" },
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.allowances.out.shrink", label: "A design allowance that can shrink" },
      ],
      titleKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.allowances.title",
      titleDefault: "Carry design allowance and risk as separate lines",
      whatKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.allowances.what",
      whatDefault:
        "Carry the design allowance for the class as its own line, carry the allowance for identified risks as a second one, and write the reason for each beside it rather than in a covering note.",
      whyKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.allowances.why",
      whyDefault:
        "The two answer different questions and only one of them shrinks as drawings arrive. Rolled into a single contingency, the design maturing forces you either to cut a number you should keep or to keep one you should cut, and neither version can be explained to the client without explaining the mistake.",
      moduleLabel: "Allowances & Contingency",
      moduleLabelKey: "nav.allowances",
      to: "/allowances",
    },
    {
      id: "elemental",
      icon: "ListTree",
      inputs: [
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.elemental.in.priced", label: "Priced bill by trade" },
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.elemental.in.area", label: "Gross floor area" },
      ],
      outputs: [
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.elemental.out.summary", label: "Elemental summary" },
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.elemental.out.rates", label: "Cost per square metre by element" },
      ],
      titleKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.elemental.title",
      titleDefault: "Roll the cost up by element as well as by trade",
      whatKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.elemental.what",
      whatDefault:
        "Summarise the same cost by building element, so substructure, structure, envelope, internal finishes, services and external works each carry a total and a cost per square metre alongside the trade breakdown.",
      whyKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.elemental.why",
      whyDefault:
        "A client comparing this scheme against the last one compares elements, because trades shift with the procurement route and elements do not. It is also the fastest way to find the line that is wrong: an envelope rate out by a third is invisible in a trade total and obvious per square metre.",
      moduleLabel: "Bill of Quantities",
      moduleLabelKey: "boq.title",
      to: "/boq",
    },
    {
      id: "escalate",
      icon: "TrendingUp",
      inputs: [
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.escalate.in.base", label: "Base date of the prices" },
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.escalate.in.period", label: "Construction start and finish" },
      ],
      outputs: [
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.escalate.out.escalated", label: "Escalation to the mid-point" },
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.escalate.out.dates", label: "Both dates stated on the estimate" },
      ],
      titleKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.escalate.title",
      titleDefault: "Escalate to the mid-point of construction",
      whatKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.escalate.what",
      whatDefault:
        "Apply escalation from a dated index series between the date the prices were built and the mid-point of the construction period, and state both dates on the face of the estimate.",
      whyKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.escalate.why",
      whyDefault:
        "Escalating to the tender date underprices everything that happens after it and escalating to completion overprices half the job. The mid-point is where the average dollar is actually spent, and a reviewer expects to see it, so using it is one fewer thing you have to defend.",
      moduleLabel: "Price Index",
      moduleLabelKey: "nav.price_index",
      to: "/price-index",
    },
    {
      id: "compare",
      icon: "GitCompare",
      inputs: [
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.compare.in.earlier", label: "The earlier estimate" },
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.compare.in.current", label: "The current estimate" },
      ],
      outputs: [
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.compare.out.variance", label: "Variance split by cause" },
        { labelKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.compare.out.accepted", label: "A movement the client can accept" },
      ],
      titleKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.compare.title",
      titleDefault: "Compare the classes and say what moved the number",
      whatKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.compare.what",
      whatDefault:
        "Report the newer estimate against the earlier one element by element, separating what moved because the design changed, what moved because the market moved, and what moved because an allowance was released.",
      whyKey: "cases.walk_the_estimate_from_class_d_to_class_a.step.compare.why",
      whyDefault:
        "When a Class B replaces a Class C the client asks one question, which is why the number changed. An answer split into design, market and allowance is a conversation about the project. A single variance figure is an accusation looking for somebody to attach itself to.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
