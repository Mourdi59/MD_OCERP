// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Which company profile the signed-in user chose, and the workspace it brings.
//
// The server is the source: `GET /v1/users/me/onboarding/` returns the
// `company_type` the wizard or the Modules page last saved, so the answer
// survives a reload and follows the user to another browser. `oe_company_type`
// in localStorage is only the instant cache for the first paint and for a
// server that cannot be reached; once the server answers, its answer wins and
// is written back to the cache, so the Modules page (which reads the cache)
// opens on the right profile in a browser the wizard never ran in.
//
// The query key is shared with the dashboard's first-run check, which reads
// `completed` from the same response. Whoever saves a profile writes the
// response into this key (`ME_ONBOARDING_QUERY_KEY`), so the sidebar follows
// the switch without waiting out the stale time.

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/shared/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';
import { workspaceFor, type Workspace } from './workspaces';

export const ME_ONBOARDING_QUERY_KEY = ['me-onboarding'] as const;

/** localStorage cache of the chosen profile key. Written by the wizard and the
 *  Modules page profile switch, read by the Modules page. */
export const COMPANY_TYPE_STORAGE_KEY = 'oe_company_type';

/** The part of `OnboardingResponse` the client reads. */
export interface MeOnboarding {
  completed: boolean;
  company_type?: string | null;
  company_size?: string | null;
}

function readCachedCompanyType(): string | null {
  try {
    return localStorage.getItem(COMPANY_TYPE_STORAGE_KEY);
  } catch {
    return null;
  }
}

/** The signed-in user's company preset key, or null when none was chosen. */
export function useCompanyPresetKey(): string | null {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { data } = useQuery({
    queryKey: ME_ONBOARDING_QUERY_KEY,
    queryFn: () => apiGet<MeOnboarding>('/v1/users/me/onboarding/').catch(() => null),
    enabled: isAuthenticated,
    retry: false,
    staleTime: 5 * 60_000,
    // Logout keeps the query cache, and the key names no user, so the next
    // person to sign in on this tab would inherit the previous one's profile
    // for the whole stale time. The menu mounts once per sign-in, so asking
    // again on mount costs one request per session.
    refetchOnMount: 'always',
  });

  // `data` is undefined while loading and null when the server could not be
  // asked; both fall back to the cache. An answer, even an empty one, wins.
  const serverKey = data ? (data.company_type ?? null) : undefined;

  useEffect(() => {
    if (!serverKey) return;
    try {
      if (localStorage.getItem(COMPANY_TYPE_STORAGE_KEY) !== serverKey) {
        localStorage.setItem(COMPANY_TYPE_STORAGE_KEY, serverKey);
      }
    } catch {
      // Storage unavailable: the server answer still drives this render.
    }
  }, [serverKey]);

  return serverKey !== undefined ? serverKey : readCachedCompanyType();
}

/** The workspace the user's company profile brings, or null when it has none. */
export function useCompanyWorkspace(): Workspace | null {
  return workspaceFor(useCompanyPresetKey());
}
