// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// A saved element group or Smart View as a BOQ position's quantity source:
// the viewer hands the group to a new quantity rule, the editor offers the
// project's groups, saves the choice on the rule and says when the group
// the rule names is gone.

import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mocks = vi.hoisted(() => ({
  listQuantityMaps: vi.fn(),
  fetchBIMModels: vi.fn(),
  fetchBIMElements: vi.fn(),
  fetchSmartViewProperties: vi.fn(),
  fetchBIMDataframeSchema: vi.fn(),
  previewQuantityRule: vi.fn(),
  boqList: vi.fn(),
  boqGet: vi.fn(),
  fetchProjectList: vi.fn(),
  apiGet: vi.fn(),
  fetchBIMDataframeColumnValues: vi.fn(),
  createQuantityMap: vi.fn(),
  listElementGroups: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      let d = typeof opts?.defaultValue === 'string' ? opts.defaultValue : key;
      for (const [k, v] of Object.entries(opts ?? {})) d = d.replace(`{{${k}}}`, String(v));
      return d;
    },
    i18n: { language: 'en' },
  }),
  Trans: ({ children }: { children: ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}));

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  listQuantityMaps: (...a: unknown[]) => mocks.listQuantityMaps(...a),
  fetchBIMModels: (...a: unknown[]) => mocks.fetchBIMModels(...a),
  fetchBIMElements: (...a: unknown[]) => mocks.fetchBIMElements(...a),
  fetchSmartViewProperties: (...a: unknown[]) => mocks.fetchSmartViewProperties(...a),
  fetchBIMDataframeSchema: (...a: unknown[]) => mocks.fetchBIMDataframeSchema(...a),
  previewQuantityRule: (...a: unknown[]) => mocks.previewQuantityRule(...a),
  fetchBIMDataframeColumnValues: (...a: unknown[]) => mocks.fetchBIMDataframeColumnValues(...a),
  createQuantityMap: (...a: unknown[]) => mocks.createQuantityMap(...a),
  listElementGroups: (...a: unknown[]) => mocks.listElementGroups(...a),
}));

vi.mock('@/shared/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/lib/api')>()),
  apiGet: (...a: unknown[]) => mocks.apiGet(...a),
}));

vi.mock('@/features/boq/api', () => ({
  boqApi: { list: (...a: unknown[]) => mocks.boqList(...a), get: (...a: unknown[]) => mocks.boqGet(...a) },
}));

vi.mock('@/shared/lib/projectList', () => ({
  fetchProjectList: (...a: unknown[]) => mocks.fetchProjectList(...a),
}));

vi.mock('@/features/bim_requirements/RulePackLibrary', () => ({
  RulePackLibrary: () => <div data-testid="rule-pack-library" />,
}));
vi.mock('./BIMRequirementsImport', () => ({ default: () => <div data-testid="bim-requirements-import" /> }));

import { BIMQuantityRulesPage } from './BIMQuantityRulesPage';
import { useProjectContextStore } from '@/stores/useProjectContextStore';

const CATALOG = {
  model_id: 'm-2',
  source_format: 'RVT',
  element_count: 3,
  entries: [
    { field: 'element_type', label: 'element type', group: 'identity', data_type: 'enum', source_formats: [], sample_values: ['Walls'], distinct_count: 1, truncated: false },
    { field: 'properties.Phase Created', label: 'Phase Created', group: 'properties', data_type: 'enum', source_formats: [], sample_values: ['Existing', 'New Construction'], distinct_count: 2, truncated: false },
    { field: 'properties.Pset_WallCommon.FireRating', label: 'FireRating', group: 'properties', data_type: 'enum', source_formats: [], sample_values: ['REI 60'], distinct_count: 1, truncated: false },
    { field: 'properties.layers', label: 'layers', group: 'properties', data_type: 'enum', source_formats: [], sample_values: ['<complex>'], distinct_count: 1, truncated: false },
    { field: 'quantities.Area', label: 'Area', group: 'quantities', data_type: 'number', source_formats: [], sample_values: ['12.5'], distinct_count: 1, truncated: false },
  ],
};

