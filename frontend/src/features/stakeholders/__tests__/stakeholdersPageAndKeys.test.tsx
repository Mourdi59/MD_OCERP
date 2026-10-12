// @vitest-environment jsdom
// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The page as a whole: what it shows before a framework is chosen, when the
// server fails, when the project is not visible, and once the register has
// loaded. Then the wording: every key the feature names exists in English and
// in German, and German is a translation, not a copy.

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen as page, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import de from '@/app/locales/de';
import en from '@/app/locales/en';
import { ApiError } from '@/shared/lib/api';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({ ProjectPeopleSelect: () => null }));
vi.mock('@/shared/ui/ContactSearchInput', () => ({ ContactSearchInput: () => null }));
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0, offset: 0, limit: 100 })) }));
vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  getSettings: vi.fn(),
  listFrameworks: vi.fn(),
  listStakeholders: vi.fn(),
  getReadiness: vi.fn(),
  listPlanItems: vi.fn(),
  listDue: vi.fn(),
  listEvents: vi.fn(),
  listCommitments: vi.fn(),
  listValidation: vi.fn(),
}));

import * as api from '../api';
import { StakeholdersPage } from '../StakeholdersPage';
import { commitment, readiness, settings, stakeholder } from './fixtures';

const mocked = vi.mocked(api);
const pageOf = <T,>(items: T[]) => ({ items, total: items.length, offset: 0, limit: 100 });

function open(url = '/projects/p1/stakeholders') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/projects/:projectId/stakeholders" element={<StakeholdersPage />} />
          <Route path="/projects/:projectId/stakeholders/:section" element={<StakeholdersPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocked.getSettings.mockResolvedValue(settings());
  mocked.listFrameworks.mockResolvedValue(
    pageOf([
      {
        kind: 'framework',
        source: 'shipped' as const,
        id: 'neutral',
        code: 'neutral',
        name: { key: 'stakeholders.catalogue.framework.neutral', text: null },
        state: 'published',
        latest_version: 1,
        review_status: 'unconfirmed',
        jurisdiction_countries: [],
      },
    ]),
  );
  mocked.listStakeholders.mockResolvedValue(pageOf([stakeholder()]));
  mocked.getReadiness.mockResolvedValue(readiness());
  mocked.listPlanItems.mockResolvedValue(pageOf([]));
  mocked.listDue.mockResolvedValue(pageOf([]));
  mocked.listEvents.mockResolvedValue(pageOf([]));
  mocked.listCommitments.mockResolvedValue(pageOf([commitment({ overdue: true })]));
  mocked.listValidation.mockResolvedValue(pageOf([]));
});

