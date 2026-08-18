// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The change-order register may not print a sign the reader can lose.
//
// Measured on the published frame of `/changeorders`: the `+` of every cost
// impact sat on the line above its own figure. The browser was allowed to put
// it there because `+` and the currency symbol are both prefix-numeric and
// only one prefix may open an unbreakable numeric run - a rule about the
// characters on screen, which does not care whether the cell was written as
// `{x >= 0 ? '+' : ''}{formatCurrency(x, cur)}` or as a single call.
//
// Two things had to be true to close it, and neither can be seen from the
// formatter alone, so they are checked here against the source of the page:
//
//   * the element holding the figure says it may not be broken. This is the
//     one that closes the wrap, and it is needed even for a single string,
//     because a currency rendering carries a space of its own ("1.234,50 €");
//   * the sign comes out of the formatter rather than the page, so it lands
//     where the reader's language puts it - `signedMoneyIsOneNumber.test.ts`
//     covers what that string looks like, this file only checks that the page
//     asks for it.
//
// It reads the file rather than rendering the page because what is being
// asserted is a property of every signed-money cell on it, present and future,
// and mounting the register would prove it for whichever rows the fixture
// happens to hold. The same hand-written sign appears next to money on other
// screens (`/costmodel`, `/analytics`, the bill compare drawer); this file is
// deliberately scoped to the page that was measured rather than made into an
// app-wide gate that would be red on work nobody has done yet.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const PAGE = join(__dirname, 'ChangeOrdersPage.tsx');

/**
 * The file with its comments removed.
 *
 * The comment on `formatSignedCurrency` quotes the defective shape on purpose,
 * as the record of what went wrong. Scanning the raw text would read that
 * quotation as a live call site and fail on the documentation of the fix.
 */
function code(): string {
  return readFileSync(PAGE, 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^[ \t]*\/\/.*$/gm, '');
}

describe('a signed cost impact on the change-order register', () => {
  it('is never assembled from a hand-written sign and a separate figure', () => {
    // The exact shape that shipped: a ternary emitting a bare plus, with the
    // amount following as its own expression.
    expect(code()).not.toMatch(/\?\s*'\+'\s*:\s*''\s*\}\s*\{/);
  });

  it('asks the formatter for the sign', () => {
    // Whatever else changes, the register has to have at least one signed
    // amount, or the two assertions around this one are satisfied by a page
    // that stopped showing the sign at all.
    expect(code()).toContain('formatSignedCurrency(');
    expect(code().match(/\{formatSignedCurrency\(/g)?.length ?? 0).toBeGreaterThan(0);
  });

  it('renders every signed amount inside an element that cannot break it', () => {
    const source = code();
    const offenders: string[] = [];
    const call = /\{formatSignedCurrency\(/g;
    let match: RegExpExecArray | null;
    while ((match = call.exec(source)) !== null) {
      // The element the expression sits in: everything from the nearest
      // opening angle bracket up to the call itself. That window carries the
      // tag name and its className, which is where the rule has to be stated.
      const tagStart = source.lastIndexOf('<', match.index);
      const tag = source.slice(tagStart, match.index);
      if (!tag.includes('whitespace-nowrap')) {
        offenders.push(tag.split('\n')[0]!.trim().slice(0, 80));
      }
    }
    expect(offenders).toEqual([]);
  });
});
