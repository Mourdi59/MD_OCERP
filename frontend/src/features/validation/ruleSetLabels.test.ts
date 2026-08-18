// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Three screens printed the validation engine's own identifiers at a reader:
// the rule-set chips on the validation page, the report card in the chat
// panel, and the pack list in project settings. Only the first had a name map,
// which is why only the first read correctly. These cases hold the map that
// all three now share.
import { describe, it, expect } from 'vitest';
import { ruleSetLabel, ruleSetListLabel, splitRuleSets } from './ruleSetLabels';

/** Stands in for i18next: returns the defaultValue, as an English run would. */
const t = (_key: string, opts?: Record<string, unknown>) => String(opts?.defaultValue ?? '');

describe('ruleSetLabel', () => {
  it('names the set that was caught on a screenshot', () => {
    // The frame showed "BOQ quality boq_quality" beside a clean "MasterFormat".
    expect(ruleSetLabel('boq_quality', t)).toBe('BOQ quality');
  });

  it('never returns the identifier unchanged for a set it knows', () => {
    const known = ['boq_quality', 'din276', 'gaeb', 'nrm', 'masterformat', 'bim_compliance', 'project_completeness'];
    for (const set of known) {
      expect(ruleSetLabel(set, t)).not.toBe(set);
    }
  });

  it('turns an unknown identifier into words rather than printing it raw', () => {
    // A pack we have never heard of still must not put an underscore on screen.
    expect(ruleSetLabel('custom_site_rules', t)).toBe('custom site rules');
    expect(ruleSetLabel('custom_site_rules', t)).not.toContain('_');
  });

  it('leaves a single-word unknown identifier alone', () => {
    expect(ruleSetLabel('onorm', t)).toBe('onorm');
  });
});

describe('splitRuleSets', () => {
  it('unpacks the plus-joined column the report stores', () => {
    expect(splitRuleSets('boq_quality+masterformat')).toEqual(['boq_quality', 'masterformat']);
  });

  it('treats absence as no sets rather than as one empty set', () => {
    // The chat card falls back to a generic title on an empty list, so an
    // empty string here must not become a list containing "".
    expect(splitRuleSets(null)).toEqual([]);
    expect(splitRuleSets(undefined)).toEqual([]);
    expect(splitRuleSets('')).toEqual([]);
    expect(splitRuleSets('+')).toEqual([]);
  });
});

describe('ruleSetListLabel', () => {
  it('names every set in a stored column', () => {
    expect(ruleSetListLabel('boq_quality+masterformat', t)).toBe('BOQ quality · MasterFormat');
  });

  it('returns an empty string when there is nothing to name', () => {
    // The caller prints a fallback title on empty, so this must be falsy
    // rather than a stray separator.
    expect(ruleSetListLabel(null, t)).toBe('');
  });

  it('carries no underscore through from any input', () => {
    expect(ruleSetListLabel('boq_quality+some_unknown_pack', t)).not.toContain('_');
  });
});
