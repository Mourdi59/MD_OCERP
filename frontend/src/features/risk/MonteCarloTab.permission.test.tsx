// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The run-simulation button follows the permission of the call behind it
// (`risk.update`, editor and above). A viewer gets the button disabled with the
// reason in its tooltip instead of a 403 after the click.
//
// The test setup's i18n mock renders each label's English defaultValue.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/shared/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/lib/api')>()),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

import * as api from '@/shared/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';
import { MonteCarloTab } from './MonteCarloTab';

const postMock = vi.mocked(api.apiPost);

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MonteCarloTab projectId="p-1" currency="EUR" />
    </QueryClientProvider>,
  );
}

const runButton = () => screen.getByRole('button', { name: /run simulation/i });

describe('MonteCarloTab run button', () => {
  beforeEach(() => {
    postMock.mockReset();
    postMock.mockResolvedValue({});
  });

  it('is disabled for a viewer and says why, without firing the call', () => {
    useAuthStore.setState({ userRole: 'viewer' });
    renderTab();
    const button = runButton();
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', 'Running a simulation needs the editor role.');
    fireEvent.click(button);
    expect(postMock).not.toHaveBeenCalled();
  });

  it('is enabled for an editor, with no tooltip', () => {
    useAuthStore.setState({ userRole: 'editor' });
    renderTab();
    const button = runButton();
    expect(button).toBeEnabled();
    expect(button).not.toHaveAttribute('title');
  });
});
