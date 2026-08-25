// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Build a partida from its precio descompuesto" (ES).
//
// A Spanish presupuesto is not a price list, it is a tree: a partida carries a
// descomposicion of mano de obra, materiales and maquinaria at stated
// rendimientos, and any part of it that is itself made on site is a precio
// auxiliar with a descomposicion of its own. The platform models both with the
// same object, an assembly whose components carry a resource type, a factor
// and a quantity, so an auxiliar is built first and then priced into the
// partida above it exactly the way a base de precios does it.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "build-a-precio-descompuesto",
  order: 1141,
  region: "ES",
  category: "estimating",
  companyTypes: ["cost-consultant", "general-contractor", "subcontractor"],
  roles: ["estimator", "quantity-surveyor"],
  icon: "Layers",
  titleKey: "cases.build_a_precio_descompuesto.title",
  titleDefault: "Build a partida from its precio descompuesto",
  descKey: "cases.build_a_precio_descompuesto.desc",
  descDefault:
    "Price the resources once, build the precios auxiliares your work is actually made of, compose the partida from them at stated rendimientos, and let the unit rate be calculated rather than typed in.",
  longDescKey: "cases.build_a_precio_descompuesto.longdesc",
  longDescDefault:
    "The descomposicion is what makes a Spanish presupuesto defensible: anyone reading it can see how many hours of oficial and how many kilos of steel are behind a square metre, and can argue with the rendimiento rather than with the price. Building it in the platform uses one object twice. A precio auxiliar, the mortero or the hormigon made on site, is an assembly of resources; the partida above it is an assembly that includes that auxiliar as a component alongside its own labour, material and plant. Costes indirectos and medios auxiliares go in as their own components rather than as a coefficient nobody can see, so the rate the bill shows is the sum of things a reader can check.",
  estMinutes: 20,
  steps: [
    {
      id: "resources",
      icon: "Database",
      inputs: [
        {
          labelKey: "cases.build_a_precio_descompuesto.step.resources.in.quotes",
          label: "Supplier quotes and labour costs",
        },
        {
          labelKey: "cases.build_a_precio_descompuesto.step.resources.in.units",
          label: "Units of measure",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_a_precio_descompuesto.step.resources.out.rates",
          label: "Priced resource rates",
        },
        {
          labelKey: "cases.build_a_precio_descompuesto.step.resources.out.typed",
          label: "Labour, material and plant separated",
        },
      ],
      titleKey: "cases.build_a_precio_descompuesto.step.resources.title",
      titleDefault: "Price the resources once",
      whatKey: "cases.build_a_precio_descompuesto.step.resources.what",
      whatDefault:
        "Put the mano de obra, materiales and maquinaria into the catalog as priced resources, each with the unit it is bought or paid in and a resource type that says which of the three it is. An hour of oficial de primera, a tonne of cement, a day of retroexcavadora.",
      whyKey: "cases.build_a_precio_descompuesto.step.resources.why",
      whyDefault:
        "Every partida in the presupuesto will lean on these same few dozen rates. Priced once, a change to the steel price moves every partida that contains steel in one edit. Priced inside each partida, the same change is a search through four hundred lines and you will miss some.",
      moduleLabel: "Resource Catalog",
      moduleLabelKey: "catalog.title",
      to: "/catalog",
    },
    {
      id: "auxiliar",
      icon: "FlaskConical",
      inputs: [
        {
          labelKey: "cases.build_a_precio_descompuesto.step.auxiliar.in.rates",
          label: "Priced resource rates",
        },
        {
          labelKey: "cases.build_a_precio_descompuesto.step.auxiliar.in.recipe",
          label: "Mix quantities per unit",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_a_precio_descompuesto.step.auxiliar.out.aux",
          label: "Precio auxiliar with a computed rate",
        },
      ],
      titleKey: "cases.build_a_precio_descompuesto.step.auxiliar.title",
      titleDefault: "Build the precios auxiliares first",
      whatKey: "cases.build_a_precio_descompuesto.step.auxiliar.what",
      whatDefault:
        "Anything made on site before it goes into the work is an auxiliar: the mortero, the hormigon amasado en obra, the encofrado you assemble and reuse. Build each one as its own assembly, in its own unit, from the resources you just priced.",
      whyKey: "cases.build_a_precio_descompuesto.step.auxiliar.why",
      whyDefault:
        "The mortero appears in the brickwork, the rendering and the paving, and it is one mix. Modelled once as an auxiliar it stays one number in three partidas. Retyped into each of them it is three numbers that drift apart the first time the sand price moves, and nobody notices which one is stale.",
      moduleLabel: "Assemblies",
      moduleLabelKey: "nav.assemblies",
      to: "/assemblies",
    },
    {
      id: "compose",
      icon: "Combine",
      inputs: [
        {
          labelKey: "cases.build_a_precio_descompuesto.step.compose.in.aux",
          label: "Precios auxiliares priced",
        },
        {
          labelKey: "cases.build_a_precio_descompuesto.step.compose.in.rendimientos",
          label: "Rendimientos per unit of work",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_a_precio_descompuesto.step.compose.out.assembly",
          label: "Partida assembly with a built-up rate",
        },
        {
          labelKey: "cases.build_a_precio_descompuesto.step.compose.out.breakdown",
          label: "Readable priced breakdown",
        },
      ],
      titleKey: "cases.build_a_precio_descompuesto.step.compose.title",
      titleDefault: "Compose the partida at stated rendimientos",
      whatKey: "cases.build_a_precio_descompuesto.step.compose.what",
      whatDefault:
        "Build the partida as an assembly in the unit the bill measures it in, and give every component the quantity of that resource one unit of work consumes. Add the costes indirectos and the medios auxiliares as their own components so a reader can see them rather than infer them from a coefficient.",
      whyKey: "cases.build_a_precio_descompuesto.step.compose.why",
      whyDefault:
        "The rendimiento is the number the argument is actually about. Written down, a client who thinks one point three hours per square metre is generous can say so and you can answer with a postcalc. Buried in a lump rate, the same disagreement comes out as a claim that you are expensive, and there is nothing to point at.",
      moduleLabel: "Assemblies",
      moduleLabelKey: "nav.assemblies",
      to: "/assemblies",
    },
    {
      id: "apply",
      icon: "Calculator",
      inputs: [
        {
          labelKey: "cases.build_a_precio_descompuesto.step.apply.in.assembly",
          label: "Partida assembly and its rate",
        },
        {
          labelKey: "cases.build_a_precio_descompuesto.step.apply.in.positions",
          label: "Bill positions to price",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_a_precio_descompuesto.step.apply.out.priced",
          label: "Priced bill positions",
        },
        {
          labelKey: "cases.build_a_precio_descompuesto.step.apply.out.linked",
          label: "Rate linked to its breakdown",
        },
      ],
      titleKey: "cases.build_a_precio_descompuesto.step.apply.title",
      titleDefault: "Put the calculated rate on the bill",
      whatKey: "cases.build_a_precio_descompuesto.step.apply.what",
      whatDefault:
        "Apply the assembly to the position in the bill so the unit rate is the total of the descomposicion rather than a number somebody keyed in. Do the same for the partidas that share a recipe and differ only in thickness or diameter.",
      whyKey: "cases.build_a_precio_descompuesto.step.apply.why",
      whyDefault:
        "A typed rate and its breakdown stop agreeing the moment either changes, and the bill is the one everybody reads. Linking them means the presupuesto you print and the calculation you defend are the same arithmetic, which is the whole reason for building the descomposicion in the first place.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "keep",
      icon: "Warehouse",
      inputs: [
        {
          labelKey: "cases.build_a_precio_descompuesto.step.keep.in.assemblies",
          label: "Finished descompuesto rates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_a_precio_descompuesto.step.keep.out.database",
          label: "Your own cost database",
        },
        {
          labelKey: "cases.build_a_precio_descompuesto.step.keep.out.reuse",
          label: "Rates ready for the next estimate",
        },
      ],
      titleKey: "cases.build_a_precio_descompuesto.step.keep.title",
      titleDefault: "Keep it as your own base de precios",
      whatKey: "cases.build_a_precio_descompuesto.step.keep.what",
      whatDefault:
        "Move the descompuestos you are happy with into the cost database as your own base de precios, with the codes you want to search by. The next presupuesto starts from these instead of from a published base you have to correct in the same three places every time.",
      whyKey: "cases.build_a_precio_descompuesto.step.keep.why",
      whyDefault:
        "A published base de precios is a good starting point and a poor finishing one: its rendimientos are regional averages and its prices are last year's. The version corrected by your own jobs is worth more than either, and it only accumulates if somebody puts it somewhere other than in the last project folder.",
      moduleLabel: "Cost Database",
      moduleLabelKey: "costs.title",
      to: "/costs",
    },
  ],
};

export default playbook;
