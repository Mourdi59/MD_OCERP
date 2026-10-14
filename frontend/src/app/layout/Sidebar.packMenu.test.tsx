// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The sidebar hands the active framework pack's rows to the menu editor's own
// list: once when the pack is chosen, never again after the user has had their
// say, and not before the saved list has arrived.
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

const api = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}));
const hidden = vi.hoisted(() => ({
  list: [] as string[],
  loading: false,
  set: vi.fn(),
}));

vi.mock('@/shared/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/shared/lib/api')>('@/shared/lib/api');
  return { ...actual, ...api };
});
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: unknown }) =>
      typeof opts?.defaultValue === 'string' ? opts.defaultValue : key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}));
vi.mock('@/shared/lib/useI18nReady', () => ({ useI18nReady: () => 0 }));
vi.mock('./CustomBranding', () => ({ CustomBranding: () => null }));
vi.mock('@/shared/ui/UpdateChecker', () => ({ UpdateNotification: () => null, UpdateBadge: () => null }));
vi.mock('@/features/modules/RequestCustomModuleDialog', () => ({
  RequestCustomModuleDialog: () => null,
}));
vi.mock('@/shared/hooks/useSidebarBadges', () => ({
  useSidebarBadges: () => ({ tasks: 0, rfi: 0, safety: 0 }),
}));
vi.mock('@/shared/hooks/useHiddenModules', () => ({
  useHiddenModules: () => ({
    hiddenModules: hidden.list,
    setHiddenModules: hidden.set,
    isLoading: hidden.loading,
  }),
}));
vi.mock('@/features/projects/useProjectProfile', () => ({
  useActiveProjectProfile: () => ({ projectId: null, profile: undefined, isLoading: false }),
  buildModuleGate: () => ({ active: false, byRoute: () => null }),
}));

import { Sidebar } from './Sidebar';
import { packMarker } from './packMenu';

const SLUG = 'eleven-areas-framework';

function packIs(manifest: Record<string, unknown> | null): void {
  api.apiGet.mockImplementation((path: string) => {
    if (path === '/v1/partner-pack/current') {
      return Promise.resolve(manifest ? { active: true, manifest } : { active: false });
    }
    if (path === '/v1/users/me/onboarding/') return Promise.resolve({ completed: true, company_type: null });
    return Promise.resolve([]);
  });
}

function renderSidebar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <Sidebar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 30));

beforeEach(() => {
  hidden.list = [];
  hidden.loading = false;
  hidden.set.mockReset();
  api.apiGet.mockReset();
});
afterEach(cleanup);

describe('Sidebar with a framework pack', () => {
  it('hides the rows of the modules the pack selects, with the marker, in the editor list', async () => {
    hidden.list = ['/rfi'];
    packIs({ slug: SLUG, default_modules: ['oe_site_logistics', 'oe_unlisted'] });
    renderSidebar();
    await waitFor(() => expect(hidden.set).toHaveBeenCalledTimes(1));
    expect(hidden.set).toHaveBeenCalledWith(['/rfi', packMarker(SLUG), '/site-logistics']);
  });

  it('leaves the list alone after the marker is stored, so a row shown again stays shown', async () => {
    hidden.list = [packMarker(SLUG)];
    packIs({ slug: SLUG, default_modules: ['oe_site_logistics'] });
    renderSidebar();
    await waitFor(() => expect(api.apiGet).toHaveBeenCalledWith('/v1/partner-pack/current'));
    await settle();
    expect(hidden.set).not.toHaveBeenCalled();
  });

  it('waits for the saved list before writing', async () => {
    hidden.loading = true;
    packIs({ slug: SLUG, default_modules: ['oe_site_logistics'] });
    renderSidebar();
    await waitFor(() => expect(api.apiGet).toHaveBeenCalledWith('/v1/partner-pack/current'));
    await settle();
    expect(hidden.set).not.toHaveBeenCalled();
  });

  it('does nothing for a pack that does not hide rows, or when no pack is active', async () => {
    packIs({ slug: 'some-country-pack', default_modules: ['oe_site_logistics'] });
    renderSidebar();
    await waitFor(() => expect(api.apiGet).toHaveBeenCalledWith('/v1/partner-pack/current'));
    await settle();
    cleanup();
    packIs(null);
    renderSidebar();
    await settle();
    expect(hidden.set).not.toHaveBeenCalled();
  });
});
