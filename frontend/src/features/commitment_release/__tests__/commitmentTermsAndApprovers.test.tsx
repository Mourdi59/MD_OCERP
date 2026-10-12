// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Two forms whose fields come from the server: the contract figures an abort
// basis works with (typed as percentages, sent as fractions, and only those
// of the basis that is chosen), and the approver of a tier, where a row that
// names a deputy without an approver is sent as filled and refused in words.

import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/approval-routes/api', () => ({ listRoutes: vi.fn(async () => []) }));
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({
  ProjectPeopleSelect: ({ id, value, onChange }: { id?: string; value?: string; onChange: (userId: string) => void }) => (
    <input id={id} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
  ),
}));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    putAbortTerms: vi.fn(),
    listAssignments: vi.fn(),
    putAssignments: vi.fn(),
    generateRoutes: vi.fn(),
  };
});

import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import type { AbortBasis, AbortParameterField, AbortTerms } from '../api';
import { AbortTermsDialog } from '../AbortTermsDialog';
import { ApproverSetup } from '../SetupPanel';
import type { LabelContext } from '../labels';
import { enT } from './i18nMock';
import { item, matrix, projectCan } from './fixtures';

const mocked = vi.mocked(api);
const labels: LabelContext = { t: enT, language: 'en', exists: (key) => enT(key) !== key };
const page = <T,>(items: T[]) => ({ items, total: items.length, offset: 0, limit: 100 });

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

function field(name: string, standard: string | null): AbortParameterField {
  return {
    name,
    type: 'fraction',
    unit: 'fraction_of_one',
    min: '0',
    max: '1',
    default: standard,
    required: standard === null,
    statutory: false,
    label_key: `commitment.abort_parameter.${name}`,
    note_key: null,
  };
}

function basis(id: string, fields: AbortParameterField[]): AbortBasis {
  return {
    kind: 'abort_basis',
    source: 'shipped',
    id,
    code: id,
    name: { key: null, text: { en: id } },
    state: 'active',
    versions: [1],
    latest_version: 1,
    review_status: 'verified',
    jurisdiction_countries: [],
    method: 'performed_plus_fee',
    parameter_fields: fields,
  };
}

const WITH_FEE = basis('with_fee', [field('fee_pct', '0.05'), field('profit_pct', null)]);
const PROFIT_ONLY = basis('profit_only', [field('profit_pct', null)]);
const NO_FIGURES = basis('no_figures', []);

const input = (id: string) => document.getElementById(id) as HTMLInputElement | null;
const sentParameters = () => mocked.putAbortTerms.mock.calls[0]![2].parameters;

beforeEach(() => {
  vi.resetAllMocks();
});
afterEach(cleanup);

