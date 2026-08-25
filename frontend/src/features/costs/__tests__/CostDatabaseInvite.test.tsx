// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The cost-database invitation is the first thing a new estimator meets on
 * /costs, and the same prompt the dashboard shows while nothing is imported.
 * These tests hold the decisions that make it an invitation rather than an
 * error report: it says what a cost database is for before it says what to
 * press, it hands the user the importer, and it carries no warning colour,
 * no warning icon and no exclamation mark.
 *
 * Run: npx vitest run src/features/costs/__tests__/CostDatabaseInvite.test.tsx
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CostDatabaseInvite } from '../CostDatabaseInvite';

describe('CostDatabaseInvite', () => {
  it('opens with what a cost database is for, then the action', () => {
    render(<CostDatabaseInvite onImport={() => undefined} onCreateOwn={() => undefined} />);

    expect(screen.getByText('Start your cost database')).toBeInTheDocument();
    expect(
      screen.getByText(/holds the unit rates you price work with/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /import a database/i }),
    ).toBeInTheDocument();
  });

  it('says what the import leaves behind', () => {
    render(<CostDatabaseInvite onImport={() => undefined} />);

    expect(
      screen.getByText(/its rates are searchable here/i),
    ).toBeInTheDocument();
  });

  it('routes both paths to their existing flows', () => {
    const onImport = vi.fn();
    const onCreateOwn = vi.fn();
    render(<CostDatabaseInvite onImport={onImport} onCreateOwn={onCreateOwn} />);

    fireEvent.click(screen.getByRole('button', { name: /import a database/i }));
    expect(onImport).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /add your first rate/i }));
    expect(onCreateOwn).toHaveBeenCalledTimes(1);
  });

  it('offers the second path only when the caller can serve it', () => {
    render(<CostDatabaseInvite onImport={() => undefined} />);

    expect(screen.queryByRole('button', { name: /add your first rate/i })).toBeNull();
  });

  it('carries a single action in the compact band', () => {
    const onImport = vi.fn();
    render(<CostDatabaseInvite variant="compact" onImport={onImport} />);

    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: /import a database/i }));
    expect(onImport).toHaveBeenCalledTimes(1);
  });

  it.each(['page', 'compact'] as const)(
    'reads as an invitation, not as a problem (%s)',
    (variant) => {
      const { container } = render(
        <CostDatabaseInvite
          variant={variant}
          onImport={() => undefined}
          onCreateOwn={() => undefined}
        />,
      );

      const text = container.textContent ?? '';
      expect(text).not.toMatch(/!/);
      expect(text).not.toMatch(/no data|not found|no database|nothing here|empty/i);

      // No warning or error surface anywhere in the tree. An empty state is
      // not an alert, and a tint borrowed from the alert palette says it is.
      expect(
        container.querySelectorAll(
          '[class*="semantic-warning"], [class*="semantic-error"], [class*="amber"], [class*="red-"], [class*="orange"]',
        ),
      ).toHaveLength(0);
    },
  );
});
