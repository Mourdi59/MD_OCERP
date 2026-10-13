// @vitest-environment jsdom
// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The communication plan as a reader meets it: what is due, the standing
// lines and what took place, then the three dialogs that write to it. Also
// where a commitment says it was promised, since that picks from the same
// project records.

import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen as page, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiError } from '@/shared/lib/api';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({ ProjectPeopleSelect: () => null }));
vi.mock('@/shared/ui/ContactSearchInput', () => ({ ContactSearchInput: () => null }));
vi.mock('@/features/meetings/api', () => ({
  fetchMeetings: vi.fn(async () => [{ id: 'm1', title: 'Site meeting 12', date: '2026-09-10' }]),
}));
vi.mock('@/features/correspondence/api', () => ({
  fetchCorrespondence: vi.fn(async () => ({
    items: [{ id: 'l1', subject: 'Notice of night works', date_received: null, date_sent: '2026-09-02' }],
    total: 1,
    offset: 0,
    limit: 100,
  })),
}));
vi.mock('@/features/tasks/api', () => ({
  fetchTasks: vi.fn(async () => ({ items: [], total: 0, offset: 0, limit: 50 })),
}));
vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  listProjectRisks: vi.fn(async () => ({ items: [], total: 0, offset: 0, limit: 100 })),
  listRequirementOptions: vi.fn(async () => ({ items: [] })),
  listReleaseItems: vi.fn(async () => ({ items: [], available: true, reason: null })),
  listGates: vi.fn(async () => ({
    items: [
      { code: 'G2', name: 'Design freeze', status: 'planned' },
      { code: 'G3', name: 'Start of works', status: 'planned' },
    ],
    gates_in_use: true,
  })),
  createPlanItem: vi.fn(),
  updatePlanItem: vi.fn(),
  deletePlanItem: vi.fn(),
  recordOccurrence: vi.fn(),
  createEvent: vi.fn(),
  updateEvent: vi.fn(),
  createCommitment: vi.fn(),
}));

import * as api from '../api';
import { CommitmentDialog } from '../CommitmentDialog';
import { EventDialog } from '../EventDialog';
import { PlanItemDialog } from '../PlanItemDialog';
import { PlanPanel, frequencyText } from '../PlanPanel';
import { enT } from './i18nMock';
import { commitment, due, event, planItem, screen, settings, stakeholder } from './fixtures';

const mocked = vi.mocked(api);

