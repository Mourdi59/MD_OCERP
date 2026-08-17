// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Estimate with your own crew rates" (US).
//
// The objection is "we have no rate database and the commercial suppliers do",
// which treats a priced catalogue as the thing that makes estimating possible.
// The case answers it the other way round: the numbers a contractor already
// has, what they pay their own crews and what their own suppliers quoted, are
// better evidence than any national average, and the work is assembling them
// once rather than buying them yearly.
//
// The US-specific weight is the crew rate. An American estimator prices labour
// as a crew with a burdened hourly rate and a production rate, not as a
// national unit price, and federal work often wants the cost split into labour,
// material and equipment. Burden components are named as categories rather than
// as rates: the percentages differ by state, by trade and by year, and a number
// printed here would be an unverified claim in user-facing copy. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "estimate-with-your-own-crew-rates",
  order: 1063,
  region: "US",
  category: "estimating",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  roles: ["estimator", "quantity-surveyor", "commercial-manager"],
  icon: "Calculator",
  titleKey: "cases.estimate_with_your_own_crew_rates.title",
  titleDefault: "Estimate with your own crew rates",
  descKey: "cases.estimate_with_your_own_crew_rates.desc",
  descDefault:
    "Build a burdened crew rate from what you actually pay, add your own material and equipment prices, let waste and coverage turn quantities into purchases, and combine them into assemblies that reprice themselves when a rate moves.",
  longDescKey: "cases.estimate_with_your_own_crew_rates.longdesc",
  longDescDefault:
    "The usual reason a contractor rents a commercial rate catalogue is that building one sounds like a year of work. It is not: the numbers are already in your payroll, your last three purchase orders and the quotes on your desk, and they are worth more than a national average because they are what this company, in this city, actually pays. This case assembles them once so an estimate stops being a spreadsheet of remembered numbers. What sits on top of the base cost, the overhead and profit, bonds, insurance, contingency and escalation, is a separate decision each company makes its own way, and it is applied over rates you can defend rather than over rates you rented.",
  estMinutes: 20,
  steps: [
    {
      id: "crew",
      icon: "HardHat",
      inputs: [
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.crew.in.wages", label: "Base wages by trade" },
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.crew.in.burden", label: "Payroll taxes, insurance and fringe" },
      ],
      outputs: [
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.crew.out.rate", label: "Burdened hourly rate per trade" },
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.crew.out.crew", label: "Crew rate for the mix you send out" },
      ],
      titleKey: "cases.estimate_with_your_own_crew_rates.step.crew.title",
      titleDefault: "Start with what an hour of your crew actually costs",
      whatKey: "cases.estimate_with_your_own_crew_rates.step.crew.what",
      whatDefault:
        "Enter the base wage for each trade you employ, then add the burden that rides on it: payroll taxes, workers compensation, liability insurance and any fringe you pay. Group the trades into the crews you actually dispatch, so a rate describes a truck that shows up rather than one worker in isolation.",
      whyKey: "cases.estimate_with_your_own_crew_rates.step.crew.why",
      whyDefault:
        "An unburdened wage understates the cost of an hour by a margin large enough to lose a job on, and it is the single most common reason a bid that looked profitable was not. Burden also varies more than people expect between states and trades, which is exactly why your own figure beats a published one.",
      moduleLabel: "Labor Rates",
      moduleLabelKey: "nav.labor_rates",
      to: "/labor-rates",
    },
    {
      id: "prices",
      icon: "Database",
      inputs: [
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.prices.in.quotes", label: "Supplier quotes and past purchase orders" },
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.prices.in.plant", label: "Owned and rented equipment costs" },
      ],
      outputs: [
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.prices.out.items", label: "Priced material and equipment items" },
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.prices.out.source", label: "Each price traceable to its source" },
      ],
      titleKey: "cases.estimate_with_your_own_crew_rates.step.prices.title",
      titleDefault: "Put your own prices in, with where they came from",
      whatKey: "cases.estimate_with_your_own_crew_rates.step.prices.what",
      whatDefault:
        "Load the material and equipment prices you have evidence for, from supplier quotes and the purchase orders you already placed, and keep the source and the date on each one rather than entering a bare number.",
      whyKey: "cases.estimate_with_your_own_crew_rates.step.prices.why",
      whyDefault:
        "A price with a source can be defended in a bid review and updated when the quote expires. A price without one is a number somebody typed, and within a year nobody on the team will know whether it is still true or who to ask.",
      // `nav.costs`, not `costs.title`: both answer "Cost Database" in English,
      // and the existing playbooks settled on this one. Two keys behind one
      // label is how the same chip starts reading differently in another
      // locale, which is exactly the divergence P-16 tracks.
      moduleLabel: "Cost Database",
      moduleLabelKey: "costs.title",
      to: "/costs",
    },
    {
      id: "waste",
      icon: "Ruler",
      inputs: [
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.waste.in.net", label: "Net measured quantity" },
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.waste.in.coverage", label: "Coverage and pack size" },
      ],
      outputs: [
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.waste.out.buy", label: "The quantity you actually buy" },
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.waste.out.factor", label: "Waste allowance per material" },
      ],
      titleKey: "cases.estimate_with_your_own_crew_rates.step.waste.title",
      titleDefault: "Turn the measured quantity into the purchased quantity",
      whatKey: "cases.estimate_with_your_own_crew_rates.step.waste.what",
      whatDefault:
        "Set the waste allowance and the coverage rate per material, so a measured area becomes the number of units ordered, rounded the way the material is actually sold.",
      whyKey: "cases.estimate_with_your_own_crew_rates.step.waste.why",
      whyDefault:
        "Takeoff measures the building; the invoice measures what was delivered, and the two are never the same number. Keeping the allowance explicit per material means the difference is a stated assumption somebody can argue with, rather than a pad hidden inside a unit rate.",
      moduleLabel: "Waste Factors",
      moduleLabelKey: "nav.waste_factors",
      to: "/waste-factors",
    },
    {
      id: "assembly",
      icon: "Layers",
      inputs: [
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.assembly.in.rates", label: "Crew rates and priced items" },
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.assembly.in.output", label: "Production rate per crew" },
      ],
      outputs: [
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.assembly.out.unit", label: "A unit rate you can explain" },
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.assembly.out.split", label: "Labor, material and equipment kept apart" },
      ],
      titleKey: "cases.estimate_with_your_own_crew_rates.step.assembly.title",
      titleDefault: "Assemble the unit rate so it rebuilds itself",
      whatKey: "cases.estimate_with_your_own_crew_rates.step.assembly.what",
      whatDefault:
        "Combine the crew rate, the production rate and the materials into an assembly for the work you do repeatedly, keeping labor, material and equipment as separate components rather than collapsing them into one figure.",
      whyKey: "cases.estimate_with_your_own_crew_rates.step.assembly.why",
      whyDefault:
        "Two things follow from the split. When a wage or a supplier price moves, every assembly built on it reprices without anyone reopening old estimates, which is the difference between a rate base and a spreadsheet. And where a contract asks for the cost broken into labor, material and equipment, as federal work commonly does, the breakdown already exists instead of being reconstructed under deadline.",
      moduleLabel: "Assemblies",
      moduleLabelKey: "nav.assemblies",
      to: "/assemblies",
    },
    {
      id: "escalation",
      icon: "TrendingUp",
      inputs: [
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.escalation.in.dated", label: "Rates with the date they were set" },
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.escalation.in.window", label: "Bid date and construction window" },
      ],
      outputs: [
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.escalation.out.current", label: "Rates moved to bid day" },
        { labelKey: "cases.estimate_with_your_own_crew_rates.step.escalation.out.stated", label: "Escalation stated, not buried" },
      ],
      titleKey: "cases.estimate_with_your_own_crew_rates.step.escalation.title",
      titleDefault: "Move last year's rates to the day you bid",
      whatKey: "cases.estimate_with_your_own_crew_rates.step.escalation.what",
      whatDefault:
        "Track how your own rates have moved over time and carry them forward to the bid date, and where the work runs long, forward again to the midpoint of construction rather than pricing everything at today.",
      whyKey: "cases.estimate_with_your_own_crew_rates.step.escalation.why",
      whyDefault:
        "A rate base decays quietly. Nobody notices a catalogue is eighteen months old until the material arrives at a different price, and by then the number is in a contract. Escalation applied as a visible step is a decision the reviewer can check; escalation applied by feel is a guess nobody can find later.",
      moduleLabel: "Price Index",
      moduleLabelKey: "nav.price_index",
      to: "/price-index",
    },
  ],
};

export default playbook;
