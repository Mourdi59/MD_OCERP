// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Everything a person picks instead of typing: the document a link counts
// (and the line of a contract), the gate and area of an item, the record a
// precondition reads, the item or project that takes an item over. Plus the
// dry run that says what a new amount on a document would do.
//
// The document lists belong to other modules. Their answers here are built
// from `documentRows.ts`, which copies the field names of those modules'
// response models, and the request paths are asserted literally.

import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({
  ProjectPeopleSelect: ({ placeholder }: { placeholder?: string }) => <input aria-label={placeholder} readOnly />,
}));
vi.mock('@/shared/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/lib/api')>();
  return { ...actual, apiGet: vi.fn() };
});
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getReferences: vi.fn(),
    listTransferTargets: vi.fn(),
    checkDocument: vi.fn(),
    addPrecondition: vi.fn(),
    removePrecondition: vi.fn(),
    addLink: vi.fn(),
    createItem: vi.fn(),
    updateItem: vi.fn(),
    transferItem: vi.fn(),
    requestAbort: vi.fn(),
  };
});

import { ApiError, apiGet } from '@/shared/lib/api';
import * as api from '../api';
import type { References, TransferTarget } from '../api';
import {
  LISTED_KINDS,
  PAGE_SIZE,
  listContractLines,
  listDocuments,
  toContractLines,
  toDocumentList,
} from '../documents';
import { ItemDialog } from '../ItemDialog';
import { EndItem } from '../ItemDecisions';
import { LinkList } from '../ItemLinks';
import { PreconditionList } from '../ItemParts';
import type { LabelContext } from '../labels';
import {
  areaOptions,
  frameDocumentOptions,
  fundingOptions,
  gateOptions,
  plantItemOptions,
  preconditionRefName,
  withCurrent,
} from '../references';
import { checkOutcome, draftOfItem, itemProblems, toItemInput } from '../rules';
import { CHANGE_ORDER_ROW, CONTRACT_LINE_ROW, CONTRACT_ROW, LIST_ANSWERS } from './documentRows';
import { enT } from './i18nMock';
import { OWNER_CAN, can, item, link, matrix, precondition } from './fixtures';

const mocked = vi.mocked(api);
const apiGetMock = vi.mocked(apiGet);
const labels: LabelContext = { t: enT, language: 'en', exists: () => false };
const names = () => null;
const LINES_PATH = '/v1/contracts/contracts/c1/lines';

const plain = (en: string) => ({ key: null, text: { en } });

function references(over: Partial<References> = {}): References {
  return {
    has_model: true,
    gates: [
      { code: 'g2', name: plain('Gate 2 Design freeze'), status: 'in_preparation', last_outcome: null },
      { code: 'site_start', name: { key: null, text: null }, status: 'not_started', last_outcome: null },
    ],
    areas: [
      { code: 'procurement', name: plain('Procurement') },
      { code: 'design', name: plain('Design') },
    ],
    frame_documents: [
      { id: 'fd1', doc_type: 'procurement_strategy', name: plain('Procurement strategy'), area_code: 'procurement', status: 'binding' },
    ],
    funding_applications: [{ id: 'fa1', code: 'FA-01', title: 'Regional grant', status: 'approved' }],
    ...over,
  };
}

const NO_MODEL = references({ has_model: false, gates: [], areas: [], frame_documents: [], funding_applications: [] });

function targets(over: Partial<TransferTarget>[] = []): TransferTarget[] {
  const base: TransferTarget[] = [
    {
      project_id: 'p1',
      project_name: 'Riverside offices',
      same_project: true,
      can: { allowed: true, reason: null },
      items: [{ id: 'i2', code: 'CR-002', title: 'Lift order' }],
    },
    {
      project_id: 'p2',
      project_name: 'Harbour depot',
      same_project: false,
      can: { allowed: true, reason: null },
      items: [{ id: 'j1', code: 'CR-101', title: 'Depot lifts' }],
    },
  ];
  return base.map((row, i) => ({ ...row, ...(over[i] ?? {}) }));
}

/** Answer the lists of the other modules the way those modules do. */
function answerLists(extra: Record<string, unknown> = {}) {
  const byPath: Record<string, unknown> = { [LINES_PATH]: [CONTRACT_LINE_ROW], ...extra };
  for (const kind of LISTED_KINDS) byPath[LIST_ANSWERS[kind].path] ??= LIST_ANSWERS[kind].payload;
  apiGetMock.mockImplementation((async (path: string) => {
    if (path in byPath) return byPath[path];
    throw new ApiError(404, 'Not Found', { detail: `no such path in this test: ${path}` });
  }) as never);
}

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

const byId = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const optionTexts = (select: HTMLElement) => within(select).getAllByRole('option').map((o) => o.textContent);

beforeEach(() => {
  vi.resetAllMocks();
  answerLists();
  mocked.getReferences.mockResolvedValue(references());
});
afterEach(cleanup);

