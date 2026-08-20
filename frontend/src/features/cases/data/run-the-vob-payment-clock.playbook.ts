// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run the VOB/B payment clock" (DE).
//
// Register the contract, raise the interim invoice against it, open a payment
// clock over the invoice and let the module count the deadline paragraph 16
// VOB/B sets. The dates named here are the ones the payment clock module
// actually computes for the German regimes: the claim falls due on receipt of
// the statement and the final date for payment is 21 calendar days later for an
// Abschlagsrechnung, 30 for a Schlussrechnung. VOB/B carries no payment notice
// and no pay-less notice, so those two rows of the clock stay empty and the
// case says so rather than inventing a notice to serve. Content strings are key
// plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "run-the-vob-payment-clock",
  order: 1053,
  region: "DE",
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  roles: ["contract-administrator", "commercial-manager", "quantity-surveyor"],
  icon: "CalendarClock",
  titleKey: "cases.run_the_vob_payment_clock.title",
  titleDefault: "Run the VOB/B payment clock",
  descKey: "cases.run_the_vob_payment_clock.desc",
  descDefault:
    "Register the contract, raise each Abschlagsrechnung against it, open a payment clock over the invoice and let the module count the days paragraph 16 VOB/B gives the client, so an overdue payment is a dated record rather than a feeling.",
  longDescKey: "cases.run_the_vob_payment_clock.longdesc",
  longDescDefault:
    "Money has a clock under VOB/B. An interim invoice falls due within 21 calendar days of the client receiving the verifiable statement of work, and the final invoice runs on its own longer window of 30 days, which the module carries as a second regime because they are two different clocks. A firm that does not track the chain - invoice out, period running, due, in default - is lending its client money at no charge and finds out months later, when the dates it would need are scattered across three inboxes.",
  estMinutes: 12,
  steps: [
    {
      id: "contract",
      icon: "FileSignature",
      inputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.contract.in.bauvertrag", label: "Signed Bauvertrag" },
        { labelKey: "cases.run_the_vob_payment_clock.step.contract.in.schedule", label: "Priced schedule of values" },
      ],
      outputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.contract.out.registered", label: "Registered contract" },
        { labelKey: "cases.run_the_vob_payment_clock.step.contract.out.retention", label: "Retention terms on record" },
      ],
      titleKey: "cases.run_the_vob_payment_clock.step.contract.title",
      titleDefault: "Register the contract",
      whatKey: "cases.run_the_vob_payment_clock.step.contract.what",
      whatDefault:
        "Create the contract for the job with its type, its priced schedule of values and its retention percentage, so the sums you will invoice against are on record before the first Abschlagsrechnung leaves the office.",
      whyKey: "cases.run_the_vob_payment_clock.step.contract.why",
      whyDefault:
        "A payment deadline only bites when both sides agree what was ordered. A contract carrying the priced schedule turns a challenged invoice into an arithmetic question instead of an argument about scope.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "claim",
      icon: "Calculator",
      inputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.claim.in.contract", label: "Registered contract" },
        { labelKey: "cases.run_the_vob_payment_clock.step.claim.in.measured", label: "Work measured this period" },
      ],
      outputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.claim.out.invoice", label: "Abschlagsrechnung" },
        { labelKey: "cases.run_the_vob_payment_clock.step.claim.out.net", label: "Net sum applied for" },
      ],
      titleKey: "cases.run_the_vob_payment_clock.step.claim.title",
      titleDefault: "Raise the Abschlagsrechnung",
      whatKey: "cases.run_the_vob_payment_clock.step.claim.what",
      whatDefault:
        "On the progress claims tab, value the work done in the period against the schedule of values and raise it as the interim invoice, with the period it covers, the retention deducted and the net sum you are asking for.",
      whyKey: "cases.run_the_vob_payment_clock.step.claim.why",
      whyDefault:
        "The clock is counted against this document, so it has to state the work, the period and the sum before it goes out. A statement the client can check is what sets the period running; one they cannot check comes back as a query, and a query costs you the days it takes to answer.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "openclock",
      icon: "Scale",
      inputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.openclock.in.invoice", label: "Abschlagsrechnung" },
        { labelKey: "cases.run_the_vob_payment_clock.step.openclock.in.receipt", label: "Date the client received it" },
        { labelKey: "cases.run_the_vob_payment_clock.step.openclock.in.amount", label: "Sum applied for" },
      ],
      outputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.openclock.out.clock", label: "Open payment clock" },
        { labelKey: "cases.run_the_vob_payment_clock.step.openclock.out.regime", label: "Statutory regime on record" },
      ],
      titleKey: "cases.run_the_vob_payment_clock.step.openclock.title",
      titleDefault: "Open a clock over the invoice",
      whatKey: "cases.run_the_vob_payment_clock.step.openclock.what",
      whatDefault:
        "Open a clock and pick the German regime for interim payments under paragraph 16 VOB/B. Enter the date the client received the statement as the application date, then the sum applied for and the currency.",
      whyKey: "cases.run_the_vob_payment_clock.step.openclock.why",
      whyDefault:
        "The period runs from receipt, not from the day you printed the invoice. Entering the posting date moves every deadline in your own favour and leaves you holding a date you cannot prove on the one occasion it has to be proved.",
      moduleLabel: "Payment Clock",
      moduleLabelKey: "nav.payment_clock",
      to: "/payment-clock",
    },
    {
      id: "dates",
      icon: "CalendarClock",
      inputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.dates.in.clock", label: "Open payment clock" },
        { labelKey: "cases.run_the_vob_payment_clock.step.dates.in.regime", label: "Chosen regime" },
      ],
      outputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.dates.out.due", label: "Due date" },
        { labelKey: "cases.run_the_vob_payment_clock.step.dates.out.final", label: "Final date for payment" },
        { labelKey: "cases.run_the_vob_payment_clock.step.dates.out.derivation", label: "Derivation you can quote" },
      ],
      titleKey: "cases.run_the_vob_payment_clock.step.dates.title",
      titleDefault: "Read the dates the module computed",
      whatKey: "cases.run_the_vob_payment_clock.step.dates.what",
      whatDefault:
        "Open the clock detail. The sum payable leads, the due date and the final date for payment sit under it, and the derivation spells out each date against the provision it came from. On a VOB/B clock the two notice rows stay empty.",
      whyKey: "cases.run_the_vob_payment_clock.step.dates.why",
      whyDefault:
        "They stay empty because VOB/B sets no payment notice and no pay-less notice, so there is nothing to serve and nothing to chase, only the money and the date it stops being on time. A derivation you can read out loud is what turns a phone call about a late payment into a quotable line.",
      moduleLabel: "Payment Clock",
      moduleLabelKey: "nav.payment_clock",
      to: "/payment-clock",
    },
    {
      id: "watch",
      icon: "AlertTriangle",
      inputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.watch.in.clocks", label: "Open clocks on the project" },
        { labelKey: "cases.run_the_vob_payment_clock.step.watch.in.finaldates", label: "Final dates for payment" },
      ],
      outputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.watch.out.overdue", label: "Overdue invoices flagged" },
        { labelKey: "cases.run_the_vob_payment_clock.step.watch.out.register", label: "Breach register rows" },
      ],
      titleKey: "cases.run_the_vob_payment_clock.step.watch.title",
      titleDefault: "Watch the clock count each deadline",
      whatKey: "cases.run_the_vob_payment_clock.step.watch.what",
      whatDefault:
        "Come back to the list as the month runs. It says how many clocks the project carries and how many are past their final date, badges the overdue ones, and fills the breach register underneath. Open an overdue one and the findings name the sum outstanding, the days it has run past the final date and the rate the statutory interest runs at.",
      whyKey: "cases.run_the_vob_payment_clock.step.watch.why",
      whyDefault:
        "Reading a clock is what writes its register, so a quiet register on a project nobody opens is telling you about the reading and not about the payments. The interest is due as of right and starts running the moment the date passes, without having to be claimed separately, so the only thing standing between you and it is a record that says when.",
      moduleLabel: "Payment Clock",
      moduleLabelKey: "nav.payment_clock",
      to: "/payment-clock",
    },
    {
      id: "receivable",
      icon: "Banknote",
      inputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.receivable.in.claim", label: "Certified progress claim" },
        { labelKey: "cases.run_the_vob_payment_clock.step.receivable.in.overdue", label: "Overdue clocks" },
      ],
      outputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.receivable.out.invoice", label: "Receivable on the books" },
        { labelKey: "cases.run_the_vob_payment_clock.step.receivable.out.total", label: "Overdue total in the cash picture" },
      ],
      titleKey: "cases.run_the_vob_payment_clock.step.receivable.title",
      titleDefault: "See what the delay is costing you",
      whatKey: "cases.run_the_vob_payment_clock.step.receivable.what",
      whatDefault:
        "Open the receivable side of Finance: the invoice raised from the certified claim, its due date, and the total the project is carrying overdue. It sits in the same cash picture as the money you have already spent doing the work it pays for.",
      whyKey: "cases.run_the_vob_payment_clock.step.receivable.why",
      whyDefault:
        "This is what an untracked payment deadline actually is - your own working capital lent to the client at no charge, for as long as nobody counts it. Seeing the overdue total beside the budget turns a vague chase into a decision about which invoice gets escalated first.",
      moduleLabel: "Finance",
      moduleLabelKey: "finance.title",
      to: "/projects/:projectId/finance",
    },
    {
      id: "escalate",
      icon: "Send",
      inputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.escalate.in.reading", label: "Clock reading" },
        { labelKey: "cases.run_the_vob_payment_clock.step.escalate.in.invoice", label: "Abschlagsrechnung" },
      ],
      outputs: [
        { labelKey: "cases.run_the_vob_payment_clock.step.escalate.out.letter", label: "Nachfrist letter on file" },
        { labelKey: "cases.run_the_vob_payment_clock.step.escalate.out.record", label: "Escalation record" },
      ],
      titleKey: "cases.run_the_vob_payment_clock.step.escalate.title",
      titleDefault: "Escalate with the record assembled",
      whatKey: "cases.run_the_vob_payment_clock.step.escalate.what",
      whatDefault:
        "Write the Nachfrist letter and file it with the invoice and the clock reading it quotes: the date of receipt, the final date for payment, the days late and the sum outstanding. The module runs no grace period of its own, so that date is one you set and mind by hand.",
      whyKey: "cases.run_the_vob_payment_clock.step.escalate.why",
      whyDefault:
        "By the time a payment is worth escalating, the facts are months old and spread across three inboxes. A letter whose every date came off a record you kept as you went is the one that moves the client's accounts department, and it is the same file anyone advising you later asks for first.",
      moduleLabel: "Documents",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
  ],
};

export default playbook;
