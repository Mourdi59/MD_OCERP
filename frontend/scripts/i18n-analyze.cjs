// Analyze locale: count truly missing vs identical-to-EN vs translated (any non-identical)
//
// The percentages this prints are coverage of the en.ts keyspace. That is not
// the same as coverage of the locale file: every locale also carries keys en.ts
// does not, because the English for the case playbooks and the module guides
// lives inline in source as a t() defaultValue rather than in a locale file.
// The summary names that count separately so a number is never printed without
// saying what it counts.
//
// The extractor below is kept byte identical with the copy in i18n-diff.cjs.
// Change one and change the other in the same edit: the two are one parser with
// two homes, and a fix applied to only one of them is how a locale gate has
// silently diverged from its twin before.
const fs = require('fs');
const path = require('path');

/**
 * Read one string literal out of `src` starting at `src[p]`, which must be a
 * quote character, and return the decoded value plus the index just past the
 * closing quote.
 *
 * The value is decoded rather than sliced raw because a locale file may spell
 * the same string two ways. en.ts holds
 *   'No steps match "{{query}}"'
 * in single quotes so the embedded double quotes need no escape, while every
 * other locale writes that same text double quoted as
 *   "No steps match \"{{query}}\""
 * Compared as raw source those two differ, and the English-equal check would
 * then call an untranslated string translated. Comparing decoded text is what
 * makes the check mean what it says.
 */
function readStringLiteral(src, p) {
  const quote = src[p];
  p++;
  let out = '';
  while (p < src.length) {
    const c = src[p];
    if (c === '\\') {
      const esc = src[p + 1];
      p += 2;
      if (esc === 'n') out += '\n';
      else if (esc === 't') out += '\t';
      else if (esc === 'r') out += '\r';
      else if (esc === 'b') out += '\b';
      else if (esc === 'f') out += '\f';
      else if (esc === 'v') out += '\v';
      else if (esc === '\n') continue;
      else if (esc === 'x') {
        out += String.fromCharCode(parseInt(src.slice(p, p + 2), 16));
        p += 2;
      } else if (esc === 'u') {
        if (src[p] === '{') {
          const end = src.indexOf('}', p);
          out += String.fromCodePoint(parseInt(src.slice(p + 1, end), 16));
          p = end + 1;
        } else {
          out += String.fromCharCode(parseInt(src.slice(p, p + 4), 16));
          p += 4;
        }
      } else out += esc;
      continue;
    }
    if (c === quote) return { value: out, next: p + 1 };
    out += c;
    p++;
  }
  return { value: out, next: p };
}

/** Every character JavaScript accepts as the start of a string literal. */
const QUOTES = '"\'`';

/**
 * Advance past whitespace, separating commas and comments.
 *
 * The translation block is not pure data: en.ts carries 130 comment lines
 * inside it, grouping the keys by feature. Nine of those comments contain a
 * quote character, in prose such as
 *   // --- Module "Show more" expansion copy (intro_more) for pages whose
 *   // --- Header: What's-new / News button + popover ---
 * A parser that does not know about comments reads those quotes as the start of
 * a key or a string, loses its place, and drops every pair until it happens to
 * resynchronise. That is what hid the whole intro_more group.
 */
function skipTrivia(src, p) {
  for (;;) {
    while (p < src.length && /[\s,]/.test(src[p])) p++;
    if (src[p] === '/' && src[p + 1] === '/') {
      const nl = src.indexOf('\n', p);
      p = nl === -1 ? src.length : nl + 1;
      continue;
    }
    if (src[p] === '/' && src[p + 1] === '*') {
      const end = src.indexOf('*/', p + 2);
      p = end === -1 ? src.length : end + 2;
      continue;
    }
    return p;
  }
}

/**
 * Parse the flat `"translation": { ... }` block of a locale file into a plain
 * key to string map.
 *
 * A locale file is one level deep: dotted keys mapped to string values. Two
 * things in that block are not plain double-quoted data, and an earlier version
 * of this parser mishandled both, between them hiding 27 keys of en.ts from
 * every coverage report this script produced:
 *
 *   1. Comments, some of which contain quote characters. See skipTrivia above.
 *   2. Values written in single quotes because the text itself contains a
 *      double quote. Only the double quote used to open a string here, so such
 *      a value fell into the skip-this-pair branch below.
 */
