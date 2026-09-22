// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// What the sidebar offers in Simple mode, with and without a company
// workspace. The rows are read as hrefs off the rendered links, in document
// order, so the order a general contractor reads the menu in is what is
// pinned, and a row that renders twice shows up as a count.
//
// The profile comes from the server (`GET /v1/users/me/onboarding/`), which is
// what lets the workspace follow the user to another browser; the tests below
// answer that call and, in two of them, disagree with the local cache on
// purpose to show which one wins.

import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

const api = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}));

vi.mock('@/shared/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/shared/lib/api')>('@/shared/lib/api');
  return { ...actual, ...api };
});

// The suite-wide mock answers `t(key, { defaultValue: undefined })` by calling
// `.replace` on undefined, and most menu rows carry no defaultLabel. Labels
// are not what these tests read, so any string will do.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: unknown }) =>
      typeof opts?.defaultValue === 'string' ? opts.defaultValue : key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}));

// Surfaces around the menu that make their own calls and decide nothing here.
vi.mock('@/shared/lib/useI18nReady', () => ({ useI18nReady: () => 0 }));
vi.mock('./CustomBranding', () => ({ CustomBranding: () => null }));
vi.mock('@/shared/ui/UpdateChecker', () => ({ UpdateNotification: () => null }));
vi.mock('@/shared/ui/ArticleNewsCard', () => ({ ArticleNewsCard: () => null }));
vi.mock('@/features/modules/RequestCustomModuleDialog', () => ({
  RequestCustomModuleDialog: () => null,
}));
vi.mock('@/shared/hooks/useSidebarBadges', () => ({
  useSidebarBadges: () => ({ tasks: 0, rfi: 0, safety: 0 }),
}));
vi.mock('@/shared/hooks/useHiddenModules', () => ({
  useHiddenModules: () => ({ hiddenModules: [], setHiddenModules: vi.fn() }),
}));
vi.mock('@/features/projects/useProjectProfile', () => ({
  useActiveProjectProfile: () => ({ projectId: null, profile: undefined, isLoading: false }),
  buildModuleGate: () => ({ active: false, byRoute: () => null }),
}));

import { Sidebar } from './Sidebar';
import { useAuthStore } from '@/stores/useAuthStore';
import { useModuleStore } from '@/stores/useModuleStore';
import { useViewModeStore } from '@/stores/useViewModeStore';

/** Answer the two calls the menu depends on: the backend module list (none
 *  disabled) and the signed-in user's onboarding record. */
function serverSays(companyType: string | null): void {
  api.apiGet.mockImplementation((path: string) => {
    if (path === '/v1/users/me/onboarding/') {
      return Promise.resolve({ completed: true, company_type: companyType });
    }
    return Promise.resolve([]);
  });
}

function renderAt(entry = '/', cachedOnboarding?: unknown) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (cachedOnboarding !== undefined) client.setQueryData(['me-onboarding'], cachedOnboarding);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Sidebar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const nav = () => screen.getByRole('navigation', { name: 'Main navigation' });

/** Menu rows in document order. The two tiles at the foot of the list
 *  (manage modules, developer guide) are not screens and are left out. */
function menuHrefs(root: HTMLElement = nav()): string[] {
  return within(root)
    .getAllByRole('link')
    .map((a) => a.getAttribute('href') ?? '')
    .filter((href) => href !== '/modules' && href !== '/modules/developer-guide');
}

const GC_WORKSPACE = [
  '/',
  '/inbox',
  '/projects',
  '/boq',
  '/finance?tab=budgets',
  '/contracts',
  '/subcontractors',
  '/changeorders',
  '/contracts?tab=claims',
  '/finance?tab=payments',
  '/finance?tab=retention',
  '/schedule',
  '/daily-diary',
  '/punchlist',
  '/closeout',
];

// Simple mode as it has always been: the groups without `hideInSimple`, minus
// their `advancedOnly` rows. Written out rather than derived from the catalogue,
// because deriving it would restate the rule under test.
const TODAYS_SIMPLE = [
  '/',
  '/projects',
  '/cases',
  '/files',
  '/inbox',
  '/timeline',
  '/takeoff?tab=measurements',
  '/dwg-takeoff',
  '/bim',
  '/quantities',
  '/costs',
  '/catalog',
  '/cost-explorer',
  '/assemblies',
  '/cost-match',
  '/fx',
  '/boq',
  '/templates',
  '/regional-exchange',
  '/match-elements',
  '/project-intelligence',
  '/rom-estimate',
  '/methodologies',
  '/sheets',
  '/geo',
  '/pointcloud',
  '/contracts',
  '/payment-clock',
  '/tax-withholding',
  '/tax-rates',
  '/einvoice-clearance',
];

beforeEach(() => {
  localStorage.clear();
  api.apiGet.mockReset();
  useAuthStore.setState({ isAuthenticated: true, userRole: 'editor' });
  // Every module on, so the rows below depend on the mode and the profile only.
  useModuleStore.setState({ enabledModules: {}, hiddenGroups: [] });
  // The store reads localStorage once at import, so the mode is set on it.
  useViewModeStore.getState().setMode('simple');
});

afterEach(() => cleanup());

