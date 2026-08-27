// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The company honeycomb: the second subject the shared comb was generalised
// for, and the three things that generalisation could quietly get wrong.
//
//  1. THE TINT IS PER CELL. The module comb paints every cell in the one
//     discipline colour of the case it belongs to, and that was the only tint
//     the comb had ever been asked for. Company types each carry their own
//     colour everywhere else in the product, so a comb that painted them all
//     alike would be inventing a relationship the palette denies - and it
//     would still look deliberate. Two cells, two different tile classes.
//
//  2. THE CELLS ARE THE CASE'S OWN, AND ONLY THOSE. No ghost cells for the
//     company types a case was not written for: a hexagon nobody can act on
//     reads as disabled. The census belongs in the caption, in words, counted
//     against COMPANY_TYPE_META rather than against a number written here -
//     a literal would go on passing after a ninth company type shipped.
//
//  3. ACTIVATING A CELL LEADS SOMEWHERE REAL. It writes the hub's own
//     "I work as..." filter and opens the hub. Asserting the click alone
//     would pass for a button that navigated and narrowed nothing, which is
//     the state the reader would read as the filter being broken.
//
// Run: npx vitest run src/features/cases/companyHive.test.tsx --pool=forks

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { CaseCompanyHive } from './CompanyHive';
import { COMPANY_TYPE_BY_ID, COMPANY_TYPE_META } from './companyTypes';
import { companyThumbFor } from './caseFaces';
import { useCasesStore } from './useCasesStore';
import type { CompanyType, Playbook, PlaybookStep } from './types';

vi.mock('react-i18next', () => {
  const t = (key: string, opts?: Record<string, unknown>) => {
    if (typeof opts === 'object' && opts !== null && 'defaultValue' in opts) {
      // Mirror i18next's plural pick, so a test reads the form a user reads.
      const template =
        'count' in opts && opts.count !== 1 && typeof opts.defaultValue_other === 'string'
          ? opts.defaultValue_other
          : String(opts.defaultValue);
      return template.replace(/\{\{(\w+)\}\}/g, (_m, name: string) =>
        name in opts ? String(opts[name]) : `{{${name}}}`,
      );
    }
    return key;
  };
  return {
    useTranslation: () => ({ t, i18n: { language: 'en' } }),
    initReactI18next: { type: '3rdParty', init: () => {} },
  };
});

const navigateSpy = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual =
    await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateSpy };
});

/* ── Fixtures ─────────────────────────────────────────────────────────── */

const STEP: PlaybookStep = {
  id: 's1',
  to: '/boq',
  moduleLabel: 'BOQ',
  titleKey: 't.s1',
  titleDefault: 'Step',
  whatKey: 'w.s1',
  whatDefault: 'What',
  whyKey: 'y.s1',
  whyDefault: 'Why',
};

function playbook(companyTypes: CompanyType[]): Playbook {
  return {
    id: 'fixture',
    order: 1,
    category: 'estimating',
    companyTypes,
    titleKey: 'fixture.title',
    titleDefault: 'Fixture',
    descKey: 'fixture.desc',
    descDefault: 'Fixture case',
    estMinutes: 5,
    steps: [STEP],
  };
}

function renderHive(companyTypes: CompanyType[]) {
  return render(
    <MemoryRouter initialEntries={['/cases/fixture']}>
      <CaseCompanyHive playbook={playbook(companyTypes)} />
    </MemoryRouter>,
  );
}

/** The label a company type wears everywhere in the product. Read from the
 *  metadata rather than typed out, so renaming one does not leave a test
 *  asserting a name no user ever sees. */
function labelOf(id: CompanyType): string {
  return COMPANY_TYPE_BY_ID[id].labelDefault;
}

/** The accessible name of a cell, which is not the name printed on it.
 *  The drawing says the company; the accessible name says what activating it
 *  does, so a band of cells is not read out as a band of bare nouns. Written
 *  out in full rather than matched on the label alone: a name query that only
 *  had to contain the company would go on passing for a cell that had lost the
 *  phrase, and losing it is the defect `cases.card.company_filter` was put back
 *  on these cells to fix. Both halves stay pinned, because the printed name is
 *  asserted separately through getByText. */
function actionNameOf(id: CompanyType): string {
  return `Show cases for ${labelOf(id)}`;
}

beforeEach(() => {
  navigateSpy.mockClear();
  useCasesStore.setState({ companyTypes: [] });
  try {
    localStorage.clear();
  } catch {
    /* storage unavailable in this environment - the store tolerates it. */
  }
});

/* ── Tests ────────────────────────────────────────────────────────────── */

describe('CaseCompanyHive', () => {
  it('draws one cell per company type the case declares, and no others', () => {
    renderHive(['general-contractor', 'subcontractor']);

    expect(screen.getAllByRole('button')).toHaveLength(2);
    expect(screen.getByText(labelOf('general-contractor'))).toBeInTheDocument();
    expect(screen.getByText(labelOf('subcontractor'))).toBeInTheDocument();
    // The five the case was not written for are absent, not greyed out.
    expect(screen.queryByText(labelOf('owner-operator'))).not.toBeInTheDocument();
  });

  it('gives every cell its own colour rather than one comb-wide tint', () => {
    renderHive(['general-contractor', 'subcontractor']);

    const faceFor = (id: CompanyType) =>
      screen.getByRole('button', { name: actionNameOf(id) }).querySelector('span')?.className ?? '';

    const gc = faceFor('general-contractor');
    const sub = faceFor('subcontractor');
    expect(gc).toContain(COMPANY_TYPE_BY_ID['general-contractor'].tint.tile);
    expect(sub).toContain(COMPANY_TYPE_BY_ID['subcontractor'].tint.tile);
    expect(gc).not.toEqual(sub);
  });

  it('counts the case against the whole census, not a number written here', () => {
    renderHive(['general-contractor', 'subcontractor']);

    expect(
      screen.getByText(`2 of ${COMPANY_TYPE_META.length} company types`),
    ).toBeInTheDocument();
  });

  it('narrows the hub to that company AND opens it', () => {
    renderHive(['general-contractor', 'subcontractor']);

    screen.getByRole('button', { name: actionNameOf('subcontractor') }).click();

    expect(useCasesStore.getState().companyTypes).toEqual(['subcontractor']);
    expect(navigateSpy).toHaveBeenCalledWith('/cases');
  });

  it('puts the firm on its own cell', () => {
    renderHive(['general-contractor']);

    const img = screen
      .getByRole('button', { name: actionNameOf('general-contractor') })
      .querySelector('img');
    expect(img?.getAttribute('src')).toBe(companyThumbFor('general-contractor'));
    // Decorative: the label beside it is what a reader acts on.
    expect(img?.getAttribute('alt')).toBe('');
  });

  it('renders nothing for a case that names no company type', () => {
    const { container } = renderHive([]);
    expect(container).toBeEmptyDOMElement();
  });

  it('drops a company id that no longer exists instead of drawing a dead cell', () => {
    // A renamed id has no label, no colour and no hub filter to lead to.
    renderHive(['general-contractor', 'retired-company-type' as unknown as CompanyType]);

    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(
      screen.getByText(`1 of ${COMPANY_TYPE_META.length} company types`),
    ).toBeInTheDocument();
  });
});
