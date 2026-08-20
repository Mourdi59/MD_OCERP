// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Register source data before it blocks the schedule".
//
// Register the source documents a project depends on, verify them, see which
// ones are expiring or missing against the programme, and clear the blockers
// before they stop work. Content strings are key plus inline English default
// and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "register-source-data-before-it-blocks-the-schedule",
  order: 1033,
  category: "planning",
  companyTypes: ["project-manager", "designer", "general-contractor"],
  roles: ["planner", "document-controller", "project-manager"],
  stage: "plan",
  icon: "DatabaseZap",
  titleKey: "cases.register_source_data_before_it_blocks_the_schedule.title",
  titleDefault: "Register source data before it blocks the schedule",
  descKey: "cases.register_source_data_before_it_blocks_the_schedule.desc",
  descDefault:
    "Register the source documents the project depends on, verify them, see what is expiring or missing against the programme, and clear the blockers before they stop work.",
  longDescKey: "cases.register_source_data_before_it_blocks_the_schedule.longdesc",
  longDescDefault:
    "A survey that expired last month or a report nobody chased is invisible until the activity that needs it is due to start. Registering source data as a live list, checked against the schedule, is what surfaces the gap while there is still time to close it.",
  estMinutes: 9,
  steps: [
    {
      id: "register",
      icon: "ListPlus",
      inputs: [
        {
          labelKey:
            "cases.register_source_data_before_it_blocks_the_schedule.step.register.in.documents",
          label: "Surveys and reports",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.register_source_data_before_it_blocks_the_schedule.step.register.out.entries",
          label: "Registered source data",
        },
      ],
      titleKey: "cases.register_source_data_before_it_blocks_the_schedule.step.register.title",
      titleDefault: "Register the source documents",
      whatKey: "cases.register_source_data_before_it_blocks_the_schedule.step.register.what",
      whatDefault:
        "Log every survey, report, consent and reference document the project relies on, with its source, its date and the date it stops being valid.",
      whyKey: "cases.register_source_data_before_it_blocks_the_schedule.step.register.why",
      whyDefault:
        "A document that only lives on someone's laptop is a document the rest of the team is working blind without. Registering it is what makes it something the whole project can rely on and check.",
      moduleLabel: "Source Data",
      moduleLabelKey: "source_data.title",
      to: "/projects/:projectId/source-data",
    },
    {
      id: "verify",
      icon: "BadgeCheck",
      inputs: [
        {
          labelKey:
            "cases.register_source_data_before_it_blocks_the_schedule.step.verify.in.entries",
          label: "Registered source data",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.register_source_data_before_it_blocks_the_schedule.step.verify.out.status",
          label: "Verification status",
        },
      ],
      titleKey: "cases.register_source_data_before_it_blocks_the_schedule.step.verify.title",
      titleDefault: "Verify each item",
      whatKey: "cases.register_source_data_before_it_blocks_the_schedule.step.verify.what",
      whatDefault:
        "Check each registered item is complete, current and from a source the team trusts, and mark it verified so anyone downstream knows it is safe to design or build against.",
      whyKey: "cases.register_source_data_before_it_blocks_the_schedule.step.verify.why",
      whyDefault:
        "A registered document is not the same as a trustworthy one. Verifying it once, up front, is cheaper than a design team discovering the ground survey was preliminary after they have already built on it.",
      moduleLabel: "Source Data",
      moduleLabelKey: "source_data.title",
      to: "/projects/:projectId/source-data",
    },
    {
      id: "check-schedule",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.register_source_data_before_it_blocks_the_schedule.step.check-schedule.in.status",
          label: "Verification status",
        },
        {
          labelKey:
            "cases.register_source_data_before_it_blocks_the_schedule.step.check-schedule.in.activities",
          label: "Upcoming activities",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.register_source_data_before_it_blocks_the_schedule.step.check-schedule.out.blockers",
          label: "Blocking gaps",
        },
      ],
      titleKey: "cases.register_source_data_before_it_blocks_the_schedule.step.check-schedule.title",
      titleDefault: "See what is expiring or missing against the programme",
      whatKey: "cases.register_source_data_before_it_blocks_the_schedule.step.check-schedule.what",
      whatDefault:
        "Compare the source data record against the schedule to find the item expiring before the activity that needs it starts, and the activity with no source data behind it at all.",
      whyKey: "cases.register_source_data_before_it_blocks_the_schedule.step.check-schedule.why",
      whyDefault:
        "The cost of a missing document is not the document, it is the crew standing idle on the day the activity was due to start. Checking against the programme is what turns a filing gap into a schedule risk you can actually see.",
      moduleLabel: "4D Schedule",
      moduleLabelKey: "nav.schedule",
      to: "/schedule",
    },
    {
      id: "clear",
      icon: "CircleCheckBig",
      inputs: [
        {
          labelKey:
            "cases.register_source_data_before_it_blocks_the_schedule.step.clear.in.blockers",
          label: "Blocking gaps",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.register_source_data_before_it_blocks_the_schedule.step.clear.out.cleared",
          label: "Cleared blockers",
        },
      ],
      titleKey: "cases.register_source_data_before_it_blocks_the_schedule.step.clear.title",
      titleDefault: "Clear the blockers",
      whatKey: "cases.register_source_data_before_it_blocks_the_schedule.step.clear.what",
      whatDefault:
        "Chase the missing or expiring items with enough lead time to renew, reorder or reissue them before the activity that depends on them is due.",
      whyKey: "cases.register_source_data_before_it_blocks_the_schedule.step.clear.why",
      whyDefault:
        "Finding the gap early is only useful if someone closes it. Clearing each blocker against its deadline is what keeps the source data list from becoming a list of excuses after the fact.",
      moduleLabel: "Source Data",
      moduleLabelKey: "source_data.title",
      to: "/projects/:projectId/source-data",
    },
  ],
};

export default playbook;