function renderAt(url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/bim/rules" element={<BIMQuantityRulesPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useProjectContextStore.setState({ activeProjectId: 'p-1', activeProjectName: 'Villa' });
  mocks.listQuantityMaps.mockResolvedValue({ items: [], total: 0 });
  mocks.fetchBIMModels.mockResolvedValue({
    items: [
      { id: 'm-1', name: 'Structure', status: 'ready' },
      { id: 'm-2', name: 'Architecture', status: 'ready' },
    ],
    total: 2,
  });
  mocks.fetchBIMElements.mockResolvedValue({ items: [], total: 0 });
  mocks.fetchSmartViewProperties.mockResolvedValue(CATALOG);
  mocks.boqList.mockResolvedValue([
    { id: 'b-1', name: 'Shell', is_locked: false },
    { id: 'b-2', name: 'Finishes', is_locked: false },
  ]);
  mocks.boqGet.mockResolvedValue({ id: 'b-2', positions: [] });
  mocks.fetchProjectList.mockResolvedValue([{ id: 'p-1', name: 'Villa' }, { id: 'p-2', name: 'Palazzo' }]);
  mocks.apiGet.mockResolvedValue([]);
  mocks.fetchBIMDataframeSchema.mockResolvedValue([
    { name: 'id', type: 'VARCHAR' },
    { name: 'phase created', type: 'VARCHAR', label: 'Phase Created' },
    { name: 'width', type: 'DOUBLE', label: 'Width' },
  ]);
  mocks.fetchBIMDataframeColumnValues.mockResolvedValue({
    items: [
      { value: 'New Construction', count: 40 },
      { value: 'Existing', count: 12 },
      { value: 'Demolished', count: 3 },
    ],
    total: 3,
    offset: 0,
    limit: 200,
  });
  mocks.createQuantityMap.mockImplementation(async (payload: Record<string, unknown>) => ({
    ...payload,
    id: 'r-new',
    created_at: '2026-10-11T00:00:00Z',
    updated_at: '2026-10-11T00:00:00Z',
  }));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const GROUP_LINK = '/bim/rules?project_id=p-1&model_id=m-2&new=1&group_id=g-kept&group_name=Kept%20walls';

function save() {
  fireEvent.click(screen.getByRole('button', { name: 'common.save' }));
}

describe('a saved group or Smart View as the quantity source', () => {
  beforeEach(() => {
    mocks.listElementGroups.mockResolvedValue([
      { id: 'g-other', name: 'Doors', model_id: 'm-2', is_dynamic: true, filter_criteria: {} },
      { id: 'g-kept', name: 'Kept walls', model_id: 'm-2', is_dynamic: true, filter_criteria: {} },
    ]);
  });

  it('opens a new rule fed by the group handed over from the viewer, aimed at a position', async () => {
    renderAt(GROUP_LINK);
    const dialog = await screen.findByRole('dialog');
    const select = dialog.querySelector('#rule-element-group') as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe('g-kept'));
    expect((dialog.querySelector('#rule-name') as HTMLInputElement).value).toBe('Kept walls - quantity');
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
      'None, the filters below select',
      'Doors',
      'Kept walls',
    ]);
    expect(mocks.listElementGroups).toHaveBeenCalledWith('p-1');
  });

  it('saves the group on the rule', async () => {
    renderAt(GROUP_LINK);
    const dialog = await screen.findByRole('dialog');
    const select = dialog.querySelector('#rule-element-group') as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe('g-kept'));
    // The target defaults to an existing position; for the save itself an
    // auto-created one is enough.
    fireEvent.click(screen.getByLabelText(/auto-create/i));
    save();
    await waitFor(() => expect(mocks.createQuantityMap).toHaveBeenCalled());
    expect(mocks.createQuantityMap.mock.calls[0]![0].metadata.element_group_id).toBe('g-kept');
  });

  it('sends a cleared group as null so the server clears it too', async () => {
    renderAt(GROUP_LINK);
    const dialog = await screen.findByRole('dialog');
    const select = dialog.querySelector('#rule-element-group') as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe('g-kept'));
    fireEvent.click(screen.getByLabelText(/auto-create/i));
    fireEvent.change(select, { target: { value: '' } });
    save();
    await waitFor(() => expect(mocks.createQuantityMap).toHaveBeenCalled());
    expect(mocks.createQuantityMap.mock.calls[0]![0].metadata.element_group_id).toBeNull();
  });

  it('says so when the group the rule names is gone', async () => {
    mocks.listElementGroups.mockResolvedValue([]);
    renderAt(GROUP_LINK);
    await screen.findByRole('dialog');
    expect(await screen.findByTestId('rule-element-group-missing')).toBeTruthy();
  });
});
