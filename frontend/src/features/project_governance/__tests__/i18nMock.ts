// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// A `t` that reads the real English locale, so a component test sees the
// words a reader sees and fails on a key that is missing from en.ts (it then
// renders the bare key, which no assertion on English text will match).

import en from '@/app/locales/en';

const table = en.translation;

export function enT(key: string, opts?: Record<string, unknown>): string {
  let text: string | undefined;
  if (opts && typeof opts.count === 'number') {
    text = table[`${key}_${opts.count === 1 ? 'one' : 'other'}`];
  }
  text = text ?? table[key];
  if (text === undefined) return key;
  for (const [k, v] of Object.entries(opts ?? {})) {
    if (k === 'defaultValue') continue;
    text = text.split(`{{${k}}}`).join(String(v));
  }
  return text;
}

export const i18nMockModule = {
  useTranslation: () => ({
    t: enT,
    i18n: { language: 'en', exists: (k: string) => k in table },
  }),
  initReactI18next: { type: '3rdParty', init: () => undefined },
  Trans: ({ children }: { children?: unknown }) => children ?? null,
};
