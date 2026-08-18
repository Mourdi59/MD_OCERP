// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// @ts-nocheck
// Pin the test process to UTC so any test that formats dates with local-time
// getters (e.g. buildExportFilename) is timezone-stable, regardless of the
// machine running it or how the fixture Date was constructed. Set before any
// module reads the timezone.
process.env.TZ = 'UTC';

// The assignment above lands in a worker process, where Node re-reads the zone
// after it changes. It does NOT land in a worker thread: `--pool=threads`
// shares one process, the zone is already resolved by the time this file runs,
// and the write is accepted and ignored. The symptom is a handful of date
// tests failing by exactly the host's offset while every other test passes,
// which reads like a bug in the code under test rather than in how the run was
// invoked. Measured on this repo at +0200: default pool 39 passed, the same
// file under `--pool=threads` 5 failed, and `TZ=UTC` in the environment before
// node starts made those 5 pass again.
//
// So say it out loud instead of letting five assertions imply it. Anyone who
// reaches for `--pool=threads` as a load workaround gets one sentence naming
// the cause rather than a date arithmetic mystery.
const resolvedZone = new Intl.DateTimeFormat().resolvedOptions().timeZone;
if (process.env.TZ === 'UTC' && resolvedZone !== 'UTC' && new Date().getTimezoneOffset() !== 0) {
  throw new Error(
    `Tests must run in UTC, but this worker resolved ${resolvedZone}. Setting process.env.TZ ` +
      'here cannot move a worker thread. Drop --pool=threads, or put TZ=UTC in the environment ' +
      'before node starts.',
  );
}

import '@testing-library/jest-dom';
import { configure } from '@testing-library/dom';

// Under full-suite parallel load (worker starvation on 2-core CI runners and
// local runs) the default 1s `findBy*`/`waitFor` budget intermittently expires
// before chained React Query mocks resolve and re-render. 5s only raises the
// upper bound — fast tests stay exactly as fast.
configure({ asyncUtilTimeout: 5000 });

// Node's `undici`-backed `fetch` rejects an `AbortSignal` created via the
// jsdom-provided `AbortController` ("Expected signal to be an instance of
// AbortSignal") because the two constructors come from different realms.
// jsdom replaces the global classes, leaving production code (which calls
// `new AbortController()` against the active global) with signals that
// undici treats as foreign. Wrap `fetch` so any non-native signal is silently
// dropped — tests don't exercise abort behaviour and MSW intercepts requests
// regardless of the signal field.
{
  const originalFetch = globalThis.fetch;
  if (typeof originalFetch === 'function') {
    globalThis.fetch = ((input, init) => {
      if (init && 'signal' in init) {
        // Drop the realm-mismatched signal; keep the rest of the init.
        const { signal: _signal, ...rest } = init;
        return originalFetch(input, rest);
      }
      return originalFetch(input, init);
    }) as typeof fetch;
  }
}


// Mock i18next. We expose the same surface that production code imports
// from `react-i18next` — `useTranslation`, `Trans`, AND `initReactI18next`
// (a noop plugin shape). Components that pull `t(key)` get sensible
// English fallbacks via `defaultValue`; components that import
// `initReactI18next` (because they live downstream of `app/i18n.ts`) get
// a no-op plugin so the import side-effect doesn't crash.
const noopPlugin = { type: '3rdParty', init: () => {} };
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (typeof opts === 'object' && opts !== null && 'defaultValue' in opts) {
        // Mirror the two i18next behaviours real components rely on:
        // (1) pick the ``_other`` plural default whenever ``count`` is
        // present and not 1 (English plural rule), and (2) interpolate
        // ``{{var}}`` placeholders from the options. Without this the mock
        // returned templates like "{{count}} record" verbatim.
        let template = opts.defaultValue as string;
        if (
          'count' in opts &&
          opts.count !== 1 &&
          typeof opts.defaultValue_other === 'string'
        ) {
          template = opts.defaultValue_other as string;
        }
        return template.replace(/\{\{(\w+)\}\}/g, (_match, name) =>
          name in opts ? String(opts[name]) : `{{${name}}}`,
        );
      }
      return key;
    },
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: noopPlugin,
  I18nextProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// Mock react-router-dom navigation
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => ({}),
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
  };
});

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });
