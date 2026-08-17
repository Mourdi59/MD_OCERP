// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Bill the month with a payment application" (US).
//
// The US monthly billing cycle as a project manager runs it: a schedule of
// values agreed against the contract sum, a continuation sheet showing work
// completed this period and materials stored, retainage held per line, and a
// certificate face that adds up to the payment now due. The forms themselves
// are described by what they do, never by a publisher's designation. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "bill-the-month-with-a-payment-application",
  order: 1060,
  region: "US",
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor", "project-manager"],
  roles: ["project-manager", "commercial-manager", "quantity-surveyor"],
  icon: "Receipt",
  titleKey: "cases.bill_the_month_with_a_payment_application.title",
  titleDefault: "Bill the month with a payment application",
  descKey: "cases.bill_the_month_with_a_payment_application.desc",
  descDefault:
    "Agree a schedule of values against the contract sum, bill the period on a continuation sheet with stored materials and retainage, and issue a certificate face whose arithmetic the owner's accountant can follow.",
  longDescKey: "cases.bill_the_month_with_a_payment_application.longdesc",
  longDescDefault:
    "In the US the monthly application is the contract. The schedule of values is what the owner agreed to pay against, the continuation sheet is where each line states work completed previously, work completed this period and materials presently stored, and the certificate face is the single page that turns all of it into one number now due. Getting the arithmetic right matters more than the letterhead: the total earned to date has to tie to the lines, the retainage has to be the rate the contract actually holds, and the previous certificates figure has to be what was certified before, not what was invoiced. This case runs that cycle once on a live contract.",
  estMinutes: 16,
  steps: [
    {
      id: "sov",
      icon: "ListTree",
      inputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.sov.in.contract", label: "Signed contract and sum" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.sov.in.bill", label: "Priced bill or breakdown" },
      ],
      outputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.sov.out.sov", label: "Schedule of values" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.sov.out.tie", label: "Line total tied to contract sum" },
      ],
      titleKey: "cases.bill_the_month_with_a_payment_application.step.sov.title",
      titleDefault: "Break the contract sum into a schedule of values",
      whatKey: "cases.bill_the_month_with_a_payment_application.step.sov.what",
      whatDefault:
        "On the contract, enter the schedule of values line by line from the priced bill: an item number, a description the owner will recognise, and a scheduled value. Check that the lines add up to the contract sum exactly before you bill anything against them.",
      whyKey: "cases.bill_the_month_with_a_payment_application.step.sov.why",
      whyDefault:
        "Every later application is measured against these lines, so a schedule that does not tie to the contract sum poisons every month that follows. This is also the page an owner's representative reads for front-loading, which is the fastest way to have a first application sent back.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "retainage",
      icon: "Percent",
      inputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.retainage.in.terms", label: "Payment terms in the contract" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.retainage.in.sov", label: "Schedule of values" },
      ],
      outputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.retainage.out.rate", label: "Retainage rate on record" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.retainage.out.event", label: "Release event named" },
      ],
      titleKey: "cases.bill_the_month_with_a_payment_application.step.retainage.title",
      titleDefault: "Record the retainage the contract actually holds",
      whatKey: "cases.bill_the_month_with_a_payment_application.step.retainage.what",
      whatDefault:
        "Set the retainage percentage on the contract from the executed agreement, and name the event that releases it. Do this from the contract wording rather than from what the last job did.",
      whyKey: "cases.bill_the_month_with_a_payment_application.step.retainage.why",
      whyDefault:
        "Retainage is the largest single deduction on the application and the one most often carried over from a previous job by habit. A rate that is half a point wrong is a five figure argument on a mid-size contract, and it repeats every month until someone notices.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "period",
      icon: "CalendarDays",
      inputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.period.in.progress", label: "Work completed this period" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.period.in.stored", label: "Materials presently stored" },
      ],
      outputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.period.out.claim", label: "Application for the period" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.period.out.dates", label: "Period start and end on record" },
      ],
      titleKey: "cases.bill_the_month_with_a_payment_application.step.period.title",
      titleDefault: "Open the application for the period and bill the work done",
      whatKey: "cases.bill_the_month_with_a_payment_application.step.period.what",
      whatDefault:
        "Raise the application for this billing period and go down the schedule of values entering what was completed in the period and what material is on site or stored off site but not yet installed. Work billed in earlier periods is already carried forward for you.",
      whyKey: "cases.bill_the_month_with_a_payment_application.step.period.why",
      whyDefault:
        "Stored material is the line owners scrutinise hardest, because it is money for something that is not yet built. Keeping it in its own column, rather than folded into work completed, is what makes it defensible instead of arguable.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "changes",
      icon: "GitCompare",
      inputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.changes.in.orders", label: "Approved change orders" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.changes.in.sum", label: "Original contract sum" },
      ],
      outputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.changes.out.adjusted", label: "Adjusted contract sum" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.changes.out.net", label: "Net change by change order" },
      ],
      titleKey: "cases.bill_the_month_with_a_payment_application.step.changes.title",
      titleDefault: "Fold the approved change orders into the contract sum",
      whatKey: "cases.bill_the_month_with_a_payment_application.step.changes.what",
      whatDefault:
        "Check that every change order approved before the period end is reflected, so the application shows the original contract sum, the net change by change orders and the adjusted contract sum as three separate figures.",
      whyKey: "cases.bill_the_month_with_a_payment_application.step.changes.why",
      whyDefault:
        "An application that bills changed work against an unchanged contract sum reads as an overbill, and it will be certified down. Showing the three figures separately is what lets the owner agree the change and the billing in one pass instead of two.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "certificate",
      icon: "FileCheck2",
      inputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.certificate.in.lines", label: "Completed continuation sheet" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.certificate.in.previous", label: "Previously certified total" },
      ],
      outputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.certificate.out.due", label: "Current payment due" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.certificate.out.balance", label: "Balance to finish" },
      ],
      titleKey: "cases.bill_the_month_with_a_payment_application.step.certificate.title",
      titleDefault: "Read the certificate face and check it ties",
      whatKey: "cases.bill_the_month_with_a_payment_application.step.certificate.what",
      whatDefault:
        "Open the payment application view and read the summary the owner will read: total completed and stored to date, retainage on work and on stored material, total earned less retainage, less previous certificates, current payment due, balance to finish. Every figure is built from the lines you just entered, so check the total earned against the continuation sheet and the previous certificates figure against what was actually certified.",
      whyKey: "cases.bill_the_month_with_a_payment_application.step.certificate.why",
      whyDefault:
        "Applications are rejected on arithmetic far more often than on merit. A summary that is derived from the lines rather than typed beside them is the difference between one review cycle and three.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "issue",
      icon: "Send",
      inputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.issue.in.checked", label: "Checked application" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.issue.in.recipient", label: "Owner or architect of record" },
      ],
      outputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.issue.out.pdf", label: "Application PDF" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.issue.out.submitted", label: "Submission dated and logged" },
      ],
      titleKey: "cases.bill_the_month_with_a_payment_application.step.issue.title",
      titleDefault: "Issue the application and log the date it went out",
      whatKey: "cases.bill_the_month_with_a_payment_application.step.issue.what",
      whatDefault:
        "Export the application as a PDF, submit it, and let the contract record the date it was submitted. The application then moves through submitted, certified and paid as the owner acts on it.",
      whyKey: "cases.bill_the_month_with_a_payment_application.step.issue.why",
      whyDefault:
        "Prompt payment clocks in most states start from a dated submission, not from a conversation. The dated record is also the first thing anyone asks for when a payment is late.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "money",
      icon: "Banknote",
      inputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.money.in.certified", label: "Certified application" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.money.in.receipts", label: "Payments received" },
      ],
      outputs: [
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.money.out.position", label: "Cash position for the job" },
        { labelKey: "cases.bill_the_month_with_a_payment_application.step.money.out.held", label: "Retainage held to date" },
      ],
      titleKey: "cases.bill_the_month_with_a_payment_application.step.money.title",
      titleDefault: "Watch the money against what you billed",
      whatKey: "cases.bill_the_month_with_a_payment_application.step.money.what",
      whatDefault:
        "In finance, read the job against the applications: billed, certified, received, and the retainage held to date across every period. Anything certified and not received is what your next call is about.",
      whyKey: "cases.bill_the_month_with_a_payment_application.step.money.why",
      whyDefault:
        "The application is only half the cycle. A contractor who knows on the day that a certified application has not been paid, and by how much, is running the job. One who finds out at month end is funding the owner.",
      moduleLabel: "Finance",
      moduleLabelKey: "finance.title",
      to: "/projects/:projectId/finance",
    },
  ],
};

export default playbook;