function extractResource(filePath) {
  const src = fs.readFileSync(filePath, 'utf8');
  const startMarker = '"translation": {';
  const startIdx = src.indexOf(startMarker);
  if (startIdx < 0) throw new Error('translation block not found in ' + filePath);
  let i = startIdx + startMarker.length;
  const startBody = i;
  let depth = 1;
  while (i < src.length && depth > 0) {
    const c = src[i];
    if (c === '/' && (src[i + 1] === '/' || src[i + 1] === '*')) {
      i = skipTrivia(src, i);
      continue;
    }
    if (QUOTES.includes(c)) {
      i = readStringLiteral(src, i).next;
      continue;
    }
    if (c === '{') depth++;
    else if (c === '}') depth--;
    i++;
  }
  const body = src.slice(startBody, i - 1);

  const pairs = {};
  let p = 0;
  while (p < body.length) {
    p = skipTrivia(body, p);
    if (p >= body.length) break;
    if (!QUOTES.includes(body[p])) {
      p++;
      continue;
    }
    const k = readStringLiteral(body, p);
    p = skipTrivia(body, k.next);
    if (body[p] === ':') p = skipTrivia(body, p + 1);
    if (!QUOTES.includes(body[p])) {
      // Not a string value (an object, an array, a number). Skip the whole pair
      // by scanning to the next comma that sits outside any bracket.
      let nested = 0;
      while (p < body.length) {
        const c = body[p];
        if (c === '{' || c === '[') nested++;
        else if (c === '}' || c === ']') nested--;
        else if (c === ',' && nested === 0) break;
        p++;
      }
      continue;
    }
    const v = readStringLiteral(body, p);
    pairs[k.value] = v.value;
    p = v.next;
  }
  return pairs;
}

const locale = process.argv[2];
const mode = process.argv[3] || 'summary';
const en = extractResource(path.join(__dirname, '..', 'src', 'app', 'locales', 'en.ts'));
const t = extractResource(path.join(__dirname, '..', 'src', 'app', 'locales', `${locale}.ts`));

const missing = [];
const identical = [];
const translated = [];
for (const k of Object.keys(en)) {
  if (!(k in t)) missing.push(k);
  else if (t[k] === en[k]) identical.push(k);
  else translated.push(k);
}
// Keys the locale carries that en.ts does not. Nothing above measures these,
// so they are reported on their own line rather than folded into a percentage.
const outsideBase = Object.keys(t).filter((k) => !(k in en));
const total = Object.keys(en).length;

if (mode === 'list-missing') {
  for (const k of missing) console.log(JSON.stringify({ key: k, en: en[k] }));
} else if (mode === 'list-identical') {
  for (const k of identical) console.log(JSON.stringify({ key: k, en: en[k] }));
} else if (mode === 'list-needs') {
  // both missing AND identical need work
  for (const k of [...missing, ...identical]) console.log(JSON.stringify({ key: k, en: en[k] }));
} else if (mode === 'list-outside-base') {
  for (const k of outsideBase) console.log(k);
} else {
  console.log(`Locale: ${locale}`);
  console.log(`Base: en.ts, ${total} keys. Every percentage below is of that base.`);
  console.log(`Translated (different from EN): ${translated.length} (${(translated.length / total * 100).toFixed(2)}% of base)`);
  console.log(`Identical to EN (likely untranslated): ${identical.length}`);
  console.log(`Missing in locale: ${missing.length}`);
  console.log(`Need-to-translate: ${missing.length + identical.length}`);
  console.log(`Outside base: ${outsideBase.length} keys in ${locale}.ts that en.ts does not hold,`);
  console.log(`  English for those lives inline in source. Nothing above measures them.`);
  console.log(`Locale file holds ${Object.keys(t).length} keys in total.`);
}
