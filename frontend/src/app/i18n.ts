// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { useTranslation as useI18nTranslation } from 'react-i18next';

export const SUPPORTED_LANGUAGES = [
  { code: 'en', name: 'English', flag: '🇬🇧', country: 'gb' },
  // American English is a regional variant of the entry above, in the same sense
  // es-MX is one of es: the file under `locales/en-US.ts` holds only the words
  // American practice names differently, and every other key is answered by
  // `en.ts` through the fallback chain. The region subtag is upper case because
  // that is how i18next normalises a two-part code, and the bundle has to be
  // registered under the same spelling it looks up.
  { code: 'en-US', name: 'English (US)', english: 'English (United States)', flag: '🇺🇸', country: 'us' },
  { code: 'de', name: 'Deutsch', english: 'German', flag: '🇩🇪', country: 'de' },
  { code: 'fr', name: 'Français', english: 'French', flag: '🇫🇷', country: 'fr' },
  { code: 'es', name: 'Español', english: 'Spanish', flag: '🇪🇸', country: 'es' },
  { code: 'es-MX', name: 'Español (México)', english: 'Spanish (Mexico)', flag: '🇲🇽', country: 'mx' },
  { code: 'es-CL', name: 'Español (Chile)', english: 'Spanish (Chile)', flag: '🇨🇱', country: 'cl' },
  { code: 'es-CO', name: 'Español (Colombia)', english: 'Spanish (Colombia)', flag: '🇨🇴', country: 'co' },
  { code: 'pt', name: 'Português', english: 'Portuguese', flag: '🇵🇹', country: 'pt' },
  { code: 'pt-BR', name: 'Português (Brasil)', english: 'Portuguese (Brazil)', flag: '🇧🇷', country: 'br' },
  { code: 'ru', name: 'Русский', english: 'Russian', flag: '🇷🇺', country: 'ru' },
  { code: 'zh', name: '简体中文', english: 'Chinese (Simplified)', flag: '🇨🇳', country: 'cn' },
  { code: 'ar', name: 'العربية', english: 'Arabic', flag: '🇸🇦', country: 'sa', dir: 'rtl' },
  { code: 'hi', name: 'हिन्दी', english: 'Hindi', flag: '🇮🇳', country: 'in' },
  { code: 'tr', name: 'Türkçe', english: 'Turkish', flag: '🇹🇷', country: 'tr' },
  { code: 'it', name: 'Italiano', english: 'Italian', flag: '🇮🇹', country: 'it' },
  { code: 'nl', name: 'Nederlands', english: 'Dutch', flag: '🇳🇱', country: 'nl' },
  { code: 'pl', name: 'Polski', english: 'Polish', flag: '🇵🇱', country: 'pl' },
  { code: 'cs', name: 'Čeština', english: 'Czech', flag: '🇨🇿', country: 'cz' },
  { code: 'ja', name: '日本語', english: 'Japanese', flag: '🇯🇵', country: 'jp' },
  { code: 'ko', name: '한국어', english: 'Korean', flag: '🇰🇷', country: 'kr' },
  { code: 'sv', name: 'Svenska', english: 'Swedish', flag: '🇸🇪', country: 'se' },
  { code: 'no', name: 'Norsk', english: 'Norwegian', flag: '🇳🇴', country: 'no' },
  { code: 'da', name: 'Dansk', english: 'Danish', flag: '🇩🇰', country: 'dk' },
  { code: 'fi', name: 'Suomi', english: 'Finnish', flag: '🇫🇮', country: 'fi' },
  { code: 'bg', name: 'Български', english: 'Bulgarian', flag: '🇧🇬', country: 'bg' },
  { code: 'hr', name: 'Hrvatski', english: 'Croatian', flag: '🇭🇷', country: 'hr' },
  { code: 'id', name: 'Bahasa Indonesia', english: 'Indonesian', flag: '🇮🇩', country: 'id' },
  { code: 'ro', name: 'Română', english: 'Romanian', flag: '🇷🇴', country: 'ro' },
  { code: 'th', name: 'ไทย', english: 'Thai', flag: '🇹🇭', country: 'th' },
  { code: 'vi', name: 'Tiếng Việt', english: 'Vietnamese', flag: '🇻🇳', country: 'vn' },
  // Mongolian is deliberately not offered: five invented roots passed every
  // gate in mn.ts and the file needs a native-speaker pass before the
  // language returns. The locale file stays on disk so the work resumes from
  // where it stopped, but nothing loads it while it is off this list.
  { code: 'ky', name: 'Кыргызча', english: 'Kyrgyz', flag: '🇰🇬', country: 'kg' },
  { code: 'et', name: 'Eesti', english: 'Estonian', flag: '🇪🇪', country: 'ee' },
  { code: 'bn', name: 'বাংলা', english: 'Bengali', flag: '🇧🇩', country: 'bd' },
  { code: 'kk', name: 'Қазақша', english: 'Kazakh', flag: '🇰🇿', country: 'kz' },
  { code: 'fil', name: 'Filipino', english: 'Filipino', flag: '🇵🇭', country: 'ph' },
  { code: 'ur', name: 'اردو', english: 'Urdu', flag: '🇵🇰', country: 'pk', dir: 'rtl' },
  { code: 'fa', name: 'فارسی', english: 'Persian', flag: '🇮🇷', country: 'ir', dir: 'rtl' },
  { code: 'he', name: 'עברית', english: 'Hebrew', flag: '🇮🇱', country: 'il', dir: 'rtl' },
  { code: 'el', name: 'Ελληνικά', english: 'Greek', flag: '🇬🇷', country: 'gr' },
  // `uk` is the ISO 639-1 code for Ukrainian, and it is also the string this
  // codebase already uses for the United Kingdom as a *region*: a BoQ preset
  // region, a country-pack id, and the country map in CreateProjectPage all
  // carry `uk` meaning Britain. The two live in different namespaces and must
  // stay that way. Nothing may derive a UI language from a region code, or a
  // British project would come up in Ukrainian.
  { code: 'uk', name: 'Українська', english: 'Ukrainian', flag: '🇺🇦', country: 'ua' },
  // Uzbek is written in Latin script: the Latin alphabet has been the official
  // one since 1993 and is what public and construction documentation uses. The
  // two modifier letters in the language's own name are U+02BB, not an
  // apostrophe, and a straight quote there is a misspelling rather than a
  // typographic preference.
  { code: 'uz', name: 'Oʻzbekcha', english: 'Uzbek', flag: '🇺🇿', country: 'uz' },
];

