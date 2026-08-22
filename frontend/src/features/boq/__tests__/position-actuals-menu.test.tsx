// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Right click a position, open the position actuals panel.
 *
 * This does not cover the panel, which has its own tests next to it in
 * features/costmodel. It covers the WIRING, and it exists because that wiring
 * lives in BOQGrid.tsx and BOQEditorPage.tsx, two files several agents edit at
 * once. The prop, the menu entry and the handler are four small additive hunks
 * sitting beside other people's four small additive hunks, which is exactly
 * the shape of change that a merge drops silently: nothing fails to compile,
 * no other test notices, and the menu item is simply gone.
 *
 * So the assertions are deliberately about the seam rather than the feature.
 * If someone's rebase eats the CtxItem, the prop or the id it passes, one of
 * these fails and names which.
 */
import { describe, it, expect, vi, beforeAll, afterEach } from 'vitest';
import { render, cleanup, fireEvent, act } from '@testing-library/react';
import { createElement } from 'react';

import BOQGrid from '../BOQGrid';
import type { Position } from '../api';

vi.mock('@/features/collab_locks', () => ({
  acquireLock: vi.fn(async () => ({ ok: true, lock: { id: 'lock-test' } })),
  releaseLock: vi.fn(async () => undefined),
}));

// jsdom has no layout: AG Grid sizes its viewport from client rects, so give
// every element a viewport-sized box or the grid renders zero rows and the
// test passes for the wrong reason.
beforeAll(() => {
  for (const prop of ['clientHeight', 'offsetHeight'] as const) {
    Object.defineProperty(HTMLElement.prototype, prop, { configurable: true, get: () => 800 });
  }
  for (const prop of ['clientWidth', 'offsetWidth'] as const) {
    Object.defineProperty(HTMLElement.prototype, prop, { configurable: true, get: () => 1600 });
  }
  HTMLElement.prototype.getBoundingClientRect = function () {
    return {
      width: 1600, height: 800, top: 0, left: 0, bottom: 800, right: 1600,
      x: 0, y: 0, toJSON: () => ({}),
    } as DOMRect;
  };
  Object.defineProperty(HTMLElement.prototype, 'offsetParent', {
    configurable: true,
    get() { return this.parentElement; },
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function makePosition(n: number): Position {
  return {
    id: `pos-${n}`,
    boq_id: 'boq-1',
    ordinal: `01.0${n}`,
    description: `Position ${n}`,
    unit: 'm2',
    quantity: 10 + n,
    unit_rate: 5 + n,
    total: (10 + n) * (5 + n),
    parent_id: null,
    position_type: 'position',
    validation_status: 'valid',
    metadata: {},
  } as unknown as Position;
}

const noop = () => undefined;

function renderGrid(overrides: Record<string, unknown> = {}) {
  return render(
    createElement(BOQGrid, {
      positions: [makePosition(1), makePosition(2), makePosition(3)],
      onUpdatePosition: noop,
      onDeletePosition: noop,
      onAddPosition: noop,
      onSelectSuggestion: noop,
      onSaveToDatabase: noop,
      onFormulaApplied: noop,
      collapsedSections: new Set<string>(),
      onToggleSection: noop,
      currencySymbol: '€',
      currencyCode: 'EUR',
      locale: 'en-US',
      footerRows: [],
      ...overrides,
    }),
  );
}

async function flush(ms = 0) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

async function waitUntil(cond: () => boolean, what: string, timeoutMs = 4000) {
  const t0 = Date.now();
  while (!cond()) {
    if (Date.now() - t0 > timeoutMs) throw new Error(`timed out waiting for: ${what}`);
    await flush(25);
  }
}

/** Right click the description cell of a position row. */
async function openContextMenu(rowId: string) {
  const el = document.querySelector<HTMLElement>(
    `.ag-row[row-id="${rowId}"] .ag-cell[col-id="description"]`,
  );
  if (!el) throw new Error(`row ${rowId} not rendered`);
  await act(async () => {
    fireEvent.contextMenu(el);
  });
  await flush(25);
}

/**
 * The menu entry, found by its i18n KEY as well as its English text.
 *
 * The key is what renders when i18next has no bundle loaded, which is the
 * case in this harness, and the English is what renders when it does. Matching
 * either keeps the test about whether the entry EXISTS rather than about which
 * i18n state the runner happened to be in. It deliberately does not accept a
 * defaultValue spelling, because this key carries none by design.
 */
function actualsMenuItem(): HTMLElement | undefined {
  const wanted = ['boq.position_actuals', 'Position actuals'];
  return Array.from(document.querySelectorAll<HTMLElement>('button, [role="menuitem"], div'))
    .filter((el) => el.children.length === 0 || el.tagName === 'BUTTON')
    .find((el) => wanted.includes((el.textContent ?? '').trim()));
}

describe('BOQ position context menu, position actuals entry', () => {
  it('offers the entry and hands the clicked position id to the handler', async () => {
    const onShowPositionActuals = vi.fn();
    renderGrid({ onShowPositionActuals });
    await waitUntil(
      () => !!document.querySelector('.ag-row[row-id="pos-2"]'),
      'grid rows to render',
    );

    await openContextMenu('pos-2');
    const item = actualsMenuItem();
    expect(item, 'position actuals entry missing from the context menu').toBeTruthy();

    await act(async () => {
      fireEvent.click(item!);
    });

    // The id matters as much as the click: the panel is opened BY id, and a
    // wiring that passes the wrong row opens a confidently wrong drawer.
    expect(onShowPositionActuals).toHaveBeenCalledTimes(1);
    expect(onShowPositionActuals).toHaveBeenCalledWith('pos-2');
  });

  it('hides the entry when no handler is supplied', async () => {
    // Same graceful degrade as the copilot and price-analysis entries beside
    // it. This is the negative half: without it, an entry rendered
    // unconditionally would pass the test above and then throw on a page that
    // does not pass the prop.
    renderGrid();
    await waitUntil(
      () => !!document.querySelector('.ag-row[row-id="pos-2"]'),
      'grid rows to render',
    );

    await openContextMenu('pos-2');
    expect(actualsMenuItem()).toBeFalsy();
  });
});
