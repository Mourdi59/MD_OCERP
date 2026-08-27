// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Issue #439 - the GAEB Exchange module ships `navItems: []` with a comment
 * saying it is reached from /boq, and nothing in the BOQ workflow reached it.
 *
 * The entry point is an item at the foot of the BOQ editor's Export menu. What
 * matters is not that the item exists but that it carries the BOQ the editor
 * currently has open, so the target page does not have to ask again for
 * context the user already gave. Rendering it twice with different ids is what
 * separates a real hand-off from a hardcoded URL that happens to look right.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { BOQToolbar, type BOQToolbarProps } from '../BOQToolbar';

function stubT(key: string, options?: Record<string, string | number>): string {
  const fallback = options?.defaultValue;
  return typeof fallback === 'string' ? fallback : key;
}

function makeProps(overrides: Partial<BOQToolbarProps>): BOQToolbarProps {
  return {
    t: stubT,
    projectId: 'proj-alpha',
    boqId: 'boq-17',
    canUndo: false,
    canRedo: false,
    onUndo: vi.fn(),
    onRedo: vi.fn(),
    onShowVersionHistory: vi.fn(),
    onAddPosition: vi.fn(),
    onAddSection: vi.fn(),
    onOpenCostDb: vi.fn(),
    onOpenAssembly: vi.fn(),
    onImportClick: vi.fn(),
    isImporting: false,
    importInputRef: { current: null },
    onImportInputChange: vi.fn(),
    onExport: vi.fn(),
    onValidate: vi.fn(),
    onRecalculate: vi.fn(),
    isRecalculating: false,
    aiChatOpen: false,
    onToggleAiChat: vi.fn(),
    costFinderOpen: false,
    onToggleCostFinder: vi.fn(),
    smartPanelOpen: false,
    onToggleSmartPanel: vi.fn(),
    hasPositions: true,
    qualityScoreRing: null,
    summary: null,
    ...overrides,
  };
}

/** Renders the toolbar and opens the Export menu (portaled to document.body). */
function renderWithMenuOpen(overrides: Partial<BOQToolbarProps> = {}) {
  const view = render(
    <MemoryRouter>
      <BOQToolbar {...makeProps(overrides)} />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'boq.export' }));
  return view;
}

function gaebExchangeHref(): string | null {
  return screen.getByRole('menuitem', { name: /GAEB Exchange/ }).getAttribute('href');
}

describe('BOQ editor export menu - GAEB Exchange entry point', () => {
  it('hands the open project and BOQ to the GAEB Exchange module', () => {
    renderWithMenuOpen({ projectId: 'proj-alpha', boqId: 'boq-17' });

    expect(gaebExchangeHref()).toBe(
      '/gaeb-exchange?project_id=proj-alpha&boq_id=boq-17&tab=export',
    );
  });

  it('carries whichever BOQ is open, not a fixed link', () => {
    const first = renderWithMenuOpen({ projectId: 'proj-alpha', boqId: 'boq-17' });
    const firstHref = gaebExchangeHref();
    first.unmount();

    renderWithMenuOpen({ projectId: 'proj-beta', boqId: 'boq-99' });
    const secondHref = gaebExchangeHref();

    expect(secondHref).toBe(
      '/gaeb-exchange?project_id=proj-beta&boq_id=boq-99&tab=export',
    );
    expect(secondHref).not.toBe(firstHref);
  });

  it('leaves the existing one-click GAEB export in place', () => {
    const onExport = vi.fn();
    renderWithMenuOpen({ onExport });

    fireEvent.click(screen.getByRole('menuitem', { name: 'GAEB XML (.x83)' }));
    expect(onExport).toHaveBeenCalledWith('gaeb');
  });
});
