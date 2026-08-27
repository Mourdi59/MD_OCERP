// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Issue #439, receiving half. The BOQ workflow now links here with the open
 * project and BOQ in the query string; a page that ignored them would silently
 * drop the context and be worse than no link at all.
 *
 * The active-project store is deliberately set to a DIFFERENT project than the
 * one in the link. The page already pre-filled the import picker from the
 * header selection, so a test that used the same id for both would pass
 * against code that never read the URL.
 *
 * Every assertion about a cleared field waits for the list that field draws
 * from to arrive first. An empty select is the state before loading as well as
 * the state after a bad id is dropped, and only the second one is the claim.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { generateGAEBXML, type ExportPosition } from './data/gaebExport';

/** The project selected in the top bar - never the one the deep link names. */
const HEADER_PROJECT = 'proj-header';

const PROJECTS = [
  { id: 'proj-alpha', name: 'Neubau Alpha' },
  { id: HEADER_PROJECT, name: 'Sanierung Header' },
];

const BOQS_BY_PROJECT: Record<string, { id: string; name: string }[]> = {
  'proj-alpha': [
    { id: 'boq-17', name: 'Hauptangebot LV' },
    { id: 'boq-18', name: 'Nachtrag 1' },
  ],
  [HEADER_PROJECT]: [{ id: 'boq-70', name: 'Rohbau' }],
};

/** Placeholder option plus one per row. */
const projectOptionCount = PROJECTS.length + 1;
const alphaBoqOptionCount = BOQS_BY_PROJECT['proj-alpha']!.length + 1;

let currentSearch = '';

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => ({}),
    useSearchParams: () => [new URLSearchParams(currentSearch), vi.fn()],
  };
});

vi.mock('@/shared/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/lib/api')>();
  return {
    ...actual,
    getAuthToken: vi.fn(() => 'test-token'),
    triggerDownload: vi.fn(),
    apiGet: vi.fn(async (path: string) => {
      if (path.startsWith('/v1/projects/')) return PROJECTS;
      const list = path.match(/^\/v1\/boq\/boqs\/\?project_id=(.*)$/);
      if (list) return BOQS_BY_PROJECT[decodeURIComponent(list[1]!)] ?? [];
      if (/^\/v1\/boq\/boqs\/[^/?]+$/.test(path)) return { positions: [] };
      return [];
    }),
  };
});

vi.mock('@/stores/useToastStore', () => ({
  useToastStore: () => vi.fn(),
}));

vi.mock('@/stores/useProjectContextStore', () => ({
  useProjectContextStore: (selector: (s: { activeProjectId: string }) => unknown) =>
    selector({ activeProjectId: HEADER_PROJECT }),
}));

import GAEBExchangeModule from './GAEBExchangeModule';

const SAMPLE_POSITIONS: ExportPosition[] = [
  { id: 's1', ordinal: '01', description: 'Erdarbeiten', unit: '', quantity: 0, unitRate: 0, total: 0, isSection: true },
  { id: 'p1', ordinal: '01.001', description: 'Baugrubenaushub', unit: 'm3', quantity: 120, unitRate: 18.5, total: 2220, section: 'Erdarbeiten' },
];

function renderAt(search: string) {
  currentSearch = search;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/gaeb-exchange${search}`]}>
        <GAEBExchangeModule />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const exportProject = () => screen.getByTestId('gaeb-export-project') as HTMLSelectElement;
const exportBoq = () => screen.getByTestId('gaeb-export-boq') as HTMLSelectElement;
const importProject = () => screen.getByTestId('gaeb-import-project') as HTMLSelectElement;

const optionCount = (el: HTMLSelectElement) => el.querySelectorAll('option').length;

/**
 * The import target pickers only exist once a file has been parsed, so the
 * import-side assertions have to get a real GAEB file through the drop zone
 * first. Round-tripping the module's own exporter keeps the fixture honest.
 */
async function dropGaebFile() {
  const { xml } = generateGAEBXML({
    format: 'X83',
    projectName: 'Testprojekt',
    boqName: 'LV',
    currency: 'EUR',
    positions: SAMPLE_POSITIONS,
  });
  const file = new File([xml], 'tender.x83', { type: 'application/xml' });
  const dropZone = screen.getByText(/Drop a GAEB XML file here/).closest('div')!;
  fireEvent.drop(dropZone, { dataTransfer: { files: [file] } });
  await waitFor(() => expect(screen.getByTestId('gaeb-import-project')).toBeInTheDocument());
}

beforeEach(() => {
  currentSearch = '';
});

describe('GAEB Exchange deep link from the BOQ workflow', () => {
  it('opens the Export tab with the linked project and BOQ preselected', async () => {
    renderAt('?project_id=proj-alpha&boq_id=boq-17&tab=export');

    // The Export tab owns these selects, so finding them proves the tab too.
    await waitFor(() => expect(optionCount(exportProject())).toBe(projectOptionCount));
    await waitFor(() => expect(optionCount(exportBoq())).toBe(alphaBoqOptionCount));

    expect(exportProject().value).toBe('proj-alpha');
    expect(exportProject().value).not.toBe(HEADER_PROJECT);
    expect(exportBoq().value).toBe('boq-17');
  });

  it('leaves the Export tab empty when nothing was handed over', async () => {
    renderAt('');

    fireEvent.click(screen.getByTestId('gaeb-tab-export'));
    await waitFor(() => expect(optionCount(exportProject())).toBe(projectOptionCount));

    expect(exportProject().value).toBe('');
    expect(exportBoq().value).toBe('');
  });

  it('drops a BOQ id that does not resolve and keeps the rest of the context', async () => {
    renderAt('?project_id=proj-alpha&boq_id=boq-deleted&tab=export');

    // Wait for the BOQ list itself, so an empty picker cannot be mistaken for
    // "not loaded yet".
    await waitFor(() => expect(optionCount(exportBoq())).toBe(alphaBoqOptionCount));

    expect(exportBoq().value).toBe('');
    expect(exportProject().value).toBe('proj-alpha');
  });

  it('drops a project id that does not resolve without breaking the page', async () => {
    renderAt('?project_id=proj-gone&boq_id=boq-17&tab=export');

    await waitFor(() => expect(optionCount(exportProject())).toBe(projectOptionCount));

    expect(exportProject().value).toBe('');
    expect(exportBoq().value).toBe('');
  });

  it('preselects the linked project on the Import tab over the header selection', async () => {
    renderAt('?project_id=proj-alpha&tab=import');
    await dropGaebFile();

    await waitFor(() => expect(optionCount(importProject())).toBe(projectOptionCount));
    expect(importProject().value).toBe('proj-alpha');
    expect(importProject().value).not.toBe(HEADER_PROJECT);
  });

  it('still falls back to the header project when no link supplied one', async () => {
    renderAt('');
    await dropGaebFile();

    await waitFor(() => expect(optionCount(importProject())).toBe(projectOptionCount));
    expect(importProject().value).toBe(HEADER_PROJECT);
  });
});
