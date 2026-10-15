// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * An estimate can be renamed from the editor header and from a list row.
 *
 * The server always accepted PATCH /boqs/{id} with a name, but no screen
 * offered it. The header title turns into an input (pencil or double click):
 * Enter or blur saves, Esc cancels, an empty name is refused, and a locked
 * estimate offers nothing. The list row asks in a dialog and shares the
 * mutation.
 *
 * Run:  npx vitest run src/features/boq/__tests__/renameEstimate.test.tsx
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { BOQRenameTitle } from '../BOQRenameTitle';
import { BOQRenameDialog } from '../BOQRenameDialog';
import { useToastStore } from '@/stores/useToastStore';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _key,
  }),
  initReactI18next: { type: '3rdParty', init: () => undefined },
}));

const update = vi.fn();
vi.mock('../api', () => ({
  boqApi: { update: (...args: unknown[]) => update(...args) },
}));

function renderWith(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
  return { invalidate };
}

describe('renaming an estimate', () => {
  beforeEach(() => {
    update.mockReset();
    update.mockResolvedValue({});
    useToastStore.setState({ toasts: [] });
  });
  afterEach(cleanup);

  it('saves a new name on Enter and refreshes the editor and the list', async () => {
    const { invalidate } = renderWith(<BOQRenameTitle boqId="b1" name="Old name" locked={false} />);
    fireEvent.click(screen.getByTestId('boq-rename-button'));
    const input = screen.getByTestId('boq-rename-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '  New name  ' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(update).toHaveBeenCalledWith('b1', { name: 'New name' }));
    await waitFor(() => expect(screen.queryByTestId('boq-rename-input')).toBeNull());
    const keys = invalidate.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(['boq', 'b1']));
    expect(keys).toContain(JSON.stringify(['all-boqs']));
    expect(useToastStore.getState().toasts.some((x) => x.type === 'success')).toBe(true);
  });

  it('opens on a double click of the title and saves on blur', async () => {
    renderWith(<BOQRenameTitle boqId="b1" name="Old name" locked={false} />);
    fireEvent.doubleClick(screen.getByRole('heading', { name: 'Old name' }));
    const input = screen.getByTestId('boq-rename-input');
    fireEvent.change(input, { target: { value: 'Blur name' } });
    fireEvent.blur(input);
    await waitFor(() => expect(update).toHaveBeenCalledWith('b1', { name: 'Blur name' }));
  });

  it('Esc cancels without a request', () => {
    renderWith(<BOQRenameTitle boqId="b1" name="Old name" locked={false} />);
    fireEvent.click(screen.getByTestId('boq-rename-button'));
    const input = screen.getByTestId('boq-rename-input');
    fireEvent.change(input, { target: { value: 'Never saved' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByTestId('boq-rename-input')).toBeNull();
    expect(update).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: 'Old name' })).toBeTruthy();
  });

  it('refuses an empty name', () => {
    renderWith(<BOQRenameTitle boqId="b1" name="Old name" locked={false} />);
    fireEvent.click(screen.getByTestId('boq-rename-button'));
    const input = screen.getByTestId('boq-rename-input');
    fireEvent.change(input, { target: { value: '   ' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(update).not.toHaveBeenCalled();
    expect(screen.getByTestId('boq-rename-input')).toBeTruthy();
  });

  it('offers nothing on a locked estimate', () => {
    renderWith(<BOQRenameTitle boqId="b1" name="Old name" locked />);
    expect(screen.queryByTestId('boq-rename-button')).toBeNull();
    fireEvent.doubleClick(screen.getByRole('heading', { name: 'Old name' }));
    expect(screen.queryByTestId('boq-rename-input')).toBeNull();
  });

  it('keeps the input open and toasts an error when the server refuses', async () => {
    update.mockRejectedValue(new Error('boom'));
    renderWith(<BOQRenameTitle boqId="b1" name="Old name" locked={false} />);
    fireEvent.click(screen.getByTestId('boq-rename-button'));
    const input = screen.getByTestId('boq-rename-input');
    fireEvent.change(input, { target: { value: 'Other' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() =>
      expect(useToastStore.getState().toasts.some((x) => x.type === 'error')).toBe(true),
    );
    expect(screen.queryByTestId('boq-rename-input')).not.toBeNull();
  });

  it('the list dialog saves through the same mutation and closes', async () => {
    const onClose = vi.fn();
    renderWith(<BOQRenameDialog boqId="b2" name="Row name" onClose={onClose} />);
    fireEvent.change(screen.getByTestId('boq-rename-dialog-input'), { target: { value: 'Row renamed' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(update).toHaveBeenCalledWith('b2', { name: 'Row renamed' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
