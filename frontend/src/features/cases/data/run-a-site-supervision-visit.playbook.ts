// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run a site supervision visit".
//
// Plan and conduct a supervision visit, log observations and flag hidden
// works that need inspecting before they are covered, compare plan against
// what was actually built, and turn a finding into a tracked change.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "run-a-site-supervision-visit",
  order: 1035,
  category: "site",
  companyTypes: ["general-contractor", "project-manager", "subcontractor"],
  roles: ["site-manager", "project-manager"],
  stage: "build",
  icon: "ClipboardCheck",
  titleKey: "cases.run_a_site_supervision_visit.title",
  titleDefault: "Run a site supervision visit",
  descKey: "cases.run_a_site_supervision_visit.desc",
  descDefault:
    "Plan and conduct a supervision visit, log observations and flag hidden works to inspect before they are covered, compare plan against actual, and report the visit.",
  longDescKey: "cases.run_a_site_supervision_visit.longdesc",
  longDescDefault:
    "A supervision visit that produces only a memory is a visit that could not have happened. Planning the visit against what should be checked, logging what is actually found, and reporting the gap is what turns a walk around the site into evidence the work was properly overseen.",
  estMinutes: 11,
  steps: [
    {
      id: "plan-visit",
      icon: "CalendarCheck",
      inputs: [
        {
          labelKey: "cases.run_a_site_supervision_visit.step.plan-visit.in.programme",
          label: "Programme of works",
        },
        {
          labelKey: "cases.run_a_site_supervision_visit.step.plan-visit.in.checkpoints",
          label: "Hold and witness points",
        },
      ],
      outputs: [
        {
          labelKey: "cases.run_a_site_supervision_visit.step.plan-visit.out.plan",
          label: "Visit plan",
        },
      ],
      titleKey: "cases.run_a_site_supervision_visit.step.plan-visit.title",
      titleDefault: "Plan the visit",
      whatKey: "cases.run_a_site_supervision_visit.step.plan-visit.what",
      whatDefault:
        "Set the areas and activities the visit will cover, including any hold or witness point that must be seen before work continues past it.",
      whyKey: "cases.run_a_site_supervision_visit.step.plan-visit.why",
      whyDefault:
        "A visit with no plan turns into whatever is visible on the day, and hidden works that needed checking get covered before anyone thought to look. Planning against the programme is what catches the point before it is missed.",
      moduleLabel: "Site Supervision",
      moduleLabelKey: "site_supervision.title",
      to: "/projects/:projectId/site-supervision",
    },
    {
      id: "log-observations",
      icon: "Eye",
      inputs: [
        {
          labelKey: "cases.run_a_site_supervision_visit.step.log-observations.in.plan",
          label: "Visit plan",
        },
      ],
      outputs: [
        {
          labelKey: "cases.run_a_site_supervision_visit.step.log-observations.out.observations",
          label: "Logged observations",
        },
        {
          labelKey: "cases.run_a_site_supervision_visit.step.log-observations.out.flags",
          label: "Flagged hidden works",
        },
      ],
      titleKey: "cases.run_a_site_supervision_visit.step.log-observations.title",
      titleDefault: "Log observations and flag hidden works",
      whatKey: "cases.run_a_site_supervision_visit.step.log-observations.what",
      whatDefault:
        "Walk the visit plan, log what is found against each point with a photo where it matters, and flag any work that is about to be covered and still needs inspecting first.",
      whyKey: "cases.run_a_site_supervision_visit.step.log-observations.why",
      whyDefault:
        "Once reinforcement is poured over or a duct is boxed in, the only proof of what was underneath is the record made before it disappeared. Flagging it in the moment is the only point that record can be made.",
      moduleLabel: "Site Supervision",
      moduleLabelKey: "site_supervision.title",
      to: "/projects/:projectId/site-supervision",
    },
    {
      id: "compare",
      icon: "GitCompare",
      inputs: [
        {
          labelKey: "cases.run_a_site_supervision_visit.step.compare.in.observations",
          label: "Logged observations",
        },
      ],
      outputs: [
        {
          labelKey: "cases.run_a_site_supervision_visit.step.compare.out.variances",
          label: "Plan-versus-actual variances",
        },
      ],
      titleKey: "cases.run_a_site_supervision_visit.step.compare.title",
      titleDefault: "Compare plan versus actual",
      whatKey: "cases.run_a_site_supervision_visit.step.compare.what",
      whatDefault:
        "Set what was actually observed against what the drawings and the programme said should be there, and pull out anywhere the two disagree.",
      whyKey: "cases.run_a_site_supervision_visit.step.compare.why",
      whyDefault:
        "A variance nobody names stays a verbal disagreement between the site and the office. Comparing plan against actual on the record is what turns it into something that can actually be resolved.",
      moduleLabel: "Site Supervision",
      moduleLabelKey: "site_supervision.title",
      to: "/projects/:projectId/site-supervision",
    },
    {
      id: "report-and-link",
      icon: "FileOutput",
      inputs: [
        {
          labelKey: "cases.run_a_site_supervision_visit.step.report-and-link.in.variances",
          label: "Plan-versus-actual variances",
        },
      ],
      outputs: [
        {
          labelKey: "cases.run_a_site_supervision_visit.step.report-and-link.out.report",
          label: "Visit report",
        },
        {
          labelKey: "cases.run_a_site_supervision_visit.step.report-and-link.out.change",
          label: "Change order raised",
        },
      ],
      titleKey: "cases.run_a_site_supervision_visit.step.report-and-link.title",
      titleDefault: "Report the visit and link a finding to a change",
      whatKey: "cases.run_a_site_supervision_visit.step.report-and-link.what",
      whatDefault:
        "Export the visit report for the record, and where a finding actually changes scope, cost or time, raise it as a change order linked straight back to the observation.",
      whyKey: "cases.run_a_site_supervision_visit.step.report-and-link.why",
      whyDefault:
        "A finding that stays a note on a visit report never gets priced or programmed. Linking it to a change order is what makes sure what was seen on site actually reaches the people who commit budget and time.",
      moduleLabel: "Change Orders",
      moduleLabelKey: "nav.changeorders",
      to: "/changeorders",
    },
  ],
};

export default playbook;
