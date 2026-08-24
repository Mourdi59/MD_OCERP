// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import {
  PRESETS,
  getUniversalPresets,
  getRegionalPresets,
  isUniversalPreset,
  UNIVERSAL_PRESET_IDS,
  type ColumnPreset,
} from '../index';

describe('BOQ preset registry', () => {
  it('exposes 16 presets total', () => {
    expect(PRESETS).toHaveLength(16);
  });

  it('partitions cleanly into universal (7) + regional (9)', () => {
    expect(getUniversalPresets()).toHaveLength(7);
    expect(getRegionalPresets()).toHaveLength(9);
    expect(getUniversalPresets().length + getRegionalPresets().length).toBe(PRESETS.length);
  });

  it('every preset has a unique id', () => {
    const ids = PRESETS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('every preset has at least one column', () => {
    for (const p of PRESETS) {
      expect(p.columns.length).toBeGreaterThan(0);
    }
  });

  it('every column inside a preset has a unique name', () => {
    for (const p of PRESETS) {
      const names = p.columns.map((c) => c.name);
      expect(new Set(names).size).toBe(names.length);
    }
  });

  it('column names are snake_case-ish (lower / digits / underscore only)', () => {
    const valid = /^[a-z][a-z0-9_]*$/;
    for (const p of PRESETS) {
      for (const c of p.columns) {
        expect(c.name, `${p.id}.${c.name}`).toMatch(valid);
      }
    }
  });

  it('select-type columns include non-empty options', () => {
    for (const p of PRESETS) {
      for (const c of p.columns) {
        if (c.column_type === 'select') {
          expect(c.options, `${p.id}.${c.name}`).toBeDefined();
          expect(c.options!.length).toBeGreaterThan(0);
        }
      }
    }
  });

  it('column_type stays in the supported set', () => {
    const allowed = new Set(['text', 'number', 'date', 'select']);
    for (const p of PRESETS) {
      for (const c of p.columns) {
        expect(allowed.has(c.column_type)).toBe(true);
      }
    }
  });

  it('region is one of the documented values', () => {
    const allowedRegions = new Set([
      'universal',
      'germany',
      'austria',
      'usa',
      'australia',
      'brazil',
      'uk',
      'china',
      'canada',
      'integration',
    ]);
    for (const p of PRESETS) {
      expect(allowedRegions.has(p.region), `${p.id} → ${p.region}`).toBe(true);
    }
  });

  it('isUniversalPreset agrees with the region tag', () => {
    for (const p of PRESETS) {
      expect(isUniversalPreset(p)).toBe(p.region === 'universal');
    }
  });

  it('UNIVERSAL_PRESET_IDS lists exactly the universal presets', () => {
    const expected = new Set(getUniversalPresets().map((p) => p.id));
    expect(UNIVERSAL_PRESET_IDS).toEqual(expected);
  });

  it('keeps existing preset ids stable (no rename of v1.x presets)', () => {
    // Renaming a preset id silently invalidates anything that referenced
    // it (saved templates, telemetry, screenshots). Lock the existing
    // ids so a rename has to be deliberate.
    const ids = new Set(PRESETS.map((p) => p.id));
    for (const legacy of [
      'procurement',
      'notes',
      'quality',
      'sustainability',
      'gaeb_ava',
      'oenorm_brz',
      'bim',
    ]) {
      expect(ids.has(legacy), `legacy preset id removed: ${legacy}`).toBe(true);
    }
  });

  it('every regional preset has a non-universal region tag', () => {
    for (const p of getRegionalPresets()) {
      expect(p.region).not.toBe('universal');
    }
  });

  it('exposes the new v2.7.0 universal presets (status, tendering, schedule)', () => {
    const ids = new Set(getUniversalPresets().map((p) => p.id));
    expect(ids.has('status_scope')).toBe(true);
    expect(ids.has('tendering')).toBe(true);
    expect(ids.has('schedule')).toBe(true);
  });

  it('exposes the new v2.7.0 country presets (USA / AU / BR / UK)', () => {
    const ids = new Set(getRegionalPresets().map((p) => p.id));
    expect(ids.has('csi_masterformat')).toBe(true);
    expect(ids.has('aiqs_australia')).toBe(true);
    expect(ids.has('sinapi_brazil')).toBe(true);
    expect(ids.has('nrm2_uk')).toBe(true);
  });

  it('exposes the China / Canada country presets', () => {
    const ids = new Set(getRegionalPresets().map((p) => p.id));
    expect(ids.has('gbt50500_china')).toBe(true);
    expect(ids.has('unit_price_canada')).toBe(true);
  });

  it('every derived column names a resource_role', () => {
    // A derived column with no role matches every resource type, so
    // `resource_sum` returns the position's whole resource buildup and
    // `percentage_of_unit_rate` returns that buildup measured against the
    // stored `unit_rate` - a reading of whether the position adds up, not of
    // any one trade's share. Both are read-only, so the user cannot correct
    // them. The role is what makes the column mean anything; never let one
    // ship without it.
    for (const p of PRESETS) {
      for (const c of p.columns) {
        if (c.derived) {
          expect(c.resource_role, `${p.id}.${c.name}`).toBeDefined();
        }
      }
    }
  });

  it('derived columns stay numeric', () => {
    for (const p of PRESETS) {
      for (const c of p.columns) {
        if (c.derived) {
          expect(c.column_type, `${p.id}.${c.name}`).toBe('number');
        }
      }
    }
  });

  it('China preset derives the three cost elements from resources', () => {
    const cn = PRESETS.find((p) => p.id === 'gbt50500_china');
    expect(cn).toBeDefined();
    const byName = new Map(cn!.columns.map((c) => [c.name, c]));
    expect(byName.get('rengong_fei')?.derived).toBe('resource_sum');
    expect(byName.get('rengong_fei')?.resource_role).toBe('labor');
    expect(byName.get('cailiao_fei')?.derived).toBe('resource_sum');
    expect(byName.get('cailiao_fei')?.resource_role).toBe('material');
    expect(byName.get('jixie_fei')?.derived).toBe('resource_sum');
    // The machine-shift rate carries the operator, so the machinery element
    // sweeps both roles - the one place a country preset differs from GAEB.
    expect(byName.get('jixie_fei')?.resource_role).toEqual(['equipment', 'operator']);
    // The feature description is free text and the item code keeps its
    // leading zeros, so neither may drift to `number`.
    expect(byName.get('xiangmu_tezheng')?.column_type).toBe('text');
    expect(byName.get('xiangmu_bianma')?.column_type).toBe('text');
  });

  it('China preset states the whole unit-rate composition', () => {
    // Three cost elements plus management fee, profit and risk. Drop one and
    // the composition reads short to the estimator it is written for.
    const cn = PRESETS.find((p) => p.id === 'gbt50500_china');
    const names = new Set(cn!.columns.map((c) => c.name));
    for (const part of [
      'rengong_fei',
      'cailiao_fei',
      'jixie_fei',
      'guanli_fei_pct',
      'lirun_pct',
      'fengxian_pct',
    ]) {
      expect(names.has(part), `composition is missing ${part}`).toBe(true);
    }
  });

  it('China management fee, profit and risk stay free-input, not derived', () => {
    // These two are part of the composition of a comprehensive unit rate, and
    // a per-position column is where that composition lives. But no resource
    // role denotes either of them, so deriving them would print a resource
    // share under a heading that promises a fee rate - and read-only, so the
    // estimator could not fix it. Free-input `number`, like GAEB's Wagnis %.
    const cn = PRESETS.find((p) => p.id === 'gbt50500_china');
    const byName = new Map(cn!.columns.map((c) => [c.name, c]));
    for (const name of ['guanli_fei_pct', 'lirun_pct', 'fengxian_pct']) {
      const col = byName.get(name);
      expect(col, name).toBeDefined();
      expect(col!.column_type).toBe('number');
      expect(col!.derived).toBeUndefined();
      expect(col!.resource_role).toBeUndefined();
    }
  });

  it('Canada preset carries rate composition, not classification codes', () => {
    // Canada classifies to MasterFormat, so the division / section codes are
    // the `csi_masterformat` preset's job. Restating them here would put two
    // column names on one fact.
    const ca = PRESETS.find((p) => p.id === 'unit_price_canada');
    expect(ca).toBeDefined();
    const names = ca!.columns.map((c) => c.name);
    expect(names).not.toContain('csi_division');
    expect(names).not.toContain('csi_section');
    const byName = new Map(ca!.columns.map((c) => [c.name, c]));
    for (const name of ['ca_labour', 'ca_material', 'ca_equipment', 'ca_subcontract']) {
      expect(byName.get(name)?.derived, name).toBe('resource_sum');
    }
    // Overhead and profit are contractor decisions, not resource sums.
    expect(byName.get('ca_overhead_pct')?.derived).toBeUndefined();
    expect(byName.get('ca_profit_pct')?.derived).toBeUndefined();
  });

  it('Canada tax regimes name no rate', () => {
    // Provincial rates move; one baked into an option string is a number
    // nobody comes back to correct.
    const ca = PRESETS.find((p) => p.id === 'unit_price_canada');
    const tax = ca!.columns.find((c) => c.name === 'ca_tax_regime');
    expect(tax?.column_type).toBe('select');
    expect(tax?.options?.length).toBeGreaterThan(0);
    for (const opt of tax!.options!) {
      expect(opt, `tax option carries a rate: ${opt}`).not.toMatch(/\d/);
    }
  });

  it('preset shape conforms to ColumnPreset (smoke type-test)', () => {
    const p: ColumnPreset | undefined = PRESETS[0];
    expect(p).toBeDefined();
    expect(p).toHaveProperty('id');
    expect(p).toHaveProperty('region');
    expect(p).toHaveProperty('icon');
    expect(p).toHaveProperty('columns');
  });
});
