// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <BillPositionPicker> and the cost-spine helpers behind it.
//
// Two behaviours carry the weight here and neither is about the happy path.
//
// What the picker does when there is nothing to pick: a project whose cost
// spine has never been generated must get no control at all rather than an
// empty dropdown, because a permanent empty control on the order form is
// furniture for a choice nobody can make.
//
// What it does when there is more to pick than it can hold: the search goes to
// the server, so the assertions are about the request that leaves rather than
// about a list being filtered in the browser. A test that only checks the
// rendered options would pass just as well against a filter over a capped page,
// which is the defect this control was rewritten to remove.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  BillPositionPicker,
  optionLabel,
  type BillPositionPickerProps,
} from './BillPositionPicker';
import {
  SPINE_PAGE_SIZE,
  fetchBillPositions,
  fetchPositionLine,
  type CostSpineLine,
} from './costSpineApi';

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet } from '@/shared/lib/api';

const mockGet = vi.mocked(apiGet);

function line(over: Partial<CostSpineLine> = {}): CostSpineLine {
  return {
    id: over.id ?? 'cl-1',
    project_id: 'p1',
    code: over.code ?? '1.1',
    description: over.description ?? 'Reinforced concrete C30/37',
    unit: over.unit ?? 'm3',
    source: 'boq',
    boq_position_id: over.boq_position_id === undefined ? 'pos-1' : over.boq_position_id,
    boq_id: 'b1',
    estimate_quantity: '120',
    estimate_unit_rate: '180.00',
    estimate_amount: '21600.00',
    currency: 'EUR',
    status: 'active',
    ...over,
  };
}

/** `n` distinct positions, numbered so the sort has something to do. */
function bill(n: number): CostSpineLine[] {
  return Array.from({ length: n }, (_, i) =>
    line({ id: `cl-${i}`, code: `1.${i + 1}`, boq_position_id: `pos-${i}` }),
  );
}

/** Every URL `apiGet` was asked for, in order. */
function requestedUrls(): string[] {
  return mockGet.mock.calls.map((call) => String(call[0]));
}

function renderPicker(props: Partial<BillPositionPickerProps> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BillPositionPicker projectId="p1" value={null} onChange={() => {}} {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockGet.mockReset();
});

describe('fetchBillPositions', () => {
  it('asks the server for linked positions only, so the rows and the count agree', async () => {
    mockGet.mockResolvedValue([]);
    await fetchBillPositions('p1');

    const url = requestedUrls()[0];
    expect(url).toContain('/v1/costmodel/projects/p1/spine/lines/');
    expect(url).toContain('linked_to_position=true');
    expect(url).toContain('status=active');
    expect(url).toContain(`limit=${SPINE_PAGE_SIZE}`);
  });

  it('omits the search parameter entirely when nothing was typed', async () => {
    // The endpoint declares search with min_length=1. Sending an empty string
    // for a cleared box answers 422, which would turn "show everything again"
    // into an error the buyer cannot get out of.
    mockGet.mockResolvedValue([]);
    await fetchBillPositions('p1', '');
    await fetchBillPositions('p1', '   ');

    for (const url of requestedUrls()) {
      expect(url).not.toContain('search=');
    }
  });

  it('sends the trimmed term when something was typed', async () => {
    mockGet.mockResolvedValue([]);
    await fetchBillPositions('p1', '  concrete  ');

    expect(requestedUrls()[0]).toContain('search=concrete');
  });

  it('calls a full page truncated and a short page whole', async () => {
    mockGet.mockResolvedValueOnce(bill(SPINE_PAGE_SIZE));
    expect((await fetchBillPositions('p1')).truncated).toBe(true);

    mockGet.mockResolvedValueOnce(bill(3));
    expect((await fetchBillPositions('p1')).truncated).toBe(false);
  });

  it('orders a page the way the bill numbers it, not as text', async () => {
    mockGet.mockResolvedValue([
      line({ id: 'a', code: '1.10' }),
      line({ id: 'b', code: '1.2' }),
      line({ id: 'c', code: '1.1' }),
    ]);

    const page = await fetchBillPositions('p1');
    expect(page.positions.map((p) => p.code)).toEqual(['1.1', '1.2', '1.10']);
  });
});

describe('fetchPositionLine', () => {
  it('resolves one position by its own id', async () => {
    mockGet.mockResolvedValue([line({ id: 'cl-9', boq_position_id: 'pos-9' })]);

    const found = await fetchPositionLine('p1', 'pos-9');

    expect(found?.id).toBe('cl-9');
    expect(requestedUrls()[0]).toContain('boq_position_id=pos-9');
  });

  it('answers null for a position that is off the spine', async () => {
    mockGet.mockResolvedValue([]);
    expect(await fetchPositionLine('p1', 'pos-none')).toBeNull();
  });

  it('does not filter by status, so a closed line still names the link that exists', async () => {
    // The list filters on active because it offers choices. This names a choice
    // already made, and CostLineUpdate carries status, so any PATCH can close
    // the line an order was attributed to months ago. Filtering here would
    // answer "no such line" for a link the order really holds, the control
    // would render blank, and the next save would write the blank back.
    mockGet.mockResolvedValue([line({ id: 'cl-9', boq_position_id: 'pos-9', status: 'closed' })]);

    const found = await fetchPositionLine('p1', 'pos-9');

    expect(found?.id).toBe('cl-9');
    expect(requestedUrls()[0]).not.toContain('status=');
  });
});

describe('optionLabel', () => {
  it('reads the way the bill reads', () => {
    expect(optionLabel(line({ code: '1.1' }))).toBe('1.1 - Reinforced concrete C30/37 (m3)');
  });

  it('leaves out the brackets when the position has no unit', () => {
    expect(optionLabel(line({ code: '2', description: 'Preliminaries', unit: null }))).toBe(
      '2 - Preliminaries',
    );
  });
});