describe('the stakeholders page', () => {
  it('asks for a framework first on a project that has none, and loads nothing else', async () => {
    mocked.getSettings.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'settings_missing', message: 'No framework chosen' } }),
    );
    open();
    expect(await page.findByText('Stakeholder management is not set up yet')).toBeTruthy();
    expect(await page.findByTestId('framework-settings')).toBeTruthy();
    expect(page.getAllByTestId('framework-option')).toHaveLength(1);
    expect((page.getByTestId('framework-save') as HTMLButtonElement).disabled).toBe(false);
    expect(page.queryByRole('tablist')).toBeNull();
    expect(mocked.listStakeholders).not.toHaveBeenCalled();
    expect(mocked.listCommitments).not.toHaveBeenCalled();
  });

  it('follows the flag sent with the empty state: a viewer sees the frameworks and cannot choose one', async () => {
    mocked.getSettings.mockRejectedValue(
      new ApiError(404, 'Not Found', {
        detail: { code: 'settings_missing', can: { edit: false, read_personal: false, manage_organisation: false } },
      }),
    );
    open();
    const option = (await page.findByTestId('framework-option')) as HTMLInputElement;
    expect(option.disabled).toBe(true);
    expect((page.getByTestId('framework-save') as HTMLButtonElement).disabled).toBe(true);
    expect(page.getByTestId('disabled-reason').getAttribute('data-reason')).toBe('organisation');
  });

  it('reads a project the reader may not see as a failure, not as an empty project', async () => {
    mocked.getSettings.mockRejectedValue(new ApiError(404, 'Not Found', { detail: 'Not found' }));
    open();
    expect(await page.findByText('The stakeholders could not be loaded')).toBeTruthy();
    expect(page.queryByText('Stakeholder management is not set up yet')).toBeNull();
    expect(page.queryByTestId('framework-settings')).toBeNull();
  });

  it('says so when the server fails, and offers to try again', async () => {
    mocked.getSettings.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    open();
    expect(await page.findByText('The stakeholders could not be loaded')).toBeTruthy();
    const before = mocked.getSettings.mock.calls.length;
    fireEvent.click(page.getByRole('button', { name: /retry|again/i }));
    await waitFor(() => expect(mocked.getSettings.mock.calls.length).toBeGreaterThan(before));
  });

  it('opens on the register and counts what is overdue on the tabs', async () => {
    open();
    const row = await page.findByTestId('register-row');
    expect(within(row).getByText('Building authority')).toBeTruthy();
    expect(await page.findByTestId('readiness-strip')).toBeTruthy();
    const tabs = page.getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent?.replace(/\d+$/, ''))).toEqual([
      'Register',
      'Analysis',
      'Communication plan',
      'Commitments',
      'Organisation and mandates',
      'Settings',
    ]);
    expect(tabs[3]?.textContent).toBe('Commitments1');
  });

  it('lists the checks that did not pass under the register, the blocking ones first', async () => {
    const finding = (over: Partial<api.ValidationFinding>): api.ValidationFinding => ({
      rule_id: 'stakeholders.role_not_vacant',
      passed: false,
      severity: 'warning',
      message: 'The required role Client has no holder',
      element_ref: 'client',
      suggestion: null,
      ...over,
    });
    mocked.listValidation.mockResolvedValue(
      pageOf([
        finding({}),
        finding({ rule_id: 'stakeholders.assessment_current', passed: true, message: 'ok' }),
        finding({ rule_id: 'stakeholders.mandate_one_decider', severity: 'Severity.ERROR', message: 'Nobody decides order awards', suggestion: 'Mark one role or body as the decider' }),
      ]),
    );
    open();
    const panel = await page.findByTestId('checks-panel');
    await waitFor(() => expect(panel.getAttribute('data-state')).toBe('open'));
    const findings = within(page.getByTestId('checks-panel')).getAllByTestId('check-finding');
    expect(findings.map((f) => f.getAttribute('data-blocking'))).toEqual(['true', 'false']);
    expect(findings[0]?.textContent).toBe('Nobody decides order awardsMark one role or body as the decider');
    expect(findings[1]?.textContent).toBe('The required role Client has no holder');
  });

  it('says that every check passes when none is open, and that the checks could not run when they fail', async () => {
    const first = open();
    expect((await page.findByTestId('checks-panel')).getAttribute('data-state')).toBe('clear');
    first.unmount();
    mocked.listValidation.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    open();
    await waitFor(() => expect(page.getByTestId('checks-panel').getAttribute('data-state')).toBe('failed'));
    expect(page.getByTestId('register-row')).toBeTruthy();
  });

  it('shows the empty register with its one action, and no export of nothing', async () => {
    mocked.listStakeholders.mockResolvedValue(pageOf([]));
    open();
    expect(await page.findByText('No stakeholders yet')).toBeTruthy();
    expect(page.getByTestId('stakeholder-add')).toBeTruthy();
    expect(page.queryByTestId('export-register')).toBeNull();
  });

  it('says so when a link names a stakeholder the register does not hold, and leads back', async () => {
    open('/projects/p1/stakeholders?stakeholder=gone');
    expect(await page.findByText('This stakeholder is not in the register')).toBeTruthy();
    expect(page.queryByTestId('register-table')).toBeNull();
    fireEvent.click(page.getByTestId('stakeholder-missing-back'));
    expect(await page.findByTestId('register-row')).toBeTruthy();
  });

  it('reopens the tab the link names', async () => {
    open('/projects/p1/stakeholders?tab=commitments');
    expect(await page.findByTestId('commitments-panel')).toBeTruthy();
    expect(page.queryByTestId('register-table')).toBeNull();
  });

  it('says so when one list fails, without hiding the rest of the page', async () => {
    mocked.listCommitments.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    open('/projects/p1/stakeholders?tab=commitments');
    expect(await page.findByText('The commitments could not be loaded')).toBeTruthy();
    expect(page.getAllByRole('tab')).toHaveLength(6);
  });

  it('opens the section a notification links to by path', async () => {
    open('/projects/p1/stakeholders/commitments?commitment=c1');
    expect(await page.findByTestId('commitments-panel')).toBeTruthy();
  });

  it('falls back to the register on a tab it does not know', async () => {
    open('/projects/p1/stakeholders?tab=nonsense');
    expect(await page.findByTestId('register-row')).toBeTruthy();
  });
});

const sources = import.meta.glob('../*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

/** Every message key the feature sources name as a string literal. */
function usedKeys(): string[] {
  const keys = new Set<string>();
  for (const src of Object.values(sources)) {
    for (const match of src.matchAll(/'(stakeholders(?:\.[a-z0-9_]+){2,})'/g)) keys.add(match[1] as string);
  }
  return [...keys].sort();
}

const placeholders = (text: string) => [...text.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort();

const LONG_DASH = new RegExp(`[${String.fromCharCode(0x2013, 0x2014)}]`);

// Words German writes the same way. Anything else that reads the same in both
// locales is an untranslated string.
const SAME_IN_GERMAN = new Set(['Neutral', 'Person', 'Name', 'Format', 'Status', 'Stakeholder', 'Register']);

describe('the wording', () => {
  const keys = usedKeys();
  const enTable = en.translation;
  const deTable = de.translation;

  it('finds the keys of the feature', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(15);
    expect(keys.length).toBeGreaterThan(300);
    expect(keys).toContain('stakeholders.ui.title');
  });

  it('has every key in English and in German', () => {
    expect(keys.filter((k) => !(k in enTable))).toEqual([]);
    expect(keys.filter((k) => !(k in deTable))).toEqual([]);
  });

  it('keeps the placeholders of a sentence in German', () => {
    const differing = keys.filter((k) => placeholders(enTable[k] ?? '').join() !== placeholders(deTable[k] ?? '').join());
    expect(differing).toEqual([]);
  });

  it('translates German instead of copying English', () => {
    const copied = keys.filter((k) => {
      if (!k.startsWith('stakeholders.ui.')) return false;
      const text = enTable[k] ?? '';
      if (text !== deTable[k]) return false;
      const words = text.replace(/\{\{\w+\}\}/g, '');
      return /[A-Za-z]/.test(words) && !SAME_IN_GERMAN.has(text);
    });
    expect(copied).toEqual([]);
  });

  it('writes no long dash and leaves no placeholder syntax broken', () => {
    const bad = keys.filter((k) => {
      const both = `${enTable[k] ?? ''}${deTable[k] ?? ''}`;
      return LONG_DASH.test(both) || /[{}]/.test(both.replace(/\{\{\w+\}\}/g, ''));
    });
    expect(bad).toEqual([]);
  });
});
