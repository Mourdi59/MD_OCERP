// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The documents of a project that an item can count: contracts, purchase
// orders, change and variation orders, and the packages an award comes from.
//
// The commitment API takes a document id and has no list of its own, so the
// picker reads each kind from the module that owns it. Those lists answer as
// a bare array or as a page, and name their rows differently; this file
// reduces every row to an id and one readable line.

import { apiGet } from '@/shared/lib/api';

import type { LinkKind } from './api';

export interface DocumentOption {
  id: string;
  /** "SC-014 Structural works": the number or code, then the title. */
  label: string;
}

/** Kinds the picker offers. A contract line is linked through its contract. */
export const PICKABLE_KINDS: readonly LinkKind[] = [
  'contract',
  'purchase_order',
  'change_order',
  'variation_order',
  'tender_package',
  'bid_package',
  'rfq',
];

const LIST_PATH: Record<string, (projectId: string) => string> = {
  contract: (id) => `/v1/contracts/contracts/?project_id=${id}&limit=100`,
  purchase_order: (id) => `/v1/procurement/?project_id=${id}&limit=100`,
  change_order: (id) => `/v1/changeorders/?project_id=${id}`,
  variation_order: (id) => `/v1/variations/variation-orders/?project_id=${id}&limit=100`,
  tender_package: (id) => `/v1/tendering/packages/?project_id=${id}`,
  bid_package: (id) => `/v1/bid-management/bid-packages/?project_id=${id}&limit=100`,
  rfq: (id) => `/v1/rfq-bidding/?project_id=${id}`,
};

type Row = Record<string, unknown>;

const text = (value: unknown): string => (typeof value === 'string' ? value.trim() : '');

/** One readable line for a row of any of the lists: its number or code, then its title or name. */
export function documentLabel(row: Row): string {
  const number = text(row.code) || text(row.po_number) || text(row.rfq_number) || text(row.vo_number) || text(row.number);
  const title = text(row.title) || text(row.name) || text(row.description);
  return [number, title].filter(Boolean).join(' ');
}

export function toDocumentOptions(payload: unknown): DocumentOption[] {
  const rows: unknown[] = Array.isArray(payload)
    ? payload
    : payload && typeof payload === 'object' && Array.isArray((payload as { items?: unknown }).items)
      ? (payload as { items: unknown[] }).items
      : [];
  const options: DocumentOption[] = [];
  for (const raw of rows) {
    if (!raw || typeof raw !== 'object') continue;
    const row = raw as Row;
    const id = text(row.id);
    if (!id) continue;
    options.push({ id, label: documentLabel(row) || id });
  }
  return options;
}

export async function listDocuments(projectId: string, kind: LinkKind): Promise<DocumentOption[]> {
  const path = LIST_PATH[kind];
  if (!path) return [];
  return toDocumentOptions(await apiGet<unknown>(path(projectId)));
}