describe('Simple mode with a general contractor profile', () => {
  it('shows the workspace rows, in order, and nothing else until More modules opens', async () => {
    serverSays('general_contractor');
    renderAt('/');

    const workspace = await screen.findByTestId('sidebar-workspace');
    expect(menuHrefs(workspace)).toEqual(GC_WORKSPACE);
    expect(menuHrefs()).toEqual(GC_WORKSPACE);
    expect(screen.getByText('General Contractor')).toBeTruthy();

    const more = screen.getByTestId('sidebar-more-modules');
    expect(more.getAttribute('aria-expanded')).toBe('false');
  });

  it('reveals every other screen under More modules without listing a workspace row twice', async () => {
    serverSays('general_contractor');
    renderAt('/');

    fireEvent.click(await screen.findByTestId('sidebar-more-modules'));

    const hrefs = menuHrefs();
    expect(hrefs.slice(0, GC_WORKSPACE.length)).toEqual(GC_WORKSPACE);
    // Screens Simple mode hid outright are now one click away...
    for (const route of ['/rfi', '/finance', '/variations', '/fx', '/geo', '/crm']) {
      expect(hrefs).toContain(route);
    }
    // ...and the workspace's own rows appear once, in the workspace.
    for (const route of GC_WORKSPACE) {
      expect(hrefs.filter((href) => href === route)).toHaveLength(1);
    }
    expect(screen.getByTestId('sidebar-more-modules').getAttribute('aria-expanded')).toBe('true');
  });

  it('lights the tab row a link opens, not the row of its page', async () => {
    serverSays('general_contractor');
    renderAt('/contracts?tab=claims');

    const workspace = await screen.findByTestId('sidebar-workspace');
    const link = (href: string) =>
      within(workspace)
        .getAllByRole('link')
        .find((a) => a.getAttribute('href') === href)!;
    await waitFor(() => expect(link('/contracts?tab=claims').className).toContain('font-semibold'));
    expect(link('/contracts').className).not.toContain('font-semibold');
  });

  it('opens More modules by itself when the current screen lives there', async () => {
    serverSays('general_contractor');
    renderAt('/rfi');

    const more = await screen.findByTestId('sidebar-more-modules');
    await waitFor(() => expect(more.getAttribute('aria-expanded')).toBe('true'));
    expect(menuHrefs()).toContain('/rfi');
  });

  it('follows the server, not the cache of whoever used this browser before', async () => {
    localStorage.setItem('oe_company_type', 'general_contractor');
    serverSays('estimator');
    renderAt('/');

    await waitFor(() => expect(screen.queryByTestId('sidebar-workspace')).toBeNull());
    expect(menuHrefs()).toEqual(TODAYS_SIMPLE);
    expect(localStorage.getItem('oe_company_type')).toBe('estimator');
  });

  it('asks again when the menu mounts, so the next sign-in on this tab gets its own profile', async () => {
    // Logout keeps the query cache: the previous user's fresh record is still in it.
    serverSays('estimator');
    renderAt('/', { completed: true, company_type: 'general_contractor' });

    await waitFor(() => expect(screen.queryByTestId('sidebar-workspace')).toBeNull());
    expect(menuHrefs()).toEqual(TODAYS_SIMPLE);
  });

  it('reaches a browser the wizard never ran in', async () => {
    serverSays('general_contractor');
    renderAt('/');

    expect(menuHrefs(await screen.findByTestId('sidebar-workspace'))).toEqual(GC_WORKSPACE);
    expect(localStorage.getItem('oe_company_type')).toBe('general_contractor');
  });
});

describe('without a workspace, or in Advanced mode', () => {
  it('Simple mode for a profile with no workspace is what it always was', async () => {
    serverSays('estimator');
    renderAt('/');

    await waitFor(() => expect(api.apiGet).toHaveBeenCalledWith('/v1/users/me/onboarding/'));
    expect(screen.queryByTestId('sidebar-workspace')).toBeNull();
    expect(screen.queryByTestId('sidebar-more-modules')).toBeNull();
    expect(menuHrefs()).toEqual(TODAYS_SIMPLE);
  });

  it('Simple mode with no profile at all is what it always was', async () => {
    serverSays(null);
    renderAt('/');

    await waitFor(() => expect(api.apiGet).toHaveBeenCalledWith('/v1/users/me/onboarding/'));
    expect(menuHrefs()).toEqual(TODAYS_SIMPLE);
  });

  it('Advanced mode ignores the workspace and shows the whole catalogue', async () => {
    useViewModeStore.getState().setMode('advanced');
    serverSays('general_contractor');
    renderAt('/');

    await waitFor(() => expect(api.apiGet).toHaveBeenCalledWith('/v1/users/me/onboarding/'));
    expect(screen.queryByTestId('sidebar-workspace')).toBeNull();
    expect(screen.queryByTestId('sidebar-more-modules')).toBeNull();
    const hrefs = menuHrefs();
    expect(hrefs.slice(0, 6)).toEqual(['/', '/projects', '/cases', '/files', '/inbox', '/timeline']);
    for (const route of ['/subcontractors', '/changeorders', '/finance', '/fx', '/geo']) {
      expect(hrefs).toContain(route);
    }
    expect(hrefs).not.toContain('/finance?tab=budgets');
  });
});
