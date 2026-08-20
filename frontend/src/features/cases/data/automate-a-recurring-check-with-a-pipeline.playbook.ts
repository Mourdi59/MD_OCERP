// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Automate a check you keep doing by hand".
//
// Build a recurring quality check once in the pipeline builder, from a shipped
// template, lint it so no step is wired to nothing, and leave it saved for the
// next person. Content strings are key plus inline English default and live
// only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "automate-a-recurring-check-with-a-pipeline",
  order: 1038,
  category: "quality",
  companyTypes: ["general-contractor", "cost-consultant", "bim-consultant"],
  roles: ["bim-coordinator", "quantity-surveyor"],
  icon: "Workflow",
  titleKey: "cases.automate_a_recurring_check_with_a_pipeline.title",
  titleDefault: "Automate a check you keep doing by hand",
  descKey: "cases.automate_a_recurring_check_with_a_pipeline.desc",
  descDefault:
    "Take the check you run manually every week, build it once as a pipeline from a ready-made template, lint it so nothing is quietly wired to nothing, and leave it in the library so it runs the same way every time.",
  longDescKey: "cases.automate_a_recurring_check_with_a_pipeline.longdesc",
  longDescDefault:
    "Every commercial team has two or three checks that live in somebody's head: scan for positions still at zero, look at what the ten biggest items are doing, make sure nothing goes out unvalidated. They get done well when that person has time and skipped when they do not. A pipeline is how that check stops depending on the person, and the templates exist so building it is an afternoon's work rather than a project.",
  estMinutes: 14,
  steps: [
    {
      id: "template",
      icon: "Boxes",
      inputs: [
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.template.in.check",
          label: "The check you do by hand",
        },
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.template.in.gallery",
          label: "Template gallery",
        },
      ],
      outputs: [
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.template.out.graph",
          label: "A graph that already runs",
        },
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.template.out.named",
          label: "Named pipeline",
        },
      ],
      titleKey: "cases.automate_a_recurring_check_with_a_pipeline.step.template.title",
      titleDefault: "Start from a template",
      whatKey: "cases.automate_a_recurring_check_with_a_pipeline.step.template.what",
      whatDefault:
        "Open the pipeline builder and take the ready-made graph closest to the check you do by hand: flag positions still at zero, list the costliest items, guard a budget ceiling, or gate an export behind validation. It lands on the canvas already wired and already runnable.",
      whyKey: "cases.automate_a_recurring_check_with_a_pipeline.step.template.why",
      whyDefault:
        "An empty canvas is where most automation ideas die, because the first hour goes on working out which port feeds which. Starting from a graph that runs on the first click means you begin by reading logic that works, and change it, rather than guessing at logic that does not.",
      moduleLabel: "Pipeline Builder",
      moduleLabelKey: "nav.pipelines",
      to: "/pipelines",
    },
    {
      id: "wire",
      icon: "Waypoints",
      inputs: [
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.wire.in.template",
          label: "Template graph",
        },
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.wire.in.data",
          label: "Your bill or catalog",
        },
      ],
      outputs: [
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.wire.out.bound",
          label: "Graph bound to real data",
        },
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.wire.out.thresholds",
          label: "Thresholds set for this job",
        },
      ],
      titleKey: "cases.automate_a_recurring_check_with_a_pipeline.step.wire.title",
      titleDefault: "Point it at your own data",
      whatKey: "cases.automate_a_recurring_check_with_a_pipeline.step.wire.what",
      whatDefault:
        "Swap the template's source for your own bill, catalog or validation findings, then set the numbers that matter on this job: the ceiling the budget guard trips at, the figure a threshold gate compares against. Add a computed column, a group and total, a rename or a fan-out where the shape does not quite fit, and a non-empty guard so an empty source stops the run instead of passing it.",
      whyKey: "cases.automate_a_recurring_check_with_a_pipeline.step.wire.why",
      whyDefault:
        "A template carries the logic, never your project's numbers. A ceiling left at the demo figure passes everything you feed it, which is worse than having no guard at all, because the run goes green and everyone believes a check was done.",
      moduleLabel: "Pipeline Builder",
      moduleLabelKey: "nav.pipelines",
      to: "/pipelines",
    },
    {
      id: "lint",
      icon: "AlertTriangle",
      inputs: [
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.lint.in.graph",
          label: "Wired graph",
        },
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.lint.in.ports",
          label: "Required inputs per node",
        },
      ],
      outputs: [
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.lint.out.clean",
          label: "Issue count at zero",
        },
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.lint.out.run",
          label: "A run with findings",
        },
      ],
      titleKey: "cases.automate_a_recurring_check_with_a_pipeline.step.lint.title",
      titleDefault: "Lint it, then run it",
      whatKey: "cases.automate_a_recurring_check_with_a_pipeline.step.lint.what",
      whatDefault:
        "Read the issue count before you press run. It flags any step whose required input has no incoming wire, and any node sitting on the canvas as an island with no wire at all. Clear those, run the pipeline, then read what each step actually did rather than just the final total.",
      whyKey: "cases.automate_a_recurring_check_with_a_pipeline.step.lint.why",
      whyDefault:
        "A step wired to nothing does not fail. It simply never runs, and the pipeline reports success while doing less than the canvas makes it look like it does. That is the failure worth hunting, because a green run is precisely what stops anyone looking again.",
      moduleLabel: "Pipeline Builder",
      moduleLabelKey: "nav.pipelines",
      to: "/pipelines",
    },
    {
      id: "act",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.act.in.findings",
          label: "Pipeline findings",
        },
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.act.in.positions",
          label: "The positions they point at",
        },
      ],
      outputs: [
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.act.out.fixed",
          label: "Corrected positions",
        },
        {
          labelKey: "cases.automate_a_recurring_check_with_a_pipeline.step.act.out.saved",
          label: "A check that now runs itself",
        },
      ],
      titleKey: "cases.automate_a_recurring_check_with_a_pipeline.step.act.title",
      titleDefault: "Act on what it found",
      whatKey: "cases.automate_a_recurring_check_with_a_pipeline.step.act.what",
      whatDefault:
        "Take the findings through into validation, fix the positions they point at, and save the workflow so it shows up in the picker next month instead of being rebuilt from memory.",
      whyKey: "cases.automate_a_recurring_check_with_a_pipeline.step.act.why",
      whyDefault:
        "Automation only pays back on the second run. A check that lives in one person's head gets skipped the week they are on leave, and on a long job that is reliably the week it would have caught something expensive.",
      moduleLabel: "Validation",
      moduleLabelKey: "nav.validation",
      to: "/validation",
    },
  ],
};

export default playbook;
