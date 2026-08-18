// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// A stored validation report only has a duration if something timed the run.
// The engine times live runs, but seeded and older reports carry no duration at
// all, and the page used to resolve that absence to zero - which then printed
// "Duration: 0.0ms" as though the run had been measured and found instant.
//
// The render site is guarded by the compiler: fmtFixed takes a strict number,
// so a null cannot reach it unchecked. Nothing in the type system, though,
// stops the mapping itself from inventing a zero again. These cases are that
// guard: they fail if the old `?? 0` comes back, and they fail if the fix
// overshoots into `|| null` and swallows a duration that genuinely was zero.
import { describe, it, expect } from 'vitest';
import { mapStoredReport } from './ValidationPage';

type StoredMetadata = {
  duration_ms?: number;
  rule_sets?: string[];
  unsupported_rule_sets?: string[];
} | null;

function storedReport(metadata: StoredMetadata) {
  return {
    id: 'report-1',
    project_id: 'project-1',
    target_type: 'boq',
    target_id: 'boq-1',
    rule_set: 'boq_quality',
    status: 'passed',
    score: '0.92',
    total_rules: 4,
    passed_count: 4,
    error_count: 0,
    warning_count: 0,
    results: [],
    created_at: '2026-08-18T09:00:00Z',
    metadata,
  };
}

describe('mapStoredReport duration', () => {
  it('carries a recorded duration through unchanged', () => {
    expect(mapStoredReport(storedReport({ duration_ms: 12.5 })).duration_ms).toBe(12.5);
  });

  it('reports no duration when the metadata records none', () => {
    expect(mapStoredReport(storedReport({ rule_sets: ['boq_quality'] })).duration_ms).toBeNull();
  });

  it('reports no duration when the report has no metadata at all', () => {
    expect(mapStoredReport(storedReport(null)).duration_ms).toBeNull();
  });

  it('keeps a measured zero, which is not the same as an unmeasured one', () => {
    expect(mapStoredReport(storedReport({ duration_ms: 0 })).duration_ms).toBe(0);
  });
});

