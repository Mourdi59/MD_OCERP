// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction

import { apiGet, apiDelete } from '@/shared/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RebarShape {
  id: string;
  shape_code: string;
  bar_mark: string;
  diameter: number;
  length: number;
  quantity: number;
  weight: number;
  member: string | null;
  super_group: string | null;
  parameters: Record<string, unknown>;
}

export interface RebarCuttingEntry {
  diameter: number;
  bar_count: number;
  total_weight: number;
}

export interface RebarImport {
  id: string;
  project_id: string;
  filename: string;
  shape_count: number;
  total_weight: number;
  created_at: string;
}

export interface RebarPreviewResponse {
  filename: string;
  shapes: RebarShape[];
  cutting: RebarCuttingEntry[];
  shape_count: number;
  total_weight: number;
  warnings: string[];
}

// ---------------------------------------------------------------------------
// Fetchers
// ---------------------------------------------------------------------------

const BASE = '/v1/rebar-schedule';

export async function fetchImports(projectId: string): Promise<RebarImport[]> {
  return apiGet<RebarImport[]>(`${BASE}/imports?project_id=${projectId}`);
}

export async function fetchImport(importId: string): Promise<RebarImport> {
  return apiGet<RebarImport>(`${BASE}/imports/${importId}`);
}

export async function fetchShapes(importId: string): Promise<RebarShape[]> {
  return apiGet<RebarShape[]>(`${BASE}/imports/${importId}/shapes`);
}

export async function fetchCutting(importId: string): Promise<RebarCuttingEntry[]> {
  return apiGet<RebarCuttingEntry[]>(`${BASE}/imports/${importId}/cutting`);
}

export async function deleteImport(importId: string): Promise<void> {
  return apiDelete(`${BASE}/imports/${importId}`);
}

/**
 * Upload and preview an ABS file without storing it.
 * Uses raw fetch + FormData because apiPost sets Content-Type to
 * application/json which breaks multipart uploads.
 */
export async function previewAbsFile(file: File): Promise<RebarPreviewResponse> {
  const token = useAuthStore.getState().accessToken;
  const form = new FormData();
  form.append('file', file);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90_000);

  try {
    const res = await fetch(`/api${BASE}/preview`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      const detail = typeof body?.detail === 'string' ? body.detail : 'Preview failed';
      throw new Error(detail);
    }

    return await res.json();
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('Server did not respond within 90 seconds. The file may be too large.');
    }
    throw err;
  }
}

/**
 * Import an ABS file into a project.
 * Same raw fetch pattern as preview.
 */
export async function importAbsFile(
  file: File,
  projectId: string,
): Promise<RebarImport> {
  const token = useAuthStore.getState().accessToken;
  const form = new FormData();
  form.append('file', file);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90_000);

  try {
    const res = await fetch(`/api${BASE}/imports?project_id=${projectId}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      const detail = typeof body?.detail === 'string' ? body.detail : 'Import failed';
      throw new Error(detail);
    }

    return await res.json();
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('Server did not respond within 90 seconds. The file may be too large.');
    }
    throw err;
  }
}
