// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Keep the libro de ordenes the direccion facultativa writes in" (ES).
//
// On a Spanish site the direccion facultativa issues its instructions in the
// libro de ordenes y asistencias, and the contractor signs them. The
// supervision register models exactly that act: a visit, and entries typed as
// an instruction, a deviation, a hidden-works acceptance or a motivated
// refusal, each with a status that has to be closed. The two things a paper
// libro does badly are what the case spends its later steps on: pairing the
// order with the contractor's own record of the same day, and turning an order
// that changes the work into a priced modificado instead of an argument.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "keep-the-libro-de-ordenes-on-site",
  order: 1144,
  region: "ES",
  category: "site",
  companyTypes: ["general-contractor", "designer", "project-manager"],
  roles: ["site-manager", "design-lead", "contract-administrator"],
  icon: "NotebookPen",
  titleKey: "cases.keep_the_libro_de_ordenes_on_site.title",
  titleDefault: "Keep the libro de ordenes the direccion facultativa writes in",
  descKey: "cases.keep_the_libro_de_ordenes_on_site.desc",
  descDefault:
    "Record the visit, write each order as what it actually is, pair it with the contractor's own record of that day, and send the ones that change the work into a priced modificado rather than into a conversation.",
  longDescKey: "cases.keep_the_libro_de_ordenes_on_site.longdesc",
  longDescDefault:
    "The libro de ordenes y asistencias is the direccion facultativa's channel to the contractor and it is contractual: an order written in it is an instruction, and the contractor signs to say it was received. Kept on paper it does two jobs badly. Nothing links an order to the state of the works on the day it was given, so a dispute about whether the work had already been built that way is one memory against another. And an order that plainly changes the scope sits in the book as an order, with no price on it, until somebody months later argues it was always included. Recording orders in a register that carries their type, their status and a reference to the change they feed closes both gaps while the site is still open.",
  estMinutes: 14,
  steps: [
    {
      id: "visit",
      icon: "MapPin",
      inputs: [
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.visit.in.works",
          label: "Works in progress",
        },
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.visit.in.drawings",
          label: "Approved drawings and specification",
        },
      ],
      outputs: [
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.visit.out.visit",
          label: "Dated site visit record",
        },
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.visit.out.attendees",
          label: "Attendance record by discipline",
        },
      ],
      titleKey: "cases.keep_the_libro_de_ordenes_on_site.step.visit.title",
      titleDefault: "Open the visit before you write anything",
      whatKey: "cases.keep_the_libro_de_ordenes_on_site.step.visit.what",
      whatDefault:
        "Record the visit itself: the date, who attended and in which discipline they attended. Every order written that day hangs off it, so the visit is the container rather than the paperwork.",
      whyKey: "cases.keep_the_libro_de_ordenes_on_site.step.visit.why",
      whyDefault:
        "An instruction with no visit behind it is an instruction nobody can place. Which arquitecto tecnico was there, and whether the structural engineer was, decides later whether an order about reinforcement was given by somebody entitled to give it.",
      moduleLabel: "Site Supervision",
      moduleLabelKey: "site_supervision.title",
      to: "/projects/:projectId/site-supervision",
    },
    {
      id: "order",
      icon: "PenTool",
      inputs: [
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.order.in.visit",
          label: "Open site visit record",
        },
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.order.in.observed",
          label: "What was observed on site",
        },
      ],
      outputs: [
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.order.out.entry",
          label: "Numbered order in the register",
        },
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.order.out.required",
          label: "Required action and its status",
        },
      ],
      titleKey: "cases.keep_the_libro_de_ordenes_on_site.step.order.title",
      titleDefault: "Write each order as the kind of thing it is",
      whatKey: "cases.keep_the_libro_de_ordenes_on_site.step.order.what",
      whatDefault:
        "Enter each observation under its own number and say which kind it is: work confirmed as conforming, a deviation from the project, an acceptance of work about to be covered up, an instruction to do something, or a reasoned refusal. Name the element, the location and the action required.",
      whyKey: "cases.keep_the_libro_de_ordenes_on_site.step.order.why",
      whyDefault:
        "The type is what decides who has to do what next, and it is the thing free prose loses. A hidden-works acceptance that reads like a general comment is an acceptance nobody can find once the slab is poured, and that is exactly the record everybody wants when the slab is opened again.",
      moduleLabel: "Site Supervision",
      moduleLabelKey: "site_supervision.title",
      to: "/projects/:projectId/site-supervision",
    },
    {
      id: "diary",
      icon: "CalendarDays",
      inputs: [
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.diary.in.entry",
          label: "Order given that day",
        },
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.diary.in.site",
          label: "Site labour, plant and weather",
        },
      ],
      outputs: [
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.diary.out.diary",
          label: "Daily diary record",
        },
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.diary.out.matched",
          label: "Order matched to the day's works",
        },
      ],
      titleKey: "cases.keep_the_libro_de_ordenes_on_site.step.diary.title",
      titleDefault: "Pair the order with the day it was given",
      whatKey: "cases.keep_the_libro_de_ordenes_on_site.step.diary.what",
      whatDefault:
        "On the same day, record in the diary what was on site: which trades, how many, what plant, the weather and what was actually built. Note the order reference in it so the two records point at each other.",
      whyKey: "cases.keep_the_libro_de_ordenes_on_site.step.diary.why",
      whyDefault:
        "An order to stop and rework is worth whatever the stop cost, and that cost is in the diary rather than in the order. Six months later the two together are evidence; the order on its own is a sentence, and the diary on its own is a page of crew numbers nobody can attribute to anything.",
      moduleLabel: "Daily Diary",
      moduleLabelKey: "nav.daily_diary",
      to: "/projects/:projectId/daily-diary",
    },
    {
      id: "change",
      icon: "GitCompare",
      inputs: [
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.change.in.instruction",
          label: "Instruction that changes the work",
        },
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.change.in.rates",
          label: "Contract rates and quantities",
        },
      ],
      outputs: [
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.change.out.variation",
          label: "Priced variation raised",
        },
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.change.out.linked",
          label: "Order linked to the change record",
        },
      ],
      titleKey: "cases.keep_the_libro_de_ordenes_on_site.step.change.title",
      titleDefault: "Send the ones that change the work to be priced",
      whatKey: "cases.keep_the_libro_de_ordenes_on_site.step.change.what",
      whatDefault:
        "An instruction or a deviation that alters the scope becomes a variation, priced from the contract rates where they reach and from a new descompuesto where they do not, with the order reference carried on it.",
      whyKey: "cases.keep_the_libro_de_ordenes_on_site.step.change.why",
      whyDefault:
        "Orders that change the work and never get priced are the single largest source of unpaid work on a Spanish job, and they are never denied at the time. They are denied at the end, when the only argument left is what somebody meant, and the reference from the order to the priced change is what stops that argument existing.",
      moduleLabel: "Variations",
      moduleLabelKey: "nav.variations",
      to: "/projects/:projectId/variations",
    },
    {
      id: "review",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.review.in.entries",
          label: "Orders open and closed",
        },
      ],
      outputs: [
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.review.out.report",
          label: "Report of open orders",
        },
        {
          labelKey: "cases.keep_the_libro_de_ordenes_on_site.step.review.out.agenda",
          label: "Agenda for the next site meeting",
        },
      ],
      titleKey: "cases.keep_the_libro_de_ordenes_on_site.step.review.title",
      titleDefault: "Take the open orders to the monthly meeting",
      whatKey: "cases.keep_the_libro_de_ordenes_on_site.step.review.what",
      whatDefault:
        "Report the orders still open, how long each has been open and who owes the next move, and take that list into the site meeting instead of reading the whole register out.",
      whyKey: "cases.keep_the_libro_de_ordenes_on_site.step.review.why",
      whyDefault:
        "An order nobody chases is closed by the passage of time, and both sides read that silence in their own favour. A short list of what is still open, tabled once a month, closes most of them without any escalation at all, and the ones that do not close are the real disputes rather than the forgotten ones.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
