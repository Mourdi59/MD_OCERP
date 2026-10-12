// @vitest-environment jsdom
// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// What a stakeholder and a commitment point at in the other registers of the
// project: the group a stakeholder belongs to, a risk, a task. A link is
// picked from the project's own records, is sent only when it changed, and a
// name the reader may not see is never written back empty.

import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen as page, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({ ProjectPeopleSelect: () => null }));
vi.mock('@/shared/ui/ContactSearchInput', () => ({ ContactSearchInput: () => null }));
vi.mock('@/features/meetings/api', () => ({ fetchMeetings: vi.fn(async () => []) }));
vi.mock('@/features/correspondence/api', () => ({
  fetchCorrespondence: vi.fn(async () => ({ items: [], total: 0, offset: 0, limit: 100 })),
}));
vi.mock('@/features/tasks/api', () => ({
  fetchTasks: vi.fn(async () => ({
    items: [{ id: 't1', title: 'Order the noise barrier', due_date: '2026-11-15' }],
    total: 1,
    offset: 0,
    limit: 50,
  })),
}));
vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  listProjectRisks: vi.fn(async () => ({
    items: [{ id: 'r1', code: 'R-004', title: 'Objection delays the permit' }],
    total: 1,
    offset: 0,
    limit: 100,
  })),
  listAssessments: vi.fn(async () => ({ items: [], total: 0, offset: 0, limit: 100 })),
  createStakeholder: vi.fn(),
  updateStakeholder: vi.fn(),
  createCommitment: vi.fn(),
  updateCommitment: vi.fn(),
}));

import * as api from '../api';
import type { CommitmentInput, StakeholderInput } from '../api';
import { CommitmentDialog } from '../CommitmentDialog';
import { StakeholderDetail } from '../StakeholderDetail';
import { StakeholderDialog } from '../StakeholderDialog';
import { withDescendants } from '../rules';
import { commitment, screen, stakeholder } from './fixtures';

const mocked = vi.mocked(api);

