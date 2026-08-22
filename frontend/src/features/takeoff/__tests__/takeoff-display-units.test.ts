// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Unit tests for the takeoff display-unit conversion seam.
 *
 * Storage is metric-canonical (D-TKC-016); these helpers convert at the
 * display / export boundary only. The key contracts:
 *   - metric is a strict pass-through (value bit-identical, unit normalised
 *     only to its display form), so a metric user sees no change;
 *   - imperial scales the value and relabels the unit (m -> ft, m² -> ft²,
 *     m³ -> ft³);
 *   - countable / unmapped units pass through unchanged in both systems;
 *   - `measurementLabel` reproduces the stored metric label verbatim for a
 *     metric user and the converted equivalent for an imperial user.
 */

import { describe, it, expect } from 'vitest';
import type { Measurement } from '../lib/takeoff-types';
import type { ScaleConfig } from '@/modules/pdf-takeoff/data/scale-helpers';
import {
  convertQuantity,
  convertValue,
  displayUnitFor,
  formatQuantity,
  measurementLabel,
} from '../lib/takeoff-display-units';

function m(partial: Partial<Measurement> & { id: string }): Measurement {
  return {
    type: partial.type ?? 'distance',
    points: partial.points ?? [],
    value: partial.value ?? 0,
    unit: partial.unit ?? 'm',
    label: partial.label ?? '',
    annotation: partial.annotation ?? '',
    page: partial.page ?? 1,
    group: partial.group ?? 'General',
    ...partial,
  };
}

describe('convertQuantity - metric pass-through', () => {
  it('keeps the value bit-identical and normalises the unit label', () => {
    expect(convertQuantity(12.3456, 'm', 'metric')).toEqual({
      value: 12.3456,
      unit: 'm',
    });
    expect(convertQuantity(5, 'm2', 'metric')).toEqual({ value: 5, unit: 'm²' });
    expect(convertQuantity(5, 'm²', 'metric')).toEqual({ value: 5, unit: 'm²' });
  });

  it('passes countable units through untouched', () => {
    expect(convertQuantity(3, 'pcs', 'metric')).toEqual({ value: 3, unit: 'pcs' });
  });
});

describe('convertQuantity - imperial', () => {
  it('converts length m -> ft', () => {
    const r = convertQuantity(10, 'm', 'imperial');
    expect(r.value).toBeCloseTo(32.808399, 5);
    expect(r.unit).toBe('ft');
  });

  it('converts area m² -> ft²', () => {
    const r = convertQuantity(10, 'm²', 'imperial');
    expect(r.value).toBeCloseTo(107.639, 3);
    expect(r.unit).toBe('ft²');
  });

  it('converts volume m³ -> ft³', () => {
    const r = convertQuantity(10, 'm³', 'imperial');
    expect(r.value).toBeCloseTo(353.147, 3);
    expect(r.unit).toBe('ft³');
  });

  it('leaves pcs unchanged (no imperial mapping)', () => {
    expect(convertQuantity(4, 'pcs', 'imperial')).toEqual({ value: 4, unit: 'pcs' });
  });
});

describe('displayUnitFor / convertValue', () => {
  it('returns the system unit label without a value', () => {
    expect(displayUnitFor('m', 'metric')).toBe('m');
    expect(displayUnitFor('m', 'imperial')).toBe('ft');
    expect(displayUnitFor('m²', 'imperial')).toBe('ft²');
  });

  it('convertValue returns only the converted magnitude', () => {
    expect(convertValue(10, 'm', 'metric')).toBe(10);
    expect(convertValue(10, 'm', 'imperial')).toBeCloseTo(32.808399, 5);
  });
});

describe('formatQuantity', () => {
  it('metric formats with the takeoff precision rules', () => {
    // formatMeasurement: < 100 -> 2 dp.
    expect(formatQuantity(5.5, 'm', 'metric')).toBe('5.50 m');
    expect(formatQuantity(12.5, 'm²', 'metric')).toBe('12.50 m²');
  });

  it('imperial writes a LINEAR dimension as feet and inches', () => {
    // Changed deliberately. This used to assert '32.81 ft'. Decimal feet is
    // not how a dimension is written on an American drawing, and the takeoff
    // grid has always PARSED 12'-6 3/4" on the way in, so the product could
    // read a notation it would never write back.
    // 10 m = 32.8084 ft = 393.7008 in -> 32 ft 9.7008 in -> 9 11/16 in.
    expect(formatQuantity(10, 'm', 'imperial')).toBe(`32'-9 11/16"`);
  });

  it('imperial leaves AREA and VOLUME in decimal feet', () => {
    // The linear rule must not leak. Nobody dimensions a slab as four hundred
    // square feet and three quarters, so these keep the shared formatter.
    // 134.5, not 134.55: the shared precision ladder drops to one decimal
    // above 100. That it still applies here is the assertion.
    expect(formatQuantity(12.5, 'm²', 'imperial')).toBe('134.5 ft²');
    expect(formatQuantity(2, 'm³', 'imperial')).toBe('70.63 ft³');
  });

  it('imperial passes an unconvertible unit through untouched', () => {
    // Counts and lump sums have no imperial form, so the linear branch must
    // not catch them either.
    expect(formatQuantity(3, 'pcs', 'imperial')).toBe('3.00 pcs');
  });
});

