// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Trade payment for lien rights, and get the retainage back" (US).
//
// The American payment chain is an exchange, not a transfer: money moves down
// and lien rights are released back up, one signed waiver per payment. A
// contractor who pays without collecting the waiver has paid and still carries
// the exposure; one who signs the wrong waiver type has released rights for
// money that has not cleared yet. Both are ordinary, expensive, and entirely
// avoidable by making the waiver a condition of the payment run rather than
// paperwork chased afterwards.
//
// Everything this case walks through is live: the waiver gate and the upload
// sit on the subcontractor record, the four US waiver types sit on the progress
// claim, and retainage releases against a named event on the contract. No step
// invents a surface.
//
// Deliberately unnumbered: retainage percentages, waiver deadlines and who may
// require which form are set by state law and by the contract, and they differ
// enough that any figure printed here would be an unverified claim in
// user-facing copy. The mechanics are stated; the numbers stay the reader's.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "trade-payment-for-lien-rights",
  order: 1065,
  region: "US",
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor", "developer-client"],
  // No accounting / contract-administration role exists in `ProfessionalRole`,
  // and the person who reconciles the payment against the waiver on a US job
  // often is exactly that. Using the commercial trio the other money cases use
  // rather than inventing a member of a closed union.
  roles: ["commercial-manager", "project-manager", "quantity-surveyor"],
  icon: "Handshake",
  titleKey: "cases.trade_payment_for_lien_rights.title",
  titleDefault: "Trade payment for lien rights, and get the retainage back",
  descKey: "cases.trade_payment_for_lien_rights.desc",
  descDefault:
    "Make a signed waiver the condition of getting paid rather than paperwork chased afterwards: gate the payment run on it, collect the right waiver type for each payment, and release retainage against an event both sides agreed to in advance.",
  longDescKey: "cases.trade_payment_for_lien_rights.longdesc",
  longDescDefault:
    "Money moves down the American payment chain and lien rights move back up, one signed waiver at a time. When that exchange is tracked on paper it fails in two directions at once: the payer releases funds and keeps the exposure because the waiver never arrived, and the payee signs away rights for a check that has not cleared. This case puts the exchange where the payment is, so a payment run cannot complete without the waiver it is supposed to buy, the waiver says exactly what it should say about whether the money has actually landed, and the retainage everybody forgot about comes back at a defined event instead of whenever someone remembers to ask.",
  estMinutes: 18,
  steps: [
    {
      id: "gate",
      icon: "ShieldCheck",
      inputs: [
        { labelKey: "cases.trade_payment_for_lien_rights.step.gate.in.agreements", label: "Subcontract agreements" },
        { labelKey: "cases.trade_payment_for_lien_rights.step.gate.in.policy", label: "Who must waive before being paid" },
      ],
      outputs: [
        { labelKey: "cases.trade_payment_for_lien_rights.step.gate.out.gate", label: "Payment gated on a waiver" },
        { labelKey: "cases.trade_payment_for_lien_rights.step.gate.out.exposure", label: "Open exposure visible per firm" },
      ],
      titleKey: "cases.trade_payment_for_lien_rights.step.gate.title",
      titleDefault: "Decide who cannot be paid without a waiver",
      whatKey: "cases.trade_payment_for_lien_rights.step.gate.what",
      whatDefault:
        "Mark on each subcontract agreement whether a signed waiver is required before payment is released. The requirement then travels with the firm rather than living in one person's memory of what was agreed.",
      whyKey: "cases.trade_payment_for_lien_rights.step.gate.why",
      whyDefault:
        "Chasing waivers after the money has gone out is chasing a signature from someone who no longer needs anything from you. Set as a condition of payment, the same request answers itself, because the party who wants the check is the party who has to sign.",
      moduleLabel: "Subcontractor Directory",
      moduleLabelKey: "nav.subcontractors",
      to: "/subcontractors",
    },
    {
      id: "collect",
      icon: "Upload",
      inputs: [
        { labelKey: "cases.trade_payment_for_lien_rights.step.collect.in.signed", label: "Signed waiver from each firm" },
        { labelKey: "cases.trade_payment_for_lien_rights.step.collect.in.period", label: "The payment period it covers" },
      ],
      outputs: [
        { labelKey: "cases.trade_payment_for_lien_rights.step.collect.out.filed", label: "Waivers filed against the firm" },
        { labelKey: "cases.trade_payment_for_lien_rights.step.collect.out.missing", label: "Who is still outstanding" },
      ],
      titleKey: "cases.trade_payment_for_lien_rights.step.collect.title",
      titleDefault: "Collect the signed waivers down the chain",
      whatKey: "cases.trade_payment_for_lien_rights.step.collect.what",
      whatDefault:
        "Upload each signed waiver against the firm that gave it and the period it covers, so the file sits with the payment it belongs to rather than in an inbox. What is still missing is a list, not a recollection.",
      whyKey: "cases.trade_payment_for_lien_rights.step.collect.why",
      whyDefault:
        "Exposure on a job runs to everyone who supplied labor or material, not only the firms you hold a contract with. A waiver you cannot produce on request is, for practical purposes, a waiver you do not have, and the moment you need it is the moment somebody further down the chain says they were never paid.",
      moduleLabel: "Subcontractor Directory",
      moduleLabelKey: "nav.subcontractors",
      to: "/subcontractors",
    },
    {
      id: "waiver",
      icon: "FileSignature",
      inputs: [
        { labelKey: "cases.trade_payment_for_lien_rights.step.waiver.in.claim", label: "The payment application being paid" },
        { labelKey: "cases.trade_payment_for_lien_rights.step.waiver.in.cleared", label: "Whether the payment has cleared" },
      ],
      outputs: [
        { labelKey: "cases.trade_payment_for_lien_rights.step.waiver.out.type", label: "Conditional or unconditional, partial or final" },
        { labelKey: "cases.trade_payment_for_lien_rights.step.waiver.out.chain", label: "An append-only waiver history" },
      ],
      titleKey: "cases.trade_payment_for_lien_rights.step.waiver.title",
      titleDefault: "Attach the right kind of waiver to the right payment",
      whatKey: "cases.trade_payment_for_lien_rights.step.waiver.what",
      whatDefault:
        "Record the waiver against the payment application it releases, choosing across the two axes that matter: conditional or unconditional, partial or final. Waivers accumulate as a history rather than overwriting each other, so every period keeps its own release.",
      whyKey: "cases.trade_payment_for_lien_rights.step.waiver.why",
      whyDefault:
        "The two axes are the whole point. Conditional means the release takes effect when the money actually lands; unconditional means it already has, and signing one before the funds clear gives away the leverage for a payment that can still fail. Partial covers the period, final closes out the job. Getting the pair right is the difference between a release and a gift.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "release",
      icon: "KeyRound",
      inputs: [
        { labelKey: "cases.trade_payment_for_lien_rights.step.release.in.held", label: "Retainage held to date" },
        { labelKey: "cases.trade_payment_for_lien_rights.step.release.in.event", label: "The agreed release event" },
      ],
      outputs: [
        { labelKey: "cases.trade_payment_for_lien_rights.step.release.out.released", label: "Retainage released on the event" },
        { labelKey: "cases.trade_payment_for_lien_rights.step.release.out.trail", label: "What was released, when and why" },
      ],
      titleKey: "cases.trade_payment_for_lien_rights.step.release.title",
      titleDefault: "Release the retainage on an event, not on a reminder",
      whatKey: "cases.trade_payment_for_lien_rights.step.release.what",
      whatDefault:
        "Set the event that releases retainage on the contract itself, then release against it when the event occurs. The percentage held and the event that frees it are contract terms, so they are recorded once with the contract rather than renegotiated at the end from memory.",
      whyKey: "cases.trade_payment_for_lien_rights.step.release.why",
      whyDefault:
        "Retainage is the contractor's own money, withheld for a while and then quietly forgotten by everyone who is not owed it. Tied to a named event it becomes due on a date somebody can point at; left informal it becomes the last unresolved line on a job nobody wants to reopen, and it is routinely the largest sum still outstanding when a project closes.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "reconcile",
      icon: "Landmark",
      inputs: [
        { labelKey: "cases.trade_payment_for_lien_rights.step.reconcile.in.paid", label: "Payments made and received" },
        { labelKey: "cases.trade_payment_for_lien_rights.step.reconcile.in.waivers", label: "Waivers on file for each" },
      ],
      outputs: [
        { labelKey: "cases.trade_payment_for_lien_rights.step.reconcile.out.clean", label: "Every payment matched to its release" },
        { labelKey: "cases.trade_payment_for_lien_rights.step.reconcile.out.open", label: "Remaining exposure, named" },
      ],
      titleKey: "cases.trade_payment_for_lien_rights.step.reconcile.title",
      titleDefault: "Close the loop between money out and rights released",
      whatKey: "cases.trade_payment_for_lien_rights.step.reconcile.what",
      whatDefault:
        "Reconcile the payments against the waivers held for them, so the answer to what has been paid and what has actually been released is one view rather than two lists somebody compares by hand.",
      whyKey: "cases.trade_payment_for_lien_rights.step.reconcile.why",
      whyDefault:
        "A payment without its matching release is not a closed transaction, it is an open exposure that looks closed in the ledger. The gap between the two lists is the thing a lender, a surety or a title company will ask you to produce, usually at the point where the job is otherwise finished.",
      // Project-scoped, matching the 22 playbooks that already send a reader to
      // finance. The bare `/finance` route is declared and would pass the route
      // gate, but this case reconciles one project's payments, and the two
      // routes are different surfaces rather than aliases. `/subcontractors`
      // above is the opposite call: there the project-scoped path is a redirect
      // to the bare one, so the bare one is the real destination.
      moduleLabel: "Finance",
      moduleLabelKey: "finance.title",
      to: "/projects/:projectId/finance",
    },
  ],
};

export default playbook;
