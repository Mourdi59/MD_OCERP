// @vitest-environment jsdom
// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The project organisation: who holds each role, the bodies that decide
// together, the matrix of who decides what with its exceptions per part of
// the project, the lookup, and what happens when a change would let one
// person propose and decide the same thing.

import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen as page, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiError } from '@/shared/lib/api';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({ ProjectPeopleSelect: () => null }));
vi.mock('@/shared/ui/ContactSearchInput', () => ({ ContactSearchInput: () => null }));
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0, offset: 0, limit: 100 })) }));
vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  getRoles: vi.fn(),
  listBodies: vi.fn(),
  getMandates: vi.fn(),
  putMandates: vi.fn(),
  putRoleHolders: vi.fn(),
  createBody: vi.fn(),
  updateBody: vi.fn(),
  putBodyMembers: vi.fn(),
  whoDecides: vi.fn(),
}));

import * as api from '../api';
import { conflictCases, holdersToAcknowledge } from '../ConflictAcknowledge';
import { MandateMatrix, WhoDecidesLookup } from '../MandateMatrix';
import { BodyDialog, RoleHoldersDialog } from '../OrganisationDialogs';
import { OrganisationPanel } from '../OrganisationPanel';
import { body, decider, framework, matrix, rolesView, screen, settings } from './fixtures';

const mocked = vi.mocked(api);
const pageOf = <T,>(items: T[]) => ({ items, total: items.length, offset: 0, limit: 100 });

function mount(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const readOnly = () =>
  screen({ settings: settings({ can: { edit: false, read_personal: false, manage_organisation: false } }) });

const field = (selector: string) => document.querySelector(selector) as HTMLInputElement;
const type = (selector: string, value: string) => fireEvent.change(field(selector), { target: { value } });

const conflict = (roles: string[]) =>
  new ApiError(422, 'Unprocessable', {
    detail: {
      code: 'conflict_not_acknowledged',
      message: 'One person proposes and decides here',
      violations: [
        {
          decision_type: 'order_award',
          scope: '',
          user_id: 'u-owner',
          letters: ['P', 'D'],
          roles,
          severity: 'warning',
          acknowledged: false,
        },
      ],
    },
  });

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocked.getRoles.mockResolvedValue(rolesView());
  mocked.listBodies.mockResolvedValue(pageOf([body()]));
  mocked.getMandates.mockResolvedValue(matrix());
  mocked.putRoleHolders.mockResolvedValue(rolesView());
  mocked.putMandates.mockResolvedValue(matrix());
});

describe('reading a refused change that puts one person on both sides', () => {
  const refusal = {
    code: 'conflict_not_acknowledged',
    message: '',
    violations: [
      { decision_type: 'order_award', scope: '', user_id: 'u-owner', letters: ['P', 'D'], roles: ['project_manager'] },
      { decision_type: 'order_award', scope: '' },
    ],
  };

  it('keeps the cases that name a person and a decision', () => {
    expect(conflictCases(refusal)).toEqual([
      { decisionType: 'order_award', scope: '', userId: 'u-owner', letters: ['P', 'D'], roles: ['project_manager'] },
    ]);
    expect(conflictCases(null)).toEqual([]);
  });

  it('finds the role rows a reason goes on, and says which cases have none', () => {
    const holders = rolesView().holders;
    const cases = conflictCases(refusal);
    expect(holdersToAcknowledge(cases, holders).rows.map((h) => h.id)).toEqual(['h1']);
    expect(holdersToAcknowledge(cases, holders).open).toEqual([]);
    const seat = [{ ...cases[0]!, roles: ['steering'] }];
    expect(holdersToAcknowledge(seat, holders)).toEqual({ rows: [], open: seat });
  });
});

