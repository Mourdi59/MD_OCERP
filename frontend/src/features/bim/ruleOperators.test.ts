// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The editor side of quantity rule conditions. Matching is pinned by the
// shared parity table (__tests__/ruleMatchingParity.test.ts); this pins what
// the editor stores and what it refuses.

import { describe, it, expect } from 'vitest';
import { checkConditionValue, decodeCondition, encodeCondition, parseMeasure } from './ruleOperators';

describe('checkConditionValue', () => {
  it('reads a number in the reader convention and stores it with a dot', () => {
    expect(checkConditionValue('gt', '3,5 m', 'it')).toEqual({ value: '3.5 m', problem: null, ambiguous: false });
    expect(checkConditionValue('lte', '2.5', 'en')).toEqual({ value: '2.5', problem: null, ambiguous: false });
    expect(checkConditionValue('lt', '12 m²', 'en').value).toBe('12 m2');
  });

  it('says how a number that reads two ways was read', () => {
    expect(checkConditionValue('gt', '1.500', 'it')).toEqual({ value: '1500', problem: null, ambiguous: true });
    expect(checkConditionValue('gt', '1.500', 'en')).toEqual({ value: '1.5', problem: null, ambiguous: true });
  });

  it('refuses what the server refuses', () => {
    expect(checkConditionValue('gt', 'tall', 'en').problem).toBe('value_not_number');
    expect(checkConditionValue('gt', '3 furlongs', 'en').problem).toBe('value_not_number');
    expect(checkConditionValue('contains', '  ', 'en').problem).toBe('value_required');
    expect(checkConditionValue('not_equals', '', 'en').problem).toBe('value_required');
    expect(checkConditionValue('contains', 'x'.repeat(501), 'en').problem).toBe('value_too_long');
  });

  it('leaves equality and the empty checks as they were', () => {
    expect(checkConditionValue('equals', '', 'en').problem).toBeNull();
    expect(checkConditionValue('equals', ' Muro* ', 'en').value).toBe(' Muro* ');
    expect(checkConditionValue('is_empty', 'ignored', 'en')).toEqual({ value: '', problem: null, ambiguous: false });
  });

  it('stores only values the matcher can read back', () => {
    for (const raw of ['0,25', '-3', '1.234,5 mm', '7 kg']) {
      const checked = checkConditionValue('gte', raw, 'it');
      expect(checked.problem).toBeNull();
      expect(parseMeasure(checked.value)).not.toBeNull();
    }
  });
});

describe('encodeCondition / decodeCondition', () => {
  it('keeps equals bare so older rules read the same', () => {
    expect(encodeCondition('equals', 'Progetto')).toBe('Progetto');
    expect(decodeCondition('Progetto')).toEqual({ op: 'equals', value: 'Progetto' });
    expect(decodeCondition(300)).toEqual({ op: 'equals', value: '300' });
  });

  it('round-trips every other operator', () => {
    expect(encodeCondition('is_empty', 'x')).toEqual({ $op: 'is_empty' });
    expect(decodeCondition({ $op: 'is_empty' })).toEqual({ op: 'is_empty', value: '' });
    expect(decodeCondition(encodeCondition('gt', '2.5 m'))).toEqual({ op: 'gt', value: '2.5 m' });
  });
});
