// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Certify the month against the mediciones" (ES).
//
// A certificacion de obra is a valuation of work executed, approved by the
// direccion facultativa, and it is what an invoice may be issued against. The
// platform earns against a bill position from a recorded percent complete
// (earned quantity is the design quantity times the percent, and the earned
// amount is the position total times the same), so the case is honest about
// where the number comes from: it is measured progress against the contract
// quantity, and a quantity that has genuinely changed is a change to the
// position rather than a footnote on the certificacion. The payment clock registry
// ships no Spanish row, so the regime used here is the European late-payment
// one, which is what Ley 3/2004 implements in Spain. The case names that as the
// national frame rather than implying a Spanish statutory clock of its own.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "certify-the-month-against-the-mediciones",
  order: 1145,
  region: "ES",
  category: "commercial",
  companyTypes: ["general-contractor", "cost-consultant", "developer-client"],
  roles: ["quantity-surveyor", "commercial-manager", "site-manager"],
  icon: "Percent",
  titleKey: "cases.certify_the_month_against_the_mediciones.title",
  titleDefault: "Certify the month against the mediciones",
  descKey: "cases.certify_the_month_against_the_mediciones.desc",
  descDefault:
    "Measure what was executed against each partida, value it at the contract rates, get the certificacion approved by the direccion facultativa, invoice against the approved figure and start the payment clock on the right day.",
  longDescKey: "cases.certify_the_month_against_the_mediciones.longdesc",
  longDescDefault:
    "A certificacion is a measurement before it is a payment. The valuation follows from what was executed against each partida of the contract bill, at the rates the contract fixed, and the month's certificacion is the difference between this cumulative figure and the last one. Two habits decide whether it goes through in a week or in six. Measure against the partidas rather than against a percentage of the job, because a single project-level percent is impossible to check and therefore impossible to approve quickly. And treat an exceso de medicion as what it is: a quantity that has outgrown the contract, needing an order behind it before it is certified, not a bigger number quietly added to the same line.",
  estMinutes: 18,
  steps: [
    {
      id: "measure",
      icon: "Ruler",
      inputs: [
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.measure.in.works",
          label: "Works executed this period",
        },
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.measure.in.positions",
          label: "Contract bill positions",
        },
      ],
      outputs: [
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.measure.out.percent",
          label: "Percent complete per partida",
        },
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.measure.out.quantities",
          label: "Earned quantities for the period",
        },
      ],
      titleKey: "cases.certify_the_month_against_the_mediciones.step.measure.title",
      titleDefault: "Measure the period partida by partida",
      whatKey: "cases.certify_the_month_against_the_mediciones.step.measure.what",
      whatDefault:
        "Record what is executed against each partida for the period as a percentage of its contract quantity. The earned quantity follows from that percentage and the design quantity, and the earned amount from the same percentage and the position total, so one honest number per line produces the whole valuation.",
      whyKey: "cases.certify_the_month_against_the_mediciones.step.measure.why",
      whyDefault:
        "A certificacion built from a single project percentage cannot be checked and therefore cannot be approved without a conversation. Measured line by line, the disagreement is about one partida rather than about the whole month, and the rest of the money moves while that one is settled.",
      moduleLabel: "Progress",
      moduleLabelKey: "nav.progress",
      to: "/progress",
    },
    {
      id: "value",
      icon: "Calculator",
      inputs: [
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.value.in.quantities",
          label: "Earned quantities for the period",
        },
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.value.in.rates",
          label: "Contract unit rates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.value.out.valuation",
          label: "Valuation by capitulo",
        },
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.value.out.excess",
          label: "Excesos de medicion flagged",
        },
      ],
      titleKey: "cases.certify_the_month_against_the_mediciones.step.value.title",
      titleDefault: "Value it at the contract rates",
      whatKey: "cases.certify_the_month_against_the_mediciones.step.value.what",
      whatDefault:
        "Read the valuation back against the bill, capitulo by capitulo, and check the rates it used are the contract rates. Where a partida has been measured past the quantity the contract carries, deal with it as a change to the position with an order behind it rather than as a larger figure on the same line.",
      whyKey: "cases.certify_the_month_against_the_mediciones.step.value.why",
      whyDefault:
        "An exceso certified quietly is an exceso the property can refuse at the final account, months after the work was built and paid for down the chain. Raising it as a change while it is small is the only version of that conversation where you are not asking to be paid for work already done.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "approve",
      icon: "Stamp",
      inputs: [
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.approve.in.valuation",
          label: "Valuation for the period",
        },
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.approve.in.approver",
          label: "Direccion facultativa named for approval",
        },
      ],
      outputs: [
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.approve.out.approved",
          label: "Approved certificacion",
        },
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.approve.out.date",
          label: "Approval date on record",
        },
      ],
      titleKey: "cases.certify_the_month_against_the_mediciones.step.approve.title",
      titleDefault: "Get it approved by the people who have to approve it",
      whatKey: "cases.certify_the_month_against_the_mediciones.step.approve.what",
      whatDefault:
        "Route the certificacion to the direccion facultativa, and on a public contract to whoever the contract adds after them. Keep the approval date, because the invoice follows the approval and the payment clock in the next step runs from the invoice, so an approval that slips moves everything behind it.",
      whyKey: "cases.certify_the_month_against_the_mediciones.step.approve.why",
      whyDefault:
        "Approval sitting in an inbox is the most common reason a certificacion is late, and it is invisible while it is happening because nobody has refused anything. A route with a date on each hop turns that into a question with an owner instead of a monthly complaint.",
      moduleLabel: "Approval routes",
      moduleLabelKey: "approvalRoutes.title",
      to: "/approval-routes",
    },
    {
      id: "invoice",
      icon: "ReceiptEuro",
      inputs: [
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.invoice.in.approved",
          label: "Approved certificacion",
        },
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.invoice.in.retention",
          label: "Retention and deductions",
        },
      ],
      outputs: [
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.invoice.out.invoice",
          label: "Invoice against the certificacion",
        },
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.invoice.out.ledger",
          label: "Amount carried into the accounts",
        },
      ],
      titleKey: "cases.certify_the_month_against_the_mediciones.step.invoice.title",
      titleDefault: "Invoice the approved figure, not your own",
      whatKey: "cases.certify_the_month_against_the_mediciones.step.invoice.what",
      whatDefault:
        "Raise the invoice against the approved certificacion, carrying the retention and any deduction the contract provides for, and reference the certificacion number on it. Where the work is between businesses the VAT treatment may be inversion del sujeto pasivo rather than a rate.",
      whyKey: "cases.certify_the_month_against_the_mediciones.step.invoice.why",
      whyDefault:
        "An invoice for a figure nobody approved is an invoice that will be returned, and the clock does not start on a returned invoice. Matching it to the certificacion also means the accounts and the valuation tell the same story at year end without anybody reconciling them by hand.",
      moduleLabel: "Finance",
      moduleLabelKey: "nav.finance",
      to: "/projects/:projectId/finance",
    },
    {
      id: "clock",
      icon: "Clock",
      inputs: [
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.clock.in.invoice",
          label: "Issued invoice and its date",
        },
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.clock.in.terms",
          label: "Contract payment terms",
        },
      ],
      outputs: [
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.clock.out.due",
          label: "Final date for payment",
        },
        {
          labelKey: "cases.certify_the_month_against_the_mediciones.step.clock.out.interest",
          label: "Interest rate basis if it is late",
        },
      ],
      titleKey: "cases.certify_the_month_against_the_mediciones.step.clock.title",
      titleDefault: "Start the payment clock on the right day",
      whatKey: "cases.certify_the_month_against_the_mediciones.step.clock.what",
      whatDefault:
        "Put the invoice on the payment clock under the European late-payment regime, which is what Ley 3/2004 implements in Spain. Thirty days between businesses by default, extendable to sixty by express agreement and no further unless the term is not grossly unfair, with interest at the European Central Bank reference rate plus eight points from the day it is missed. There is no Spanish regime of its own in the register, so on a public contract read the periods the LCSP fixes against the date it gives you.",
      whyKey: "cases.certify_the_month_against_the_mediciones.step.clock.why",
      whyDefault:
        "Late payment is normal in this market and interest is almost never claimed, which is precisely why it keeps happening. A tracked due date does not require you to claim anything; it just means the conversation happens on day thirty-five rather than at the final account, when nobody remembers which month was late.",
      moduleLabel: "Payment Clock",
      moduleLabelKey: "nav.payment_clock",
      to: "/payment-clock",
    },
  ],
};

export default playbook;