describe('the mandate matrix', () => {
  const show = (props: Partial<Parameters<typeof MandateMatrix>[0]> = {}) => {
    const onSaved = vi.fn();
    mount(<MandateMatrix screen={screen()} matrix={matrix()} roles={rolesView()} bodies={[body()]} onSaved={onSaved} {...props} />);
    return onSaved;
  };
  const cell = (index: number) => page.getAllByTestId('mandate-cell')[index] as HTMLSelectElement;
  const save = () => page.getByTestId('mandate-save') as HTMLButtonElement;

  it('names the columns and marks a decision nobody decides', () => {
    show();
    const head = within(page.getByTestId('mandate-table')).getAllByRole('columnheader').map((th) => th.textContent);
    expect(head).toEqual(['Decision', 'Client', 'Project manager', 'Steering committeebody']);
    const rows = page.getAllByTestId('mandate-row');
    expect(rows.map((r) => r.getAttribute('data-missing'))).toEqual(['false', 'true']);
    expect(within(rows[1]!).getByTestId('mandate-missing')).toBeTruthy();
  });

  it('follows the organisation flag: without it the matrix cannot be edited, and says who can', () => {
    show({ screen: readOnly() });
    expect((page.getByTestId('mandate-edit') as HTMLButtonElement).disabled).toBe(true);
    expect(page.getByTestId('disabled-reason').getAttribute('data-reason')).toBe('organisation');
  });

  it('will not save two deciders for one decision', () => {
    show();
    fireEvent.click(page.getByTestId('mandate-edit'));
    expect(page.getAllByTestId('mandate-cell')).toHaveLength(6);
    fireEvent.change(cell(0), { target: { value: 'D' } });
    expect(page.getByTestId('mandate-two-deciders').textContent).toContain('Order award');
    expect(save().disabled).toBe(true);
    expect(mocked.putMandates).not.toHaveBeenCalled();
  });

  it('sends every lettered cell with its stored note and nothing the server did not ask for', async () => {
    const onSaved = show();
    fireEvent.click(page.getByTestId('mandate-edit'));
    fireEvent.change(cell(0), { target: { value: 'C' } });
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    const rows = mocked.putMandates.mock.calls[0]?.[1] ?? [];
    expect(rows).toHaveLength(3);
    expect(rows.every((r) => !('id' in r))).toBe(true);
    expect(rows).toContainEqual({ decision_type: 'order_award', scope: '', holder_kind: 'role', holder_code: 'client', letter: 'C', scope_note: '' });
    expect(rows).toContainEqual({
      decision_type: 'order_award',
      scope: '',
      holder_kind: 'body',
      holder_code: 'steering',
      letter: 'D',
      scope_note: 'above the works budget',
    });
    expect(page.queryByTestId('mandate-save')).toBeNull();
  });

  it('shows an exception for one part of the project in words', () => {
    const rows = [
      ...matrix().rows,
      { id: 'm3', decision_type: 'order_award', scope: 'Lot 2', holder_kind: 'role' as const, holder_code: 'client', letter: 'D' as const, scope_note: 'facade package' },
    ];
    show({ matrix: matrix({ rows }) });
    const line = page.getByTestId('scoped-row');
    expect(line.textContent).toContain('Order award for Lot 2: Client');
    expect(line.textContent).toContain('facade package');
    expect(page.getAllByTestId('mandate-row')).toHaveLength(2);
  });

  it('shows no exceptions block while there are none and nobody edits', () => {
    show();
    expect(page.queryByTestId('scoped-mandates')).toBeNull();
  });

  it('an exception has to name its part of the project, and is then sent with it', async () => {
    const onSaved = show();
    fireEvent.click(page.getByTestId('mandate-edit'));
    expect(page.getByTestId('scoped-empty')).toBeTruthy();
    fireEvent.click(page.getByTestId('scoped-add'));
    expect(page.getByTestId('scoped-scope-missing')).toBeTruthy();
    expect(save().disabled).toBe(true);
    fireEvent.change(page.getByTestId('scoped-scope'), { target: { value: ' Lot 2 ' } });
    expect(save().disabled).toBe(false);
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(mocked.putMandates.mock.calls[0]?.[1]).toContainEqual({
      decision_type: 'order_award',
      scope: 'Lot 2',
      holder_kind: 'role',
      holder_code: 'client',
      letter: 'D',
      scope_note: '',
    });
  });

  it('will not save two deciders for the same part', () => {
    show();
    fireEvent.click(page.getByTestId('mandate-edit'));
    fireEvent.click(page.getByTestId('scoped-add'));
    fireEvent.click(page.getByTestId('scoped-add'));
    for (const input of page.getAllByTestId('scoped-scope')) fireEvent.change(input, { target: { value: 'Lot 2' } });
    expect(page.getByTestId('scoped-two-deciders').textContent).toContain('Order award for Lot 2');
    expect(save().disabled).toBe(true);
    fireEvent.click(page.getAllByTestId('scoped-remove')[1]!);
    expect(page.queryByTestId('scoped-two-deciders')).toBeNull();
    expect(save().disabled).toBe(false);
  });

  it('takes a written reason when one person proposes and decides, stores it on the role and saves again', async () => {
    mocked.putMandates.mockRejectedValueOnce(conflict(['project_manager']));
    const onSaved = show();
    fireEvent.click(page.getByTestId('mandate-edit'));
    fireEvent.click(save());
    const box = await page.findByTestId('conflict-acknowledge');
    expect(within(box).getByTestId('conflict-cases').textContent).toContain('Dana Weber');
    expect(within(box).getByTestId('conflict-cases').textContent).toContain('Order award');
    const accept = (await within(box).findByTestId('conflict-accept')) as HTMLButtonElement;
    expect(accept.disabled).toBe(true);
    fireEvent.change(within(box).getByTestId('conflict-reason'), { target: { value: ' Small team, the client co-signs ' } });
    fireEvent.click(accept);
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(mocked.putRoleHolders).toHaveBeenCalledWith(
      'p1',
      'project_manager',
      [expect.objectContaining({ roster_member_id: 'r1', conflict_rationale: 'Small team, the client co-signs' })],
      '',
    );
    expect(mocked.putMandates).toHaveBeenCalledTimes(2);
    expect(onSaved).not.toHaveBeenCalledTimes(0);
  });

  it('says what to change when the person holds no role a reason could go on', async () => {
    mocked.putMandates.mockRejectedValueOnce(conflict(['steering']));
    show();
    fireEvent.click(page.getByTestId('mandate-edit'));
    fireEvent.click(save());
    expect(await page.findByTestId('conflict-no-role')).toBeTruthy();
    expect(page.queryByTestId('conflict-accept')).toBeNull();
    expect(mocked.putRoleHolders).not.toHaveBeenCalled();
  });

  it('shows any other refusal as the server put it', async () => {
    mocked.putMandates.mockRejectedValueOnce(
      new ApiError(422, 'Unprocessable', { detail: { code: 'two_deciders', violations: [{ decision_type: 'order_award', scope: '' }] } }),
    );
    show();
    fireEvent.click(page.getByTestId('mandate-edit'));
    fireEvent.click(save());
    const refusal = await page.findByTestId('refusal');
    expect(refusal.getAttribute('data-code')).toBe('two_deciders');
    expect(page.queryByTestId('conflict-acknowledge')).toBeNull();
  });

  it('lists the accepted conflicts the server reports', () => {
    show({
      matrix: matrix({
        conflicts: [
          { decision_type: 'order_award', scope: '', user_id: 'u-owner', letters: ['P', 'D'], roles: ['project_manager'], severity: 'warning', acknowledged: true },
        ],
      }),
    });
    expect(page.getByTestId('mandate-conflicts').textContent).toContain('(accepted with a written reason)');
  });
});

