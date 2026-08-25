/**
 * Ask the TypeScript parser whether every locale bundle is well formed, and
 * whether any of them declares the same key twice.
 *
 * This exists because four separate i18n gates went green over a bundle with a
 * missing comma between two keys. Every one of them reads the locale as data,
 * with its own reader, and none of their readers cares about the separators
 * that hold the file together. They answer questions about the contents. The
 * question "can the thing that imports this actually load it" was answered by
 * nobody, because none of them is that importer.
 *
 * So this one does not bring its own parser. It uses the compiler's, which is
 * the only reader whose opinion decides whether the application starts.
 *
 * It is deliberately cheap. Parsing is not type checking, so this runs in about
 * a second over every bundle and can sit in front of a commit, where the real
 * build cannot.
 */

import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const here = dirname(fileURLToPath(import.meta.url));
// The argument exists so the gate can be aimed at a checkout of an older
// revision and shown to fail there. A gate that has only ever been seen green
// is a fact about the gate. It also means the output has to say what it read.
const localeDir = process.argv[2] ?? join(here, '..', 'src', 'app', 'locales');

const files = readdirSync(localeDir)
  .filter((f) => f.endsWith('.ts') && !f.endsWith('.test.ts'))
  .sort();

if (files.length === 0) {
  console.error('REFUSING: found no locale files, which is a fact about this script');
  process.exit(2);
}

/** Every string-or-identifier key declared in an object literal, with its line. */
function collectKeys(sourceFile) {
  const keys = [];
  const walk = (node) => {
    if (ts.isPropertyAssignment(node) || ts.isShorthandPropertyAssignment(node)) {
      const name = node.name;
      let text = null;
      if (ts.isStringLiteral(name) || ts.isNoSubstitutionTemplateLiteral(name)) text = name.text;
      else if (ts.isIdentifier(name)) text = name.text;
      if (text !== null) {
        const { line } = sourceFile.getLineAndCharacterOfPosition(name.getStart(sourceFile));
        keys.push({ text, line: line + 1, parent: node.parent });
      }
    }
    ts.forEachChild(node, walk);
  };
  walk(sourceFile);
  return keys;
}

let failed = 0;
let totalKeys = 0;

for (const file of files) {
  const path = join(localeDir, file);
  const text = readFileSync(path, 'utf8');
  const sourceFile = ts.createSourceFile(path, text, ts.ScriptTarget.ESNext, true, ts.ScriptKind.TS);

  // The parser records syntax errors here rather than throwing.
  const diagnostics = sourceFile.parseDiagnostics ?? [];
  if (diagnostics.length > 0) {
    failed += 1;
    console.error(`${file}: does not parse`);
    for (const d of diagnostics.slice(0, 5)) {
      const { line, character } = sourceFile.getLineAndCharacterOfPosition(d.start ?? 0);
      const message = ts.flattenDiagnosticMessageText(d.messageText, ' ');
      console.error(`  ${line + 1}:${character + 1}  ${message}`);
    }
    if (diagnostics.length > 5) {
      console.error(`  and ${diagnostics.length - 5} more`);
    }
    continue;
  }

  // A duplicate key is not a syntax error. The later one silently wins, so a
  // translation can be added, counted by every gate, and never reach a reader.
  const keys = collectKeys(sourceFile);
  totalKeys += keys.length;
  const seen = new Map();
  const duplicates = [];
  for (const k of keys) {
    const id = `${k.parent.pos}:${k.text}`;
    if (seen.has(id)) duplicates.push({ text: k.text, first: seen.get(id), again: k.line });
    else seen.set(id, k.line);
  }
  if (duplicates.length > 0) {
    failed += 1;
    console.error(`${file}: ${duplicates.length} key(s) declared twice in the same object`);
    for (const d of duplicates.slice(0, 10)) {
      console.error(`  ${d.text}  first at line ${d.first}, again at line ${d.again}`);
    }
    if (duplicates.length > 10) console.error(`  and ${duplicates.length - 10} more`);
  }
}

if (failed > 0) {
  console.error(`\n${failed} of ${files.length} locale bundles are not fit to import.`);
  process.exit(1);
}

console.log(
  `${files.length} locale bundles in ${localeDir} parse, ` +
    `${totalKeys.toLocaleString('en-US')} keys, no key declared twice.`,
);
