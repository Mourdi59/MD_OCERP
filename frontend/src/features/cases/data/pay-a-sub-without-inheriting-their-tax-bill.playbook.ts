// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Pay a sub without inheriting their tax bill" (US).
//
// The objection is "compliance paperwork is the accountant's problem, not the
// project's". It is answered by the calendar rather than by argument: the
// paperwork stops a payment, and it stops it on the day of the month when
// nobody has time to chase a signature.
//
// The US-specific weight is that the absence of a form is not a neutral state.
// Under backup withholding the scheme's default band is the one that deducts,
// so a subcontractor with no certified taxpayer identification number on file
// is not an open question, they are a deduction at the full rate. A payer who
// does not deduct can end up owing the amount themselves, which is how a
// missing signature becomes the payer's money rather than the payee's.
//
// Deliberately no rate, no threshold and no statute number in the copy. The
// scheme record carries all three and can be amended without anybody editing a
// case file, so a figure printed here would be an unverified claim in front of
// the reader and would age badly. The wording for the evidence follows the
// product's own: it names the signed request-for-taxpayer-identification form
// rather than a form number.
//
// This is not retainage. Money held back from a certified claim and released
// later is a different mechanism with a different owner, and the case is
// written so the two are never confused: tax withheld goes to the authority
// and the payee reclaims it themselves, retainage comes back from the payer.
//
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "pay-a-sub-without-inheriting-their-tax-bill",
  order: 1067,
  region: "US",
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor", "project-manager", "owner-operator"],
  roles: ["accountant", "finance-manager", "commercial-manager", "contract-administrator"],
  icon: "ShieldCheck",
  titleKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.title",
  titleDefault: "Pay a sub without inheriting their tax bill",
  descKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.desc",
  descDefault:
    "Record each subcontractor's tax standing and the certificates they carry, let the expiry dates come to you instead of being looked for, deduct on the base the scheme names, and pay the balance with the record already behind it.",
  longDescKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.longdesc",
  longDescDefault:
    "Nobody sets out to hold a subcontractor's payment over a certificate. It happens because the certificate expired on a date nobody was watching and the discovery is made by the person doing the pay run, on the day it has to go out. The tax side is worse than the insurance side and less well known: where no certified taxpayer identification number is on file the default is to deduct, and a payer who pays gross instead can be left owing the deducted amount themselves. This case puts both facts where they belong, which is weeks before the pay run rather than during it, and it does so as ordinary registration work rather than as a compliance project.",
  estMinutes: 16,
  steps: [
    {
      id: "standing",
      icon: "UserCheck",
      inputs: [
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.standing.in.party", label: "The subcontractor and the scheme that applies" },
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.standing.in.evidence", label: "The signed form on file, and its date" },
      ],
      outputs: [
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.standing.out.band", label: "The band their evidence supports" },
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.standing.out.rate", label: "The rate that will be deducted" },
      ],
      titleKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.standing.title",
      titleDefault: "Record what the sub's standing actually is, not what you assume",
      whatKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.standing.what",
      whatDefault:
        "Register each subcontractor against the withholding scheme with the band their evidence supports, the reference of the signed form and the date it was given. The band is what decides the rate, so it is the field to get right rather than a note in the file.",
      whyKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.standing.why",
      whyDefault:
        "The scheme's default band is the one that deducts. That is the part people are caught by: an unrecorded sub is not an open question the system will ask you about later, they are already at the full rate. Recording the standing while somebody is onboarding them costs a minute. Establishing it on payment day costs the payment.",
      moduleLabel: "Withholding Tax",
      moduleLabelKey: "nav.tax_withholding",
      to: "/tax-withholding",
    },
    {
      id: "certificates",
      icon: "ShieldCheck",
      inputs: [
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.certificates.in.policies", label: "Insurance certificates, bonds, licences" },
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.certificates.in.dates", label: "The expiry date each one carries" },
      ],
      outputs: [
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.certificates.out.register", label: "Cover recorded per subcontractor" },
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.certificates.out.state", label: "Who is covered today, at a glance" },
      ],
      titleKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.certificates.title",
      titleDefault: "Put the certificates on the register with the day they lapse",
      whatKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.certificates.what",
      whatDefault:
        "Record what each subcontractor carries and when it runs out. General liability, workers compensation, auto and umbrella are separate policies with separate dates, and so are payment, performance and bid bonds, so they are recorded separately rather than as one tick for insurance.",
      whyKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.certificates.why",
      whyDefault:
        "A certificate never fails loudly. It lapses on a date, and the first person to notice is usually the one who needed it: the adjuster after an incident, or whoever is signing the pay run. Filing one date per policy is what turns that from a discovery into a reminder.",
      moduleLabel: "Subcontractor Directory",
      moduleLabelKey: "nav.subcontractors",
      to: "/subcontractors",
    },
    {
      id: "watch",
      icon: "CalendarClock",
      inputs: [
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.watch.in.expiries", label: "Recorded expiry dates" },
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.watch.in.window", label: "How much warning you want" },
      ],
      outputs: [
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.watch.out.ahead", label: "What lapses before the next pay run" },
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.watch.out.now", label: "What has already lapsed" },
      ],
      titleKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.watch.title",
      titleDefault: "Let the dates come to you instead of being looked for",
      whatKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.watch.what",
      whatDefault:
        "Watch the recorded dates with a warning window wide enough to chase a renewal, so a policy about to run out appears next to everything else the job owes a date, rather than in a folder somebody has to remember to open.",
      whyKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.watch.why",
      whyDefault:
        "An expired certificate is not a closed item, it is the most urgent open one, and a list that treats it as finished is worse than no list. The point of the window is to move the work from the twenty-fifth of the month to a day when a phone call is still enough.",
      moduleLabel: "Deadlines",
      moduleLabelKey: "deadlines.title",
      to: "/deadlines",
    },
    {
      id: "deduct",
      icon: "Percent",
      inputs: [
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.deduct.in.gross", label: "The gross payment for the period" },
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.deduct.in.split", label: "What within it is not part of the base" },
      ],
      outputs: [
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.deduct.out.base", label: "The taxable base and the amount deducted" },
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.deduct.out.remitted", label: "Remittance recorded with its reference" },
      ],
      titleKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.deduct.title",
      titleDefault: "Deduct on the base the scheme names, not on the invoice total",
      whatKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.deduct.what",
      whatDefault:
        "Take the gross for the period, set aside whatever the scheme leaves out of the base, apply the band the sub's standing puts them in, and record the deduction against the payment. When it is remitted, keep the reference on the same record.",
      whyKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.deduct.why",
      whyDefault:
        "Two things get confused here and both cost money. The base is not the invoice total, and different schemes leave different parts out of it. And this is not retainage: what is deducted goes to the authority, the subcontractor reclaims it through their own return, and it does not come back from you. Telling a sub you are holding it is the fastest way to a dispute over money you no longer have.",
      moduleLabel: "Withholding Tax",
      moduleLabelKey: "nav.tax_withholding",
      to: "/tax-withholding",
    },
    {
      id: "pay",
      icon: "Banknote",
      inputs: [
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.pay.in.cleared", label: "Subs cleared for payment" },
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.pay.in.deduction", label: "The deduction for the period" },
      ],
      outputs: [
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.pay.out.paid", label: "Net paid, with the deduction shown" },
        { labelKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.pay.out.record", label: "A record that answers the question later" },
      ],
      titleKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.pay.title",
      titleDefault: "Pay the balance with the record already behind it",
      whatKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.pay.what",
      whatDefault:
        "Release the payment showing the gross, the deduction and the net as separate figures rather than as one adjusted number, so the sub can see what was taken and reclaim it without asking you to reconstruct it.",
      whyKey: "cases.pay_a_sub_without_inheriting_their_tax_bill.step.pay.why",
      whyDefault:
        "The question always comes back, and it comes back months later from somebody's accountant rather than from the person you dealt with. A payment that carries its own arithmetic is answered by opening it. A net figure with no working behind it is answered by a morning of somebody's time, every time it is asked.",
      moduleLabel: "Finance",
      moduleLabelKey: "finance.title",
      to: "/projects/:projectId/finance",
    },
  ],
};

export default playbook;