describe('contract figures of an abort basis', () => {
  function open(terms: Partial<AbortTerms> | null = null) {
    mocked.putAbortTerms.mockResolvedValue({} as AbortTerms);
    return wrap(
      <AbortTermsDialog
        open
        onClose={() => undefined}
        projectId="p1"
        item={item()}
        terms={terms as AbortTerms | null}
        bases={[WITH_FEE, PROFIT_ONLY, NO_FIGURES]}
        labels={labels}
        onSaved={() => undefined}
      />,
    );
  }
  const choose = (id: string) => fireEvent.change(input('abort-basis')!, { target: { value: id } });
  const save = () => fireEvent.click(screen.getByTestId('abort-terms-save'));

  it('shows no figure before a basis is chosen, and then the figures of that basis by name', () => {
    open();
    expect(screen.queryByTestId('abort-parameters')).toBeNull();
    choose('shipped:with_fee');
    expect(screen.getByLabelText(enT('commitment.abort_parameter.fee_pct'))).toBe(input('abort-parameter-fee_pct'));
    expect(input('abort-parameter-profit_pct')).not.toBeNull();
    // The standard value of the basis is shown as the percentage it is.
    expect(input('abort-parameter-fee_pct')!.placeholder).toBe('5');
    choose('shipped:no_figures');
    expect(screen.queryByTestId('abort-parameters')).toBeNull();
  });

  it('will not save without a figure the basis has no standard value for', () => {
    open();
    choose('shipped:with_fee');
    save();
    expect(screen.getByTestId('abort-terms-problems').textContent).toContain(
      enT('commitment.abort_form.problem.parameter_missing'),
    );
    expect(mocked.putAbortTerms).not.toHaveBeenCalled();
  });

  it('sends what was typed in per cent as fractions, and leaves an empty figure to the basis', async () => {
    open();
    choose('shipped:with_fee');
    fireEvent.change(input('abort-parameter-profit_pct')!, { target: { value: '7.5' } });
    save();
    await waitFor(() => expect(mocked.putAbortTerms).toHaveBeenCalledTimes(1));
    expect(sentParameters()).toEqual({ profit_pct: '0.075' });
  });

  it('opens stored figures as percentages and sends them back unchanged', async () => {
    open({ basis_code: 'with_fee', basis_source: 'shipped', parameters: { fee_pct: '0.05', profit_pct: '0.1' } });
    expect(input('abort-parameter-fee_pct')!.value).toBe('5');
    expect(input('abort-parameter-profit_pct')!.value).toBe('10');
    save();
    await waitFor(() => expect(mocked.putAbortTerms).toHaveBeenCalledTimes(1));
    expect(sentParameters()).toEqual({ fee_pct: '0.05', profit_pct: '0.1' });
  });

  it('a change of basis takes the figures of the old basis out of the form and out of the request', async () => {
    open({ basis_code: 'with_fee', basis_source: 'shipped', parameters: { fee_pct: '0.05', profit_pct: '0.1' } });
    choose('shipped:profit_only');
    expect(input('abort-parameter-fee_pct')).toBeNull();
    expect(input('abort-parameter-profit_pct')!.value).toBe('10');
    save();
    await waitFor(() => expect(mocked.putAbortTerms).toHaveBeenCalledTimes(1));
    expect(sentParameters()).toEqual({ profit_pct: '0.1' });
  });

  it('without a basis no figure travels, also when figures were stored', async () => {
    open({ basis_code: 'with_fee', basis_source: 'shipped', parameters: { fee_pct: '0.05', profit_pct: '0.1' } });
    choose('');
    save();
    await waitFor(() => expect(mocked.putAbortTerms).toHaveBeenCalledTimes(1));
    expect(sentParameters()).toEqual({});
  });

  it('tells a basis of a pack from a shipped one with the same id, and sends the source of the row chosen', async () => {
    mocked.putAbortTerms.mockResolvedValue({} as AbortTerms);
    const fromPack: AbortBasis = { ...basis('with_fee', []), source: 'pack' };
    wrap(
      <AbortTermsDialog
        open
        onClose={() => undefined}
        projectId="p1"
        item={item()}
        terms={null}
        bases={[WITH_FEE, fromPack]}
        labels={labels}
        onSaved={() => undefined}
      />,
    );
    fireEvent.change(input('abort-basis')!, { target: { value: 'pack:with_fee' } });
    // The basis of the pack has no figures, the shipped one of the same id has two.
    expect(screen.queryByTestId('abort-parameters')).toBeNull();
    fireEvent.click(screen.getByTestId('abort-terms-save'));
    await waitFor(() => expect(mocked.putAbortTerms).toHaveBeenCalledTimes(1));
    expect(mocked.putAbortTerms.mock.calls[0]![2]).toMatchObject({
      basis_code: 'with_fee',
      basis_source: 'pack',
      parameters: {},
    });
  });

  it('a figure above one hundred per cent is a problem of the form', () => {
    open();
    choose('shipped:profit_only');
    fireEvent.change(input('abort-parameter-profit_pct')!, { target: { value: '120' } });
    save();
    expect(screen.getByTestId('abort-terms-problems').textContent).toContain(
      enT('commitment.abort_form.problem.parameter_invalid'),
    );
    expect(mocked.putAbortTerms).not.toHaveBeenCalled();
  });
});

describe('approver of a tier', () => {
  function setup() {
    mocked.listAssignments.mockResolvedValue(page([]));
    return wrap(
      <ApproverSetup
        projectId="p1"
        matrix={matrix()}
        can={projectCan()}
        labels={labels}
        personName={() => null}
        onSaved={() => undefined}
      />,
    );
  }

  it('a deputy without an approver is sent as filled, and the refusal is shown in words', async () => {
    mocked.putAssignments.mockRejectedValue(
      new ApiError(422, 'Unprocessable Entity', {
        detail: {
          code: 'assignment_needs_approver',
          message_key: 'commitment.errors.assignment_needs_approver',
          message: 'Name the approver of this tier before a deputy or a validity period',
        },
      }),
    );
    setup();
    await waitFor(() => expect(input('tier-deputy-project_manager')).not.toBeNull());
    fireEvent.change(input('tier-deputy-project_manager')!, { target: { value: 'u-deputy' } });
    fireEvent.click(screen.getByTestId('approvers-save'));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain(enT('commitment.errors.assignment_needs_approver'));
    expect(mocked.putAssignments).toHaveBeenCalledWith('p1', [
      { project_role: 'project_manager', user_id: null, deputy_user_id: 'u-deputy', valid_from: null, valid_to: null },
    ]);
    expect(mocked.generateRoutes).not.toHaveBeenCalled();
  });

  it('a tier nobody filled anything in for is not sent at all', async () => {
    mocked.putAssignments.mockResolvedValue(page([]));
    mocked.generateRoutes.mockResolvedValue({ tiers: {} });
    setup();
    await waitFor(() => expect(input('tier-user-sponsor')).not.toBeNull());
    fireEvent.change(input('tier-user-sponsor')!, { target: { value: 'u-sponsor' } });
    fireEvent.click(screen.getByTestId('approvers-save'));
    await waitFor(() => expect(mocked.putAssignments).toHaveBeenCalledTimes(1));
    expect(mocked.putAssignments.mock.calls[0]![1]).toEqual([
      { project_role: 'sponsor', user_id: 'u-sponsor', deputy_user_id: null, valid_from: null, valid_to: null },
    ]);
  });
});
