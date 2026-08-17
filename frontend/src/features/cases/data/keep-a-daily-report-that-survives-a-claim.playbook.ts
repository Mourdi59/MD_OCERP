// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Keep a daily report that survives a claim" (US).
//
// The objection this case answers is not "we do not keep reports", it is "one
// more system the foreman will not open". So the case is built around the
// minute-a-day path: today's report starts as yesterday's, hours are booked
// where they are already worked, and the record only has to be assembled once,
// at the moment it is needed, rather than reconstructed months later.
//
// The US-specific weight sits in two places. Federal work is reported against
// a calendar with no holes in it, so an unaccounted day is a finding rather
// than an omission, and equipment is reported as worked, idle and down rather
// than as a single presence flag. Content strings are key plus inline English
// default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "keep-a-daily-report-that-survives-a-claim",
  order: 1061,
  region: "US",
  category: "site",
  companyTypes: ["general-contractor", "subcontractor", "project-manager"],
  roles: ["site-manager", "foreman", "project-manager"],
  icon: "ClipboardList",
  titleKey: "cases.keep_a_daily_report_that_survives_a_claim.title",
  titleDefault: "Keep a daily report that survives a claim",
  descKey: "cases.keep_a_daily_report_that_survives_a_claim.desc",
  descDefault:
    "Write the day from yesterday's report, book the crew against cost codes, record equipment worked, idle and down, leave no day unaccounted for, and hand the finished record to the claim that needs it.",
  longDescKey: "cases.keep_a_daily_report_that_survives_a_claim.longdesc",
  longDescDefault:
    "A delay is argued eighteen months after the day it happened, from whatever was written down at the time. Nothing written later carries the same weight, and nothing written at the time carries any weight at all if the calendar around it has holes. This case runs the daily record as a one-minute habit rather than a reporting exercise: the day opens as a copy of yesterday, the hours are booked where the crew already books them, plant is reported in the three states a federal report asks for, and the run of days is closed so that no reader can point at a gap. The pay-off is at the end, where the record is handed to a claim already assembled instead of being reconstructed from memory and phone photos.",
  estMinutes: 16,
  steps: [
    {
      id: "today",
      icon: "CalendarDays",
      inputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.today.in.yesterday", label: "Yesterday's report" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.today.in.crew", label: "Who turned up today" },
      ],
      outputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.today.out.report", label: "Today's report, written" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.today.out.stamp", label: "Author and time on record" },
      ],
      titleKey: "cases.keep_a_daily_report_that_survives_a_claim.step.today.title",
      titleDefault: "Start today's report from yesterday's, not from a blank page",
      whatKey: "cases.keep_a_daily_report_that_survives_a_claim.step.today.what",
      whatDefault:
        "Open the site diary and create today from the previous day. The crews, areas and activities carry over, so the work is editing what changed rather than typing the whole day again: who is on which area, what got done, what stopped.",
      whyKey: "cases.keep_a_daily_report_that_survives_a_claim.step.today.why",
      whyDefault:
        "A blank form at the end of a long day gets three words in it. A form that already reads like yesterday gets corrected, and a corrected form is a real record. This is the whole difference between a diary that is kept and one that exists in the contract only.",
      moduleLabel: "Daily Diary",
      moduleLabelKey: "nav.daily_diary",
      to: "/projects/:projectId/daily-diary",
    },
    {
      id: "hours",
      icon: "Clock",
      inputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.hours.in.crew", label: "Crew on site today" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.hours.in.codes", label: "Cost codes for the work" },
      ],
      outputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.hours.out.booked", label: "Hours booked to cost codes" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.hours.out.tm", label: "Time and materials work flagged" },
      ],
      titleKey: "cases.keep_a_daily_report_that_survives_a_claim.step.hours.title",
      titleDefault: "Book the crew's hours against the work, not against the week",
      whatKey: "cases.keep_a_daily_report_that_survives_a_claim.step.hours.what",
      whatDefault:
        "Put the day's hours in field time against the cost code they were worked on, and mark separately any hours that were time and materials rather than measured work. Where a crew split across two areas, split the hours rather than rounding them to whichever area was bigger.",
      whyKey: "cases.keep_a_daily_report_that_survives_a_claim.step.hours.why",
      whyDefault:
        "Hours booked to a cost code are hours you can defend later at a rate. Hours booked to a week are payroll and nothing else. When a change is priced on actual labor, this is the only record that tells you what the labor actually was.",
      moduleLabel: "Field Time",
      moduleLabelKey: "nav.field_time",
      to: "/projects/:projectId/field-time",
    },
    {
      id: "plant",
      icon: "Truck",
      inputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.plant.in.equipment", label: "Equipment on site" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.plant.in.weather", label: "Weather and ground conditions" },
      ],
      outputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.plant.out.states", label: "Equipment worked, idle and down" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.plant.out.stopped", label: "What the conditions stopped" },
      ],
      titleKey: "cases.keep_a_daily_report_that_survives_a_claim.step.plant.title",
      titleDefault: "Record equipment in three states, and say what the weather stopped",
      whatKey: "cases.keep_a_daily_report_that_survives_a_claim.step.plant.what",
      whatDefault:
        "For each machine on site record the hours it worked, the hours it stood idle and the hours it was down, rather than a single mark that it was present. Then record the weather with the thing it prevented: not just rain, but which pour was called off and which crew stood.",
      whyKey: "cases.keep_a_daily_report_that_survives_a_claim.step.plant.why",
      whyDefault:
        "Idle plant is a cost you can claim and down plant is a cost you cannot, and only the report written on the day can tell them apart. Weather recorded on its own proves the weather happened, which nobody disputes; weather recorded against the activity it stopped is what proves the delay.",
      moduleLabel: "Daily Diary",
      moduleLabelKey: "nav.daily_diary",
      to: "/projects/:projectId/daily-diary",
    },
    {
      id: "gaps",
      icon: "CalendarCheck",
      inputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.gaps.in.range", label: "The period being reported" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.gaps.in.reports", label: "Reports written so far" },
      ],
      outputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.gaps.out.closed", label: "Every calendar day accounted for" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.gaps.out.reason", label: "No-work days given a reason" },
      ],
      titleKey: "cases.keep_a_daily_report_that_survives_a_claim.step.gaps.title",
      titleDefault: "Close the calendar so there is no day without an answer",
      whatKey: "cases.keep_a_daily_report_that_survives_a_claim.step.gaps.what",
      whatDefault:
        "Review the period as a run of days rather than as a list of reports, and give the empty ones an explicit reason: weekend, holiday, shutdown, weather, no access. A day with no work is still a day that gets a report saying so.",
      whyKey: "cases.keep_a_daily_report_that_survives_a_claim.step.gaps.why",
      whyDefault:
        "Federal construction reporting asks for every calendar day to be accounted for, and a missing day is read as a record that was not kept rather than as a day nothing happened. The other side does not have to prove what was in the gap, only that the gap is there.",
      moduleLabel: "Daily Diary",
      moduleLabelKey: "nav.daily_diary",
      to: "/projects/:projectId/daily-diary",
    },
    {
      id: "evidence",
      icon: "FileSearch",
      inputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.evidence.in.reports", label: "The days in question" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.evidence.in.photos", label: "Photos and correspondence" },
      ],
      outputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.evidence.out.bundle", label: "Evidence bound to the event" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.evidence.out.timeline", label: "Timeline a reader can follow" },
      ],
      titleKey: "cases.keep_a_daily_report_that_survives_a_claim.step.evidence.title",
      titleDefault: "Bind the days to the event they are going to have to prove",
      whatKey: "cases.keep_a_daily_report_that_survives_a_claim.step.evidence.what",
      whatDefault:
        "In claims evidence, collect the days that bear on one event into a single bundle with the photos, instructions and correspondence that belong to them, and put them in the order they happened.",
      whyKey: "cases.keep_a_daily_report_that_survives_a_claim.step.evidence.why",
      whyDefault:
        "Evidence assembled while the job is running takes an hour. The same evidence assembled from an archive after the job closed takes a week and comes back incomplete, because the people who knew which photo belonged to which day have moved on.",
      moduleLabel: "Claims Evidence",
      moduleLabelKey: "nav.claims_evidence",
      to: "/projects/:projectId/claims-evidence",
    },
    {
      id: "price",
      icon: "Receipt",
      inputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.price.in.bundle", label: "The evidence bundle" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.price.in.hours", label: "Booked hours and plant time" },
      ],
      outputs: [
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.price.out.variation", label: "A priced change, not an assertion" },
        { labelKey: "cases.keep_a_daily_report_that_survives_a_claim.step.price.out.trace", label: "Each cost traceable to a day" },
      ],
      titleKey: "cases.keep_a_daily_report_that_survives_a_claim.step.price.title",
      titleDefault: "Turn the record into a priced change",
      whatKey: "cases.keep_a_daily_report_that_survives_a_claim.step.price.what",
      whatDefault:
        "Raise the variation from the bundle so the labor, plant and material on it come from the hours and equipment states already booked, rather than from an estimate made after the fact.",
      whyKey: "cases.keep_a_daily_report_that_survives_a_claim.step.price.why",
      whyDefault:
        "A number that can be walked back to a specific day, a specific crew and a specific machine gets argued about on its merits. A number that cannot gets treated as a negotiating position, and negotiating positions get halved.",
      moduleLabel: "Variations",
      moduleLabelKey: "nav.variations",
      to: "/projects/:projectId/variations",
    },
  ],
};

export default playbook;