describe('looking up who decides', () => {
  it('names the holder, the people behind it today and what stands in the way', async () => {
    mocked.whoDecides.mockResolvedValue(decider());
    mount(<WhoDecidesLookup screen={screen()} matrix={matrix()} roles={rolesView()} bodies={[body()]} />);
    expect(page.queryByTestId('who-answer')).toBeNull();
    fireEvent.click(page.getByTestId('who-lookup'));
    const answer = await page.findByTestId('who-answer');
    expect(within(answer).getByText('Decided by: Steering committee')).toBeTruthy();
    expect(within(answer).getByText('Today that is: Dana Weber')).toBeTruthy();
    expect(within(answer).getByTestId('who-flag').getAttribute('data-flag')).toBe('body_inquorate');
    expect(mocked.whoDecides).toHaveBeenCalledWith('p1', { decisionType: 'order_award', amount: undefined });
  });

  it('asks for an amount only where the decision has one', () => {
    mount(<WhoDecidesLookup screen={screen()} matrix={matrix()} roles={rolesView()} bodies={[]} />);
    expect(page.getByText('Amount (optional)')).toBeTruthy();
    fireEvent.change(page.getByTestId('who-decision'), { target: { value: 'stakeholder_commitment' } });
    expect(page.queryByText('Amount (optional)')).toBeNull();
  });
});

