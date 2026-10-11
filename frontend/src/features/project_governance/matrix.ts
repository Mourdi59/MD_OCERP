// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The areas x phases matrix, built from what the list endpoints return.
//
// A column is a phase and the gate that leaves it. A cell is the frame
// documents that area owes at that gate, plus readiness where the client
// knows it: the outcome of a decided gate, and the area check of the next
// gate (the only gate whose detail the screen loads, one request instead of
// one per gate). Gates further ahead have no readiness yet, which is what the
// cell then says.

import type {
  CheckStatus,
  DocumentStatus,
  FrameDocument,
  GateDetail,
  GovernanceArea,
  GovernanceGate,
  GovernancePhase,
  Outcome,
} from './api';

export interface MatrixColumn {
  phase: GovernancePhase;
  gate: GovernanceGate | null;
  isCurrent: boolean;
}

export type CellReadiness =
  | { kind: 'decided'; outcome: Outcome | '' }
  | { kind: 'check'; status: CheckStatus; stale: boolean }
  | { kind: 'pending' }
  | { kind: 'none' };

export interface MatrixCell {
  documents: Array<{ id: string; docType: string; status: DocumentStatus }>;
  readiness: CellReadiness;
}

export interface MatrixRow {
  area: GovernanceArea;
  cells: MatrixCell[];
}

export interface GovernanceMatrixData {
  columns: MatrixColumn[];
  rows: MatrixRow[];
}

/** The gate the project has to pass next: the first live gate, in order, that is not decided. */
export function nextGate(gates: GovernanceGate[]): GovernanceGate | null {
  const live = gates.filter((g) => !g.historic).sort((a, b) => a.sort_order - b.sort_order);
  return live.find((g) => g.status !== 'decided') ?? null;
}

export function buildMatrix(input: {
  phases: GovernancePhase[];
  currentPhase: string | null;
  areas: GovernanceArea[];
  gates: GovernanceGate[];
  documents: FrameDocument[];
  nextDetail: GateDetail | null;
}): GovernanceMatrixData {
  const phases = [...input.phases].sort((a, b) => a.order - b.order);
  const live = input.gates.filter((g) => !g.historic);
  const columns: MatrixColumn[] = phases.map((phase) => ({
    phase,
    gate: live.find((g) => g.from_phase === phase.code) ?? null,
    isCurrent: phase.code === input.currentPhase,
  }));
  const areas = input.areas.filter((a) => !a.retired).sort((a, b) => a.sort_order - b.sort_order);

  const rows = areas.map<MatrixRow>((area) => ({
    area,
    cells: columns.map<MatrixCell>(({ gate }) => {
      const documents = gate
        ? input.documents
            .filter((d) => d.area_id === area.id && d.required_at_gates.includes(gate.code))
            .map((d) => ({ id: d.id, docType: d.doc_type, status: d.status }))
        : [];
      return { documents, readiness: readinessOf(area, gate, input.nextDetail) };
    }),
  }));
  return { columns, rows };
}

function readinessOf(area: GovernanceArea, gate: GovernanceGate | null, detail: GateDetail | null): CellReadiness {
  if (!gate) return { kind: 'none' };
  if (gate.status === 'decided') return { kind: 'decided', outcome: gate.last_outcome };
  if (detail && detail.gate.id === gate.id) {
    if (!area.applicable) return { kind: 'check', status: 'not_applicable', stale: false };
    const row = detail.areas.find((a) => a.area_id === area.id);
    return { kind: 'check', status: row?.check?.status ?? 'not_assessed', stale: !!row?.check?.stale };
  }
  return { kind: 'pending' };
}
