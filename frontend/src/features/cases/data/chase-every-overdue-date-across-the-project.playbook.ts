// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Chase every overdue date in one place".
//
// The cross-module deadline register gathers the due dates each module tracks
// on its own, the sweep tells the owners and escalates what has gone stale,
// and the worst item becomes a tracked action. Content strings are key plus
// inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "chase-every-overdue-date-across-the-project",
  order: 1040,
  category: "site",
  companyTypes: ["general-contractor", "project-manager", "developer-client"],
  roles: ["project-manager", "contract-administrator"],
  icon: "CalendarClock",
  titleKey: "cases.chase_every_overdue_date_across_the_project.title",
  titleDefault: "Chase every overdue date in one place",
  descKey: "cases.chase_every_overdue_date_across_the_project.desc",
  descDefault:
    "Pull every due date the platform tracks into a single register, see what is genuinely late rather than what feels late, let the sweep tell the owners, and turn the worst one into a task somebody owns.",
  longDescKey: "cases.chase_every_overdue_date_across_the_project.longdesc",
  longDescDefault:
    "Correspondence knows its response deadlines. The quality register knows when a corrective action was due. The punch list knows which items have sat open since the last walk. None of them knows about the others, which is how a project ends up late on four fronts while every individual list still looks manageable. The register is the one view that adds them up, and the sweep is what stops the reading being purely academic.",
  estMinutes: 9,
  steps: [
    {
      id: "register",
      icon: "ListChecks",
      inputs: [
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.register.in.dates",
          label: "Due dates across modules",
        },
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.register.in.filter",
          label: "Overdue filter",
        },
      ],
      outputs: [
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.register.out.list",
          label: "One overdue register",
        },
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.register.out.days",
          label: "Days late on each item",
        },
      ],
      titleKey: "cases.chase_every_overdue_date_across_the_project.step.register.title",
      titleDefault: "See what is actually late",
      whatKey: "cases.chase_every_overdue_date_across_the_project.step.register.what",
      whatDefault:
        "Open the deadline register and switch it to overdue. It gathers the dates each module already tracks, correspondence response deadlines, corrective actions off non-conformance reports, open punch items, and groups them by module with the days late on each, so you read one list instead of opening three.",
      whyKey: "cases.chase_every_overdue_date_across_the_project.step.register.why",
      whyDefault:
        "A project rarely slips in one obvious place. It slips a few days here and a week there, in registers nobody reads together, and by the time it is visible in the programme the reasons are two months old. One list turns a vague feeling that things are drifting into a count you can do something about this morning.",
      moduleLabel: "Deadlines",
      moduleLabelKey: "deadlines.title",
      to: "/deadlines",
    },
    {
      id: "sweep",
      icon: "Send",
      inputs: [
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.sweep.in.items",
          label: "Overdue items",
        },
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.sweep.in.owners",
          label: "Owners and managers",
        },
      ],
      outputs: [
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.sweep.out.notified",
          label: "Owners told",
        },
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.sweep.out.escalated",
          label: "Escalations past the grace window",
        },
      ],
      titleKey: "cases.chase_every_overdue_date_across_the_project.step.sweep.title",
      titleDefault: "Let the sweep tell the owners",
      whatKey: "cases.chase_every_overdue_date_across_the_project.step.sweep.what",
      whatDefault:
        "The overdue sweep runs across the same register and pushes a reminder to whoever owns each late item. Once an item has sat past the grace window it escalates to the project managers, once and only once, and the register shows you what it moved.",
      whyKey: "cases.chase_every_overdue_date_across_the_project.step.sweep.why",
      whyDefault:
        "Very little slips because somebody decided to ignore it. It slips because nobody told them it was theirs. Escalating on a grace window rather than on day one is what keeps the escalation worth reading, because a manager copied into everything reads none of it.",
      moduleLabel: "Deadlines",
      moduleLabelKey: "deadlines.title",
      to: "/deadlines",
    },
    {
      id: "action",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.action.in.worst",
          label: "The worst overdue item",
        },
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.action.in.owner",
          label: "A named owner",
        },
      ],
      outputs: [
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.action.out.task",
          label: "Task with an owner and a date",
        },
        {
          labelKey: "cases.chase_every_overdue_date_across_the_project.step.action.out.cleared",
          label: "Register entry cleared",
        },
      ],
      titleKey: "cases.chase_every_overdue_date_across_the_project.step.action.title",
      titleDefault: "Turn the worst one into a tracked action",
      whatKey: "cases.chase_every_overdue_date_across_the_project.step.action.what",
      whatDefault:
        "Take the item sitting at the top of the overdue list and raise a task against it with a named owner and a date you actually believe. Work it until the underlying record closes, at which point the entry drops out of the register on its own.",
      whyKey: "cases.chase_every_overdue_date_across_the_project.step.action.why",
      whyDefault:
        "A reminder tells somebody a date has passed. It does not tell them what to do next, and the ones that have gone badly overdue are usually the ones where that is not obvious. The register only shortens when the source record closes, so the task has to point at the real work rather than at the reminder about it.",
      moduleLabel: "Tasks",
      moduleLabelKey: "tasks.title",
      to: "/tasks",
    },
  ],
};

export default playbook;