export function getLanguageByCode(code: string): (typeof SUPPORTED_LANGUAGES)[number] {
  return SUPPORTED_LANGUAGES.find((l) => l.code === code) ?? SUPPORTED_LANGUAGES[0]!;
}

/**
 * Normalize a partner-pack ``default_locale`` to a supported UI language code.
 *
 * Pack manifests carry BCP-47 locales that often include a region subtag
 * (batimatech-ca ships ``fr-CA`` for French Canada, uk-jct ships ``en-GB``,
 * commercial-denver ships ``en-US``). A regional code the UI actually ships is
 * answered with itself, because a pack that names a region has asked for that
 * region and stripping it would hand a Denver pack British English. Anything
 * else falls back to the base language (``fr-CA`` -> ``fr``), and a locale we do
 * not ship at all returns ``'en'``, so a pack can never force the app into a
 * language that has no strings.
 */
export function normalizePackLocale(locale: string | null | undefined): string {
  if (!locale) return 'en';
  const trimmed = locale.trim();
  // Match how i18next writes a two-part code, so 'en-us' and 'EN-us' both find
  // the 'en-US' we ship rather than falling through to the base language.
  const parts = trimmed.split('-');
  const regional =
    parts.length === 2 ? `${parts[0]!.toLowerCase()}-${parts[1]!.toUpperCase()}` : trimmed;
  if (SUPPORTED_LANGUAGES.some((l) => l.code === regional)) return regional;
  const base = parts[0]!.toLowerCase();
  return SUPPORTED_LANGUAGES.some((l) => l.code === base) ? base : 'en';
}

// Re-export useTranslation for convenience
export const useTranslation = useI18nTranslation;

// English ships in the main bundle as the i18next fallback. Every other
// locale lives in its own per-language chunk and is fetched on demand —
// see ``loadLocaleResource`` below.
import enResource from './locales/en';

// Module translations applied at runtime
const moduleTranslations: Record<string, Record<string, Record<string, string>>> = {};

// Track which non-English locales have been hydrated so we don't fetch
// the same chunk twice (e.g. on every ``languageChanged`` round trip).
const loadedLocales = new Set<string>(['en']);

/**
 * Load a per-locale resource chunk and merge it into i18next.
 *
 * Vite turns the dynamic ``import(`./locales/${code}.ts`)`` literal into
 * one chunk per matching file under ``src/app/locales/``, so a French
 * user only downloads ``fr.ts`` (~50 KB gzip) instead of the previous
 * ~1.28 MB monolithic ``i18n-data`` chunk.
 *
 * Idempotent. Safe to call repeatedly. Failures are logged and treated
 * as non-fatal — i18next's ``fallbackLng: 'en'`` keeps the UI usable.
 */