function mount(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const readOnly = () =>
  screen({ settings: settings({ can: { edit: false, read_personal: false, manage_organisation: false } }) });

const field = (selector: string) => document.querySelector(selector) as HTMLInputElement;
const type = (selector: string, value: string) => fireEvent.change(field(selector), { target: { value } });

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('how often a plan line recurs, in words', () => {
  it('names a preset, a trigger and keeps an own rule as stored', () => {
    expect(frequencyText(enT, { frequency: 'FREQ=MONTHLY', trigger_kind: null, trigger_ref: null })).toBe('Every month');
    expect(frequencyText(enT, { frequency: '', trigger_kind: 'gate', trigger_ref: '' })).toBe('Each time a gate is submitted for review');
    expect(frequencyText(enT, { frequency: '', trigger_kind: 'gate', trigger_ref: 'G2' })).toBe('Each time G2 is submitted for review');
    expect(frequencyText(enT, { frequency: '', trigger_kind: 'gate', trigger_ref: 'G2' }, () => 'Design freeze')).toBe(
      'Each time Design freeze is submitted for review',
    );
    expect(frequencyText(enT, { frequency: '', trigger_kind: 'event', trigger_ref: 'stakeholders.commitment.fulfilled' })).toBe(
      'Each time a commitment is fulfilled',
    );
    expect(frequencyText(enT, { frequency: '', trigger_kind: 'event', trigger_ref: 'something.else' })).toBe('When a project event happens');
    expect(frequencyText(enT, { frequency: 'FREQ=WEEKLY;BYDAY=TU', trigger_kind: null, trigger_ref: null })).toBe('FREQ=WEEKLY;BYDAY=TU');
  });
});

describe('the communication plan', () => {
  const panel = (props: Partial<Parameters<typeof PlanPanel>[0]> = {}) =>
    mount(<PlanPanel screen={screen()} items={[planItem()]} due={[due()]} events={[event()]} stakeholders={[stakeholder()]} {...props} />);

  it('explains itself when nothing is planned or recorded, with the one action', () => {
    panel({ items: [], due: [], events: [] });
    expect(page.getByText('No communication planned yet')).toBeTruthy();
    expect(page.queryByTestId('plan-panel')).toBeNull();
    fireEvent.click(page.getByTestId('plan-item-add'));
    expect(page.getByTestId('plan-item-dialog')).toBeTruthy();
  });

  it('a viewer sees the plan but no way to change it, and is told why', () => {
    panel({ screen: readOnly() });
    expect((page.getByTestId('plan-item-add') as HTMLButtonElement).disabled).toBe(true);
    expect(page.getByTestId('disabled-reason').getAttribute('data-reason')).toBe('edit');
    expect(page.queryByTestId('due-record')).toBeNull();
    expect(page.queryByTestId('plan-item-edit')).toBeNull();
    expect(page.queryByTestId('event-add')).toBeNull();
  });

  it('lists what is due, marks what is overdue and leaves out what is done', () => {
    panel({ due: [due(), due({ date: '2026-11-01', overdue: false }), due({ date: '2026-09-01', done: true })] });
    const entries = page.getAllByTestId('due-entry');
    expect(entries.map((e) => e.getAttribute('data-overdue'))).toEqual(['true', 'false']);
    expect(within(entries[0]!).getByTestId('due-overdue')).toBeTruthy();
    expect(within(entries[0]!).getByText('Letter, Inform, Dana Weber')).toBeTruthy();
  });

  it('says so when nothing is due', () => {
    panel({ due: [] });
    expect(page.getByTestId('due-empty').textContent).toBe('Nothing is due in the coming weeks.');
  });

  it('describes a plan line: how often, through what, to whom, by whom', () => {
    panel();
    const entry = page.getByTestId('plan-entry');
    expect(within(entry).getByText('Every month, Letter, Inform')).toBeTruthy();
    expect(within(entry).getByText('Audience: Neighbour')).toBeTruthy();
    expect(within(entry).getByText('Responsible: Dana Weber')).toBeTruthy();
    expect(within(entry).getByText('What happens on site next month')).toBeTruthy();
  });

  it('marks the plan line a notification linked to, and only that one', () => {
    panel({ items: [planItem(), planItem({ id: 'pl2', title: 'Authority briefing' })], focusItemId: 'pl2' });
    const entries = page.getAllByTestId('plan-entry');
    expect(entries.map((e) => e.getAttribute('data-focused'))).toEqual([null, 'true']);
  });

  it('shows what took place, and that feedback is still owed', () => {
    panel();
    const entry = page.getByTestId('event-entry');
    expect(within(entry).getByText('With: Building authority')).toBeTruthy();
    expect(within(entry).getByText('Residents asked for quiet hours')).toBeTruthy();
    expect(within(entry).getByTestId('feedback-missing').textContent).toContain('promised feedback by');
  });

  it('says so when nothing is recorded yet', () => {
    panel({ events: [] });
    expect(page.getByTestId('events-empty').textContent).toBe('Nothing is recorded yet.');
  });

  it('records a due occurrence against its plan line and its date', async () => {
    const onChanged = vi.fn();
    mocked.recordOccurrence.mockResolvedValue(event());
    panel({ screen: screen({ onChanged }) });
    fireEvent.click(page.getByTestId('due-record'));
    expect(field('#event-title').value).toBe('Neighbour newsletter');
    fireEvent.click(page.getByTestId('event-save'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.recordOccurrence).toHaveBeenCalledWith('p1', 'pl1', expect.objectContaining({ occurrence_date: '2026-10-01', title: 'Neighbour newsletter' }));
    expect(page.queryByTestId('event-dialog')).toBeNull();
  });

  it('shows the reason of the server when a line cannot be removed', async () => {
    mocked.deletePlanItem.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'plan_item_not_found', message: 'Plan item not found' } }),
    );
    panel();
    fireEvent.click(page.getByTestId('plan-item-delete'));
    fireEvent.click(page.getByTestId('confirm-dialog-confirm'));
    expect(await page.findByText('Plan item not found')).toBeTruthy();
  });
});