describe('<BillPositionPicker>', () => {
  it('renders nothing at all for a project with no cost spine', async () => {
    mockGet.mockResolvedValue([]);
    const { container } = renderPicker();

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('renders nothing when the read fails, because to a buyer that is the same thing', async () => {
    mockGet.mockRejectedValue(new Error('module not installed'));
    const { container } = renderPicker();

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('offers the positions and an unlinked choice', async () => {
    mockGet.mockResolvedValue([line({ code: '1.1' })]);
    renderPicker();

    const select = await screen.findByRole('combobox');
    const options = Array.from(select.querySelectorAll('option'));
    expect(options).toHaveLength(2);
    expect(options.map((o) => o.value)).toEqual(['', 'pos-1']);
  });

  it('emits the position id, never the cost line', async () => {
    mockGet.mockResolvedValue([line({ id: 'cl-1', boq_position_id: 'pos-1' })]);
    const onChange = vi.fn();
    renderPicker({ onChange });

    const select = await screen.findByRole('combobox');
    await userEvent.selectOptions(select, 'pos-1');

    expect(onChange).toHaveBeenCalledWith('pos-1');
  });

  it('emits null when the buyer unlinks the line', async () => {
    mockGet.mockResolvedValue([line()]);
    const onChange = vi.fn();
    renderPicker({ onChange, value: 'pos-1' });

    const select = await screen.findByRole('combobox');
    await userEvent.selectOptions(select, '');

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('names each control by its line number so a form of eight is usable', async () => {
    mockGet.mockResolvedValue([line()]);
    renderPicker({ line: 3 });

    expect(await screen.findByLabelText(/line 3/i)).toBeTruthy();
  });

  it('hides the search box for a bill short enough to read', async () => {
    mockGet.mockResolvedValue(bill(4));
    renderPicker();

    await screen.findByRole('combobox');
    expect(screen.queryByRole('searchbox')).toBeNull();
  });

  it('shows the search box once the bill is longer than the eye', async () => {
    mockGet.mockResolvedValue(bill(40));
    renderPicker();

    expect(await screen.findByRole('searchbox')).toBeTruthy();
  });

  it('says so when the list on screen is only a page of the register', async () => {
    mockGet.mockResolvedValue(bill(SPINE_PAGE_SIZE));
    renderPicker();

    expect(await screen.findByText(/showing the first/i)).toBeTruthy();
  });

  it('says nothing of the sort when the whole bill fits', async () => {
    mockGet.mockResolvedValue(bill(5));
    renderPicker();

    await screen.findByRole('combobox');
    expect(screen.queryByText(/showing the first/i)).toBeNull();
  });

  it('sends the typed term to the server rather than filtering what it loaded', async () => {
    mockGet.mockResolvedValue(bill(SPINE_PAGE_SIZE));
    renderPicker();
    const box = await screen.findByRole('searchbox');

    await userEvent.type(box, 'concrete');

    await waitFor(() => {
      expect(requestedUrls().some((u) => u.includes('search=concrete'))).toBe(true);
    });
  });

  it('does not send an empty search when the box is cleared', async () => {
    // The regression this guards: a debounced box that posts search= on clear
    // gets a 422, and the buyer is left looking at an error instead of the
    // list they started from.
    mockGet.mockResolvedValue(bill(SPINE_PAGE_SIZE));
    renderPicker();
    const box = await screen.findByRole('searchbox');

    await userEvent.type(box, 'abc');
    await waitFor(() => {
      expect(requestedUrls().some((u) => u.includes('search=abc'))).toBe(true);
    });
    await userEvent.clear(box);

    await waitFor(() => {
      expect(requestedUrls().every((u) => !/[?&]search=(&|$)/.test(u))).toBe(true);
    });
  });

  it('stays on screen when a search matches nothing, so it can be corrected', async () => {
    // The render-nothing rule reads the unsearched page, never the results. A
    // control that vanished on a typo would take the buyer's line attribution
    // with it and give them no way back.
    mockGet.mockResolvedValue(bill(SPINE_PAGE_SIZE));
    renderPicker();
    const box = await screen.findByRole('searchbox');

    mockGet.mockResolvedValue([]);
    await userEvent.type(box, 'no such position');

    await waitFor(() => {
      expect(requestedUrls().some((u) => u.includes('search=no'))).toBe(true);
    });
    expect(screen.getByRole('combobox')).toBeTruthy();
  });

  it('fetches a selection the loaded page does not contain', async () => {
    // An order raised against position 900 of a 2000-line bill. The page does
    // not hold it, and a control that cannot find its own value renders as
    // unlinked, which the next save would write back.
    mockGet.mockImplementation(async (url: unknown) => {
      if (String(url).includes('boq_position_id=pos-900')) {
        return [line({ id: 'cl-900', code: '9.1', description: 'Screed', boq_position_id: 'pos-900' })];
      }
      return bill(SPINE_PAGE_SIZE);
    });

    renderPicker({ value: 'pos-900' });

    const select = (await screen.findByRole('combobox')) as HTMLSelectElement;
    await waitFor(() => {
      expect(
        Array.from(select.querySelectorAll('option')).some((o) => o.value === 'pos-900'),
      ).toBe(true);
    });
    expect(select.value).toBe('pos-900');
  });

  it('asks for nothing extra when the selection is already on the page', async () => {
    mockGet.mockResolvedValue(bill(20));
    renderPicker({ value: 'pos-3' });

    await screen.findByRole('combobox');
    await waitFor(() => {
      expect(requestedUrls().every((u) => !u.includes('boq_position_id='))).toBe(true);
    });
  });
});
