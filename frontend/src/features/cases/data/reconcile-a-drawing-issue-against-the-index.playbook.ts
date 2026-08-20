// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Reconcile a drawing issue against the index".
//
// Take an issued sheet set in, diff it against the drawing index, then chase
// what never arrived and account for what turned up unannounced. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "reconcile-a-drawing-issue-against-the-index",
  order: 1045,
  category: "bim",
  companyTypes: ["general-contractor", "bim-consultant", "project-manager"],
  roles: ["document-controller", "bim-coordinator"],
  stage: "build",
  icon: "GitCompare",
  titleKey: "cases.reconcile_a_drawing_issue_against_the_index.title",
  titleDefault: "Reconcile a drawing issue against the index",
  descKey: "cases.reconcile_a_drawing_issue_against_the_index.desc",
  descDefault:
    "Diff an issued sheet set against the drawing index and see what is missing, what turned up unannounced and what is sitting at a revision the index does not expect, then chase the gaps with the numbers in hand.",
  longDescKey: "cases.reconcile_a_drawing_issue_against_the_index.longdesc",
  longDescDefault:
    "A drawing issue is normally accepted on trust: the covering note says forty-two sheets, somebody counts forty-two files and the set goes into the register. This case does the comparison properly. It normalises the sheet numbers first, so a set written A-101 and an index written A 101 still line up, then separates the three failures that actually cost money, the sheet that never came, the sheet nobody told you about, and the sheet that came at the wrong revision.",
  estMinutes: 8,
  steps: [
    {
      id: "intake",
      icon: "Upload",
      inputs: [
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.intake.in.issue",
          label: "Issued PDF set",
        },
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.intake.in.covering",
          label: "Covering transmittal",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.intake.out.sheets",
          label: "Individual numbered sheets",
        },
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.intake.out.revisions",
          label: "Revision read off each one",
        },
      ],
      titleKey:
        "cases.reconcile_a_drawing_issue_against_the_index.step.intake.title",
      titleDefault: "Take in the issued sheet set",
      whatKey:
        "cases.reconcile_a_drawing_issue_against_the_index.step.intake.what",
      whatDefault:
        "Load the issued set into the project files and split it into individual sheets, so each drawing lands as its own record with a number and a revision picked up from the title block rather than sitting inside a two hundred page file.",
      whyKey: "cases.reconcile_a_drawing_issue_against_the_index.step.intake.why",
      whyDefault:
        "You cannot reconcile a bundle. Until the issue is broken into numbered sheets the only way to answer whether A-114 arrived is for somebody to scroll, and nobody scrolls the same set twice, which is how a missing sheet survives three weeks of everybody assuming it is in there.",
      moduleLabel: "Documents",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
    {
      id: "reconcile",
      icon: "GitCompare",
      inputs: [
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.reconcile.in.sheets",
          label: "Sheets you actually hold",
        },
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.reconcile.in.index",
          label: "Drawing index or issue register",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.reconcile.out.missing",
          label: "Missing and extra lists",
        },
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.reconcile.out.mismatch",
          label: "Revision mismatches",
        },
      ],
      titleKey:
        "cases.reconcile_a_drawing_issue_against_the_index.step.reconcile.title",
      titleDefault: "Reconcile it against the index",
      whatKey:
        "cases.reconcile_a_drawing_issue_against_the_index.step.reconcile.what",
      whatDefault:
        "Point the completeness check at the index, either the index PDF the designer issued or a sheet list pasted straight in, and run it. It reports what the index expects and you do not hold, what you hold and the index never mentioned, and what matched but at a different revision.",
      whyKey:
        "cases.reconcile_a_drawing_issue_against_the_index.step.reconcile.why",
      whyDefault:
        "Sheet numbers get written a dozen ways across a project, A-101, A 101, a.101, so ticking two lists off by eye reliably misses the ones that differ only by a hyphen. The check collapses those differences before it compares, which is why it finds gaps a careful person reading the same two lists will not.",
      moduleLabel: "Plan Room",
      moduleLabelKey: "nav.plan_room",
      to: "/plan-room",
    },
    {
      id: "chase",
      icon: "Send",
      inputs: [
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.chase.in.missing",
          label: "Missing sheet numbers",
        },
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.chase.in.log",
          label: "Transmittal log",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.chase.out.request",
          label: "Request naming each sheet",
        },
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.chase.out.trail",
          label: "Dated chase trail",
        },
      ],
      titleKey:
        "cases.reconcile_a_drawing_issue_against_the_index.step.chase.title",
      titleDefault: "Chase what never arrived",
      whatKey: "cases.reconcile_a_drawing_issue_against_the_index.step.chase.what",
      whatDefault:
        "Check the missing list against the transmittal record first, to be sure the sheets were genuinely never issued rather than mislaid on your side, then go back to the issuer with the exact numbers and the revision each one should be at.",
      whyKey: "cases.reconcile_a_drawing_issue_against_the_index.step.chase.why",
      whyDefault:
        "A designer answers we sent everything in one line, and answers a list of eleven sheet numbers in a day. Naming the gap precisely, against the transmittal that was meant to carry it, turns a fortnight of email into a short conversation, and leaves a dated trail if the missing sheet later costs somebody a week.",
      moduleLabel: "Transmittals",
      moduleLabelKey: "transmittals.title",
      to: "/files/transmittals",
    },
    {
      id: "account",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.account.in.extra",
          label: "Extra sheets and mismatches",
        },
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.account.in.register",
          label: "Drawing register",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.account.out.registered",
          label: "Everything registered",
        },
        {
          labelKey:
            "cases.reconcile_a_drawing_issue_against_the_index.step.account.out.agreed",
          label: "Agreed current revision",
        },
      ],
      titleKey:
        "cases.reconcile_a_drawing_issue_against_the_index.step.account.title",
      titleDefault: "Account for what arrived unannounced",
      whatKey:
        "cases.reconcile_a_drawing_issue_against_the_index.step.account.what",
      whatDefault:
        "Work the other two lists. Register the sheets that came in outside the index so they stop being invisible, and for every revision mismatch settle which side is behind, the index or the set, before anyone builds from either.",
      whyKey:
        "cases.reconcile_a_drawing_issue_against_the_index.step.account.why",
      whyDefault:
        "An extra sheet is usually one somebody issued without updating the index, which makes it the drawing nobody is tracking. A revision mismatch is worse, because both parties are certain they hold the current sheet and one of them is pricing or pouring to geometry that has already moved.",
      moduleLabel: "Documents",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
  ],
};

export default playbook;
