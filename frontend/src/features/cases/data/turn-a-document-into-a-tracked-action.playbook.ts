// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Turn a document into a tracked action".
//
// A letter, an RFI or a captured message becomes a task that carries its
// source with it, so the work is owned and the origin stays readable months
// later. Content strings are key plus inline English default and live only
// here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "turn-a-document-into-a-tracked-action",
  order: 1041,
  category: "site",
  companyTypes: ["general-contractor", "subcontractor", "project-manager"],
  roles: ["document-controller", "project-manager"],
  icon: "ClipboardList",
  titleKey: "cases.turn_a_document_into_a_tracked_action.title",
  titleDefault: "Turn a document into a tracked action",
  descKey: "cases.turn_a_document_into_a_tracked_action.desc",
  descDefault:
    "Spot the letter, RFI or captured message that is asking for something to be done rather than filed, raise a task straight off it that keeps the title, the date and the link back, then work it with the source still attached.",
  longDescKey: "cases.turn_a_document_into_a_tracked_action.longdesc",
  longDescDefault:
    "Documents arrive all day and most of them only need reading. The few that need doing get lost in the same pile, and the usual fix, someone retyping a task from a letter, drops the reference number and rounds the date to next week. Creating the task from the source keeps both, and the task then carries a badge showing which document it grew from, which is what makes the question asked six months later a one-click answer.",
  estMinutes: 8,
  steps: [
    {
      id: "find",
      icon: "MessageSquare",
      inputs: [
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.find.in.items",
          label: "Letters, RFIs and captures",
        },
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.find.in.dates",
          label: "Response-required dates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.find.out.item",
          label: "The item that needs doing",
        },
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.find.out.due",
          label: "The date it carries",
        },
      ],
      titleKey: "cases.turn_a_document_into_a_tracked_action.step.find.title",
      titleDefault: "Find the one that needs doing",
      whatKey: "cases.turn_a_document_into_a_tracked_action.step.find.what",
      whatDefault:
        "Go down the correspondence list, the RFIs or your inbound captures and pick out the item that is not asking for a reply but for something to happen on site. Note the response-required-by date it carries, because that is the date the task will inherit.",
      whyKey: "cases.turn_a_document_into_a_tracked_action.step.find.why",
      whyDefault:
        "Most documents need filing and a handful need doing, and telling those apart is the whole job. It is also the job that gets skipped at four on a Friday, which is how a letter with a fourteen-day deadline gets read properly on day fifteen.",
      moduleLabel: "Correspondence",
      moduleLabelKey: "correspondence.title",
      to: "/correspondence",
    },
    {
      id: "create",
      icon: "NotebookPen",
      inputs: [
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.create.in.source",
          label: "The source document",
        },
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.create.in.prefill",
          label: "Prefilled title and date",
        },
      ],
      outputs: [
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.create.out.task",
          label: "Task in the list",
        },
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.create.out.link",
          label: "Recorded link to the source",
        },
      ],
      titleKey: "cases.turn_a_document_into_a_tracked_action.step.create.title",
      titleDefault: "Create the task from the source",
      whatKey: "cases.turn_a_document_into_a_tracked_action.step.create.what",
      whatDefault:
        "Use Create task on the item itself. It prefills the title from the subject, a description pointing back at the record, the due date from the response-required-by date and an assignee where one can be worked out. Adjust what needs adjusting, submit, and the task lands in the tasks list with its origin recorded.",
      whyKey: "cases.turn_a_document_into_a_tracked_action.step.create.why",
      whyDefault:
        "Retyping a task out of a letter is where the reference number goes missing and the deadline quietly becomes next Friday. Creating it from the source keeps both, and keeps the letter and the task as one piece of work rather than two records nobody ever links back together.",
      moduleLabel: "Tasks",
      moduleLabelKey: "tasks.title",
      to: "/tasks",
    },
    {
      id: "close",
      icon: "CheckCircle2",
      inputs: [
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.close.in.task",
          label: "Open task",
        },
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.close.in.badge",
          label: "Source badge",
        },
      ],
      outputs: [
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.close.out.done",
          label: "Completed task",
        },
        {
          labelKey: "cases.turn_a_document_into_a_tracked_action.step.close.out.trace",
          label: "Traceable to the document",
        },
      ],
      titleKey: "cases.turn_a_document_into_a_tracked_action.step.close.title",
      titleDefault: "Work it and keep the source attached",
      whatKey: "cases.turn_a_document_into_a_tracked_action.step.close.what",
      whatDefault:
        "Work the task from the list. It shows a badge naming the kind of document it came from, and the badge links back to the record, so whoever picks it up can read the original before they act. Close it only when the thing the document asked for is genuinely done.",
      whyKey: "cases.turn_a_document_into_a_tracked_action.step.close.why",
      whyDefault:
        "A task with no visible origin gets closed on somebody's guess about what it meant. Months later, when a client asks what was done about a particular letter, the badge is the difference between answering in a click and losing an afternoon in the archive.",
      moduleLabel: "Tasks",
      moduleLabelKey: "tasks.title",
      to: "/tasks",
    },
  ],
};

export default playbook;
