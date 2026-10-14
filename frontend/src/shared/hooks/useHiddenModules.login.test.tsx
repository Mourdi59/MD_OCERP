// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Login sequence: the pack menu must never see an empty list while the server
// copy (which already carries the pack marker) is still on its way.
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const api = vi.hoisted(() => ({ apiGet: vi.fn(), apiPut: vi.fn() }));
const auth = vi.hoisted(() => ({ state: { userEmail: null as string | null, isAuthenticated: false } }));
const listeners = vi.hoisted(() => new Set<() => void>());

vi.mock('@/shared/lib/api', () => api);
vi.mock('@/stores/useAuthStore', async () => {
  const React = await import('react');
  return {
    useAuthStore: <T,>(selector: (s: typeof auth.state) => T): T => {
      const [, force] = React.useReducer((n: number) => n + 1, 0);
      React.useEffect(() => {
        listeners.add(force as () => void);
        return () => void listeners.delete(force as () => void);
      }, []);
      return selector(auth.state);
    },
  };
});

import { useHiddenModules } from './useHiddenModules';
import { applyPackMenu, packMarker } from '@/app/layout/packMenu';

const SLUG = 'eleven-areas-framework';
const SERVER_LIST = [packMarker(SLUG), '/crm'];

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  localStorage.clear();
  auth.state = { userEmail: null, isAuthenticated: false };
  api.apiGet.mockReset();
  api.apiPut.mockReset().mockResolvedValue({ hidden_modules: [] });
});
afterEach(cleanup);

describe('useHiddenModules on a fresh login', () => {
  it('reports loading until the server list has been folded into the state', async () => {
    api.apiGet.mockResolvedValue({ hidden_modules: SERVER_LIST });
    // What the sidebar's pack effect does on every render where isLoading is false.
    const seen: Array<{ loading: boolean; applied: string[] | null }> = [];
    const { result } = renderHook(
      () => {
        const hook = useHiddenModules();
        seen.push({
          loading: hook.isLoading,
          applied: hook.isLoading
            ? null
            : applyPackMenu({
                hidden: hook.hiddenModules,
                activeSlug: SLUG,
                packModules: [],
                routeModules: {},
                hideableRoutes: ['/crm', '/quantities'],
              }),
        });
        return hook;
      },
      { wrapper },
    );
    expect(result.current.isLoading).toBe(true);

    auth.state = { userEmail: 'a@b.c', isAuthenticated: true };
    act(() => listeners.forEach((fn) => fn()));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.hiddenModules).toEqual(SERVER_LIST);
    // Never a single render where the pack would have been applied.
    expect(seen.filter((s) => s.applied !== null)).toEqual([]);
    expect(api.apiPut).not.toHaveBeenCalled();
  });

  it('stays loading when the server copy cannot be fetched', async () => {
    api.apiGet.mockRejectedValue(new Error('boom'));
    auth.state = { userEmail: 'a@b.c', isAuthenticated: true };
    const { result } = renderHook(() => useHiddenModules(), { wrapper });
    await waitFor(() => expect(api.apiGet).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 30));
    expect(result.current.isLoading).toBe(true);
  });
});
