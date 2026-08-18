// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The banner may not congratulate a project it knows nothing about.
//
// Found by reading a screenshot: a project with no mobilisation plan showed
// "Ready to mobilise - all commencement gates are satisfied" over "Gates
// cleared 0 of 0" with every category not applicable. No gate saw it, because
// every value involved was well formed. The two cases below named `undetermined`
// are that screenshot, one for each of the two defaults that produced it.

import { describe, expect, it } from 'vitest';

import { mobilisationGateState } from './mobilisationGate';

const gate = (over: Partial<{ gate_ready: boolean; gate_total: number }> = {}) => ({
  gate_ready: true,
  gate_total: 4,
  ...over,
});

const readiness = (over: Partial<{ gate_ready: boolean; gate_total: number }> = {}) => ({
  gate_ready: over.gate_ready ?? true,
  overall: { gate_total: over.gate_total ?? 4 },
});

describe('what the mobilisation banner may claim', () => {
  it('makes no claim when nothing has loaded', () => {
    // The defect exactly: `gate?.gate_ready ?? readiness?.gate_ready ?? true`
    // turned "no answer yet" into "ready", in green, with a tick.
    expect(mobilisationGateState(undefined, undefined)).toBe('undetermined');
  });

  it.each([
    ['the gate endpoint', () => mobilisationGateState(undefined, gate({ gate_total: 0 }))],
    ['the readiness report', () => mobilisationGateState(readiness({ gate_total: 0 }), undefined)],
  ])('makes no claim over nought gates reported by %s', (_source, call) => {
    // Vacuous truth is the right answer to "is anything blocking" and the
    // wrong answer to "is everything done". The banner asks the second.
    expect(call()).toBe('undetermined');
  });

  it('says ready only when gates exist and all of them are satisfied', () => {
    expect(mobilisationGateState(undefined, gate({ gate_ready: true, gate_total: 3 }))).toBe('ready');
    expect(mobilisationGateState(readiness({ gate_ready: true, gate_total: 3 }), undefined)).toBe('ready');
  });

  it('says blocked when a gate is still open', () => {
    expect(mobilisationGateState(undefined, gate({ gate_ready: false, gate_total: 3 }))).toBe('blocked');
    expect(mobilisationGateState(readiness({ gate_ready: false, gate_total: 3 }), undefined)).toBe('blocked');
  });

  it('prefers the gate endpoint over the readiness report', () => {
    // Both present and disagreeing, so the assertion fails if the precedence
    // is dropped rather than passing by coincidence.
    expect(mobilisationGateState(readiness({ gate_ready: false }), gate({ gate_ready: true }))).toBe('ready');
    expect(mobilisationGateState(readiness({ gate_ready: true }), gate({ gate_ready: false }))).toBe('blocked');
  });

  it('falls through to the readiness report when the gate endpoint is silent', () => {
    expect(mobilisationGateState(readiness({ gate_ready: false, gate_total: 2 }), undefined)).toBe('blocked');
  });
});
