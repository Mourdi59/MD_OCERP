// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Read a FIEBDC-3 presupuesto somebody sent you" (ES).
//
// The shipped Spanish case exports a bill to FIEBDC-3. This one runs the other
// way, which is the direction a contractor and a cost consultant meet far more
// often: a promotor or an architect sends a BC3 and the answer is due in days.
//
// The honest part of the case is what the importer does NOT bring across. It
// reads the version record, the chapter and partida concepts, the extended
// texts and the measured total per partida. It does not build the
// descomposicion behind a rate, it does not keep the individual measurement
// lines behind a total, and it does not apply the coefficient record. Each of
// those is stated where the user would otherwise assume it, and the missing
// descomposicion is what carries the reader into the assemblies case.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "read-a-fiebdc3-presupuesto",
  order: 1140,
  region: "ES",
  category: "estimating",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  roles: ["estimator", "quantity-surveyor"],
  icon: "FolderInput",
  titleKey: "cases.read_a_fiebdc3_presupuesto.title",
  titleDefault: "Read a FIEBDC-3 presupuesto somebody sent you",
  descKey: "cases.read_a_fiebdc3_presupuesto.desc",
  descDefault:
    "Take the BC3 a promotor or an architect sends you, bring the capitulos and partidas in without retyping them, check the codes are ones you can send back, and rebuild by hand the two things the format carries but the import does not.",
  longDescKey: "cases.read_a_fiebdc3_presupuesto.longdesc",
  longDescDefault:
    "FIEBDC-3 is how a presupuesto travels in Spain, and receiving one is the ordinary case rather than the exception. The import brings across the chapter and partida hierarchy with codes, units, unit rates, the extended texts and the measured total on each partida, which is enough to answer the bill line for line. Two things stay behind on purpose. The descomposicion behind each unit rate, and the auxiliary resources it is built from, are read only far enough to tell an auxiliary apart from a partida, so a rate you need to defend is one you rebuild as an assembly of your own. The measurement detail behind a total, the lines of uds by largo by ancho by alto, is not retained either, so a quantity you doubt is one you re-measure rather than one you unpick. The coefficient record is captured and not applied, exactly as on the way out, so overhead, profit and IVA stay where the receiving side decides them.",
  estMinutes: 16,
  steps: [
    {
      id: "receive",
      icon: "FileInput",
      inputs: [
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.receive.in.file",
          label: "BC3 budget file",
        },
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.receive.in.invite",
          label: "Invitation and tender terms",
        },
      ],
      outputs: [
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.receive.out.filed",
          label: "Filed tender document",
        },
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.receive.out.revision",
          label: "Revision on record",
        },
      ],
      titleKey: "cases.read_a_fiebdc3_presupuesto.step.receive.title",
      titleDefault: "File the file before you open it",
      whatKey: "cases.read_a_fiebdc3_presupuesto.step.receive.what",
      whatDefault:
        "Save the BC3 exactly as it arrived into the project files, next to the invitation and the terms it came with. Do not rename it and do not open it in an editor first, because a save from the wrong tool rewrites the encoding and the accents in the partida texts go with it.",
      whyKey: "cases.read_a_fiebdc3_presupuesto.step.receive.why",
      whyDefault:
        "Presupuestos get reissued, sometimes twice in a week, and the question that arrives later is always which version you priced. A filed original answers it in one click. It also gives you something to compare against when the second file lands and nobody says what changed.",
      moduleLabel: "Documents",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
    {
      id: "import",
      icon: "Upload",
      inputs: [
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.import.in.file",
          label: "BC3 budget file",
        },
      ],
      outputs: [
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.import.out.positions",
          label: "Imported bill positions",
        },
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.import.out.tree",
          label: "Chapter and item tree",
        },
      ],
      titleKey: "cases.read_a_fiebdc3_presupuesto.step.import.title",
      titleDefault: "Import the presupuesto as a bill",
      whatKey: "cases.read_a_fiebdc3_presupuesto.step.import.what",
      whatDefault:
        "Import the BC3. Capitulos arrive as sections and partidas as positions, each with its concept code, its unit, the unit rate the sender carried and the measured total. The extended texts fill in the long descriptions, and the encoding is detected rather than assumed, so a file written in the Windows charset that market still uses reads correctly.",
      whyKey: "cases.read_a_fiebdc3_presupuesto.step.import.why",
      whyDefault:
        "Retyping a presupuesto of six hundred partidas is where a transposed quantity and a dropped line get in, and neither shows up until somebody prices them. Importing keeps your answer tied to the codes and the wording the sender issued, which is also what lets you hand a priced file back rather than a spreadsheet.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "verify",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.verify.in.positions",
          label: "Imported bill positions",
        },
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.verify.in.codes",
          label: "Concept code on every position",
        },
      ],
      outputs: [
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.verify.out.report",
          label: "Validation report",
        },
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.verify.out.checked",
          label: "Codes checked and cleared",
        },
      ],
      titleKey: "cases.read_a_fiebdc3_presupuesto.step.verify.title",
      titleDefault: "Check the codes you will have to send back",
      whatKey: "cases.read_a_fiebdc3_presupuesto.step.verify.what",
      whatDefault:
        "Run the bill through validation. The FIEBDC-3 rules ask two things of every position: that it kept a concept code at all, and that the code has a shape the format accepts, which rules out a stray space, a leading dot and the control characters a spreadsheet round trip leaves behind.",
      whyKey: "cases.read_a_fiebdc3_presupuesto.step.verify.why",
      whyDefault:
        "A position that lost its code prices perfectly well and then cannot be exported back to BC3 without losing the reference the sender uses to find it. That is discovered on the afternoon of the deadline, when the file will not open on their side and nobody can tell you which of six hundred lines is at fault.",
      moduleLabel: "Validation",
      moduleLabelKey: "validation.title",
      to: "/validation",
    },
    {
      id: "rebuild",
      icon: "Layers",
      inputs: [
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.rebuild.in.positions",
          label: "Partidas with a rate and no breakdown",
        },
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.rebuild.in.resources",
          label: "Your own resource rates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.rebuild.out.assembly",
          label: "Assembly with a built-up rate",
        },
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.rebuild.out.priced",
          label: "Priced breakdown you can defend",
        },
      ],
      titleKey: "cases.read_a_fiebdc3_presupuesto.step.rebuild.title",
      titleDefault: "Rebuild the descomposicion the import left behind",
      whatKey: "cases.read_a_fiebdc3_presupuesto.step.rebuild.what",
      whatDefault:
        "The import reads the decomposition records only far enough to tell an auxiliary resource apart from a real partida, so what you have is a rate without the mano de obra, materiales and maquinaria under it. Pick the partidas that carry your risk and build each one as an assembly with its own rendimientos and resource rates.",
      whyKey: "cases.read_a_fiebdc3_presupuesto.step.rebuild.why",
      whyDefault:
        "The sender's unit rate tells you what they expect to pay, not what the work costs you. Rebuilding the twenty partidas that hold most of the money is a morning's work and it is the only version of the number you can argue for afterwards, whether the argument is a baja to justify or a modificado to price.",
      moduleLabel: "Assemblies",
      moduleLabelKey: "nav.assemblies",
      to: "/assemblies",
    },
    {
      id: "record",
      icon: "NotebookPen",
      inputs: [
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.record.in.priced",
          label: "Priced bill positions",
        },
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.record.in.gaps",
          label: "Quantities taken on trust",
        },
      ],
      outputs: [
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.record.out.basis",
          label: "Written basis of estimate",
        },
        {
          labelKey: "cases.read_a_fiebdc3_presupuesto.step.record.out.flagged",
          label: "Assumptions flagged",
        },
      ],
      titleKey: "cases.read_a_fiebdc3_presupuesto.step.record.title",
      titleDefault: "Write down what you took on trust",
      whatKey: "cases.read_a_fiebdc3_presupuesto.step.record.what",
      whatDefault:
        "Record the assumptions the file forced on you. The measurement lines behind each total do not survive the import, so every quantity you did not re-measure yourself is a quantity you accepted from the sender, and that belongs in writing rather than in somebody's memory.",
      whyKey: "cases.read_a_fiebdc3_presupuesto.step.record.why",
      whyDefault:
        "A quantity accepted without comment becomes a quantity you warranted. Naming the ones you took as given costs a paragraph now and is the difference between a re-measure and an argument when the work on site turns out to be a third more than the partida said.",
      moduleLabel: "Basis of Estimate",
      moduleLabelKey: "nav.estimate_basis",
      to: "/estimate-basis",
    },
  ],
};

export default playbook;
