/**
 * Field-worker mobile shell.
 *
 * Implements the bottom-nav + thumb-zone layout described in
 * `docs/architecture/FIELD_WORKER_MOBILE_DESIGN.md` §6. The `/field` route in
 * `App.tsx` lazy-loads this chunk.
 *
 * What lives HERE:
 *   - Full-viewport shell with no sidebar / no desktop AppLayout
 *   - Bottom-nav with 4 fixed tabs (Today / Capture / Crew / Profile)
 *   - 56 px sticky header with current project name + offline/sync badge
 *   - Safe-area-aware padding via `env(safe-area-inset-*)`
 *   - Today / Capture / Crew tab bodies wired to the field-diary API; writes
 *     captured through the shared offline mutation queue (no second queue).
 *
 * What lives ELSEWHERE:
 *   - PIN-redemption screen at `/field/{token}` → separate `FieldAuthPage`
 *     (persists the session into sessionStorage; this shell reads it).
 *
 * Touch-target rule: every interactive element on this shell stays at
 * ≥48×48 px (WCAG 2.2 SC 2.5.8 AAA + Apple HIG + Material 3).
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Clock, Camera, Users, User } from 'lucide-react';
import { registerFieldServiceWorker } from '@/shared/lib/offline';
import { useFieldSync } from './useFieldSync';
import { OfflineStatusBadge } from './OfflineStatusBadge';
import { readFieldSession } from './fieldApi';
import { TodayTab, CaptureTab, CrewTab } from './FieldTabs';

/**
 * Auth headers for replayed field writes. The field session token + PIN are
 * stored in sessionStorage by the (future) PIN-redemption screen
 * (`FieldAuthPage`); reading them here keeps this offline slice self-contained
 * and free of a cross-lane store dependency. Returns an empty object when no
 * session is present, so the queue still drains harmlessly in that state.
 */
function fieldAuthHeaders(): Record<string, string> {
  try {
    const token = sessionStorage.getItem('oe_field_session_token');
    const pin = sessionStorage.getItem('oe_field_session_pin');
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (pin) headers['X-Field-PIN'] = pin;
    return headers;
  } catch {
    return {};
  }
}

type FieldTab = 'today' | 'capture' | 'crew' | 'profile';

interface FieldTabDef {
  key: FieldTab;
  label: string;
  Icon: typeof Clock;
}

const TABS: readonly FieldTabDef[] = [
  { key: 'today', label: 'Today', Icon: Clock },
  { key: 'capture', label: 'Capture', Icon: Camera },
  { key: 'crew', label: 'Crew', Icon: Users },
  { key: 'profile', label: 'Me', Icon: User },
] as const;

export function FieldShellPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<FieldTab>('today');
  const session = readFieldSession();

  // Stable headers provider so the queue sender is constructed once.
  const getHeaders = useCallback(() => fieldAuthHeaders(), []);
  const { online, pending, syncing, syncNow, enqueue } = useFieldSync(getHeaders);

  // Register the scoped field service worker so the shell + last-viewed data
  // load offline. Best-effort: a failure does not affect the IndexedDB queue.
  useEffect(() => {
    void registerFieldServiceWorker();
  }, []);

  return (
    <div
      className="flex min-h-screen flex-col bg-white"
      style={{
        // iOS safe-area inset so the bottom nav doesn't sit under the
        // home indicator on iPhone X+ in standalone PWA mode.
        paddingBottom: 'env(safe-area-inset-bottom)',
        paddingTop: 'env(safe-area-inset-top)',
      }}
    >
      {/* Sticky 56 px header — project name placeholder + offline/sync badge. */}
      <header className="sticky top-0 z-10 flex h-14 items-center justify-between gap-2 border-b border-slate-200 bg-white px-4">
        <span className="min-w-0 truncate text-base font-semibold text-slate-900">
          {session
            ? t('field.header', { defaultValue: 'Field time' })
            : t('field.header_no_session', { defaultValue: 'Field - sign in' })}
        </span>
        <div className="flex shrink-0 items-center gap-2">
          <OfflineStatusBadge
            online={online}
            pending={pending}
            syncing={syncing}
            onSyncNow={() => {
              void syncNow();
            }}
          />
          <button
            type="button"
            aria-label="Help"
            className="flex h-11 w-11 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100"
          >
            ?
          </button>
        </div>
      </header>

      {/* Tab body. */}
      <main className="flex flex-1 flex-col items-stretch overflow-y-auto">
        {tab === 'today' && <TodayTab session={session} />}
        {tab === 'capture' && <CaptureTab session={session} enqueue={enqueue} />}
        {tab === 'crew' && <CrewTab session={session} enqueue={enqueue} />}
        {tab === 'profile' && (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-4 py-8 text-center">
            <p className="text-sm text-slate-500">
              {session
                ? t('field.profile_signed_in', { defaultValue: 'Signed in as a field worker.' })
                : t('field.no_session', { defaultValue: 'Open the link from your SMS to start.' })}
            </p>
            <p className="text-xs text-slate-400">
              {online
                ? t('field.sync_online', { defaultValue: 'Online - changes sync automatically.' })
                : t('field.sync_offline', { defaultValue: 'Offline - changes are saved and will sync.' })}
            </p>
          </div>
        )}
      </main>

      {/* Bottom nav — fixed 64 px, 4 tabs. */}
      <nav
        className="sticky bottom-0 flex border-t border-slate-200 bg-white"
        aria-label="Field navigation"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        {TABS.map(({ key, label, Icon }) => {
          const active = key === tab;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              aria-current={active ? 'page' : undefined}
              aria-label={label}
              className={`flex h-16 flex-1 flex-col items-center justify-center gap-1 text-xs ${
                active ? 'text-sky-600' : 'text-slate-500'
              }`}
            >
              <Icon size={28} aria-hidden="true" />
              <span>{label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}

export default FieldShellPage;