function mount(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const field = (selector: string) => document.querySelector(selector) as HTMLSelectElement;
const choose = (selector: string, value: string) => fireEvent.change(field(selector), { target: { value } });
const values = (selector: string) => Array.from(field(selector).querySelectorAll('option')).map((o) => o.value);

const street = stakeholder({ id: 'g1', code: 'STK-010', display_name: 'Mill Lane residents', name: 'Mill Lane residents', is_group: true });
const house = stakeholder({ id: 's2', code: 'STK-011', display_name: 'Number 4', name: 'Number 4', parent_stakeholder_id: 'g1' });
const flat = stakeholder({ id: 's3', code: 'STK-012', display_name: 'Top flat', name: 'Top flat', parent_stakeholder_id: 's2' });
const authority = stakeholder();
const register = [authority, street, house, flat];

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('what is filed under a stakeholder', () => {
  it('follows the chain to any depth and survives a loop in the data', () => {
    expect([...withDescendants(register, 'g1')].sort()).toEqual(['g1', 's2', 's3']);
    expect([...withDescendants(register, 's1')]).toEqual(['s1']);
    const loop = [
      { id: 'a', parent_stakeholder_id: 'b' },
      { id: 'b', parent_stakeholder_id: 'a' },
    ];
    expect([...withDescendants(loop, 'a')].sort()).toEqual(['a', 'b']);
  });
});

describe('editing where a stakeholder belongs', () => {
  const dialog = (row: ReturnType<typeof stakeholder> | null) => {
    const onSaved = vi.fn();
    mount(<StakeholderDialog screen={screen()} stakeholder={row} stakeholders={register} onClose={() => undefined} onSaved={onSaved} />);
    return onSaved;
  };
  const save = () => fireEvent.click(page.getByTestId('stakeholder-save'));
  const sent = (): StakeholderInput => mocked.updateStakeholder.mock.calls[0]?.[2] ?? {};

  it('offers everyone except the stakeholder itself and what is filed under it', () => {
    dialog(street);
    expect(values('#stakeholder-parent')).toEqual(['', 's1']);
  });

  it('sends the new group and leaves an untouched link out of the request', async () => {
    mocked.updateStakeholder.mockResolvedValue(house);
    const onSaved = dialog(house);
    expect(field('#stakeholder-parent').value).toBe('g1');
    choose('#stakeholder-parent', 's1');
    save();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(sent()).toMatchObject({ parent_stakeholder_id: 's1' });
    expect('risk_id' in sent()).toBe(false);
    expect('geo' in sent()).toBe(false);
  });

  it('takes the stakeholder out of its group', async () => {
    mocked.updateStakeholder.mockResolvedValue(house);
    const onSaved = dialog(house);
    choose('#stakeholder-parent', '');
    save();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(sent().parent_stakeholder_id).toBeNull();
  });

  it('picks a risk from the risk register of the project', async () => {
    mocked.updateStakeholder.mockResolvedValue(authority);
    const onSaved = dialog(authority);
    await waitFor(() => expect(values('#stakeholder-risk')).toEqual(['', 'r1']));
    expect(page.getByText('R-004: Objection delays the permit')).toBeTruthy();
    choose('#stakeholder-risk', 'r1');
    save();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(sent()).toMatchObject({ risk_id: 'r1' });
    expect('parent_stakeholder_id' in sent()).toBe(false);
  });

  it('keeps a stored risk the list does not offer, and does not send it', async () => {
    mocked.updateStakeholder.mockResolvedValue(authority);
    const onSaved = dialog(stakeholder({ risk_id: 'r-old' }));
    await waitFor(() => expect(values('#stakeholder-risk')).toEqual(['', 'r-old', 'r1']));
    expect(field('#stakeholder-risk').value).toBe('r-old');
    save();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect('risk_id' in sent()).toBe(false);
  });

  it('never writes back the name or the place of a private person it may not see', async () => {
    const hidden = stakeholder({ id: 's9', display_name: '', name: null, masked: true, is_confidential: true, geo: null });
    mocked.updateStakeholder.mockResolvedValue(hidden);
    const onSaved = dialog(hidden);
    expect((document.querySelector('#stakeholder-name') as HTMLInputElement).disabled).toBe(true);
    expect(page.getByText('The name is hidden from you and stays as it is.')).toBeTruthy();
    save();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect('display_name' in sent()).toBe(false);
    expect('geo' in sent()).toBe(false);
  });

  it('a new stakeholder carries a group only when one was picked', async () => {
    mocked.createStakeholder.mockResolvedValue(authority);
    const onSaved = dialog(null);
    fireEvent.change(document.querySelector('#stakeholder-name') as HTMLInputElement, { target: { value: 'Number 6' } });
    choose('#stakeholder-category', 'permitting_authority');
    save();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const body: StakeholderInput = mocked.createStakeholder.mock.calls[0]?.[1] ?? {};
    expect(body).toMatchObject({ display_name: 'Number 6' });
    expect('parent_stakeholder_id' in body).toBe(false);
    expect('risk_id' in body).toBe(false);
  });
});

describe('a stakeholder page shows where it belongs', () => {
  const detail = (row: ReturnType<typeof stakeholder>) =>
    mount(<StakeholderDetail screen={screen()} stakeholder={row} stakeholders={register} onBack={() => undefined} />);

  it('names the group of a member', () => {
    detail(house);
    expect(page.getByTestId('stakeholder-parent-line').textContent).toBe('Part of Mill Lane residents');
    expect(page.getByTestId('stakeholder-members-line').textContent).toBe('Includes Top flat');
  });

  it('says nothing for a stakeholder that stands alone', () => {
    detail(authority);
    expect(page.queryByTestId('stakeholder-parent-line')).toBeNull();
    expect(page.queryByTestId('stakeholder-members-line')).toBeNull();
  });
});

describe('what a commitment is tied to', () => {
  const dialog = (row: ReturnType<typeof commitment>) => {
    const onSaved = vi.fn();
    mount(
      <CommitmentDialog screen={screen()} commitment={row} stakeholders={[authority]} events={[]} onClose={() => undefined} onSaved={onSaved} />,
    );
    return onSaved;
  };
  const sent = (): CommitmentInput => mocked.updateCommitment.mock.calls[0]?.[2] ?? {};

  it('ties it to a task and a risk of the project', async () => {
    mocked.updateCommitment.mockResolvedValue(commitment());
    const onSaved = dialog(commitment());
    await waitFor(() => expect(values('#commitment-task')).toEqual(['', 't1']));
    await waitFor(() => expect(values('#commitment-risk')).toEqual(['', 'r1']));
    choose('#commitment-task', 't1');
    choose('#commitment-risk', 'r1');
    fireEvent.click(page.getByTestId('commitment-save'));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(sent()).toMatchObject({ task_id: 't1', risk_id: 'r1' });
  });

  it('leaves both links out of the request when they were not changed', async () => {
    mocked.updateCommitment.mockResolvedValue(commitment());
    const onSaved = dialog(commitment({ task_id: 't-old', risk_id: 'r1' }));
    await waitFor(() => expect(values('#commitment-task')).toEqual(['', 't-old', 't1']));
    fireEvent.click(page.getByTestId('commitment-save'));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect('task_id' in sent()).toBe(false);
    expect('risk_id' in sent()).toBe(false);
  });

  it('removes a link when the reader picks none', async () => {
    mocked.updateCommitment.mockResolvedValue(commitment());
    const onSaved = dialog(commitment({ task_id: 't1' }));
    choose('#commitment-task', '');
    fireEvent.click(page.getByTestId('commitment-save'));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(sent().task_id).toBeNull();
  });
});
