// @vitest-environment jsdom
// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The analysis grid, the choice of framework, and the two documents the
// module files for the gate, including the reason a binding document asks
// for before it takes a new revision.

import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen as page, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiError } from '@/shared/lib/api';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  getGrid: vi.fn(),
  listFrameworks: vi.fn(),
  putSettings: vi.fn(),
  fileFrameDocument: vi.fn(),
  downloadExport: vi.fn(),
}));

import * as api from '../api';
import { AnalysisGrid } from '../AnalysisGrid';
import { ExportBar, FrameworkSettings } from '../FrameworkSettings';
import { enExists, enT } from './i18nMock';
import { grid, gridItem, salience, screen, settings } from './fixtures';

const mocked = vi.mocked(api);
const labels = { t: enT, language: 'en', exists: enExists };
const pageOf = <T,>(items: T[]) => ({ items, total: items.length, offset: 0, limit: 100 });

const shipped = (over: Partial<api.FrameworkSummary> = {}): api.FrameworkSummary => ({
  kind: 'stakeholder_framework',
  source: 'shipped',
  id: 'neutral',
  code: 'neutral',
  name: { key: 'stakeholders.catalogue.framework.neutral', text: null },
  state: 'published',
  latest_version: 1,
  review_status: 'unconfirmed',
  jurisdiction_countries: [],
  ...over,
});

function mount(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const viewer = () => settings({ can: { edit: false, read_personal: false, manage_organisation: false } });

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocked.getGrid.mockResolvedValue(grid());
  mocked.listFrameworks.mockResolvedValue(pageOf([shipped()]));
  mocked.putSettings.mockResolvedValue(settings());
  mocked.fileFrameDocument.mockResolvedValue({});
  mocked.downloadExport.mockResolvedValue(undefined);
});

describe('the analysis grid', () => {
  const show = (method = 'power_interest') => {
    const onOpen = vi.fn();
    const onMethod = vi.fn();
    mount(<AnalysisGrid screen={screen()} method={method} onMethod={onMethod} onOpen={onOpen} />);
    return { onOpen, onMethod };
  };

  it('explains itself when the register is empty', async () => {
    mocked.getGrid.mockResolvedValue(grid({ items: [] }));
    show();
    expect(await page.findByText('Nothing to analyse yet')).toBeTruthy();
    expect(page.queryByTestId('analysis-grid')).toBeNull();
  });

  it('puts each stakeholder in the cell the server placed them in, and opens them from there', async () => {
    const { onOpen } = show();
    await page.findByTestId('grid-square');
    expect(page.getAllByTestId('grid-cell')).toHaveLength(25);
    const cell = page.getAllByTestId('grid-cell').find((td) => td.getAttribute('data-x') === '5' && td.getAttribute('data-y') === '4')!;
    fireEvent.click(within(cell).getByText('Building authority'));
    expect(onOpen).toHaveBeenCalledWith('s1');
    expect(page.getAllByTestId('grid-chip')).toHaveLength(1);
  });

  it('draws the highest value of the vertical scale on top', async () => {
    show();
    await page.findByTestId('grid-square');
    expect(page.getAllByTestId('grid-cell')[0]?.getAttribute('data-y')).toBe('5');
    expect(page.getByText('Power 5')).toBeTruthy();
    expect(page.getByText('Interest 1')).toBeTruthy();
  });

  it('lists the stakeholders nobody assessed under this method, and says so when that is everyone', async () => {
    mocked.getGrid.mockResolvedValue(grid({ items: [gridItem({ assessment_id: null, position: null, scores: null, classification: 'not_assessed' })] }));
    show();
    expect(await page.findByTestId('grid-none-placed')).toBeTruthy();
    expect(within(page.getByTestId('grid-unplaced')).getByText('Building authority')).toBeTruthy();
    expect(page.queryByTestId('grid-square')).toBeNull();
  });

  it('groups by class when the method has no two number scales', async () => {
    mocked.getGrid.mockResolvedValue(
      grid({
        method_code: 'salience',
        dimensions: salience.dimensions,
        classes: salience.classes,
        items: [gridItem({ classification: 'definitive', position: { sets: ['power', 'legitimacy', 'urgency'] } })],
      }),
    );
    show('salience');
    await page.findByTestId('grid-classes');
    const groups = page.getAllByTestId('grid-class');
    expect(groups.map((g) => g.querySelector('h3')?.textContent)).toEqual(['Definitive1', 'Dormant0']);
    expect(page.queryByTestId('grid-square')).toBeNull();
  });

  it('never prints the name of a person the reader may not see', async () => {
    mocked.getGrid.mockResolvedValue(grid({ items: [gridItem({ name: null, masked: true })] }));
    show();
    expect((await page.findByTestId('grid-chip')).textContent).toBe('Private person (name hidden)');
  });

  it('lets the reader switch between the methods of the framework', async () => {
    const { onMethod } = show();
    fireEvent.change(await page.findByTestId('grid-method'), { target: { value: 'salience' } });
    expect(onMethod).toHaveBeenCalledWith('salience');
  });

  it('says so when the analysis cannot be loaded, and offers to try again', async () => {
    mocked.getGrid.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    show();
    expect(await page.findByText('The analysis could not be loaded')).toBeTruthy();
    const before = mocked.getGrid.mock.calls.length;
    fireEvent.click(page.getByRole('button', { name: /retry/i }));
    await waitFor(() => expect(mocked.getGrid.mock.calls.length).toBeGreaterThan(before));
  });
});

