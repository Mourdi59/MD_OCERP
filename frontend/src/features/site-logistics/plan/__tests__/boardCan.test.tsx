// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The verdict on adding to the delivery board: a button is active only on an
// answer the server gave, and a failed read is said and can be asked again.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('../../api', () => ({ fetchBoardCan: vi.fn() }));

import * as siteApi from '../../api';
import { BoardCanNotice, useBoardCreate } from '../boardCan';
import { denied } from '../rules';

const fetchBoardCan = vi.mocked(siteApi.fetchBoardCan);
const yes = { allowed: true, applies: true, reason: null };

function Probe({ projectId }: { projectId: string }) {
  const may = useBoardCreate(projectId, 'delivery');
  return (
    <>
      <BoardCanNotice projectId={projectId} />
      <button disabled={denied(may)}>Book</button>
    </>
  );
}

function renderProbe(projectId = 'p1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Probe projectId={projectId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => fetchBoardCan.mockReset());
afterEach(cleanup);

describe('what may be added to the delivery board', () => {
  it('keeps the button disabled until the server has answered', async () => {
    let answer: (value: siteApi.BoardCreate) => void = () => undefined;
    fetchBoardCan.mockReturnValueOnce(new Promise((resolve) => (answer = resolve)));
    renderProbe();
    expect(screen.getByRole('button', { name: 'Book' })).toBeDisabled();
    expect(screen.queryByTestId('board-can-failed')).toBeNull();
    answer({ delivery: { create: yes } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Book' })).toBeEnabled());
  });

  it('says that a failed read failed, keeps the button disabled, and asks again on request', async () => {
    fetchBoardCan.mockRejectedValueOnce(new Error('network'));
    fetchBoardCan.mockResolvedValueOnce({ delivery: { create: yes } });
    renderProbe();
    const notice = await screen.findByTestId('board-can-failed');
    expect(notice).toHaveTextContent('What you may do here could not be loaded.');
    expect(screen.getByRole('button', { name: 'Book' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Book' })).toBeEnabled());
    expect(screen.queryByTestId('board-can-failed')).toBeNull();
  });

  it('asks nothing and refuses nothing without a project', () => {
    renderProbe('');
    expect(screen.getByRole('button', { name: 'Book' })).toBeEnabled();
    expect(fetchBoardCan).not.toHaveBeenCalled();
  });
});
