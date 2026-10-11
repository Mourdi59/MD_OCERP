// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * A failed edit in the BOQ editor explains itself in the reader's language.
 *
 * The add, update and delete failure toasts printed ``err.message`` as is,
 * so a dropped connection read "Failed to fetch", and the add section
 * dialog closed before the request, losing the typed name on a failure. They now go through
 * ``getErrorMessage``, which turns a network failure, a timeout or an API
 * refusal into a sentence meant for the user.
 *
 * Run:  npx vitest run src/features/boq/__tests__/editFailureToastIsReadable.test.tsx
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock('react-i18next', () => {
  const t = (key: string, opts?: Record<string, unknown>) => {
    const fallback = opts?.defaultValue;
    return typeof fallback === 'string' ? fallback : key;
  };
  const value = { t, i18n: { language: 'en', changeLanguage: () => {} } };
  return {
    useTranslation: () => value,
    Trans: ({ children }: { children: React.ReactNode }) => children,
    initReactI18next: { type: '3rdParty', init: () => {} },
    I18nextProvider: ({ children }: { children: React.ReactNode }) => children,
  };
});

const grid: { rowIds: string[]; select: ((ids: string[]) => void) | undefined } = { rowIds: [], select: undefined };

vi.mock('../BOQGrid', () => ({
  __esModule: true,
  default: React.forwardRef<
    unknown,
    { positions?: { id: string }[]; onSelectionChanged?: (ids: string[]) => void }
  >(function BOQGridStub(props, _ref) {
    grid.rowIds = (props.positions ?? []).map((p) => p.id);
    grid.select = props.onSelectionChanged;
    return <div data-testid="boq-grid-stub" />;
  }),
}));

vi.mock('@/features/bim/api', () => ({
  fetchBIMModels: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}));

vi.mock('@/shared/hooks/useBackendModuleOff', () => ({
  useBackendModuleOff: () => () => false,
}));

const BOQ_ID = 'boq-1';
const PROJECT_ID = 'proj-1';

const row = (id: string, ordinal: string, description: string, parent_id: string | null, unit: string) => ({
  id,
  boq_id: BOQ_ID,
  parent_id,
  ordinal,
  description,
  unit,
  quantity: unit ? 10 : 0,
  unit_rate: unit ? 50 : 0,
  total: unit ? 500 : 0,
  classification: {},
  source: 'manual',
  confidence: null,
  validation_status: 'pending',
  sort_order: 0,
  metadata: {},
});

const api = vi.hoisted(() => ({
  deletePosition: vi.fn(async () => undefined),
  addPosition: vi.fn(async () => {
    throw new TypeError('Failed to fetch');
  }),
  addSection: vi.fn(async () => {
    throw new Error("Cannot read properties of undefined (reading 'id')");
  }),
}));

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    boqApi: {
      get: vi.fn(async () => ({
        id: BOQ_ID,
        project_id: PROJECT_ID,
        name: 'Riverside HQ Bill',
        status: 'draft',
        is_locked: false,
        positions: [
          row('s1', '01', 'Shell', null, ''),
          row('p1', '01.001', 'Reinforced concrete wall C30/37', 's1', 'm2'),
        ],
      })),
      deletePosition: api.deletePosition,
      addPosition: api.addPosition,
      addSection: api.addSection,
      getMarkups: vi.fn(async () => ({ markups: [] })),
      getCostBreakdown: vi.fn(async () => ({
        boq_id: BOQ_ID,
        grand_total: 500,
        direct_cost: 500,
        categories: [],
        markups: [],
        top_resources: [],
      })),
      getLimits: vi.fn(async () => ({ max_nesting_depth: 5 })),
      getActivity: vi.fn(async () => []),
    },
  };
});

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    projectsApi: {
      ...actual.projectsApi,
      get: vi.fn(async () => ({ id: PROJECT_ID, name: 'Riverside HQ', currency: 'EUR', fx_rates: [] })),
    },
  };
});

import { BOQEditorPage } from '../BOQEditorPage';
import { useAuthStore } from '@/stores/useAuthStore';
import { useToastStore } from '@/stores/useToastStore';

async function renderEditor() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity, gcTime: Infinity } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/boq/${BOQ_ID}`]}>
        <Routes>
          <Route path="/boq/:boqId" element={<BOQEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByTestId('boq-grid-stub', {}, { timeout: 10_000 });
  await waitFor(() => expect(grid.rowIds).toEqual(expect.arrayContaining(['s1', 'p1'])), { timeout: 10_000 });
}

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  grid.rowIds = [];
  grid.select = undefined;
  useToastStore.setState({ toasts: [] });
  useAuthStore.setState({ userRole: 'editor' });
});

afterEach(() => cleanup());

describe('a failed edit in the BOQ editor', () => {
  it('shows a readable reason, not the raw network error of the browser', async () => {
    await renderEditor();
    fireEvent.keyDown(document.body, { key: 'Enter', ctrlKey: true });
    await waitFor(() => expect(api.addPosition).toHaveBeenCalled());
    await waitFor(() =>
      expect(useToastStore.getState().toasts.some((t) => t.title === 'Failed to add position')).toBe(true),
    );
    const toast = useToastStore.getState().toasts.find((t) => t.title === 'Failed to add position');
    expect(toast?.message).toBe('Could not reach the server. Please check your connection.');
  });

  it('keeps the add section dialog open with the typed name and shows no developer text', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    await renderEditor();
    fireEvent.click(screen.getAllByTitle('boq.add_section')[0]!);
    const name = (await screen.findByLabelText('Enter section name:')) as HTMLInputElement;
    fireEvent.change(name, { target: { value: 'Earthworks' } });
    fireEvent.click(screen.getByTestId('boq-add-section-confirm'));
    await waitFor(() => expect(api.addSection).toHaveBeenCalled());
    await waitFor(() =>
      expect(useToastStore.getState().toasts.some((t) => t.title === 'Failed to add section')).toBe(true),
    );
    const toast = useToastStore.getState().toasts.find((t) => t.title === 'Failed to add section');
    expect(toast?.message).not.toMatch(/Cannot read properties/);
    expect((screen.getByLabelText('Enter section name:') as HTMLInputElement).value).toBe('Earthworks');
  });
});