export async function loadLocaleResource(code: string): Promise<void> {
  if (loadedLocales.has(code)) return;
  if (!SUPPORTED_LANGUAGES.some((l) => l.code === code)) return;
  try {
    const mod = await import(`./locales/${code}.ts`);
    const resource = (mod.default ?? mod) as { translation: Record<string, string> };
    // ``deep=false`` keeps the resource bundle as a flat dictionary —
    // critical because every locale file ships dotted keys like
    // ``"match_elements.title"`` and a deep merge auto-nests them under
    // ``match_elements.title``, which then can't be found by the flat
    // lookup the rest of the app expects (and breaks Header/Sidebar
    // translations for any locale loaded after init).
    i18n.addResourceBundle(code, 'translation', resource.translation, false, true);
    loadedLocales.add(code);
    // Force every ``useTranslation`` subscriber to re-render with the
    // freshly merged bundle. ``addResourceBundle`` already emits
    // ``store#added``, but components mounted outside Suspense (Header,
    // Sidebar) sometimes miss that event when StrictMode re-mounts them
    // mid-flight. Explicitly re-emitting ``languageChanged`` is the
    // signal react-i18next listens to unconditionally — every
    // useTranslation hook re-resolves its t() and re-renders.
    if (i18n.language === code) {
      i18n.emit('languageChanged', code);
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn(`i18n: failed to load locale "${code}", falling back to English`, err);
  }
}

/**
 * Switch the active UI language, guaranteeing its strings are registered
 * *before* the switch is announced. Use this from every language switcher.
 *
 * A bare ``i18n.changeLanguage(code)`` flips i18next to the new language
 * synchronously, but the per-locale chunk is lazy-loaded — so at that instant
 * the store holds no strings for ``code`` and every ``t()`` resolves through
 * the English ``fallbackLng``. The UI then depends on the async chunk landing
 * and firing a *second* re-render to recover, which flashes English and, under
 * StrictMode's mount churn, can be missed entirely (the "lazy-locale Header
 * race") — leaving the interface in English until a manual reload.
 *
 * Loading the chunk first means ``changeLanguage`` emits ``languageChanged``
 * with the resources already in the store, so every ``useTranslation``
 * subscriber re-renders straight into the target language. This mirrors the
 * load-then-switch order already used by ``usePartnerPackLocale``.
 *
 * ``loadLocaleResource`` is idempotent, so re-selecting a loaded language just
 * runs the cheap ``changeLanguage`` call. Failures inside ``loadLocaleResource``
 * are swallowed there (English fallback), so the switch still proceeds.
 */
export async function changeLanguage(code: string): Promise<void> {
  await loadLocaleResource(code);
  await i18n.changeLanguage(code);
}

export function applyModuleTranslations(
  moduleId: string,
  translations: Record<string, Record<string, string>>,
) {
  moduleTranslations[moduleId] = translations;
  // Merge into i18next
  for (const [lng, keys] of Object.entries(translations)) {
    if (keys && typeof keys === 'object') {
      i18n.addResourceBundle(lng, 'translation', keys, true, true);
    }
  }
}

/**
 * Resolve the initial UI language.
 *
 * Priority chain (first match wins):
 *   1. ``?lang=`` URL query param (validated against ``SUPPORTED_LANGUAGES``).
 *      If valid we also persist it to ``localStorage`` so the choice survives
 *      a refresh after the param is dropped from the URL.
 *   2. ``localStorage`` (``i18nextLng`` key) — last user choice.
 *   3. ``navigator.language`` — best-effort browser default.
 *   4. ``'en'`` — final fallback.
 *
 * SSR-safe: every ``window`` / ``localStorage`` / ``navigator`` access is
 * guarded so the function returns ``'en'`` when called outside a browser.
 */
function resolveInitialLanguage(): string {
  const supported = SUPPORTED_LANGUAGES.map((l) => l.code);
  const isValid = (code: string | null | undefined): code is string =>
    !!code && supported.includes(code);

  if (typeof window === 'undefined') return 'en';

  // 1. URL ?lang= param wins — useful for shareable localised links.
  try {
    const urlLang = new URLSearchParams(window.location.search).get('lang');
    if (isValid(urlLang)) {
      try {
        window.localStorage.setItem('i18nextLng', urlLang);
      } catch {
        // localStorage unavailable (private browsing) — non-fatal.
      }
      return urlLang;
    }
  } catch {
    // URL parsing failure — fall through to next source.
  }

  // 2. Stored preference from a previous session.
  try {
    const stored = window.localStorage.getItem('i18nextLng');
    if (isValid(stored)) return stored;
  } catch {
    // localStorage unavailable — fall through.
  }

  // 3. Browser locale (strip region: "de-CH" → "de").
  const browserLang = (navigator.language || 'en').split('-')[0];
  if (isValid(browserLang)) return browserLang;

  // 4. Final fallback.
  return 'en';
}

const initialLanguage = resolveInitialLanguage();

i18n
  .use(initReactI18next)
  .init({
    // Initialize synchronously: every resource this init needs is already in
    // memory (the bundled EN object), so deferring init to a timer only opens
    // a boot window where ``t()`` echoes raw keys. With sync init the store
    // is ready the moment this module finishes evaluating, which the
    // ``initialLocaleReady`` mount gate below relies on.
    initImmediate: false,
    // Only English is bundled synchronously — every other locale is
    // lazy-loaded by ``loadLocaleResource`` below. ``fallbackLng: 'en'``
    // means missing keys (e.g. while the locale chunk is still in
    // flight) render in English instead of as raw key strings.
    resources: { en: enResource },
    lng: initialLanguage,
    // The regional variants fall back to their own language before English, so
    // a key not localised for Chile shows Spanish rather than English. That is
    // what lets those files carry only the words that actually differ.
    //
    // en-US needs no line of its own. i18next resolves a two-part code through
    // ['en-US', 'en'] before it ever consults this map, and the `default` branch
    // below names the same fallback again, so a key absent from en-US.ts is
    // answered by en.ts either way. Asserted in enUSFallsBackToEnglish.test.ts
    // rather than assumed, because a missing key and a resolved one look alike
    // on screen when every call site passes a defaultValue.
    fallbackLng: {
      'es-MX': ['es', 'en'],
      'es-CL': ['es', 'en'],
      'es-CO': ['es', 'en'],
      'pt-BR': ['pt', 'en'],
      default: ['en'],
    },
    // All translation keys are stored as flat strings with literal dots
    // (e.g. "match_elements.title"). Disable the dot-as-namespace
    // separator so lookups don't try to walk a nested object path that
    // doesn't exist in the resource shape. Without this, keys lazy-loaded
    // via ``addResourceBundle(..., deep=true)`` get auto-nested and become
    // unreachable from headers/sidebars rendered before the chunk arrives,
    // while the synchronously bundled EN resource stays flat — yielding a
    // silent EN-only fallback for every dotted key once a non-EN locale
    // is active.
    keySeparator: false,
    nsSeparator: false,
    interpolation: {
      escapeValue: false,
    },
    react: {
      useSuspense: false,
      // Re-render useTranslation subscribers on a language switch AND when a
      // lazily loaded bundle finishes loading. ``languageChanged`` is the
      // react-i18next default; ``loaded`` additionally covers a locale chunk
      // that resolves right after the switch. Together with
      // ``bindI18nStore: 'added'`` below (fired by ``addResourceBundle``) this
      // guarantees a re-render however the strings arrive.
      bindI18n: 'languageChanged loaded',
      // Re-render useTranslation subscribers when a resource bundle is
      // added (e.g. when a non-EN locale chunk lazy-loads via
      // ``loadLocaleResource``). Without this, components rendered
      // before the chunk arrives (Header, Sidebar) stay stuck on the
      // English fallback for their lifetime — visible only for keys
      // first painted by such early components, since later-mounting
      // components re-render naturally on every state change.
      bindI18nStore: 'added',
    },
  });

// Persist language choice to localStorage so it survives page reloads,
// AND fetch the corresponding locale chunk if it isn't loaded yet.
i18n.on('languageChanged', (lng) => {
  try {
    localStorage.setItem('i18nextLng', lng);
  } catch {
    // localStorage not available (private browsing, etc.)
  }
  // Fire-and-forget; i18next will trigger a re-render when addResourceBundle
  // resolves. UI flashes English for the in-flight ms then re-paints.
  void loadLocaleResource(lng);
});

/**
 * Resolves once the resources of the *initial* language are in the store,
 * or ``null`` when there is nothing to wait for (English boot).
 *
 * i18next starts with only the bundled English resource; the active locale
 * arrives in a lazy chunk. Merely kicking that fetch off (`void load...`)
 * loses the race against React's first paint every single time — the first
 * frame of every non-English session rendered in English, whatever the cache
 * state, because the paint is synchronous and the chunk resolve never is.
 * ``main.tsx`` therefore awaits this promise (with a hard time cap so a
 * stalled fetch cannot hold the mount hostage) before mounting the app, so
 * the first frame already speaks the saved language.
 *
 * ``loadLocaleResource`` swallows its own failures (English fallback), so
 * this promise always resolves; it never rejects and never blocks forever.
 * The English path stays fully synchronous: no promise, no waiting.
 */
export const initialLocaleReady: Promise<void> | null =
  initialLanguage !== 'en' ? loadLocaleResource(initialLanguage) : null;

// Merge module-bundled translations (nav keys for regional modules, etc.)
import { getModuleTranslations } from '@/modules/_registry';
const moduleTrans = getModuleTranslations();
for (const [lng, keys] of Object.entries(moduleTrans)) {
  if (keys && typeof keys === 'object') {
    i18n.addResourceBundle(lng, 'translation', keys, true, true);
  }
}

export default i18n;
