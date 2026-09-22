// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Component tests for the optional preview source of <PopulatePreviewModal>.
//
// The modal previews claim lines from field progress, and the claim page's
// subcontractor panel reuses it for lines derived from the subs' approved
// amounts. What is worth pinning:
//
//   * left alone, the modal still asks field progress and nothing else, in
//     its own words;
//   * given a loader, it asks that loader only, with the caller's words;
//   * either way the commit goes through the one commit route, and the
//     success toast is the caller's when it gives one, the modal's otherwise.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('./api', () => ({
  populateClaimPreview: vi.fn(),
  commitClaimLines: vi.fn(),
}));

const addToast = vi.fn();
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: (sel: (s: { addToast: typeof addToast }) => unknown) => sel({ addToast }),
}));

import * as api from './api';
import type { ProgressClaimPopulatePreview } from './api';
import { PopulatePreviewModal } from './PopulatePreviewModal';

const populateMock = vi.mocked(api.populateClaimPreview);
const commitMock = vi.mocked(api.commitClaimLines);

function preview(over: Partial<ProgressClaimPopulatePreview> = {}): ProgressClaimPopulatePreview {
  return {
    claim_id: 'claim-1',
    contract_id: 'ctr-1',
    currency: 'USD',
    items: [
      {
        contract_line_id: 'line-1',
        contract_line_code: '03.10',
        contract_line_description: 'Footings',
        boq_position_id: 'pos-1',
        unit: null,
        contract_quantity: '1',
        contract_line_value: '10000',
        observed_pct: '20',
        period_label: null,
        recorded_at: null,
        period_completed_qty: '0',
        period_completed_value: '2000',
        cumulative_completed_value: '2000',
      },
    ],
    skipped_unlinked: 0,
    skipped_no_progress: 0,
    skipped_foreign_currency: 0,
    gross: '2000',
    retention: '0',
    prior_claims_total: '0',
    net_due: '2000',
    ...over,
  };
}

function renderModal(props: Partial<React.ComponentProps<typeof PopulatePreviewModal>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PopulatePreviewModal claimId="claim-1" currency="USD" onClose={vi.fn()} {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PopulatePreviewModal preview source', () => {
  it('asks field progress when no loader is given, in its own words', async () => {
    populateMock.mockResolvedValue(preview());
    renderModal();
    await waitFor(() => expect(screen.getByTestId('populate-preview-table')).toBeTruthy());
    expect(populateMock).toHaveBeenCalledWith('claim-1');
    expect(screen.getByText('Populate from progress observations')).toBeTruthy();
  });

  it('asks only the given loader, and shows the caller title and subtitle', async () => {
    const loader = vi.fn().mockResolvedValue(preview());
    renderModal({ loadPreview: loader, title: 'From the subs', subtitle: 'Approved amounts' });
    await waitFor(() => expect(screen.getByTestId('populate-preview-table')).toBeTruthy());
    expect(loader).toHaveBeenCalledWith('claim-1');
    expect(populateMock).not.toHaveBeenCalled();
    expect(screen.getByText('From the subs')).toBeTruthy();
    expect(screen.getByText('Approved amounts')).toBeTruthy();
    expect(screen.queryByText('Populate from progress observations')).toBeNull();
  });

  it('shows the caller empty text when the loader has nothing to suggest', async () => {
    const loader = vi.fn().mockResolvedValue(preview({ items: [] }));
    renderModal({ loadPreview: loader, emptyText: 'No sub lines yet' });
    await waitFor(() => expect(screen.getByTestId('populate-empty')).toBeTruthy());
    expect(screen.getByTestId('populate-empty').textContent).toContain('No sub lines yet');
  });

  it('commits a loaded preview through the same commit route', async () => {
    commitMock.mockResolvedValue({} as never);
    const loader = vi.fn().mockResolvedValue(preview());
    renderModal({ loadPreview: loader });
    await waitFor(() => expect(screen.getByTestId('populate-preview-table')).toBeTruthy());
    fireEvent.click(screen.getByText('Commit lines'));
    await waitFor(() =>
      expect(commitMock).toHaveBeenCalledWith('claim-1', [
        { contract_line_id: 'line-1', period_completed_pct: 20, period_completed_value: 2000 },
      ]),
    );
  });

  it('toasts its own words after a commit when the caller gives none', async () => {
    commitMock.mockResolvedValue({} as never);
    populateMock.mockResolvedValue(preview());
    renderModal();
    await waitFor(() => expect(screen.getByTestId('populate-preview-table')).toBeTruthy());
    fireEvent.click(screen.getByText('Commit lines'));
    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith({ type: 'success', title: 'Claim populated from progress' }),
    );
  });

  it("toasts the caller's words after a commit when it gives them", async () => {
    commitMock.mockResolvedValue({} as never);
    const loader = vi.fn().mockResolvedValue(preview());
    renderModal({ loadPreview: loader, successText: 'Lines taken from the subs' });
    await waitFor(() => expect(screen.getByTestId('populate-preview-table')).toBeTruthy());
    fireEvent.click(screen.getByText('Commit lines'));
    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith({ type: 'success', title: 'Lines taken from the subs' }),
    );
  });
});
