// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The cases block on the dashboard: the size it comes at, the way back out of
 * it, and the one contract it used to break.
 *
 * WHY A WAY OUT IS TESTED AT ALL. The block was made several times larger on
 * purpose. A block that grows and cannot be put back is worse than the small
 * one it replaced, so the controls that shrink and hide it are part of the
 * feature, not decoration on it - and they are only worth anything if they
 * write the preference the DASHBOARD already keeps. A private flag would look
 * identical on screen and be invisible to Customize, which is where a user who
 * hid the card goes looking for it. So these assert the store, not the click.
 *
 * WHY THE FACES ARE TESTED. `dealCaseFaces` documents that it must be dealt
 * over the WHOLE catalogue: the person a case wears is a property of where the
 * case sits among all cases, so a narrowed or windowed list must not re-cast
 * it. This card dealt over its own ranked window, which is exactly the thing
 * the helper warns against - the ranking reorders, so a case wore one person
 * here and a different one on the hub. The last test pins the fix with the
 * ranking deliberately reordered, because in catalogue order the bug and the
 * fix agree.
 *
 * Run: npx vitest run src/features/dashboard/__tests__/DashboardCasesCard.test.tsx
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { DashboardCasesCard } from '../DashboardCasesCard';
import { useDashboardLayoutStore } from '@/stores/useDashboardLayoutStore';
import { useCasesStore } from '@/features/cases/useCasesStore';
import { PLAYBOOKS } from '@/features/cases/playbooks';
import { dealCaseFaces } from '@/features/cases/caseFaces';

vi.mock('react-i18next', () => {
  const t = (key: string, opts?: Record<string, unknown>) => {
    if (typeof opts === 'object' && opts !== null && 'defaultValue' in opts) {
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

// The layout store PUTs its state back to the server on a debounce. Nothing
// here is about that round trip, and a request fired after the test finished
// would land in whatever ran next.
vi.mock('@/shared/lib/api', async () => {
  const actual =
    await vi.importActual<typeof import('@/shared/lib/api')>('@/shared/lib/api');
  return {
    ...actual,
    apiGet: vi.fn().mockResolvedValue({}),
    apiPut: vi.fn().mockResolvedValue({}),
  };
});

const WIDGET_ID = 'cases_learn';

/** The tiles in the gallery: the case tiles plus the one that opens the rest
 *  of the library. Counted off the grid itself rather than off `getAllByRole`,
 *  which would also collect the header's own buttons. */
function tileCount(): number {
  const card = screen.getByTestId('dashboard-cases-card');
  const grid = card.querySelector('div.grid');
  if (!grid) throw new Error('gallery grid not found');
  return grid.children.length;
}

function renderCard() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <DashboardCasesCard />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  navigateSpy.mockClear();
  useDashboardLayoutStore.setState({ order: [], hidden: [], spans: {} });
  useCasesStore.setState({ runs: {}, roles: [], companyTypes: [] });
});

describe('DashboardCasesCard size', () => {
  it('opens as a gallery of 23 cases plus the way into the rest', () => {
    renderCard();
    expect(tileCount()).toBe(24);
  });

  it('draws fewer, and fewer across, at a width the user saved earlier', () => {
    // What a reload looks like: the preference is already in the store before
    // the card mounts.
    useDashboardLayoutStore.setState({ spans: { [WIDGET_ID]: 2 } });
    renderCard();

    expect(tileCount()).toBe(9);
    const grid = screen.getByTestId('dashboard-cases-card').querySelector('div.grid');
    // The column count has to come off the same number as the tile count: the
    // grid's breakpoints are viewport-wide, so a third-width card asking for
    // six columns would draw six microscopic tiles on a wide screen.
    expect(grid?.className).toContain('sm:grid-cols-3');
    expect(grid?.className).not.toContain('xl:grid-cols-6');
  });
});

describe('DashboardCasesCard way out', () => {
  it('shrinks by writing the dashboard own width preference', () => {
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'Show this block smaller' }));

    // The value Customize shows and persists - not a private flag of this card.
    expect(useDashboardLayoutStore.getState().spans[WIDGET_ID]).toBe(4);
    expect(tileCount()).toBe(16);
  });

  it('grows back the same way', () => {
    useDashboardLayoutStore.setState({ spans: { [WIDGET_ID]: 3 } });
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'Show this block bigger' }));

    expect(useDashboardLayoutStore.getState().spans[WIDGET_ID]).toBe(4);
  });

  it('offers no control that would write a width the grid cannot draw', () => {
    // At full width there is nothing wider to go to, and the button for it
    // would set a span DashboardPage maps to nothing.
    const full = renderCard();
    expect(screen.queryByRole('button', { name: 'Show this block bigger' })).toBeNull();
    full.unmount();

    // And the mirror of it: at the narrowest width there is nothing narrower.
    useDashboardLayoutStore.setState({ spans: { [WIDGET_ID]: 2 } });
    renderCard();
    expect(screen.queryByRole('button', { name: 'Show this block smaller' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Show this block bigger' })).not.toBeNull();
  });

  it('hides into the dashboard own hidden set, and says where to find it again', () => {
    renderCard();
    const hide = screen.getByRole('button', {
      name: 'Hide this block. You can bring it back from Customize dashboard.',
    });
    // Named BEFORE the click: once hidden, the page stops rendering this card
    // and there is nothing left here to offer the way back.
    expect(hide.getAttribute('title')).toContain('Customize');

    fireEvent.click(hide);
    expect(useDashboardLayoutStore.getState().hidden).toContain(WIDGET_ID);
  });
});

describe('DashboardCasesCard faces', () => {
  it('gives a case the person it wears everywhere else, even when re-ranked', () => {
    // A role pushes matching cases to the front, so the gallery is no longer a
    // prefix of the catalogue. Dealt over the window, these tiles get faces
    // from their position in the WINDOW; dealt over the catalogue - which is
    // what the hub and the case page do - they keep their own.
    useCasesStore.setState({ roles: ['estimator'] });
    renderCard();

    const expected = dealCaseFaces(PLAYBOOKS);
    const byTitle = new Map(PLAYBOOKS.map((p) => [p.titleDefault, p]));
    const grid = screen.getByTestId('dashboard-cases-card').querySelector('div.grid');
    if (!grid) throw new Error('gallery grid not found');

    let checked = 0;
    for (const tile of Array.from(grid.children)) {
      const img = tile.querySelector('img');
      const title = tile.getAttribute('title');
      if (!img || !title) continue;
      const pb = byTitle.get(title);
      if (!pb) continue;
      expect(img.getAttribute('src')).toBe(expected.get(pb.id));
      checked += 1;
    }
    // Without this the loop is satisfied by a gallery that rendered no faces
    // at all, and the assertion above never runs.
    expect(checked).toBeGreaterThan(15);
  });
});
