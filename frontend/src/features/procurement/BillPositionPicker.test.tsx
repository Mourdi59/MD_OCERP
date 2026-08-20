// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <BillPositionPicker> and the cost-spine helpers behind it.
//
// The behaviour worth pinning down is what the picker does when there is
// nothing to pick: a project whose cost spine has never been generated must
// get no control at all rather than an empty dropdown, because a permanent
// empty control on the order form is furniture for a choice nobody can make.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  BillPositionPicker,
  optionLabel,
  type BillPositionPickerProps,
} from './BillPositionPicker';
import { billPositionOptions, matchesQuery, type CostSpineLine } from './costSpineApi';

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet } from '@/shared/lib/api';

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

function renderPicker(props: Partial<BillPositionPickerProps> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BillPositionPicker projectId="p1" value={null} onChange={() => {}} {...props} />
    </QueryClientProvider>,
  );
}

describe('cost spine helpers', () => {
  it('drops spine lines that answer to no bill position', () => {
    // A hand-made cost line has no position. Offering it would put the buyer
    // back in front of the vocabulary the server exists to keep away from them.
    const options = billPositionOptions([
      line({ id: 'a', code: '1.1' }),
      line({ id: 'b', code: '2.1', boq_position_id: null }),
    ]);
    expect(options.map((o) => o.id)).toEqual(['a']);
  });

  it('orders positions the way the bill numbers them, not as text', () => {
    const options = billPositionOptions([
      line({ id: 'c', code: '10.1' }),
      line({ id: 'a', code: '2.1' }),
    ]);
    // Plain string ordering would put 10.1 before 2.1 and scatter the bill.
    expect(options.map((o) => o.code)).toEqual(['2.1', '10.1']);
  });

  it('matches on the code and on the description', () => {
    const l = line({ code: '3.4', description: 'Reinforced concrete C30/37' });
    expect(matchesQuery(l, '3.4')).toBe(true);
    expect(matchesQuery(l, 'CONCRETE')).toBe(true);
    expect(matchesQuery(l, 'timber')).toBe(false);
    expect(matchesQuery(l, '   ')).toBe(true);
  });

  it('reads an option the way the bill does', () => {
    expect(optionLabel(line({ code: '1.1', description: 'Blinding', unit: 'm2' }))).toBe(
      '1.1 - Blinding (m2)',
    );
    expect(optionLabel(line({ code: '1.2', description: 'Provisional sum', unit: null }))).toBe(
      '1.2 - Provisional sum',
    );
  });
});

describe('<BillPositionPicker>', () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockReset();
  });

  it('renders nothing when the project has no cost spine', async () => {
    vi.mocked(apiGet).mockResolvedValue([]);
    const { container } = renderPicker();
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalled());
    expect(container.querySelector('select')).toBeNull();
  });

  it('renders nothing when the spine cannot be read at all', async () => {
    // The cost model module is a plugin and may not be installed, in which
    // case the endpoint is not there. That is the same silence to a buyer.
    vi.mocked(apiGet).mockRejectedValue(new Error('404'));
    const { container } = renderPicker();
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalled());
    expect(container.querySelector('select')).toBeNull();
  });

  it('offers the bill positions and an unlinked choice', async () => {
    vi.mocked(apiGet).mockResolvedValue([
      line({ id: 'a', code: '1.1', description: 'Blinding' }),
      line({ id: 'b', code: '1.2', description: 'Slab', boq_position_id: 'pos-2' }),
    ]);
    renderPicker();
    const select = await screen.findByRole('combobox');
    const options = Array.from(select.querySelectorAll('option'));
    // The empty option first, then one per position.
    expect(options).toHaveLength(3);
    expect(options[0].value).toBe('');
    expect(options[1].value).toBe('pos-1');
    expect(options[2].value).toBe('pos-2');
  });

  it('hands back the bill position and never the cost line', async () => {
    // The server resolves the money link when the order line is written.
    // Sending the cost line this page happens to hold would freeze a value
    // that may already be stale.
    vi.mocked(apiGet).mockResolvedValue([line({ id: 'cl-99', boq_position_id: 'pos-1' })]);
    const onChange = vi.fn();
    renderPicker({ onChange });
    const select = await screen.findByRole('combobox');
    await userEvent.selectOptions(select, 'pos-1');
    expect(onChange).toHaveBeenCalledWith('pos-1');
    expect(onChange).not.toHaveBeenCalledWith('cl-99');
  });

  it('reports a cleared choice as null rather than an empty string', async () => {
    vi.mocked(apiGet).mockResolvedValue([line()]);
    const onChange = vi.fn();
    renderPicker({ value: 'pos-1', onChange });
    const select = await screen.findByRole('combobox');
    await userEvent.selectOptions(select, '');
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('names the line it belongs to, so eight of them are distinguishable', async () => {
    vi.mocked(apiGet).mockResolvedValue([line()]);
    renderPicker({ line: 3 });
    const select = await screen.findByRole('combobox');
    expect(select.getAttribute('aria-label')).toContain('3');
  });

  it('shows no filter box for a short bill', async () => {
    vi.mocked(apiGet).mockResolvedValue([line({ id: 'a' }), line({ id: 'b', code: '1.2' })]);
    const { container } = renderPicker();
    await screen.findByRole('combobox');
    expect(container.querySelector('input[type="search"]')).toBeNull();
  });

  it('filters a long bill without dropping the buyer’s own choice', async () => {
    // Typing in the filter must never silently unlink a line that is already
    // attributed, so the selected position stays in the list even when the
    // query excludes it.
    const many = Array.from({ length: 20 }, (_, i) =>
      line({ id: `cl-${i}`, code: `1.${i}`, description: `Item ${i}`, boq_position_id: `pos-${i}` }),
    );
    vi.mocked(apiGet).mockResolvedValue(many);
    const { container } = renderPicker({ value: 'pos-7' });

    const select = await screen.findByRole('combobox');
    expect(container.querySelector('input[type="search"]')).not.toBeNull();
    expect(select.querySelectorAll('option')).toHaveLength(21);

    await userEvent.type(screen.getByRole('searchbox'), 'Item 12');
    const options = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(options).toContain('pos-12');
    expect(options).toContain('pos-7');
    expect(options).not.toContain('pos-3');
  });

  it('walks the endpoint pages instead of showing only the first two hundred', async () => {
    // The endpoint caps limit at 200 and takes no search parameter, so a bill
    // longer than that would otherwise end at position 200 and the buyer would
    // conclude theirs does not exist.
    const page = (start: number, count: number) =>
      Array.from({ length: count }, (_, i) =>
        line({
          id: `cl-${start + i}`,
          code: `1.${start + i}`,
          boq_position_id: `pos-${start + i}`,
        }),
      );
    vi.mocked(apiGet)
      .mockResolvedValueOnce(page(0, 200))
      .mockResolvedValueOnce(page(200, 5));

    renderPicker();
    const select = await screen.findByRole('combobox');
    await vi.waitFor(() => expect(select.querySelectorAll('option')).toHaveLength(206));
    expect(apiGet).toHaveBeenCalledTimes(2);
    expect(vi.mocked(apiGet).mock.calls[1][0]).toContain('offset=200');
  });
});
