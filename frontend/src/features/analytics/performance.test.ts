// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, expect, it } from 'vitest';

import {
  buildPerformanceCsv,
  csvCell,
  rangeBand,
  tableRows,
  toNumber,
  type PerformanceBenchmarkResponse,
  type PerformanceGroup,
} from './performance';

function group(overrides: Partial<PerformanceGroup> = {}): PerformanceGroup {
  return {
    key: 'm2',
    dimensions: { unit: 'm2' },
    rows: [
      {
        project_id: 'a',
        value: '2',
        numerator: '100',
        denominator: '50',
        records: 1,
        unavailable_reason: null,
      },
      {
        project_id: 'b',
        value: null,
        numerator: '40',
        denominator: '0',
        records: 1,
        unavailable_reason: 'zero_denominator',
      },
    ],
    benchmark: {
      weighted: '1.6',
      weighted_unavailable_reason: null,
      median: '1.75',
      p25: '1.625',
      p75: '1.875',
      min: '1.5',
      max: '2',
    },
    evidence: { projects_with_data: 2, projects_with_value: 1, records: 2 },
    coverage: '0.3333',
    ...overrides,
  };
}

const projects = [
  { project_id: 'a', name: 'Alpha', currency: 'EUR' },
  { project_id: 'b', name: 'Beta', currency: 'EUR' },
  { project_id: 'c', name: 'Gamma', currency: 'EUR' },
];

describe('performance helpers', () => {
  it('reads an absent value as null, never as 0', () => {
    expect(toNumber(null)).toBeNull();
    expect(toNumber(undefined)).toBeNull();
    expect(toNumber('')).toBeNull();
    expect(toNumber('1.6')).toBe(1.6);
    expect(toNumber('0')).toBe(0);
  });

  it('places a value against the P25-P75 range', () => {
    expect(rangeBand('1', '1.5', '2')).toBe('below');
    expect(rangeBand('1.5', '1.5', '2')).toBe('within');
    expect(rangeBand('3', '1.5', '2')).toBe('above');
    expect(rangeBand(null, '1.5', '2')).toBeNull();
  });

  it('lists every selected project, including one with no reading', () => {
    const rows = tableRows(group(), projects);
    expect(rows.map((r) => r.name)).toEqual(['Alpha', 'Beta', 'Gamma']);
    expect(rows[2]?.row).toBeNull();
  });

  it('neutralises a cell a spreadsheet would run as a formula', () => {
    expect(csvCell('=SUM(A1)')).toBe("'=SUM(A1)");
    expect(csvCell('-5')).toBe('-5');
    expect(csvCell('a,b')).toBe('"a,b"');
  });

  it('exports unavailable readings as a status, not as a zero', () => {
    const data: PerformanceBenchmarkResponse = {
      kpi: 'labour_hours_per_installed_unit',
      spec: {},
      aggregation: 'ratio',
      projects_selected: 3,
      projects,
      groups: [group()],
    };
    const csv = buildPerformanceCsv(data, {
      group: 'Group',
      project: 'Project',
      value: 'Value',
      numerator: 'Numerator',
      denominator: 'Denominator',
      records: 'Records',
      status: 'Status',
      weighted: 'Weighted',
      median: 'Median',
      p25: 'P25',
      p75: 'P75',
      unavailable: (reason) => `Unavailable (${reason})`,
      groupLabel: (g) => g.key,
    });
    const lines = csv.split('\r\n');
    expect(lines).toHaveLength(4);
    expect(lines[1]).toBe('m2,Alpha,2,100,50,1,,1.6,1.75,1.625,1.875');
    expect(lines[2]).toBe('m2,Beta,,40,0,1,Unavailable (zero_denominator),1.6,1.75,1.625,1.875');
    expect(lines[3]).toBe('m2,Gamma,,,,0,Unavailable (no_data),1.6,1.75,1.625,1.875');
  });
});
