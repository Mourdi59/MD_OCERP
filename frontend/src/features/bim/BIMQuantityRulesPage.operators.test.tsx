// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Quantity rule conditions beyond equality: the editor offers not equals,
// contains, greater / less than and the empty checks, refuses a value the
// comparison cannot use before the server has to, offers the model's own
// values for equals / not equals (the property search's value list), and
// saves what the rule engine reads.

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

const PREFILL =
  '/bim/rules?project_id=p-1&model_id=m-2&boq_id=b-2&new=1&element_type=Walls' +
  '&prop_key=Phase%20Created&prop_value=New%20Construction&qty_source=Area&unit=m%C2%B2';

function save() {
  fireEvent.click(screen.getByRole('button', { name: 'common.save' }));
}

describe('quantity rule conditions', () => {
  it('offers the model values for not equals and saves the condition', async () => {
    renderAt(PREFILL);
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByTestId('rule-prop-op-0'), { target: { value: 'not_equals' } });
    const valueInput = screen.getByTestId('rule-prop-value-0') as HTMLInputElement;
    await waitFor(() => {
      const options = document.getElementById(valueInput.getAttribute('list') ?? '')?.querySelectorAll('option');
      expect(Array.from(options ?? []).map((o) => o.getAttribute('value'))).toEqual([
        'New Construction',
        'Existing',
        'Demolished',
      ]);
    });
    // The property table names the column by its stored key, not the header.
    expect(mocks.fetchBIMDataframeColumnValues.mock.calls[0]?.slice(0, 2)).toEqual(['m-2', 'phase created']);
    fireEvent.change(valueInput, { target: { value: 'Demolished' } });
    save();
    await waitFor(() => expect(mocks.createQuantityMap).toHaveBeenCalled());
    expect(mocks.createQuantityMap.mock.calls[0]![0].property_filter).toEqual({
      'Phase Created': { $op: 'not_equals', value: 'Demolished' },
    });
  });

  it('keeps equals as the bare value older rules carry', async () => {
    renderAt(PREFILL);
    await screen.findByRole('dialog');
    save();
    await waitFor(() => expect(mocks.createQuantityMap).toHaveBeenCalled());
    expect(mocks.createQuantityMap.mock.calls[0]![0].property_filter).toEqual({ 'Phase Created': 'New Construction' });
  });

  it('refuses a comparison value that is not a number, and saves one with a unit', async () => {
    renderAt(PREFILL);
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByTestId('rule-prop-key-0'), { target: { value: 'Width' } });
    fireEvent.change(screen.getByTestId('rule-prop-op-0'), { target: { value: 'gt' } });
    const valueInput = screen.getByTestId('rule-prop-value-0') as HTMLInputElement;
    // A comparison offers no value list.
    expect(valueInput.getAttribute('list')).toBeNull();
    fireEvent.change(valueInput, { target: { value: 'wide' } });
    expect(screen.getByTestId('rule-prop-problem-0').textContent).toContain('Write a number');
    expect((screen.getByRole('button', { name: 'common.save' }) as HTMLButtonElement).disabled).toBe(true);
    save();
    expect(mocks.createQuantityMap).not.toHaveBeenCalled();

    fireEvent.change(valueInput, { target: { value: ' 2.5 m ' } });
    expect(screen.queryByTestId('rule-prop-problem-0')).toBeNull();
    save();
    await waitFor(() => expect(mocks.createQuantityMap).toHaveBeenCalled());
    expect(mocks.createQuantityMap.mock.calls[0]![0].property_filter).toEqual({ Width: { $op: 'gt', value: '2.5 m' } });
  });

  it('asks for a value before contains can be saved', async () => {
    renderAt(PREFILL);
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByTestId('rule-prop-op-0'), { target: { value: 'contains' } });
    fireEvent.change(screen.getByTestId('rule-prop-value-0'), { target: { value: '   ' } });
    expect(screen.getByTestId('rule-prop-problem-0').textContent).toContain('needs a value');
    expect((screen.getByRole('button', { name: 'common.save' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('takes no value for is empty', async () => {
    renderAt(PREFILL);
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByTestId('rule-prop-key-0'), { target: { value: 'Phase Demolished' } });
    fireEvent.change(screen.getByTestId('rule-prop-op-0'), { target: { value: 'is_empty' } });
    expect(screen.queryByTestId('rule-prop-value-0')).toBeNull();
    save();
    await waitFor(() => expect(mocks.createQuantityMap).toHaveBeenCalled());
    expect(mocks.createQuantityMap.mock.calls[0]![0].property_filter).toEqual({
      'Phase Demolished': { $op: 'is_empty' },
    });
  });

  it('opens a saved rule with its comparisons and lists them readably', async () => {
    mocks.listQuantityMaps.mockResolvedValue({
      items: [
        {
          id: 'r-1',
          org_id: null,
          project_id: 'p-1',
          name: 'Thick walls kept',
          name_translations: null,
          element_type_filter: 'Walls',
          property_filter: { Width: { $op: 'gte', value: '200 mm' }, 'Phase Demolished': { $op: 'is_empty' } },
          quantity_source: 'area_m2',
          multiplier: '1',
          unit: 'm²',
          waste_factor_pct: '0',
          boq_target: { auto_create: true },
          is_active: true,
          metadata: {},
          created_at: '2026-10-11T00:00:00Z',
          updated_at: '2026-10-11T00:00:00Z',
        },
      ],
      total: 1,
    });
    renderAt('/bim/rules?project_id=p-1&model_id=m-2');
    expect(await screen.findByText('Width ≥ 200 mm')).toBeTruthy();
    expect(screen.getByText('Phase Demolished is empty')).toBeTruthy();
  });
});
