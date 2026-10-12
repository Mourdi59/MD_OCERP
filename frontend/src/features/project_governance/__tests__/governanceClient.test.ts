// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The requests the governance client sends. A write never carries the
// reader's date: the server dates a decision, and a client date on a write
// was a way to make overdue conditions disappear.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/shared/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/lib/api')>();
  return {
    ...actual,
    apiGet: vi.fn(async () => ({})),
    apiPost: vi.fn(async () => ({})),
    apiPut: vi.fn(async () => ({})),
    apiPatch: vi.fn(async () => ({})),
  };
});

import * as http from '@/shared/lib/api';
import {
  addGateCondition,
  attachDocument,
  createDocument,
  decideGate,
  getGate,
  getMatrix,
  reopenGate,
  resumeGate,
  returnDocument,
  updateModelSettings,
} from '../api';

const post = vi.mocked(http.apiPost);
const get = vi.mocked(http.apiGet);
const patch = vi.mocked(http.apiPatch);

beforeEach(() => vi.clearAllMocks());

describe('governance client', () => {
  it('a decision is sent without a date', async () => {
    const body = {
      outcome: 'go' as const,
      rationale: '',
      conditions: [],
      proceed_at_risk_areas: [],
      accepted_not_applicable: [],
      hold_resume_date: null,
    };
    await decideGate('p1', 'g1', body);
    expect(post).toHaveBeenCalledWith('/v1/project-governance/projects/p1/gates/g1/decide', body);
  });

  it('no write of the client carries today', async () => {
    await decideGate('p1', 'g1', {
      outcome: 'stop',
      rationale: 'r',
      conditions: [],
      proceed_at_risk_areas: [],
      accepted_not_applicable: [],
    });
    await reopenGate('p1', 'g1', { rationale: 'r' });
    await resumeGate('p1', 'g1');
    await addGateCondition('p1', 'g1', { text: 'x', severity: 'essential' });
    await createDocument('p1', { area_id: 'a1', doc_type: 'charter' });
    await attachDocument('p1', 'd1', 'k1');
    await returnDocument('p1', 'd1');
    await updateModelSettings('p1', { decision_route_id: 'r1' });
    const urls = [...post.mock.calls, ...patch.mock.calls].map((c) => String(c[0]));
    expect(urls).toHaveLength(8);
    expect(urls.filter((u) => u.includes('today'))).toEqual([]);
  });

  it('the source has no write that builds a date into its address', () => {
    const source = readFileSync(join(__dirname, '../api.ts'), 'utf-8');
    const withToday = source.split('\n').filter((line) => line.includes('today=${'));
    // Only the two reads may say which calendar day the reader is in.
    expect(withToday).toHaveLength(2);
    expect(withToday.every((line) => line.includes('apiGet<'))).toBe(true);
  });

  it('the reads still say which day the reader is in', async () => {
    await getMatrix('p1');
    await getGate('p1', 'g1');
    expect(get.mock.calls.map((c) => String(c[0])).every((u) => /\?today=\d{4}-\d{2}-\d{2}$/.test(u))).toBe(true);
  });

  it('sends the new writes where the router takes them', async () => {
    await createDocument('p1', { area_id: 'a1', doc_type: 'charter' });
    expect(post).toHaveBeenLastCalledWith('/v1/project-governance/projects/p1/documents', { area_id: 'a1', doc_type: 'charter' });
    await attachDocument('p1', 'd1', 'k1');
    expect(post).toHaveBeenLastCalledWith('/v1/project-governance/projects/p1/documents/d1/attach', { container_id: 'k1' });
    await returnDocument('p1', 'd1');
    expect(post).toHaveBeenLastCalledWith('/v1/project-governance/projects/p1/documents/d1/return', {});
    await addGateCondition('p1', 'g1', { text: 'x', severity: 'critical', area_code: 'organisation', document_type: 'charter' });
    expect(post).toHaveBeenLastCalledWith('/v1/project-governance/projects/p1/gates/g1/conditions', {
      text: 'x',
      severity: 'critical',
      area_code: 'organisation',
      document_type: 'charter',
    });
    await updateModelSettings('p1', { decision_route_id: null });
    expect(patch).toHaveBeenLastCalledWith('/v1/project-governance/projects/p1/model', { decision_route_id: null });
  });
});