describe('choosing the framework', () => {
  const show = (current: ReturnType<typeof settings> | null) => {
    const onSaved = vi.fn();
    mount(<FrameworkSettings projectId="p1" settings={current} labels={labels} onSaved={onSaved} />);
    return onSaved;
  };
  const save = () => page.getByTestId('framework-save') as HTMLButtonElement;

  it('on a new project leaves the choice to the project country unless the reader picks one', async () => {
    const onSaved = show(null);
    await page.findByTestId('framework-option');
    expect(save().textContent).toBe('Start with the framework for the project country');
    expect(page.queryByTestId('settings-method')).toBeNull();
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(mocked.putSettings).toHaveBeenCalledWith('p1', {});
  });

  it('pins the framework the reader picked', async () => {
    const onSaved = show(null);
    fireEvent.click(await page.findByTestId('framework-option'));
    expect(save().textContent).toBe('Start with this framework');
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(mocked.putSettings).toHaveBeenCalledWith('p1', { framework_source: 'shipped', framework_id: 'neutral' });
  });

  it('names the framework and says its references are not confirmed', async () => {
    show(null);
    const option = (await page.findByTestId('framework-option')).closest('label')!;
    expect(option.textContent).toContain('Neutral stakeholder framework');
    expect(option.textContent).toContain('Built in');
    expect(option.textContent).toContain('References not yet confirmed by an expert');
  });

  it('shows the reason of the server when the first choice is refused', async () => {
    mocked.putSettings.mockRejectedValue(
      new ApiError(409, 'Conflict', { detail: { code: 'concurrent_change', message: 'Someone else changed this at the same time' } }),
    );
    const onSaved = show(null);
    await page.findByTestId('framework-option');
    fireEvent.click(save());
    expect((await page.findByTestId('refusal')).getAttribute('data-code')).toBe('concurrent_change');
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('on a project that has one, saves the method and the review interval without pinning again', async () => {
    const onSaved = show(settings());
    await page.findByTestId('framework-option');
    fireEvent.change(page.getByTestId('settings-method'), { target: { value: 'salience' } });
    fireEvent.change(page.getByRole('spinbutton'), { target: { value: '30' } });
    fireEvent.click(save());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(mocked.putSettings).toHaveBeenCalledWith('p1', { analysis_method: 'salience', review_interval_days: 30 });
  });

  it('follows the organisation flag once settings exist', async () => {
    show(viewer());
    const option = (await page.findByTestId('framework-option')) as HTMLInputElement;
    expect(option.disabled).toBe(true);
    expect(save().disabled).toBe(true);
    expect(page.getByTestId('disabled-reason').getAttribute('data-reason')).toBe('organisation');
  });

  it('leaves out retired frameworks and says so when none is left', async () => {
    mocked.listFrameworks.mockResolvedValue(pageOf([shipped({ state: 'retired' })]));
    show(null);
    expect(await page.findByText('No framework is available.')).toBeTruthy();
    expect(page.queryByTestId('framework-option')).toBeNull();
  });

  it('says so when the frameworks cannot be loaded', async () => {
    mocked.listFrameworks.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    show(null);
    expect(await page.findByText('The frameworks could not be loaded')).toBeTruthy();
    expect(page.queryByTestId('framework-save')).toBeNull();
  });
});

describe('the documents for the gate', () => {
  const show = (current = settings(), document: api.ExportDocument = 'register') =>
    mount(<ExportBar projectId="p1" settings={current} document={document} />);
  const file = () => page.getByTestId('export-register-file') as HTMLButtonElement;

  it('downloads in the format the reader picked', async () => {
    show();
    fireEvent.click(page.getByTestId('export-register-xlsx'));
    await waitFor(() => expect(mocked.downloadExport).toHaveBeenCalledWith('p1', 'register', 'xlsx'));
  });

  it('files the document without asking anything while it is not binding', async () => {
    show();
    expect(page.queryByTestId('export-register-reason')).toBeNull();
    fireEvent.click(file());
    await waitFor(() => expect(mocked.fileFrameDocument).toHaveBeenCalledTimes(1));
    expect(mocked.fileFrameDocument).toHaveBeenCalledWith('p1', { document: 'register', format: 'pdf', change_reason: '', change_impact: '' });
  });

  it('asks why a binding document changes, and files it once the reader said so', async () => {
    mocked.fileFrameDocument.mockRejectedValueOnce(
      new ApiError(422, 'Unprocessable', { detail: { code: 'change_reason_required', message: 'Give a reason for the change request' } }),
    );
    show();
    fireEvent.click(file());
    const ask = await page.findByTestId('export-register-reason');
    expect(page.queryByTestId('refusal')).toBeNull();
    expect(file().disabled).toBe(true);
    const [reason, impact] = within(ask).getAllByRole('textbox');
    fireEvent.change(reason!, { target: { value: ' Two neighbours added after the hearing ' } });
    fireEvent.change(impact!, { target: { value: 'Communication plan' } });
    expect(file().disabled).toBe(false);
    fireEvent.click(file());
    await waitFor(() => expect(mocked.fileFrameDocument).toHaveBeenCalledTimes(2));
    expect(mocked.fileFrameDocument).toHaveBeenLastCalledWith('p1', {
      document: 'register',
      format: 'pdf',
      change_reason: 'Two neighbours added after the hearing',
      change_impact: 'Communication plan',
    });
    await waitFor(() => expect(page.queryByTestId('export-register-reason')).toBeNull());
  });

  it('shows any other refusal as the server put it', async () => {
    mocked.fileFrameDocument.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'frame_document_missing', message: 'No frame document yet' } }),
    );
    show();
    fireEvent.click(file());
    const refusal = await page.findByTestId('refusal');
    expect(refusal.getAttribute('data-code')).toBe('frame_document_missing');
    expect(page.queryByTestId('export-register-reason')).toBeNull();
  });

  const blockedBy = (reason: string) => {
    const off = { applies: true, allowed: false, reason };
    return settings({ can_file: { register: off, organisation: off } });
  };

  it('lets a viewer download but not file, and says so in words', () => {
    show(blockedBy('no_permission'));
    expect(file().disabled).toBe(true);
    const note = page.getByTestId('export-register-blocked');
    expect(note.getAttribute('data-reason')).toBe('no_permission');
    expect(note.textContent).toBe('Your role can download this document but not file it for the gate.');
    expect((page.getByTestId('export-register-pdf') as HTMLButtonElement).disabled).toBe(false);
  });

  it('says what is missing when the gate has no place for the document yet', () => {
    show(blockedBy('frame_document_missing'));
    expect(file().disabled).toBe(true);
    expect(page.getByTestId('export-register-blocked').textContent).toContain('Attach a document container');
    fireEvent.click(file());
    expect(mocked.fileFrameDocument).not.toHaveBeenCalled();
  });

  it('offers only the downloads on a project run without gates', () => {
    const none = { applies: false, allowed: false, reason: 'gates_not_in_use' };
    show(settings({ can_file: { register: none, organisation: none } }));
    expect(page.queryByTestId('export-register-file')).toBeNull();
    expect(page.queryByTestId('export-register-blocked')).toBeNull();
    expect(page.getByTestId('export-register-pdf')).toBeTruthy();
    expect(page.getByTestId('export-register-xlsx')).toBeTruthy();
  });

  it('says the project is stopped when its frame documents are frozen', () => {
    show(blockedBy('frame_document_read_only'));
    expect(file().disabled).toBe(true);
    expect(page.getByTestId('export-register-blocked').textContent).toBe(
      'The project is stopped, so its frame documents take no new revision until it resumes.',
    );
  });

  it('reads a reason it does not know as words, never as a code', () => {
    show(blockedBy('brand_new_reason'));
    expect(page.getByTestId('export-register-blocked').textContent).toBe('Brand new reason');
  });

  it('files the organisation document under its own name', async () => {
    show(settings(), 'organisation');
    expect(page.getByText('Project organisation and mandates')).toBeTruthy();
    fireEvent.click(page.getByTestId('export-organisation-file'));
    await waitFor(() => expect(mocked.fileFrameDocument).toHaveBeenCalledWith('p1', expect.objectContaining({ document: 'organisation' })));
  });
});