describe('document lists of the other modules', () => {
  it.each([...LISTED_KINDS])('%s: asks the list of its module for one project and labels the row', async (kind) => {
    const want = LIST_ANSWERS[kind];
    const list = await listDocuments('p1', kind);
    expect(apiGetMock).toHaveBeenCalledWith(want.path);
    expect(list).toEqual({ options: [{ id: want.id, label: want.label, currency: want.currency }], truncated: false });
  });

  it('reads the lines of one contract by code and description', async () => {
    expect(await listContractLines('c1')).toEqual([
      { id: 'cl1', label: '1.2 Concrete frame, levels 1 to 4', currency: null },
    ]);
    expect(apiGetMock).toHaveBeenCalledWith(LINES_PATH);
    expect(toContractLines({ items: [CONTRACT_LINE_ROW] })).toEqual([]);
  });

  it('asks nothing without a project, because some lists then answer for every project', async () => {
    expect(await listDocuments('', 'change_order')).toEqual({ options: [], truncated: false });
    expect(await listDocuments('p1', 'contract_line')).toEqual({ options: [], truncated: false });
    expect(await listContractLines('')).toEqual([]);
    expect(apiGetMock).not.toHaveBeenCalled();
  });

  it('says when a list may hold more than was read', () => {
    expect(toDocumentList('contract', { items: [CONTRACT_ROW], total: 240, offset: 0, limit: 100 }).truncated).toBe(true);
    expect(toDocumentList('contract', { items: [CONTRACT_ROW], total: 1, offset: 0, limit: 100 }).truncated).toBe(false);
    // A bare list carries no count: a full page is reported as possibly cut short.
    const full = Array.from({ length: PAGE_SIZE }, (_, i) => ({ ...CHANGE_ORDER_ROW, id: `co${i}` }));
    expect(toDocumentList('change_order', full).truncated).toBe(true);
    expect(toDocumentList('change_order', full.slice(1)).truncated).toBe(false);
  });

  it('skips a row without an id, names a wordless row by its id, and reads no field of another kind', () => {
    expect(toDocumentList('tender_package', [{ name: 'No id' }, null, { id: 'x9' }]).options).toEqual([
      { id: 'x9', label: 'x9', currency: null },
    ]);
    expect(toDocumentList('contract', { detail: 'nope' })).toEqual({ options: [], truncated: false });
    // A purchase order has no `code` and no `title`; a row shaped like a contract reads as nameless.
    expect(toDocumentList('purchase_order', [{ id: 'po9', code: 'SC-1', title: 'Wrong shape' }]).options[0]?.label).toBe('po9');
  });
});

describe('names of picked records', () => {
  it('names a gate and an area by the label the server sent, and by the readable code without one', () => {
    expect(gateOptions(references(), labels)).toEqual([
      { value: 'g2', label: 'Gate 2 Design freeze' },
      { value: 'site_start', label: 'Site start' },
    ]);
    expect(areaOptions(references(), labels).map((a) => a.label)).toEqual(['Procurement', 'Design']);
    expect(gateOptions(undefined, labels)).toEqual([]);
  });

  it('tells two frame documents of one type apart by their area', () => {
    expect(frameDocumentOptions(references(), labels)).toEqual([{ value: 'fd1', label: 'Procurement strategy (Procurement)' }]);
    expect(fundingOptions(references(), labels)).toEqual([{ value: 'fa1', label: 'FA-01 Regional grant' }]);
  });

  it('keeps a stored code the list no longer carries, under a readable name', () => {
    const gates = gateOptions(references(), labels);
    expect(withCurrent(gates, 'g2', labels)).toBe(gates);
    expect(withCurrent(gates, '', labels)).toBe(gates);
    expect(withCurrent(gates, 'old_gate', labels).at(-1)).toEqual({ value: 'old_gate', label: 'Old gate' });
  });

  it('names what a precondition reads, and answers null rather than a raw id', () => {
    const refs = references();
    expect(preconditionRefName({ kind: 'gate_decided', ref_id: 'g2' }, refs, labels)).toBe('Gate 2 Design freeze');
    expect(preconditionRefName({ kind: 'funding_approved', ref_id: 'fa1' }, refs, labels)).toBe('FA-01 Regional grant');
    expect(preconditionRefName({ kind: 'funding_approved', ref_id: 'gone' }, refs, labels)).toBeNull();
    expect(preconditionRefName({ kind: 'manual', ref_id: null }, refs, labels)).toBeNull();
  });
});

