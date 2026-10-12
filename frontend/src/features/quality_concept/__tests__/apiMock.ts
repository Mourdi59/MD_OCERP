// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// A mock of the REST client that keeps its pure helpers real. It lives apart
// from the render harness so the mock factory never imports the page.

import { vi } from 'vitest';

import type * as Api from '../api';

const REAL = new Set(['refusalDetail', 'localToday']);

/** Every request function becomes a mock; the pure helpers and the query keys stay real. */
export async function apiMock(importOriginal: () => Promise<typeof Api>): Promise<typeof Api> {
  const actual = await importOriginal();
  const out: Record<string, unknown> = { ...actual };
  for (const [name, value] of Object.entries(actual)) {
    if (typeof value === 'function' && !REAL.has(name)) out[name] = vi.fn();
  }
  return out as typeof Api;
}
