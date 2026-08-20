// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Build a parametric assembly".
//
// Give an assembly named parameters, drive its component quantities from
// formulas over them, prove the graph and the numbers before anyone relies on
// it, then price a bill position from one input. Content strings are key plus
// inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "build-a-parametric-assembly",
  order: 1044,
  category: "estimating",
  companyTypes: ["cost-consultant", "general-contractor", "subcontractor"],
  roles: ["estimator", "quantity-surveyor"],
  stage: "estimate",
  icon: "Calculator",
  titleKey: "cases.build_a_parametric_assembly.title",
  titleDefault: "Build a parametric assembly",
  descKey: "cases.build_a_parametric_assembly.desc",
  descDefault:
    "Give an assembly named parameters and drive its component quantities from formulas over them: enter the wall area when you apply it and let the reinforcement, the concrete and the composite rate follow.",
  longDescKey: "cases.build_a_parametric_assembly.longdesc",
  longDescDefault:
    "A fixed recipe rate holds its proportions but not its arithmetic, so when the wall changes every component quantity has to be re-derived by hand and one of them always gets missed. A parametric assembly states the relationship once, reinforcement as wall area times a ratio, checks the parameter graph as you write it, previews the exact quantity per line before and after, then prices a bill position from a single number the estimator types in.",
  estMinutes: 12,
  steps: [
    {
      id: "parameters",
      icon: "Calculator",
      inputs: [
        {
          labelKey: "cases.build_a_parametric_assembly.step.parameters.in.buildup",
          label: "Build-up you price repeatedly",
        },
        {
          labelKey: "cases.build_a_parametric_assembly.step.parameters.in.drivers",
          label: "What actually varies job to job",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_a_parametric_assembly.step.parameters.out.params",
          label: "Named parameters",
        },
        {
          labelKey:
            "cases.build_a_parametric_assembly.step.parameters.out.defaults",
          label: "Resolved default values",
        },
      ],
      titleKey: "cases.build_a_parametric_assembly.step.parameters.title",
      titleDefault: "Name the parameters",
      whatKey: "cases.build_a_parametric_assembly.step.parameters.what",
      whatDefault:
        "Give the assembly the few named parameters it really turns on. Each is one of three kinds: an input the estimator enters when they apply it, with a sensible default; a constant that does not move, such as a rebar ratio; or a calculated value derived from the others, such as area from length times height.",
      whyKey: "cases.build_a_parametric_assembly.step.parameters.why",
      whyDefault:
        "The parameters are the questions the assembly asks whoever uses it, so keep them to the ones that genuinely change between jobs. Every extra input is another figure somebody has to be right about at half past five on the day the tender goes in.",
      moduleLabel: "Assemblies",
      moduleLabelKey: "nav.assemblies",
      to: "/assemblies",
    },
    {
      id: "formulas",
      icon: "Pencil",
      inputs: [
        {
          labelKey: "cases.build_a_parametric_assembly.step.formulas.in.params",
          label: "Named parameters",
        },
        {
          labelKey: "cases.build_a_parametric_assembly.step.formulas.in.components",
          label: "Component lines",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_a_parametric_assembly.step.formulas.out.formulas",
          label: "Quantity formulas",
        },
        {
          labelKey: "cases.build_a_parametric_assembly.step.formulas.out.marked",
          label: "Computed lines marked fx",
        },
      ],
      titleKey: "cases.build_a_parametric_assembly.step.formulas.title",
      titleDefault: "Drive the quantities from a formula",
      whatKey: "cases.build_a_parametric_assembly.step.formulas.what",
      whatDefault:
        "Set a component's quantity from a formula over the parameters instead of a fixed number, the reinforcement as wall area times the rebar ratio, the formwork as area times a double-sided factor. Any line whose quantity is computed carries an fx marker on it.",
      whyKey: "cases.build_a_parametric_assembly.step.formulas.why",
      whyDefault:
        "A fixed recipe makes you re-derive the steel by hand every time the wall moves. Written as a formula the relationship is stated once, so the ratio you agreed with the engineer is the ratio in every priced line, and the fx marker stops anyone reading a derived quantity as one that was measured.",
      moduleLabel: "Assemblies",
      moduleLabelKey: "nav.assemblies",
      to: "/assemblies",
    },
    {
      id: "prove",
      icon: "Gauge",
      inputs: [
        {
          labelKey: "cases.build_a_parametric_assembly.step.prove.in.assembly",
          label: "Draft parametric assembly",
        },
        {
          labelKey: "cases.build_a_parametric_assembly.step.prove.in.values",
          label: "Values you expect on the job",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_a_parametric_assembly.step.prove.out.errors",
          label: "Named errors, if any",
        },
        {
          labelKey: "cases.build_a_parametric_assembly.step.prove.out.preview",
          label: "Before and after per line",
        },
      ],
      titleKey: "cases.build_a_parametric_assembly.step.prove.title",
      titleDefault: "Prove it before anyone uses it",
      whatKey: "cases.build_a_parametric_assembly.step.prove.what",
      whatDefault:
        "The editor checks the parameter graph as you work and flags problems inline against the parameter or component they belong to: a name referenced but never defined, two parameters sharing a name, a formula that will not parse, a cycle where two calculated values depend on each other. Then run the expansion preview at real values and read the quantity each line moves from and to, plus the rolled-up rate the server will write.",
      whyKey: "cases.build_a_parametric_assembly.step.prove.why",
      whyDefault:
        "A cycle or a stale reference does not announce itself in a spreadsheet, it just returns a number that looks plausible. Previewing at values you actually expect is what catches a formula that is right in principle and out by a factor of ten, and because the preview runs on the same decimal arithmetic as the live expansion, the rate you read here is the rate that lands, exact to the cent.",
      moduleLabel: "Assemblies",
      moduleLabelKey: "nav.assemblies",
      to: "/assemblies",
    },
    {
      id: "apply",
      icon: "ListChecks",
      inputs: [
        {
          labelKey: "cases.build_a_parametric_assembly.step.apply.in.assembly",
          label: "Proven assembly",
        },
        {
          labelKey: "cases.build_a_parametric_assembly.step.apply.in.input",
          label: "Wall area for this element",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_a_parametric_assembly.step.apply.out.line",
          label: "Priced bill position",
        },
        {
          labelKey: "cases.build_a_parametric_assembly.step.apply.out.components",
          label: "Components at computed quantities",
        },
      ],
      titleKey: "cases.build_a_parametric_assembly.step.apply.title",
      titleDefault: "Apply it to the bill",
      whatKey: "cases.build_a_parametric_assembly.step.apply.what",
      whatDefault:
        "Place the assembly on a bill position and enter the one figure it asks for, the wall area for that element. The components expand at those values and the composite rate follows, with nobody retyping a quantity.",
      whyKey: "cases.build_a_parametric_assembly.step.apply.why",
      whyDefault:
        "This is where the parametric version earns its keep over a fixed recipe. When the wall grows at the next design issue you change one input rather than eleven component quantities, and the two or three that would quietly have been forgotten move with the rest.",
      moduleLabel: "Bill of Quantities",
      moduleLabelKey: "boq.title",
      to: "/boq",
    },
  ],
};

export default playbook;
