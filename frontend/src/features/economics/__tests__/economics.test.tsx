// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The economics screens: the figures arrive as decimal strings and are shown as
// the server sent them, an unknown figure is a dash and never zero, and every
// message key the feature uses resolves in English and German with the same
// placeholders.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

vi.mock('react-i18next', async () => {
  const table = (await import('@/app/locales/en')).default.translation as Record<string, string>;
  return {
    useTranslation: () => ({
      t: (key: string, opts?: Record<string, unknown>) => {
        let text = table[key] ?? (opts?.defaultValue as string | undefined) ?? key;
        for (const [k, v] of Object.entries(opts ?? {})) {
          if (k !== 'defaultValue') text = text.split(`{{${k}}}`).join(String(v));
        }
        return text;
      },
      i18n: { language: 'en', exists: () => true },
    }),
    initReactI18next: { type: '3rdParty', init: () => undefined },
  };
});

import en from '@/app/locales/en';
import de from '@/app/locales/de';

import type { BusinessCase, Financing } from '../api';
import { BusinessCasePanel } from '../BusinessCasePanel';
import { FindingList, isDecimal, cleanDecimal } from '../EconomicsBits';
import { FinancingPanel } from '../FinancingPanel';
import { BLOCK, FINDING, FLOW_KIND, PLAN_STATUS, SOURCE_KIND } from '../labels';

vi.mock('../hooks', () => ({
  useEconomicsAction: () => async () => undefined,
}));

afterEach(cleanup);

const CASE: BusinessCase = {
  currency: 'EUR',
  discount_rate_pct: '3.0000',
  horizon_years: 40,
  frame_total: '59200000.0000',
  lines: [
    {
      id: 'a',
      kind: 'investment',
      label: 'Construction',
      mode: 'total',
      source: 'cost_frame',
      amount: '59200000.0000',
      year_from: 0,
      year_to: 2,
      escalation_pct: '0.0000',
      notes: '',
    },
  ],
  cash_flow: [],
  key_figures: {
    total_investment: '59200000.0000',
    total_revenue: '1000.5000',
    total_operating_cost: '0',
    residual_value: '0',
    net_cash_flow: '0',
    npv: '-1234567.8900',
    irr_pct: null,
    payback_year: null,
    benefit_cost_ratio: null,
    yield_on_cost_pct: null,
  },
};

const FINANCING: Financing = {
  currency: 'EUR',
  requirement: '100.00',
  coverage: { sources_total: '90.00', shortfall: '10.00', surplus: '0.00', covered: false, coverage_pct: '90.00' },
  sources: [
    {
      id: 's1',
      kind: 'equity',
      name: 'Own funds',
      amount: '90.00',
      share_pct: '100.00',
      interest_rate_pct: null,
      funding_application_id: null,
      award: null,
      notes: '',
      tranche_total: '90.00',
      tranches: [{ id: 't1', due_on: '2027-01-15', amount: '90.00', status: 'planned', condition: '', drawn_on: null }],
    },
  ],
};

describe('business case panel', () => {
  it('shows an unknown figure as a dash and keeps the sign of a negative value', () => {
    render(<BusinessCasePanel projectId="p" data={CASE} editable={false} />);
    expect(screen.getByTestId('economics-figure-irr').textContent).toContain('-');
    expect(screen.getByTestId('economics-figure-payback').textContent).not.toContain('0');
    const npv = screen.getByTestId('economics-figure-npv').textContent ?? '';
    expect(npv).toContain('1,234,567.89');
    expect(npv).toContain('-');
  });

  it('offers no editing to a reader', () => {
    render(<BusinessCasePanel projectId="p" data={CASE} editable={false} />);
    expect(screen.queryByText('Add a line')).toBeNull();
  });
});

describe('financing panel', () => {
  it('states the shortfall apart from the surplus', () => {
    render(<FinancingPanel projectId="p" data={FINANCING} editable />);
    expect(screen.getByTestId('economics-shortfall').textContent).toContain('10.00');
    expect(screen.getAllByTestId('economics-source')).toHaveLength(1);
    expect(screen.getByText('Add a source')).toBeTruthy();
  });
});

describe('findings and inputs', () => {
  it('words a finding and falls back to its code for an unknown one', () => {
    render(
      <FindingList
        findings={[
          { code: 'financing_shortfall', ref: 'project', severity: 'error' },
          { code: 'some_new_code', ref: 'x', severity: 'warning' },
        ]}
      />,
    );
    expect(screen.getByText('The sources of finance do not cover the investment.')).toBeTruthy();
    expect(screen.getByText('some new code')).toBeTruthy();
  });

  it('reads a decimal with a comma and refuses anything else', () => {
    expect(isDecimal('12,50')).toBe(true);
    expect(cleanDecimal(' 12,50 ')).toBe('12.50');
    expect(isDecimal('1e5')).toBe(false);
    expect(isDecimal('')).toBe(false);
  });
});

describe('economics i18n keys', () => {
  const featureDir = join(__dirname, '..');
  const sources = readdirSync(featureDir)
    .filter((f) => /\.(ts|tsx)$/.test(f))
    .map((f) => readFileSync(join(featureDir, f), 'utf-8'))
    .join('\n');
  const used = new Set<string>();
  for (const m of sources.matchAll(/\bt\(\s*'(economics\.[A-Za-z0-9_.]+)'/g)) used.add(m[1]!);
  for (const map of [PLAN_STATUS, FLOW_KIND, SOURCE_KIND, FINDING, BLOCK]) {
    for (const [key] of Object.values(map)) used.add(key);
  }
  const placeholders = (text: string) => [...text.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]).sort();

  it('finds the keys it is meant to check', () => {
    expect(used.size).toBeGreaterThan(100);
    expect(used.has('economics.ui.title')).toBe(true);
  });

  it('has every key in English and German with the same placeholders', () => {
    for (const key of used) {
      const english = en.translation[key];
      const german = de.translation[key];
      expect(english, `en ${key}`).toBeTruthy();
      expect(german, `de ${key}`).toBeTruthy();
      expect(placeholders(german!), key).toEqual(placeholders(english!));
    }
  });

  it('names every finding code the server can raise', () => {
    const rules = readFileSync(join(__dirname, '../../../../../backend/app/modules/economics/rules.py'), 'utf-8');
    const block = rules.slice(rules.indexOf('CODES: dict'), rules.indexOf('@dataclass'));
    const codes = [...block.matchAll(/^\s+"(\w+)": (?:ERROR|WARNING),/gm)].map((m) => m[1]!);
    expect(codes.length).toBeGreaterThan(20);
    for (const code of codes) expect(FINDING[code], code).toBeTruthy();
  });
});