describe('planning a communication', () => {
  const dialog = (item: ReturnType<typeof planItem> | null = null) => {
    const onSaved = vi.fn();
    mount(<PlanItemDialog screen={screen()} item={item} stakeholders={[stakeholder()]} onClose={() => undefined} onSaved={onSaved} />);
    return onSaved;
  };
  const save = () => page.getByTestId('plan-item-save') as HTMLButtonElement;

  it('needs a title, an audience and a first date before it can be saved', () => {
    dialog();
    expect(save().disabled).toBe(true);
    expect(page.getByTestId('plan-audience-missing')).toBeTruthy();
    type('#plan-title', 'Monthly letter');
    fireEvent.click(within(page.getByTestId('plan-audience')).getByRole('checkbox'));
    expect(page.queryByTestId('plan-audience-missing')).toBeNull();
    expect(save().disabled).toBe(true);
    type('#plan-starts', '2026-11-01');
    expect(save().disabled).toBe(false);
  });

  it('sends the schedule as the rule the preset stands for', async () => {
    mocked.createPlanItem.mockResolvedValue(planItem());
    const onSaved = dialog();
    type('#plan-title', 'Monthly letter');
    fireEvent.click(within(page.getByTestId('plan-audience')).getByRole('checkbox'));
    type('#plan-starts', '2026-11-01');
    type('#plan-frequency', 'quarterly');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const sent = mocked.createPlanItem.mock.calls[0]?.[1] ?? {};
    expect(sent).toMatchObject({
      title: 'Monthly letter',
      audience_stakeholder_ids: ['s1'],
      frequency: 'FREQ=MONTHLY;INTERVAL=3',
      starts_on: '2026-11-01',
    });
    expect('trigger_kind' in sent).toBe(false);
  });

  it('a line set off by a project event needs no date and sends the trigger instead of a schedule', async () => {
    mocked.createPlanItem.mockResolvedValue(planItem());
    const onSaved = dialog();
    type('#plan-title', 'Briefing before each gate');
    fireEvent.click(within(page.getByTestId('plan-audience')).getByRole('checkbox'));
    type('#plan-start', 'gate');
    expect(field('#plan-starts')).toBeNull();
    expect(field('#plan-frequency')).toBeNull();
    expect(save().disabled).toBe(false);
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const sent = mocked.createPlanItem.mock.calls[0]?.[1] ?? {};
    expect(sent).toMatchObject({ trigger_kind: 'gate', trigger_ref: '' });
    expect('frequency' in sent).toBe(false);
  });

  it('picks one gate of the project by its name and stores the code', async () => {
    mocked.createPlanItem.mockResolvedValue(planItem());
    const onSaved = dialog();
    type('#plan-title', 'Briefing before the design freeze');
    fireEvent.click(within(page.getByTestId('plan-audience')).getByRole('checkbox'));
    expect(field('#plan-gate')).toBeNull();
    type('#plan-start', 'gate');
    await waitFor(() => expect([...field('#plan-gate').querySelectorAll('option')].map((o) => o.textContent)).toEqual([
      'Every gate',
      'Design freeze',
      'Start of works',
    ]));
    type('#plan-gate', 'G2');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(mocked.createPlanItem.mock.calls[0]?.[1]).toMatchObject({ trigger_kind: 'gate', trigger_ref: 'G2' });
  });

  it('moves a line to another gate, and keeps a gate the project no longer lists', async () => {
    mocked.updatePlanItem.mockResolvedValue(planItem());
    const onSaved = dialog(planItem({ trigger_kind: 'gate', trigger_ref: 'G9', frequency: '', starts_on: null }));
    await waitFor(() => expect(field('#plan-gate').querySelectorAll('option')).toHaveLength(4));
    expect(field('#plan-gate').value).toBe('G9');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect('trigger_ref' in (mocked.updatePlanItem.mock.calls[0]?.[2] ?? {})).toBe(false);
    type('#plan-gate', 'G3');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(2));
    expect(mocked.updatePlanItem.mock.calls[1]?.[2]).toMatchObject({ trigger_kind: 'gate', trigger_ref: 'G3' });
  });

  it('does not offer the gate trigger on a project run without gates, and says why', async () => {
    mocked.listGates.mockResolvedValueOnce({ items: [], gates_in_use: false });
    dialog();
    const starts = () => [...field('#plan-start').querySelectorAll('option')].map((o) => (o as HTMLOptionElement).value);
    await waitFor(() => expect(starts()).not.toContain('gate'));
    expect(starts()).toContain('schedule');
    expect(page.getByText('This project does not use gates, so a gate cannot set a line off.')).toBeTruthy();
  });

  it('keeps showing a line that waits for a gate on such a project, with the reason it never starts', async () => {
    mocked.listGates.mockResolvedValueOnce({ items: [], gates_in_use: false });
    dialog(planItem({ trigger_kind: 'gate', trigger_ref: '', frequency: '', starts_on: null }));
    expect(
      await page.findByText('This project does not use gates, so nothing sets this line off. Give it fixed dates instead.'),
    ).toBeTruthy();
    expect(field('#plan-start').value).toBe('gate');
    type('#plan-start', 'schedule');
    expect(field('#plan-gate')).toBeNull();
    expect(field('#plan-starts')).toBeTruthy();
  });

  const withoutGates = {
    items: [],
    gates_in_use: false,
    gate_bound_event_triggers: ['project_governance.gate.decided', 'project_governance.phase.changed'],
  };

  it('offers no project event only a gate can cause on a project run without gates', async () => {
    mocked.listGates.mockResolvedValueOnce(withoutGates);
    dialog();
    const starts = () => [...field('#plan-start').querySelectorAll('option')].map((o) => (o as HTMLOptionElement).value);
    await waitFor(() => expect(starts()).not.toContain('gate'));
    expect(starts()).toEqual(['schedule', 'stakeholders.commitment.fulfilled']);
  });

  it('keeps a stored line that waits for a decided gate on such a project, and says it never starts', async () => {
    mocked.listGates.mockResolvedValueOnce(withoutGates);
    dialog(planItem({ trigger_kind: 'event', trigger_ref: 'project_governance.gate.decided', frequency: '', starts_on: null }));
    expect(
      await page.findByText('This project does not use gates, so nothing sets this line off. Give it fixed dates instead.'),
    ).toBeTruthy();
    expect(field('#plan-start').value).toBe('project_governance.gate.decided');
    expect(page.queryByText('This project does not use gates, so a gate cannot set a line off.')).toBeNull();
  });

  it('names the project event a line waits for', async () => {
    mocked.createPlanItem.mockResolvedValue(planItem());
    const onSaved = dialog();
    type('#plan-title', 'Thank the neighbours');
    fireEvent.click(within(page.getByTestId('plan-audience')).getByRole('checkbox'));
    type('#plan-start', 'stakeholders.commitment.fulfilled');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(mocked.createPlanItem.mock.calls[0]?.[1]).toMatchObject({ trigger_kind: 'event', trigger_ref: 'stakeholders.commitment.fulfilled' });
  });

  it('leaves a schedule and a trigger it did not change out of an edit', async () => {
    mocked.updatePlanItem.mockResolvedValue(planItem());
    const onSaved = dialog(planItem({ frequency: 'FREQ=WEEKLY;BYDAY=TU', trigger_kind: null, trigger_ref: null }));
    expect(field('#plan-frequency').value).toBe('custom');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const sent = mocked.updatePlanItem.mock.calls[0]?.[2] ?? {};
    expect('frequency' in sent || 'trigger_kind' in sent || 'trigger_ref' in sent).toBe(false);
  });

  it('keeps a trigger this screen does not offer, and the gate a gate trigger names', async () => {
    mocked.updatePlanItem.mockResolvedValue(planItem());
    const onSaved = dialog(planItem({ trigger_kind: 'event', trigger_ref: 'something.else', starts_on: null }));
    expect(field('#plan-start').value).toBe('kept');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect('trigger_kind' in (mocked.updatePlanItem.mock.calls[0]?.[2] ?? {})).toBe(false);
  });

  it('offers only the states the line can move to', () => {
    dialog(planItem({ status: 'active' }));
    expect([...field('#plan-status').querySelectorAll('option')].map((o) => o.textContent)).toEqual([
      'Active',
      'Paused',
      'Completed',
      'Cancelled',
    ]);
  });

  it('shows the reason of the server when the line is refused', async () => {
    mocked.updatePlanItem.mockRejectedValue(
      new ApiError(422, 'Unprocessable', { detail: { code: 'invalid_frequency', message: 'The schedule is not one the plan understands' } }),
    );
    dialog(planItem());
    fireEvent.click(save());
    const refusal = await page.findByTestId('refusal');
    expect(refusal.getAttribute('data-code')).toBe('invalid_frequency');
    expect(refusal.textContent).not.toBe('');
  });
});

