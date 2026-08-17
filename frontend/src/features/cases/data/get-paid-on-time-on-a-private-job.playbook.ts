// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Get paid on time on a private job" (US).
//
// American late payment is not a negotiation, it is a statute. Every state
// writes its own prompt payment law, the window and the interest differ between
// public and private work, and the entitlement runs whether or not anybody
// invokes it. Contractors routinely absorb late payment as a cost of doing
// business because the clock lived in somebody's head, so nobody could say on
// what date the money became late or what it was worth by then.
//
// This case is built on the four US prompt payment regimes the payment clock
// already carries (Texas and California, public and private). That is the
// distinctly American part: the milestone billing and the invoice are ordinary,
// the statutory clock behind them is not.
//
// No day counts, no interest rates and no statute numbers in the copy. They
// differ by state and by whether the work is public or private, the regime
// carries the real values, and a figure printed here would be an unverified
// claim in front of the reader. Content strings are key plus inline English
// default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "get-paid-on-time-on-a-private-job",
  order: 1066,
  region: "US",
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor", "developer-client"],
  roles: ["commercial-manager", "project-manager", "quantity-surveyor"],
  icon: "Clock",
  titleKey: "cases.get_paid_on_time_on_a_private_job.title",
  titleDefault: "Get paid on time on a private job",
  descKey: "cases.get_paid_on_time_on_a_private_job.desc",
  descDefault:
    "Agree the milestones, bill them as they complete, and let the prompt payment law that governs the job run the clock, so a late payment has a date, an amount and an interest figure instead of an argument.",
  longDescKey: "cases.get_paid_on_time_on_a_private_job.longdesc",
  longDescDefault:
    "Most contractors treat late payment as weather: unpleasant, out of their hands, priced into the job. It is not. Every state sets a period within which a private owner has to pay, and interest accrues when they do not, whether or not anyone mentions it at the time. What is usually missing is not the right but the record, because nobody can say which day the money became late. This case sets the milestone schedule up front, bills against it, and runs the statutory clock for the state and the kind of work, so the conversation is about a number both sides can check rather than about who remembers the invoice going out.",
  estMinutes: 16,
  steps: [
    {
      id: "terms",
      icon: "FileSignature",
      inputs: [
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.terms.in.scope", label: "Scope and agreed price" },
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.terms.in.schedule", label: "Milestones both sides accept" },
      ],
      outputs: [
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.terms.out.contract", label: "Contract with a payment schedule" },
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.terms.out.terms", label: "Payment terms recorded, not remembered" },
      ],
      titleKey: "cases.get_paid_on_time_on_a_private_job.step.terms.title",
      titleDefault: "Write the payment schedule into the contract",
      whatKey: "cases.get_paid_on_time_on_a_private_job.step.terms.what",
      whatDefault:
        "Record the contract with its price, its payment terms and the milestones that trigger a payment, so what is owed and when is a property of the job rather than a thing two people recall differently.",
      whyKey: "cases.get_paid_on_time_on_a_private_job.step.terms.why",
      whyDefault:
        "A milestone that was never written down cannot be billed without a discussion, and the discussion always happens when you need the money. Written up front, the same milestone is an invoice trigger nobody has to justify.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "milestone",
      icon: "Milestone",
      inputs: [
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.milestone.in.done", label: "Work actually complete" },
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.milestone.in.evidence", label: "Evidence it is complete" },
      ],
      outputs: [
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.milestone.out.claim", label: "A payment claim for the milestone" },
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.milestone.out.dated", label: "The date it was submitted" },
      ],
      titleKey: "cases.get_paid_on_time_on_a_private_job.step.milestone.title",
      titleDefault: "Bill the milestone the day it completes",
      whatKey: "cases.get_paid_on_time_on_a_private_job.step.milestone.what",
      whatDefault:
        "Raise the payment claim against the milestone as it completes, with the date it went out. Billing late shortens nothing except your own runway, and the submission date is what every subsequent question turns on.",
      whyKey: "cases.get_paid_on_time_on_a_private_job.step.milestone.why",
      whyDefault:
        "The statutory clock starts from an event, and on private work that event is usually your claim arriving. A claim you sat on for two weeks is two weeks of interest you will never see, and it is the one part of the timeline entirely within your control.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "clock",
      icon: "Clock",
      inputs: [
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.clock.in.state", label: "State and whether the work is public" },
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.clock.in.submitted", label: "The date the claim went in" },
      ],
      outputs: [
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.clock.out.due", label: "The date payment becomes due" },
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.clock.out.regime", label: "The regime that governs, named" },
      ],
      titleKey: "cases.get_paid_on_time_on_a_private_job.step.clock.title",
      titleDefault: "Run the clock the law actually gives you",
      whatKey: "cases.get_paid_on_time_on_a_private_job.step.clock.what",
      whatDefault:
        "Pick the prompt payment regime that governs this job, by state and by whether the work is public or private, and start the clock from the claim. The due date is then computed from the statute rather than assumed from habit.",
      whyKey: "cases.get_paid_on_time_on_a_private_job.step.clock.why",
      whyDefault:
        "The periods are genuinely different between states and between public and private work, which is exactly why people guess and guess wrong. Naming the regime turns the due date into something checkable, and it means the same job billed in another state does not quietly inherit the wrong deadline.",
      moduleLabel: "Payment Clock",
      moduleLabelKey: "nav.payment_clock",
      to: "/payment-clock",
    },
    {
      id: "interest",
      icon: "Percent",
      inputs: [
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.interest.in.due", label: "Due date passed" },
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.interest.in.unpaid", label: "Amount still unpaid" },
      ],
      outputs: [
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.interest.out.interest", label: "Interest computed from the statute" },
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.interest.out.position", label: "A position you can put in writing" },
      ],
      titleKey: "cases.get_paid_on_time_on_a_private_job.step.interest.title",
      titleDefault: "Let the overdue amount price itself",
      whatKey: "cases.get_paid_on_time_on_a_private_job.step.interest.what",
      whatDefault:
        "Once the due date passes, the interest the regime provides accrues on the unpaid amount and is calculated rather than estimated, so a reminder can carry a figure instead of a complaint.",
      whyKey: "cases.get_paid_on_time_on_a_private_job.step.interest.why",
      whyDefault:
        "Asking to be paid is awkward and easy to defer. Sending a number that grows on a schedule the law set is neither, and it changes what the other side is deciding: not whether to be fair to you, but whether delay is now costing them more than paying.",
      moduleLabel: "Payment Clock",
      moduleLabelKey: "nav.payment_clock",
      to: "/payment-clock",
    },
    {
      id: "settle",
      icon: "Banknote",
      inputs: [
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.settle.in.received", label: "Payments received" },
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.settle.in.claims", label: "Claims raised to date" },
      ],
      outputs: [
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.settle.out.outstanding", label: "What is still owed, by age" },
        { labelKey: "cases.get_paid_on_time_on_a_private_job.step.settle.out.history", label: "Who pays late, on the record" },
      ],
      titleKey: "cases.get_paid_on_time_on_a_private_job.step.settle.title",
      titleDefault: "See who actually pays you late",
      whatKey: "cases.get_paid_on_time_on_a_private_job.step.settle.what",
      whatDefault:
        "Reconcile what was billed against what arrived, and keep the ageing rather than clearing it from memory once the money lands.",
      whyKey: "cases.get_paid_on_time_on_a_private_job.step.settle.why",
      whyDefault:
        "A client who pays a month late every time is a financing cost you are carrying without pricing it. Once that is visible per client rather than felt in general, it becomes something you can price into the next bid or decline.",
      moduleLabel: "Finance",
      moduleLabelKey: "finance.title",
      to: "/projects/:projectId/finance",
    },
  ],
};

export default playbook;