describe('gate and area of an item', () => {
  const draft = { ...draftOfItem(null, 'EUR'), code: 'CR-005', title: 'Lift installation', commitmentType: 'works', plannedAmount: '95000' };

  it('a gate without its area is a problem of the form, and both travel as codes', () => {
    expect(itemProblems({ ...draft, gateCode: 'g2' }, 'create')).toEqual(['gate_needs_area']);
    expect(itemProblems({ ...draft, gateCode: 'g2', areaCode: 'design' }, 'create')).toEqual([]);
    expect(itemProblems({ ...draft, areaCode: 'design' }, 'create')).toEqual([]);
    expect(toItemInput({ ...draft, gateCode: 'g2', areaCode: 'design' }, 'create')).toMatchObject({
      gate_code: 'g2',
      governance_area_code: 'design',
    });
    expect(toItemInput(draft, 'create')).toMatchObject({ gate_code: null, governance_area_code: null });
    expect(draftOfItem(item({ gate_code: 'g2', governance_area_code: 'design' }), 'EUR')).toMatchObject({
      gateCode: 'g2',
      areaCode: 'design',
    });
  });

  const dialog = (over: Parameters<typeof item>[0] | null = null, ownerVerdict: string | null = null) =>
    wrap(
      <ItemDialog
        open
        onClose={() => undefined}
        projectId="p1"
        matrix={matrix()}
        item={over ? item(over) : null}
        ownerVerdict={ownerVerdict}
        labels={labels}
        personName={names}
        onSaved={() => undefined}
      />,
    );
  const fillNewItem = () => {
    fireEvent.change(byId('item-code'), { target: { value: 'CR-005' } });
    fireEvent.change(byId('item-title'), { target: { value: 'Lift installation' } });
    fireEvent.change(byId('item-type'), { target: { value: matrix().commitment_types[0]!.code } });
    fireEvent.change(byId('item-amount'), { target: { value: '95000' } });
  };

  it('offers the gates and areas of the project by name, and sends the codes', async () => {
    mocked.createItem.mockResolvedValue(item());
    dialog();
    await waitFor(() => expect(byId('item-gate')).not.toBeNull());
    expect(optionTexts(byId('item-gate'))).toEqual(['No gate', 'Gate 2 Design freeze', 'Site start']);
    expect(optionTexts(byId('item-area'))).toEqual(['No area', 'Procurement', 'Design']);
    expect(byId<HTMLSelectElement>('item-gate').tagName).toBe('SELECT');

    fillNewItem();
    fireEvent.change(byId('item-gate'), { target: { value: 'g2' } });
    fireEvent.click(screen.getByTestId('item-save'));
    expect(screen.getByTestId('item-problems').querySelector('[data-problem="gate_needs_area"]')).not.toBeNull();
    expect(mocked.createItem).not.toHaveBeenCalled();

    fireEvent.change(byId('item-area'), { target: { value: 'procurement' } });
    fireEvent.click(screen.getByTestId('item-save'));
    await waitFor(() => expect(mocked.createItem).toHaveBeenCalledTimes(1));
    expect(mocked.createItem.mock.calls[0]![1]).toMatchObject({ gate_code: 'g2', governance_area_code: 'procurement' });
  });

  const PLANT = {
    available: true,
    items: [
      { id: 'pl1', code: 'PL-001', name: 'Tower crane', status: 'ordered' },
      { id: 'pl2', code: 'PL-002', name: 'Site transformer', status: 'cancelled' },
      { id: 'pl3', code: 'PL-003', name: 'Chiller', status: 'identified' },
    ],
  };

  it('a project without a plant register shows no plant item field, and a new item says nothing about one', async () => {
    mocked.createItem.mockResolvedValue(item());
    dialog();
    await waitFor(() => expect(byId('item-gate')).not.toBeNull());
    expect(byId('item-plant')).toBeNull();
    expect(screen.queryByTestId('item-plant-empty')).toBeNull();
    fillNewItem();
    fireEvent.click(screen.getByTestId('item-save'));
    await waitFor(() => expect(mocked.createItem).toHaveBeenCalledTimes(1));
    expect('plant_item_id' in mocked.createItem.mock.calls[0]![1]).toBe(false);
  });

  it('offers the plant items of the project by code and name, without the cancelled ones, and sends the id', async () => {
    mocked.getReferences.mockResolvedValue(references({ plant_items: PLANT }));
    mocked.createItem.mockResolvedValue(item());
    dialog();
    await waitFor(() => expect(byId('item-plant')).not.toBeNull());
    expect(optionTexts(byId('item-plant'))).toEqual(['No plant item', 'PL-001 Tower crane', 'PL-003 Chiller']);
    fillNewItem();
    fireEvent.change(byId('item-plant'), { target: { value: 'pl3' } });
    fireEvent.click(screen.getByTestId('item-save'));
    await waitFor(() => expect(mocked.createItem).toHaveBeenCalledTimes(1));
    expect(mocked.createItem.mock.calls[0]![1]).toMatchObject({ plant_item_id: 'pl3' });
  });

  it('a plant register without items says so instead of showing an empty select', async () => {
    mocked.getReferences.mockResolvedValue(references({ plant_items: { available: true, items: [] } }));
    dialog();
    expect(await screen.findByTestId('item-plant-empty')).toBeInTheDocument();
    expect(byId('item-plant')).toBeNull();
  });

  it('an edit sends the plant item only when it changed, and null when the link is removed', async () => {
    mocked.getReferences.mockResolvedValue(references({ plant_items: PLANT }));
    mocked.updateItem.mockResolvedValue(item());
    dialog({ plant_item_id: 'pl1', plant_item_code: 'PL-001' });
    await waitFor(() => expect(byId('item-plant')).not.toBeNull());
    expect(byId<HTMLSelectElement>('item-plant').value).toBe('pl1');
    fireEvent.change(byId('item-title'), { target: { value: 'Tower crane hire' } });
    fireEvent.click(screen.getByTestId('item-save'));
    await waitFor(() => expect(mocked.updateItem).toHaveBeenCalledTimes(1));
    expect(mocked.updateItem.mock.calls[0]![2]).toEqual({ title: 'Tower crane hire' });

    fireEvent.change(byId('item-plant'), { target: { value: '' } });
    fireEvent.click(screen.getByTestId('item-save'));
    await waitFor(() => expect(mocked.updateItem).toHaveBeenCalledTimes(2));
    expect(mocked.updateItem.mock.calls[1]![2]).toMatchObject({ plant_item_id: null });
  });

  it('keeps a stored plant item that is cancelled or gone from the register, and says which it is', () => {
    const refs = references({ plant_items: PLANT });
    expect(plantItemOptions(refs, labels, { id: 'pl2', code: 'PL-002' }).map((o) => o.label)).toEqual([
      'PL-001 Tower crane',
      'PL-002 Site transformer (cancelled)',
      'PL-003 Chiller',
    ]);
    expect(plantItemOptions(refs, labels, { id: 'pl9', code: 'PL-009' }).at(-1)).toEqual({
      value: 'pl9',
      label: 'PL-009 (no longer in the register)',
    });
    expect(plantItemOptions(refs, labels, { id: 'pl9', code: null }).at(-1)?.label).toBe('No longer in the register');
    // A list without the stored item is still a list: the stored one is the only option then.
    expect(plantItemOptions(references({ plant_items: { available: true, items: [] } }), labels, { id: 'pl9', code: 'PL-009' })).toHaveLength(1);
  });

  it('a project without phases and gates says so instead of showing empty selects', async () => {
    mocked.getReferences.mockResolvedValue(NO_MODEL);
    dialog();
    expect(await screen.findByTestId('item-gate-no-model')).toBeInTheDocument();
    expect(byId('item-gate')).toBeNull();
  });

  it('a failed gate list is said in words and does not stop the item from being saved', async () => {
    mocked.getReferences.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'down' }));
    mocked.createItem.mockResolvedValue(item());
    dialog();
    expect(await screen.findByTestId('item-gate-error')).toBeInTheDocument();
    fillNewItem();
    fireEvent.click(screen.getByTestId('item-save'));
    await waitFor(() => expect(mocked.createItem).toHaveBeenCalledTimes(1));
  });

  it('follows the server flag on an existing item and keeps a gate the list no longer carries', async () => {
    mocked.updateItem.mockResolvedValue(item());
    dialog({ gate_code: 'old_gate', governance_area_code: 'design', can: can({ edit_gate_fields: 'manage_required' }) });
    await waitFor(() => expect(byId('item-gate')).not.toBeNull());
    expect(byId<HTMLSelectElement>('item-gate')).toBeDisabled();
    expect(byId<HTMLSelectElement>('item-area')).toBeDisabled();
    expect(byId<HTMLSelectElement>('item-gate').value).toBe('old_gate');
    expect(optionTexts(byId('item-gate'))).toContain('Old gate');
    expect(screen.getByTestId('item-gate-locked')).toHaveTextContent(enT('commitment.disabled.manage_required'));

    // Saving another field does not send the gate again.
    fireEvent.change(byId('item-title'), { target: { value: 'Structural works, phase 1' } });
    fireEvent.click(screen.getByTestId('item-save'));
    await waitFor(() => expect(mocked.updateItem).toHaveBeenCalledTimes(1));
    expect(mocked.updateItem.mock.calls[0]![2]).toEqual({ title: 'Structural works, phase 1' });
  });

  it('the owner cannot be picked where the server would refuse it, and the reason is said', async () => {
    mocked.createItem.mockResolvedValue(item());
    dialog(null, 'manage_required');
    const owner = screen.getByTestId('item-owner-locked');
    expect(owner).toBeDisabled();
    expect(owner).toHaveAttribute('data-reason', 'manage_required');
    expect(screen.getByText(enT('commitment.disabled.manage_required'))).toBeInTheDocument();
    // The item is still added; the server makes the person adding it the owner.
    fillNewItem();
    fireEvent.click(screen.getByTestId('item-save'));
    await waitFor(() => expect(mocked.createItem).toHaveBeenCalledTimes(1));
    expect(mocked.createItem.mock.calls[0]![1]).toMatchObject({ owner_user_id: null });
  });

  it('an owner that may not change is shown by name, not as an open picker', () => {
    dialog({ owner_user_id: 'u-owner' }, 'field_frozen');
    expect(screen.getByTestId<HTMLInputElement>('item-owner-locked').value).toBe(enT('commitment.unknown_person'));
  });

  it('a manager may move a planned item to another gate', async () => {
    dialog({ gate_code: 'g2', governance_area_code: 'design' });
    await waitFor(() => expect(byId('item-gate')).not.toBeNull());
    expect(byId<HTMLSelectElement>('item-gate')).not.toBeDisabled();
    expect(screen.getByTestId('item-gate-hint')).toBeInTheDocument();
  });
});