describe('recording an event', () => {
  it('links the meeting it was and the letters around it', async () => {
    const onSaved = vi.fn();
    mocked.createEvent.mockResolvedValue(event());
    mount(<EventDialog screen={screen()} target={{ kind: 'new' }} stakeholders={[stakeholder()]} onClose={() => undefined} onSaved={onSaved} />);
    type('#event-title', 'Hearing on night works');
    await waitFor(() => expect(field('#event-meeting').querySelectorAll('option')).toHaveLength(2));
    type('#event-meeting', 'm1');
    fireEvent.click(await within(page.getByTestId('event-dialog')).findByLabelText(/Notice of night works/));
    fireEvent.click(page.getByTestId('event-save'));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(mocked.createEvent).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({ title: 'Hearing on night works', status: 'held', meeting_id: 'm1', correspondence_ids: ['l1'] }),
    );
  });

  it('keeps a link whose record is no longer listed', async () => {
    const onSaved = vi.fn();
    mocked.updateEvent.mockResolvedValue(event());
    const stored = event({ meeting_id: 'gone', correspondence_ids: ['old-letter'] });
    mount(<EventDialog screen={screen()} target={{ kind: 'edit', event: stored }} stakeholders={[stakeholder()]} onClose={() => undefined} onSaved={onSaved} />);
    expect(field('#event-meeting').value).toBe('gone');
    fireEvent.click(page.getByTestId('event-save'));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(mocked.updateEvent.mock.calls[0]?.[2]).toMatchObject({ meeting_id: 'gone', correspondence_ids: ['old-letter'] });
  });

  it('needs a title and a day', () => {
    mount(<EventDialog screen={screen()} target={{ kind: 'new' }} stakeholders={[]} onClose={() => undefined} onSaved={() => undefined} />);
    const save = page.getByTestId('event-save') as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    type('#event-title', 'Hearing');
    expect(save.disabled).toBe(false);
    type('#event-held', '');
    expect(save.disabled).toBe(true);
    expect(page.getByText('The register has no stakeholders yet.')).toBeTruthy();
  });
});