describe('a governance body', () => {
  const dialog = (existing: ReturnType<typeof body> | null = null) => {
    const onSaved = vi.fn();
    mount(<BodyDialog screen={screen()} body={existing} roles={framework().roles} onClose={() => undefined} onSaved={onSaved} />);
    return onSaved;
  };
  const save = () => page.getByTestId('body-save') as HTMLButtonElement;

  it('starts on the level its kind usually sits on and is created with it', async () => {
    mocked.createBody.mockResolvedValue(body({ id: 'b9' }));
    mocked.putBodyMembers.mockResolvedValue(body({ id: 'b9' }));
    const onSaved = dialog();
    expect(field('#body-level').value).toBe('3');
    type('#body-name', 'Change board');
    type('#body-code', 'Change Board');
    expect(page.getByText('Use only small letters, digits and underscores.')).toBeTruthy();
    expect(save().disabled).toBe(true);
    type('#body-code', 'change_board');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(mocked.createBody).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({ code: 'change_board', name: 'Change board', body_type: 'steering_committee', decision_level: 3, quorum_min: null }),
    );
    expect(mocked.putBodyMembers).toHaveBeenCalledWith('p1', 'b9', []);
  });

  it('keeps the level of an existing body and sends a changed one', async () => {
    mocked.updateBody.mockResolvedValue(body());
    mocked.putBodyMembers.mockResolvedValue(body());
    const onSaved = dialog(body({ decision_level: 2 }));
    expect(field('#body-level').value).toBe('2');
    expect(field('#body-code').disabled).toBe(true);
    type('#body-level', '0');
    expect(save().disabled).toBe(true);
    type('#body-level', '4');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(mocked.updateBody).toHaveBeenCalledWith('p1', 'b1', expect.objectContaining({ decision_level: 4 }));
    expect(mocked.createBody).not.toHaveBeenCalled();
  });

  it('asks how many members when the quorum is a number', () => {
    dialog();
    type('#body-name', 'Change board');
    type('#body-code', 'change_board');
    type('#body-quorum', 'min_members');
    expect(save().disabled).toBe(true);
    type('#body-quorum-min', '3');
    expect(save().disabled).toBe(false);
  });

  it('adds a member as a role, with a vote', async () => {
    mocked.updateBody.mockResolvedValue(body());
    mocked.putBodyMembers.mockResolvedValue(body());
    const onSaved = dialog(body());
    fireEvent.click(page.getByTestId('body-member-add'));
    expect(page.getAllByTestId('body-member-row')).toHaveLength(1);
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(mocked.putBodyMembers).toHaveBeenCalledWith('p1', 'b1', [
      { role_code: 'client', user_id: null, contact_id: null, voting: true, valid_from: null, valid_to: null },
    ]);
  });

  it('takes the written reason when its members would let one person propose and decide', async () => {
    mocked.updateBody.mockResolvedValue(body());
    mocked.putBodyMembers.mockRejectedValueOnce(conflict(['project_manager'])).mockResolvedValue(body());
    const onSaved = dialog(body());
    fireEvent.click(save());
    const box = await page.findByTestId('conflict-acknowledge');
    fireEvent.change(await within(box).findByTestId('conflict-reason'), { target: { value: 'Agreed with the client' } });
    fireEvent.click(within(box).getByTestId('conflict-accept'));
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(mocked.putRoleHolders.mock.calls[0]?.[2]).toEqual([expect.objectContaining({ conflict_rationale: 'Agreed with the client' })]);
    expect(mocked.putBodyMembers).toHaveBeenCalledTimes(2);
  });
});