describe('PreconditionList', () => {
  const list = (over: Parameters<typeof item>[0] = {}) => {
    const onChanged = vi.fn();
    wrap(<PreconditionList projectId="p1" item={item(over)} editVerdict={null} personName={names} onChanged={onChanged} />);
    return onChanged;
  };
  const openForm = () => fireEvent.click(screen.getByRole('button', { name: enT('commitment.preconditions.add') }));

  it('a precondition that reads another module is added by picking the record', async () => {
    mocked.addPrecondition.mockResolvedValue(item());
    const onChanged = list({ preconditions: [] });
    openForm();
    await waitFor(() => expect(optionTexts(screen.getByTestId('precondition-kind'))).toContain(enT('commitment.precondition.gate_decided')));
    fireEvent.change(screen.getByTestId('precondition-kind'), { target: { value: 'gate_decided' } });
    expect(optionTexts(screen.getByTestId('precondition-ref'))).toEqual([
      enT('commitment.preconditions.record_choose'),
      'Gate 2 Design freeze',
      'Site start',
    ]);
    expect(screen.getByTestId('precondition-add-send')).toBeDisabled();
    fireEvent.change(screen.getByTestId('precondition-ref'), { target: { value: 'g2' } });
    fireEvent.click(screen.getByTestId('precondition-add-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.addPrecondition).toHaveBeenCalledWith('p1', 'i1', { kind: 'gate_decided', ref_id: 'g2', text: '' });
  });

  it('a project that does not use gates offers no gate and says so, also when a gate list came along', async () => {
    mocked.getReferences.mockResolvedValue(references({ gates_in_use: false }));
    list({ preconditions: [] });
    openForm();
    expect(await screen.findByTestId('precondition-no-gates')).toBeInTheDocument();
    const kinds = optionTexts(screen.getByTestId('precondition-kind'));
    expect(kinds).not.toContain(enT('commitment.precondition.gate_decided'));
    expect(kinds).toContain(enT('commitment.precondition.frame_document_binding'));
    expect(screen.queryByTestId('precondition-no-records')).toBeNull();
  });

  it('a precondition that can never be met says why on its row', () => {
    list({ preconditions: [precondition({ kind: 'gate_decided', ref_id: 'g2', text: '', unreachable_reason: 'gates_not_in_use' })] });
    const note = screen.getByTestId('precondition-unreachable');
    expect(note.textContent).toContain(enT('commitment.errors.gates_not_in_use'));
    expect(note.textContent).toContain('can never be met');
  });

  it('removing a precondition needs a reason, sends it, and shows the refusal where the reader works', async () => {
    mocked.removePrecondition.mockRejectedValueOnce(
      new ApiError(409, 'Conflict', { detail: { code: 'release_pending', message: 'A release is pending' } }),
    );
    mocked.removePrecondition.mockResolvedValueOnce(undefined);
    const onChanged = list({ preconditions: [precondition()] });
    fireEvent.click(screen.getByTestId('precondition-remove'));
    expect(screen.getByTestId('precondition-remove-send')).toBeDisabled();
    fireEvent.change(byId('remove-pre1'), { target: { value: ' The brief is no longer required ' } });
    fireEvent.click(screen.getByTestId('precondition-remove-send'));
    const alert = await within(screen.getByTestId('precondition-remove-form')).findByRole('alert');
    expect(alert.textContent).toContain(enT('commitment.errors.release_pending'));
    expect(onChanged).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('precondition-remove-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.removePrecondition).toHaveBeenLastCalledWith('p1', 'i1', 'pre1', 'The brief is no longer required');
  });

  it('removal follows the server flag: refused with its reason, and off while the server has not said', () => {
    list({ preconditions: [precondition()], can: can({ remove_precondition: 'manage_required' }) });
    expect(screen.getByTestId('precondition-remove')).toBeDisabled();
    cleanup();
    const { remove_precondition: _absent, ...older } = OWNER_CAN;
    list({ preconditions: [precondition()], can: older });
    expect(screen.getByTestId('precondition-remove')).toBeDisabled();
  });

  it('offers no kind the project has no record for, and says when that changes', async () => {
    mocked.getReferences.mockResolvedValue(NO_MODEL);
    list({ preconditions: [] });
    openForm();
    expect(await screen.findByTestId('precondition-no-records')).toBeInTheDocument();
    expect(optionTexts(screen.getByTestId('precondition-kind'))).toHaveLength(4);
  });

  it('a row names the record it reads, never its id', async () => {
    list({
      preconditions: [
        precondition({ id: 'pre2', kind: 'frame_document_binding', ref_id: 'fd1', text: '', state: 'met' }),
        precondition({ id: 'pre3', kind: 'funding_approved', ref_id: 'gone', text: '' }),
      ],
    });
    await waitFor(() =>
      expect(screen.getAllByTestId('precondition-title')[0]).toHaveTextContent('Procurement strategy (Procurement)'),
    );
    // A record that is no longer listed reads as its kind.
    expect(screen.getAllByTestId('precondition-title')[1]).toHaveTextContent(enT('commitment.precondition.funding_approved'));
    expect(screen.getByTestId('preconditions').textContent).not.toMatch(/fd1|gone/);
  });

  it('a list without picked records asks the server for nothing until the form opens', () => {
    list({ preconditions: [precondition()] });
    expect(mocked.getReferences).not.toHaveBeenCalled();
  });
});

describe('LinkList', () => {
  const list = (links = [link()], editVerdict: string | null = null) => {
    const onChanged = vi.fn();
    wrap(<LinkList projectId="p1" item={item({ links })} editVerdict={editVerdict} onChanged={onChanged} />);
    return onChanged;
  };

  it('names a linked document by number and title, and a contract line with its contract', async () => {
    list([
      link({ link_id: 'l1', kind: 'contract', document_id: 'c1' }),
      link({ link_id: 'l2', kind: 'contract_line', document_id: 'cl1', contract_id: 'c1' }),
      link({ link_id: 'l3', kind: 'purchase_order', document_id: 'po1' }),
    ]);
    await waitFor(() =>
      expect(screen.getAllByTestId('link-name').map((n) => n.textContent)).toEqual([
        'SC-014 Structural works',
        '1.2 Concrete frame, levels 1 to 4, contract SC-014 Structural works',
        'PO-0007 Lift supplier',
      ]),
    );
  });

  it('a document that is not in its list reads as its kind, and a deleted one says so', async () => {
    list([
      link({ link_id: 'l1', kind: 'rfq', document_id: 'unknown' }),
      link({ link_id: 'l2', kind: 'contract', document_id: 'deleted', found: false }),
    ]);
    await waitFor(() => expect(apiGetMock).toHaveBeenCalledWith(LIST_ANSWERS.rfq.path));
    expect(screen.getAllByTestId('link-name').map((n) => n.textContent)).toEqual([
      enT('commitment.link.rfq'),
      enT('commitment.links.not_found'),
    ]);
  });

  it('links a contract line in two steps: the contract, then the line', async () => {
    mocked.addLink.mockResolvedValue(undefined);
    const onChanged = list([]);
    expect(screen.getByTestId('links-empty')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('link-add'));
    fireEvent.change(screen.getByTestId('link-kind'), { target: { value: 'contract_line' } });
    await waitFor(() => expect(optionTexts(screen.getByTestId('link-document'))).toContain('SC-014 Structural works'));
    expect(screen.queryByTestId('link-line')).toBeNull();
    fireEvent.change(screen.getByTestId('link-document'), { target: { value: 'c1' } });
    await waitFor(() => expect(optionTexts(screen.getByTestId('link-line'))).toContain('1.2 Concrete frame, levels 1 to 4'));
    expect(screen.getByTestId('link-add-send')).toBeDisabled();
    fireEvent.change(screen.getByTestId('link-line'), { target: { value: 'cl1' } });
    fireEvent.click(screen.getByTestId('link-add-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.addLink).toHaveBeenCalledWith('p1', 'i1', 'contract_line', 'cl1');
  });

  it('does not offer a document that is linked already, and says when none is left', async () => {
    list([link({ kind: 'contract', document_id: 'c1' })]);
    fireEvent.click(screen.getByTestId('link-add'));
    expect(await screen.findByTestId('link-no-documents')).toBeInTheDocument();
    expect(optionTexts(screen.getByTestId('link-document'))).toEqual([enT('commitment.links.choose')]);
  });

  it('says when the list of a kind was cut short', async () => {
    answerLists({ [LIST_ANSWERS.contract.path]: { items: [CONTRACT_ROW], total: 240, offset: 0, limit: 100 } });
    list([]);
    fireEvent.click(screen.getByTestId('link-add'));
    expect(await screen.findByTestId('link-truncated')).toHaveTextContent(String(PAGE_SIZE));
  });

  it('a reader sees the links and why they cannot change them', () => {
    list([link()], 'not_item_owner');
    expect(screen.getByTestId('link-add')).toBeDisabled();
    expect(screen.queryByTestId('link-remove')).toBeNull();
  });
});

describe('what would happen', () => {
  const open = (links = [link({ document_id: 'c1' })]) => {
    wrap(<LinkList projectId="p1" item={item({ links })} editVerdict="not_item_owner" onChanged={() => undefined} />);
    fireEvent.click(screen.getByTestId('check-open'));
  };
  const ask = (amount: string) => {
    fireEvent.change(byId('check-amount'), { target: { value: amount } });
    fireEvent.click(screen.getByTestId('check-send'));
  };

  it('a release past its date has its own sentence, not the one for an amount that does not fit', () => {
    expect(enT('commitment.check.reason.release_expired')).not.toBe(enT('commitment.check.reason.commitment_not_released'));
    expect(enT('commitment.check.reason.release_expired')).toContain('validity date');
  });

  it('tells the three kinds of "ok" and the two refusals apart', () => {
    expect(checkOutcome({ result: 'ok', item_id: 'i1' })).toBe('fits');
    expect(checkOutcome({ result: 'ok', item_id: null })).toBe('unchecked');
    expect(checkOutcome({ result: 'warn', item_id: 'i1' })).toBe('warn');
    expect(checkOutcome({ result: 'block', item_id: null })).toBe('block');
  });

  it('is absent while nothing is linked, and open to a reader', () => {
    wrap(<LinkList projectId="p1" item={item({ links: [] })} editVerdict={null} onChanged={() => undefined} />);
    expect(screen.queryByTestId('check-open')).toBeNull();
    cleanup();
    open();
    expect(screen.getByTestId('check-panel')).toBeInTheDocument();
  });

  it('sends the new total of the chosen document and shows a refusal with its figures', async () => {
    mocked.checkDocument.mockResolvedValue({
      result: 'block',
      reasons: [{ code: 'commitment_not_released', released: '1700000', ceiling: '1785000.00', would_commit: '1900000', currency: 'EUR' }],
      item_id: 'i1',
    });
    open();
    expect(screen.getByTestId('check-send')).toBeDisabled();
    ask('1900000');
    const result = await screen.findByTestId('check-result');
    expect(mocked.checkDocument).toHaveBeenCalledWith('p1', {
      kind: 'contract',
      document_id: 'c1',
      new_amount: '1900000',
      currency: 'EUR',
    });
    expect(result).toHaveAttribute('data-outcome', 'block');
    expect(result).toHaveTextContent(enT('commitment.check.outcome.block'));
    expect(screen.getByTestId('check-reason')).toHaveAttribute('data-code', 'commitment_not_released');
    expect(screen.getByTestId('check-would-commit').textContent).toMatch(/1[.,\s]?900[.,\s]?000/);
  });

  it('an amount that fits says so, and names no figure it was not given', async () => {
    mocked.checkDocument.mockResolvedValue({ result: 'ok', reasons: [], item_id: 'i1' });
    open();
    ask('1600000');
    const result = await screen.findByTestId('check-result');
    expect(result).toHaveAttribute('data-outcome', 'fits');
    expect(screen.queryByTestId('check-reason')).toBeNull();
  });

  it('does not call it a fit when the project checks nothing', async () => {
    mocked.checkDocument.mockResolvedValue({ result: 'ok', reasons: [], item_id: null });
    open();
    ask('9900000');
    const result = await screen.findByTestId('check-result');
    expect(result).toHaveAttribute('data-outcome', 'unchecked');
    expect(result).toHaveTextContent(enT('commitment.check.outcome.unchecked'));
    expect(result).not.toHaveTextContent(enT('commitment.check.outcome.fits'));
  });

  it('a warning without figures reads as its reason in words', async () => {
    mocked.checkDocument.mockResolvedValue({ result: 'warn', reasons: [{ code: 'fx_rate_missing' }], item_id: 'i1' });
    open();
    ask('1000');
    const result = await screen.findByTestId('check-result');
    expect(result).toHaveAttribute('data-outcome', 'warn');
    expect(screen.getByTestId('check-reason')).toHaveTextContent(enT('commitment.check.reason.fx_rate_missing'));
    expect(screen.queryByTestId('check-would-commit')).toBeNull();
  });

  it('asks for the amount of the change on a change order, and clears an old answer when the question changes', async () => {
    mocked.checkDocument.mockResolvedValue({ result: 'ok', reasons: [], item_id: 'i1' });
    open([link({ kind: 'change_order', document_id: 'co1' })]);
    expect(screen.getByLabelText(new RegExp(enT('commitment.check.amount_of_change')))).toBe(byId('check-amount'));
    ask('42000');
    await screen.findByTestId('check-result');
    fireEvent.change(byId('check-amount'), { target: { value: '43000' } });
    await waitFor(() => expect(screen.queryByTestId('check-result')).toBeNull());
  });

  it('does not ask about a change its contract already carries', () => {
    open([link({ kind: 'change_order', document_id: 'co1', contract_id: 'c1', notes: ['inside_contract_value:c1'] })]);
    fireEvent.change(byId('check-amount'), { target: { value: '42000' } });
    expect(screen.getByTestId('check-inside-contract')).toBeInTheDocument();
    expect(screen.getByTestId('check-send')).toBeDisabled();
  });

  it('keeps the currency the reader typed, and takes the currency of the document chosen', () => {
    open([
      link({ link_id: 'l1', document_id: 'c1', currency: 'EUR' }),
      link({ link_id: 'l2', kind: 'purchase_order', document_id: 'po1', currency: 'GBP' }),
    ]);
    const currency = byId<HTMLInputElement>('check-currency');
    expect(currency.value).toBe('EUR');
    fireEvent.change(currency, { target: { value: '' } });
    expect(currency.value).toBe('');
    fireEvent.change(byId('check-document'), { target: { value: 'l2' } });
    expect(currency.value).toBe('GBP');
  });

  it('will not send an amount it cannot read', () => {
    open();
    fireEvent.change(byId('check-amount'), { target: { value: 'about two million' } });
    expect(screen.getByTestId('check-send')).toBeDisabled();
  });

  it('shows the server sentence when the check itself is refused', async () => {
    mocked.checkDocument.mockRejectedValue(new ApiError(404, 'Not Found', { detail: { code: 'matrix_missing', message: 'No matrix' } }));
    open();
    ask('1000');
    expect(await screen.findByTestId('refusal')).toBeInTheDocument();
  });
});

describe('hand-over targets', () => {
  const end = (over: Parameters<typeof item>[0] = {}) => {
    const onChanged = vi.fn();
    wrap(
      <EndItem projectId="p1" item={item(over)} matrix={matrix()} labels={labels} personName={names} onChanged={onChanged} />,
    );
    return onChanged;
  };
  const openTransfer = () => fireEvent.click(screen.getByTestId('item-transfer'));
  const reason = (text: string) => fireEvent.change(byId('end-reason'), { target: { value: text } });

  it('inside the project it needs a target item and a reason, and names no project', async () => {
    mocked.listTransferTargets.mockResolvedValue(targets().slice(0, 1));
    mocked.transferItem.mockResolvedValue(item({ status: 'transferred' }));
    const onChanged = end();
    expect(mocked.listTransferTargets).not.toHaveBeenCalled();
    openTransfer();
    await waitFor(() => expect(byId('end-target')).not.toBeNull());
    expect(byId('end-project')).toBeNull();
    reason('Merged into the lift order');
    expect(screen.getByTestId('end-send')).toBeDisabled();
    fireEvent.change(byId('end-target'), { target: { value: 'i2' } });
    fireEvent.click(screen.getByTestId('end-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.transferItem).toHaveBeenCalledWith('p1', 'i1', { target_item_id: 'i2', reason: 'Merged into the lift order' });
  });

  it('offers another project only when the server lists it, and then names it in the request', async () => {
    mocked.listTransferTargets.mockResolvedValue(targets());
    mocked.transferItem.mockResolvedValue(item({ status: 'transferred' }));
    const onChanged = end();
    openTransfer();
    await waitFor(() => expect(byId('end-project')).not.toBeNull());
    expect(optionTexts(byId('end-project'))).toEqual(['Riverside offices (this project)', 'Harbour depot']);
    expect(optionTexts(byId('end-target'))).toContain('CR-002 Lift order');
    fireEvent.change(byId('end-project'), { target: { value: 'p2' } });
    expect(optionTexts(byId('end-target'))).toEqual([enT('commitment.end.target_choose'), 'CR-101 Depot lifts']);
    fireEvent.change(byId('end-target'), { target: { value: 'j1' } });
    reason('The depot takes the lifts');
    fireEvent.click(screen.getByTestId('end-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.transferItem).toHaveBeenCalledWith('p1', 'i1', {
      target_item_id: 'j1',
      reason: 'The depot takes the lifts',
      target_project_id: 'p2',
    });
  });

  it('a project the server refuses stays visible, cannot be chosen, and carries the reason', async () => {
    mocked.listTransferTargets.mockResolvedValue(
      targets([{}, { can: { allowed: false, reason: 'transfer_links_stay_in_project' } }]),
    );
    end();
    openTransfer();
    await waitFor(() => expect(byId('end-project')).not.toBeNull());
    const other = within(byId('end-project')).getByRole('option', { name: 'Harbour depot' }) as HTMLOptionElement;
    expect(other.disabled).toBe(true);
    const note = screen.getByTestId('transfer-project-refused');
    expect(note).toHaveAttribute('data-reason', 'transfer_links_stay_in_project');
    expect(note).toHaveTextContent(enT('commitment.errors.transfer_links_stay_in_project'));
  });

  it('with no open item to take over it says what to do first', async () => {
    mocked.listTransferTargets.mockResolvedValue(targets([{ items: [] }]).slice(0, 1));
    end();
    openTransfer();
    expect(await screen.findByTestId('transfer-no-target')).toBeInTheDocument();
    expect(byId('end-target')).toBeNull();
  });

  it('a failed lookup is shown where the reader works', async () => {
    mocked.listTransferTargets.mockRejectedValue(
      new ApiError(403, 'Forbidden', { detail: { code: 'manage_required', message: 'Managers only' } }),
    );
    end();
    openTransfer();
    expect(await screen.findByTestId('refusal')).toBeInTheDocument();
  });

  it('somebody who may not hand over is never sent to the list', () => {
    end({ can: can({ transfer: 'manage_required' }) });
    expect(screen.getByTestId('item-transfer')).toBeDisabled();
    expect(mocked.listTransferTargets).not.toHaveBeenCalled();
  });
});
