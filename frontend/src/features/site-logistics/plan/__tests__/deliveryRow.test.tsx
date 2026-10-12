// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// One row of the delivery board: what the server allows decides what the row
// offers, and a refusal that is about the delivery itself is said in words.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);

import type { BoardCan, DeliveryBooking } from '../../api';
import { DeliveryRow } from '../../SiteLogisticsPage';

const yes = { allowed: true, applies: true, reason: null };

function delivery(can: BoardCan): DeliveryBooking {
  return {
    id: 'd1',
    can,
    project_id: 'p1',
    gate_id: null,
    supplier_name: 'Rebar supplier',
    contact_name: null,
    contact_phone: null,
    vehicle_type: null,
    materials_desc: null,
    window_start: '2026-03-02T08:00:00Z',
    window_end: '2026-03-02T09:00:00Z',
    status: 'requested',
    po_ref: null,
    notes: null,
    created_by: null,
    lines: [],
    metadata: {},
    created_at: '2026-03-01T08:00:00Z',
    updated_at: '2026-03-01T08:00:00Z',
  };
}

function renderRow(can: BoardCan) {
  const onApprove = vi.fn();
  render(
    <MemoryRouter>
      <DeliveryRow
        delivery={delivery(can)}
        gate={undefined}
        busy={false}
        onApprove={onApprove}
        onReject={vi.fn()}
        onAdvance={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />
    </MemoryRouter>,
  );
  return { onApprove };
}

afterEach(cleanup);

describe('a delivery on the board', () => {
  it('shows an approval the server refuses for this delivery as a disabled button with the reason', () => {
    const { onApprove } = renderRow({
      edit: yes,
      delete: yes,
      approve: { allowed: false, applies: true, reason: 'slot_taken' },
      reject: yes,
    });
    const approve = screen.getByRole('button', { name: 'Approve' });
    expect(approve).toBeDisabled();
    expect(approve).toHaveAttribute('title', 'Another approved delivery holds this window on the gate.');
    fireEvent.click(approve);
    expect(onApprove).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeEnabled();
  });

  it('lets an allowed approval through', () => {
    const { onApprove } = renderRow({ edit: yes, delete: yes, approve: yes, reject: yes });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(onApprove).toHaveBeenCalledTimes(1);
  });

  it('offers no decision and no change to a reader without the right', () => {
    const no = { allowed: false, applies: true, reason: 'permission_denied' };
    renderRow({ edit: no, delete: no, approve: no, reject: no });
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Edit delivery' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
  });
});