describe('who holds a role', () => {
  const roster = [{ id: 'r1', user_id: 'u-owner', display_name: 'Dana Weber', email: '', company_name: '', is_active: true }] as never;
  const dialog = () => {
    const onSaved = vi.fn();
    mount(
      <RoleHoldersDialog
        screen={screen()}
        role={framework().roles[1]!}
        holders={rolesView().holders}
        roster={roster}
        onClose={() => undefined}
        onSaved={onSaved}
      />,
    );
    return onSaved;
  };
  const save = () => page.getByTestId('role-holders-save') as HTMLButtonElement;

  it('sends the holder as stored when nothing changed', async () => {
    const onSaved = dialog();
    expect((page.getByTestId('role-holder-select') as HTMLSelectElement).value).toBe('r1');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(mocked.putRoleHolders).toHaveBeenCalledWith(
      'p1',
      'project_manager',
      [{ roster_member_id: 'r1', holder_contact_id: null, deputy_roster_member_id: null, valid_from: null, valid_to: null, conflict_rationale: '' }],
      '',
    );
  });

  it('a new row has to name somebody, and an emptied list says the role becomes vacant', () => {
    dialog();
    fireEvent.click(page.getByTestId('role-holder-add'));
    expect(save().disabled).toBe(true);
    for (const remove of page.getAllByTestId('role-holder-remove')) fireEvent.click(remove);
    expect(page.getByTestId('role-holders-none').textContent).toBe('Saving now leaves the role vacant.');
    expect(save().disabled).toBe(false);
  });

  it('shows the reason of the server when the holder is refused', async () => {
    mocked.putRoleHolders.mockRejectedValueOnce(
      new ApiError(422, 'Unprocessable', { detail: { code: 'role_not_multi', message: 'This role allows only one holder at a time' } }),
    );
    dialog();
    fireEvent.click(save());
    expect((await page.findByTestId('refusal')).textContent).toBe('This role allows only one holder at a time');
  });
});

describe('the organisation tab', () => {
  it('shows the roles with a required one that is vacant, and each body with its level', async () => {
    mount(<OrganisationPanel screen={screen()} />);
    const roles = await page.findAllByTestId('role-entry');
    expect(roles.map((r) => r.getAttribute('data-vacant'))).toEqual(['true', 'false']);
    expect(within(roles[0]!).getByTestId('role-vacant').textContent).toBe('Vacant');
    expect(within(roles[1]!).getByText('Dana Weber')).toBeTruthy();
    const entry = page.getByTestId('body-entry');
    expect(within(entry).getByTestId('body-level').textContent).toBe('Escalation level 3');
    expect(within(entry).getByTestId('body-inquorate')).toBeTruthy();
    expect(page.getByTestId('mandate-matrix')).toBeTruthy();
    expect(page.getByTestId('who-decides')).toBeTruthy();
  });

  it('says so when there are no bodies yet, with the action to add one', async () => {
    mocked.listBodies.mockResolvedValue(pageOf([]));
    mount(<OrganisationPanel screen={screen()} />);
    expect((await page.findByTestId('bodies-empty')).textContent).toContain('No bodies yet');
    expect((page.getByTestId('body-add') as HTMLButtonElement).disabled).toBe(false);
  });

  it('a reader without the organisation flag sees everything and can change nothing', async () => {
    mount(<OrganisationPanel screen={readOnly()} />);
    await page.findAllByTestId('role-entry');
    expect(page.queryByTestId('role-set')).toBeNull();
    expect(page.queryByTestId('body-edit')).toBeNull();
    expect((page.getByTestId('body-add') as HTMLButtonElement).disabled).toBe(true);
    expect((page.getByTestId('mandate-edit') as HTMLButtonElement).disabled).toBe(true);
  });

  it('says so when the organisation cannot be loaded', async () => {
    mocked.getRoles.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    mount(<OrganisationPanel screen={screen()} />);
    expect(await page.findByText('The project organisation could not be loaded')).toBeTruthy();
    expect(page.queryByTestId('organisation-panel')).toBeNull();
  });
});