describe('where a commitment was promised', () => {
  const dialog = () => {
    const onSaved = vi.fn();
    mount(
      <CommitmentDialog
        screen={screen()}
        commitment={null}
        stakeholders={[stakeholder()]}
        events={[event()]}
        onClose={() => undefined}
        onSaved={onSaved}
      />,
    );
    type('#commitment-text', 'A noise barrier along the east fence');
    fireEvent.click(within(page.getByTestId('commitment-stakeholders')).getByRole('checkbox'));
    return onSaved;
  };
  const save = () => page.getByTestId('commitment-save') as HTMLButtonElement;

  it('is nowhere on record unless the reader says otherwise', async () => {
    mocked.createCommitment.mockResolvedValue(commitment());
    const onSaved = dialog();
    expect(field('#commitment-source-ref')).toBeNull();
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const sent = mocked.createCommitment.mock.calls[0]?.[1] ?? {};
    expect(sent).toMatchObject({ source_kind: 'manual', stakeholder_ids: ['s1'] });
    expect('source_ref' in sent).toBe(false);
  });

  it('a meeting has to be named before the commitment can be saved', async () => {
    mocked.createCommitment.mockResolvedValue(commitment());
    const onSaved = dialog();
    type('#commitment-source', 'meeting');
    expect(save().disabled).toBe(true);
    await waitFor(() => expect(field('#commitment-source-ref').querySelectorAll('option')).toHaveLength(2));
    type('#commitment-source-ref', 'm1');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(mocked.createCommitment.mock.calls[0]?.[1]).toMatchObject({ source_kind: 'meeting', source_ref: 'm1' });
  });

  it('offers the recorded events with their day', () => {
    dialog();
    type('#commitment-source', 'event');
    const names = [...field('#commitment-source-ref').querySelectorAll('option')].map((o) => o.textContent ?? '');
    expect(names).toHaveLength(2);
    expect(names[1]).toContain('Information evening for residents (');
  });

  it('a permit condition is written out, and changing the kind forgets the earlier choice', async () => {
    mocked.createCommitment.mockResolvedValue(commitment());
    const onSaved = dialog();
    type('#commitment-source', 'event');
    type('#commitment-source-ref', 'e1');
    type('#commitment-source', 'permit_condition');
    expect(field('#commitment-source-ref').value).toBe('');
    expect(save().disabled).toBe(true);
    type('#commitment-source-ref', 'Building permit, condition 14');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(mocked.createCommitment.mock.calls[0]?.[1]).toMatchObject({
      source_kind: 'permit_condition',
      source_ref: 'Building permit, condition 14',
    });
  });
});
