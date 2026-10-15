import path from 'path';
import { readdirSync, readFileSync } from 'fs';
import * as nodeModule from 'node:module';
import type { Plugin } from 'vite';

// Production-only packing of the per-language catalogues.
//
// Every non-English catalogue is a flat dictionary of about 58 000 dotted keys,
// and the key strings are the same in all 40-odd files. Deflate compresses each
// file on its own, so the wheel and the Docker image carried those key strings
// once per language: roughly 310 KiB compressed per catalogue, 13 MiB across
// the lot, which is most of what pushed the 18.6.0 wheel to 99.4 MiB against the
// 100 MiB PyPI per-file cap.
//
// This plugin keeps the keys in one shared chunk (``i18n-idx``) and rewrites
// every catalogue to an array of values aligned to that key list, with null for
// a key the language does not define. The rewritten module rebuilds exactly the
// same ``{ translation: { key: value } }`` object at load time, so
// ``loadLocaleChunk`` in src/app/i18n.ts reads it unchanged. English is not
// touched: it ships in the main bundle and holds the keys the others are
// measured against. ``mn`` is not a shipped language and has no chunk.
//
// ``apply: 'build'`` on purpose: the dev server and vitest keep reading the
// source files verbatim, which is what the locale tests assert against.

const KEYS_ID = 'virtual:locale-keys';
const RESOLVED_KEYS_ID = '\0' + KEYS_ID;
const LOCALE_FILE = /[\\/]src[\\/]app[\\/]locales[\\/]([a-z]{2,3}(?:-[A-Z]{2})?)\.ts$/;
const SKIPPED = new Set(['en', 'mn']);

type Catalogue = Record<string, string>;

/** Chunk name for the shared key list. Three letters so the ``i18n-xxx-hash.js``
 * patterns in vite.config.ts (precache ignore, runtime cache lane) cover it. */
export const LOCALE_KEYS_CHUNK = 'i18n-idx';

export function isPackedLocaleId(id: string): boolean {
  const match = id.match(LOCALE_FILE);
  return match !== null && !SKIPPED.has(match[1]!);
}

export function isLocaleKeysId(id: string): boolean {
  return id === RESOLVED_KEYS_ID;
}

// Type erasure goes through node:module rather than esbuild. Measured on the
// 58 000 key catalogues, esbuild's transform took 30 to 50 seconds per file and
// this takes about 0.3, and the catalogues only use erasable syntax (one ``as``
// cast). The typing is local because the installed @types/node may predate it.
const stripTypes = (nodeModule as unknown as { stripTypeScriptTypes: (code: string) => string })
  .stripTypeScriptTypes;

function readCatalogue(file: string): Catalogue {
  const source = readFileSync(file, 'utf8');
  const exportDefault = /export default (\w+);\s*$/m;
  if (!exportDefault.test(source)) {
    throw new Error(`locale-key-index: ${file} does not end in "export default <name>;"`);
  }
  const code = stripTypes(source).replace(exportDefault, 'module.exports = { default: $1 };');
  const module: { exports: { default?: { translation?: Catalogue } } } = { exports: {} };
  new Function('module', 'exports', code)(module, module.exports);
  const translation = module.exports.default?.translation;
  if (!translation || typeof translation !== 'object') {
    throw new Error(`locale-key-index: ${file} has no default export with a translation object`);
  }
  for (const [key, value] of Object.entries(translation)) {
    if (typeof value !== 'string') {
      throw new Error(`locale-key-index: ${file} key "${key}" is not a string, cannot pack it`);
    }
  }
  return translation;
}

/** Pure packing step, exported so it can be exercised without a build. */
export function packCatalogue(keys: string[], translation: Catalogue): string {
  const index = new Map(keys.map((k, i) => [k, i] as const));
  const values: Array<string | null> = new Array(keys.length).fill(null);
  for (const [key, value] of Object.entries(translation)) {
    values[index.get(key)!] = value;
  }
  while (values.length > 0 && values[values.length - 1] === null) values.pop();
  return [
    `import K from '${KEYS_ID}';`,
    `const V = ${JSON.stringify(values)};`,
    'const translation = {};',
    'for (let i = 0; i < V.length; i++) { if (V[i] !== null) translation[K[i]] = V[i]; }',
    'export default { translation };',
    '',
  ].join('\n');
}

export function localeKeyIndex(root: string): Plugin {
  const localesDir = path.resolve(root, 'src/app/locales');
  let catalogues: Map<string, Catalogue> | null = null;
  let keys: string[] = [];

  return {
    name: 'locale-key-index',
    apply: 'build',
    enforce: 'pre',
    buildStart() {
      const loaded = new Map<string, Catalogue>();
      const union = new Set<string>();
      for (const name of readdirSync(localesDir).sort()) {
        const file = path.join(localesDir, name);
        if (!isPackedLocaleId(file)) continue;
        const translation = readCatalogue(file);
        loaded.set(path.normalize(file), translation);
        for (const key of Object.keys(translation)) union.add(key);
      }
      catalogues = loaded;
      keys = [...union].sort();
    },
    resolveId(id) {
      return id === KEYS_ID ? RESOLVED_KEYS_ID : null;
    },
    load(id) {
      return id === RESOLVED_KEYS_ID ? `export default ${JSON.stringify(keys)};` : null;
    },
    transform(_code, id) {
      if (!isPackedLocaleId(id) || catalogues === null) return null;
      const translation = catalogues.get(path.normalize(id.split('?')[0]!));
      if (!translation) return null;
      return { code: packCatalogue(keys, translation), map: null };
    },
  };
}