describe('measurementLabel - metric reproduces the stored format', () => {
  const scale: ScaleConfig = { pixelsPerUnit: 100, unitLabel: 'm' };

  it('distance', () => {
    const md = m({ id: 'd', type: 'distance', value: 5.5, unit: 'm' });
    expect(measurementLabel(md, scale, 'metric')).toBe('5.50 m');
  });

  it('area with perimeter recomputed from points', () => {
    // 100x100 px square at 100 px/m -> 1 m2 area, 4 m perimeter.
    const square = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 100 },
      { x: 0, y: 100 },
    ];
    const ma = m({ id: 'a', type: 'area', value: 1, unit: 'm²', points: square });
    expect(measurementLabel(ma, scale, 'metric')).toBe('1.00 m² (P: 4.00 m)');
  });

  it('volume from stored base area + depth', () => {
    const mv = m({
      id: 'v',
      type: 'volume',
      value: 6,
      unit: 'm³',
      area: 2,
      depth: 3,
      points: [
        { x: 0, y: 0 },
        { x: 100, y: 0 },
        { x: 100, y: 100 },
      ],
    });
    expect(measurementLabel(mv, scale, 'metric')).toBe(
      'V = 6.00 m³ (A: 2.00 m² × D: 3.00 m)',
    );
  });

  it('count shows the annotation plus a live tally of placed points (issue #300)', () => {
    // The tally lives in points.length, not the static label. Mirrors the
    // on-canvas / export renderers `${annotation} (${points.length})`.
    const mc = m({
      id: 'c',
      type: 'count',
      value: 3,
      unit: 'pcs',
      annotation: 'Doors',
      label: 'Element',
      points: [
        { x: 0, y: 0 },
        { x: 10, y: 0 },
        { x: 20, y: 0 },
      ],
    });
    expect(measurementLabel(mc, scale, 'metric')).toBe('Doors (3)');
    // A count carries no convertible quantity, so imperial is identical.
    expect(measurementLabel(mc, scale, 'imperial')).toBe('Doors (3)');
  });

  it('annotation markups keep the stored label', () => {
    const mk = m({ id: 'k', type: 'cloud', value: 0, unit: '', label: 'Revision A' });
    expect(measurementLabel(mk, scale, 'metric')).toBe('Revision A');
  });
});

describe('measurementLabel - imperial converts every component', () => {
  const scale: ScaleConfig = { pixelsPerUnit: 100, unitLabel: 'm' };

  it('distance is written as a drawing dimension', () => {
    const md = m({ id: 'd', type: 'distance', value: 10, unit: 'm' });
    expect(measurementLabel(md, scale, 'imperial')).toBe(`32'-9 11/16"`);
  });

  it('area shows ft² area and ft perimeter', () => {
    const square = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 100 },
      { x: 0, y: 100 },
    ];
    // 1 m2 -> 10.7639 ft2. The perimeter is a LENGTH, so it now reads as a
    // dimension: 4 m = 157.48 in -> 2520 sixteenths -> 13 ft 1 1/2 in. The
    // area beside it stays decimal, which is the point of the pair being
    // asserted in one string.
    const ma = m({ id: 'a', type: 'area', value: 1, unit: 'm²', points: square });
    const label = measurementLabel(ma, scale, 'imperial');
    expect(label).toContain('ft²');
    expect(label).toContain('(P: ');
    expect(label).not.toContain('m²');
    expect(label).toBe(`10.76 ft² (P: 13'-1 1/2")`);
  });

  it('volume shows ft³ / ft² / ft', () => {
    const mv = m({
      id: 'v',
      type: 'volume',
      value: 6,
      unit: 'm³',
      area: 2,
      depth: 3,
      points: [
        { x: 0, y: 0 },
        { x: 100, y: 0 },
        { x: 100, y: 100 },
      ],
    });
    const label = measurementLabel(mv, scale, 'imperial');
    expect(label).toContain('ft³');
    expect(label).toContain('ft²');
    expect(label).not.toContain('m³');
    expect(label).not.toContain('m²');
  });
});
