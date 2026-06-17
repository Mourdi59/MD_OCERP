/**
 * Bordereau de prix API client.
 *
 * A "bordereau" is a shareable, deduplicated price schedule — the single
 * source of truth for unit prices across one or more BOQs.
 */

import { apiGet, apiPost, apiPatch, apiPut, apiDelete } from '@/shared/lib/api';

// ── Types ────────────────────────────────────────────────────────────────────

export interface Bordereau {
  id: string;
  project_id: string;
  name: string;
  description: string;
  currency: string;
  status: string;
  is_locked: boolean;
  created_at: string;
  updated_at: string;
  line_count: number;
  attached_boq_count: number;
}

export interface BordereauWithLines extends Bordereau {
  lines: BordereauLine[];
}

export interface BordereauLine {
  id: string;
  bordereau_id: string;
  reference_code: string | null;
  designation: string;
  unit: string;
  unit_rate: number;
  is_assembly: boolean;
  source: string;
  version: number;
  sort_order: number;
  position_count: number;
  components: BordereauComponent[];
}

export interface BordereauComponent {
  id: string;
  line_id: string;
  cost_item_id: string | null;
  description: string;
  resource_type: string | null;
  factor: number;
  quantity: number;
  unit: string;
  unit_cost: number;
  total: number;
  sort_order: number;
}

export interface PropagationResult {
  line_id: string;
  affected_boq_ids: string[];
  positions_updated: number;
  locked_boqs_skipped: string[];
}

export interface CreateBordereauData {
  project_id: string;
  name: string;
  description?: string;
  currency?: string;
}

export interface UpdateBordereauData {
  name?: string;
  description?: string;
  currency?: string;
  status?: string;
  is_locked?: boolean;
}

export interface CreateLineData {
  reference_code?: string | null;
  designation: string;
  unit: string;
  unit_rate?: number;
  is_assembly?: boolean;
  source?: string;
}

export interface UpdateLineData {
  designation?: string;
  unit?: string;
  unit_rate?: number;
  reference_code?: string | null;
  is_assembly?: boolean;
  /** Must echo the current line.version to detect concurrent edits (409 on mismatch). */
  version?: number;
}

export interface CreateComponentData {
  cost_item_id?: string | null;
  description: string;
  resource_type?: string | null;
  factor?: number;
  quantity?: number;
  unit: string;
  unit_cost: number;
}

export interface ResolveLineData {
  reference_code?: string | null;
  designation: string;
  unit: string;
}

export interface ResolveLineResponse {
  line: BordereauLine;
  created: boolean;
}

// ── Drag-and-drop contract (drawer → BOQ grid) ───────────────────────────────

/** Custom dataTransfer MIME type carrying a bordereau line across the drag. */
export const BORDEREAU_LINE_MIME = 'application/x-oe-bordereau-line';

/** Payload serialized into dataTransfer on dragstart in the BordereauDrawer. */
export interface BordereauLineDragPayload {
  lineId: string;
  designation: string;
  unit: string;
  unit_rate: number;
  is_assembly: boolean;
}

// ── API client ───────────────────────────────────────────────────────────────

export const bordereauApi = {
  // ── Bordereau CRUD ──────────────────────────────────────────────────

  list(projectId: string): Promise<Bordereau[]> {
    return apiGet<Bordereau[]>(`/v1/bordereau/bordereaux/?project_id=${projectId}`);
  },

  get(bordereauId: string): Promise<BordereauWithLines> {
    return apiGet<BordereauWithLines>(`/v1/bordereau/bordereaux/${bordereauId}`);
  },

  create(data: CreateBordereauData): Promise<Bordereau> {
    return apiPost<Bordereau, CreateBordereauData>('/v1/bordereau/bordereaux/', data);
  },

  update(bordereauId: string, data: UpdateBordereauData): Promise<Bordereau> {
    return apiPatch<Bordereau, UpdateBordereauData>(
      `/v1/bordereau/bordereaux/${bordereauId}`,
      data,
    );
  },

  remove(bordereauId: string): Promise<void> {
    return apiDelete<void>(`/v1/bordereau/bordereaux/${bordereauId}`);
  },

  // ── Attach / Detach ─────────────────────────────────────────────────

  attach(boqId: string, bordereauId: string): Promise<{ boq_id: string; bordereau_id: string; attached: boolean; positions_linked: number }> {
    return apiPost(`/v1/bordereau/boqs/${boqId}/bordereau`, { bordereau_id: bordereauId });
  },

  detach(boqId: string): Promise<void> {
    return apiDelete<void>(`/v1/bordereau/boqs/${boqId}/bordereau`);
  },

  // ── Lines ────────────────────────────────────────────────────────────

  listLines(bordereauId: string): Promise<BordereauLine[]> {
    return apiGet<BordereauLine[]>(`/v1/bordereau/bordereaux/${bordereauId}/lines`);
  },

  createLine(bordereauId: string, data: CreateLineData): Promise<BordereauLine> {
    return apiPost<BordereauLine, CreateLineData>(
      `/v1/bordereau/bordereaux/${bordereauId}/lines`,
      data,
    );
  },

  updateLine(
    bordereauId: string,
    lineId: string,
    data: UpdateLineData,
  ): Promise<PropagationResult> {
    return apiPatch<PropagationResult, UpdateLineData>(
      `/v1/bordereau/bordereaux/${bordereauId}/lines/${lineId}`,
      data,
    );
  },

  deleteLine(bordereauId: string, lineId: string): Promise<void> {
    return apiDelete<void>(`/v1/bordereau/bordereaux/${bordereauId}/lines/${lineId}`);
  },

  // ── Components ───────────────────────────────────────────────────────

  listComponents(bordereauId: string, lineId: string): Promise<BordereauComponent[]> {
    return apiGet<BordereauComponent[]>(
      `/v1/bordereau/bordereaux/${bordereauId}/lines/${lineId}/components`,
    );
  },

  replaceComponents(
    bordereauId: string,
    lineId: string,
    components: CreateComponentData[],
  ): Promise<PropagationResult> {
    return apiPut<PropagationResult, CreateComponentData[]>(
      `/v1/bordereau/bordereaux/${bordereauId}/lines/${lineId}/components`,
      components,
    );
  },

  // ── Resolve (dedup) ──────────────────────────────────────────────────

  resolve(bordereauId: string, data: ResolveLineData): Promise<ResolveLineResponse> {
    return apiPost<ResolveLineResponse, ResolveLineData>(
      `/v1/bordereau/bordereaux/${bordereauId}/resolve`,
      data,
    );
  },

  // ── Position link / unlink ───────────────────────────────────────────

  linkPosition(
    positionId: string,
    lineId: string,
  ): Promise<{ position_id: string; bordereau_line_id: string; unit_rate: number }> {
    return apiPost(`/v1/bordereau/positions/${positionId}/bordereau-link`, { line_id: lineId });
  },

  unlinkPosition(
    positionId: string,
  ): Promise<{ position_id: string; bordereau_line_id: null; unit_rate: number }> {
    return apiDelete(`/v1/bordereau/positions/${positionId}/bordereau-link`);
  },
};
