/**
 * A new model version offers its quantity rules again, and only offers.
 *
 * The banner counts the rules that priced the earlier version and sends the
 * user to each BOQ's change review on the model quantities tab. It applies
 * nothing, stays away once dismissed, and shows nothing when the lookup fails.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

const mocks = vi.hoisted(() => ({ fetchQuantityRuleOffer: vi.fn() }));

vi.mock('./api', () => ({ fetchQuantityRuleOffer: mocks.fetchQuantityRuleOffer }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (key === 'bim.rule_offer_title') return `Re-apply ${String(opts?.count)} quantity rules`;
      if (key === 'bim.rule_offer_review') return `Review in ${String(opts?.boq)}`;
      return key;
    },
  }),
}));

import { QuantityRuleOfferBanner } from './QuantityRuleOfferBanner';
import { versionParentOptions } from './modelVersions';
import type { BIMModelData } from '@/shared/ui/BIMViewer';

const OFFER = {
  model_id: 'm-2',
  parent_model_id: 'm-1',
  rule_count: 3,
  boqs: [
    { boq_id: 'b-1', boq_name: 'Main bill', rule_count: 2, position_count: 4 },
    { boq_id: 'b-2', boq_name: 'Alternates', rule_count: 1, position_count: 1 },
  ],
};

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

function renderBanner(modelId = 'm-2'): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = (node: ReactNode) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/bim']}>
        <Routes>
          <Route path="/bim" element={node} />
          <Route path="/boq/:boqId" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  render(wrap(<QuantityRuleOfferBanner modelId={modelId} />));
}

beforeEach(() => {
  mocks.fetchQuantityRuleOffer.mockReset();
  try {
    window.localStorage.clear();
  } catch {
    // no storage in this environment
  }
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('QuantityRuleOfferBanner', () => {
  it('counts the rules and opens each BOQ change review on the model quantities', async () => {
    mocks.fetchQuantityRuleOffer.mockResolvedValue(OFFER);
    renderBanner();
    expect(await screen.findByText('Re-apply 3 quantity rules')).toBeTruthy();
    expect(mocks.fetchQuantityRuleOffer).toHaveBeenCalledWith('m-2');
    expect(screen.getByText('Review in Alternates')).toBeTruthy();
    fireEvent.click(screen.getByText('Review in Main bill'));
    expect((await screen.findByTestId('where')).textContent).toBe('/boq/b-1?review=quantities');
  });

  it('shows nothing when no rule priced the earlier version', async () => {
    mocks.fetchQuantityRuleOffer.mockResolvedValue({ ...OFFER, rule_count: 0, boqs: [] });
    renderBanner();
    await waitFor(() => expect(mocks.fetchQuantityRuleOffer).toHaveBeenCalled());
    expect(screen.queryByTestId('bim-rule-offer')).toBeNull();
  });

  it('shows nothing, and no raw error, when the lookup fails', async () => {
    mocks.fetchQuantityRuleOffer.mockRejectedValue(new Error('HTTP 500'));
    renderBanner();
    await waitFor(() => expect(mocks.fetchQuantityRuleOffer).toHaveBeenCalled());
    expect(screen.queryByTestId('bim-rule-offer')).toBeNull();
    expect(screen.queryByText(/HTTP 500/)).toBeNull();
  });

  it('stays dismissed for that version, and still closes when storage is blocked', async () => {
    mocks.fetchQuantityRuleOffer.mockResolvedValue(OFFER);
    renderBanner();
    fireEvent.click(await screen.findByRole('button', { name: 'bim.rule_offer_dismiss' }));
    expect(screen.queryByTestId('bim-rule-offer')).toBeNull();
    cleanup();

    mocks.fetchQuantityRuleOffer.mockClear();
    renderBanner();
    expect(screen.queryByTestId('bim-rule-offer')).toBeNull();
    expect(mocks.fetchQuantityRuleOffer).not.toHaveBeenCalled();
    cleanup();

    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    renderBanner('m-9');
    fireEvent.click(await screen.findByRole('button', { name: 'bim.rule_offer_dismiss' }));
    expect(screen.queryByTestId('bim-rule-offer')).toBeNull();
  });
});

describe('versionParentOptions', () => {
  const model = (id: string, status: string, parent?: string): BIMModelData =>
    ({ id, name: id, filename: '', format: 'ifc', status, parent_model_id: parent ?? null }) as BIMModelData;

  it('offers finished models that no finished newer version replaced', () => {
    const options = versionParentOptions([
      model('c-v1', 'ready'),
      model('c-v2', 'ready', 'c-v1'),
      model('b-retry', 'ready'),
      model('b-failed-v2', 'error', 'b-retry'),
      model('a-importing', 'processing'),
    ]);
    expect(options.map((m) => m.id)).toEqual(['b-retry', 'c-v2']);
  });
});
