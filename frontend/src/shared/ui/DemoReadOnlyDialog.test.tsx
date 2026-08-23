// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The demonstration refusal, driven end to end.
 *
 * Every case here goes through the real transport (`apiGet` / `apiPatch`) with
 * a stubbed `fetch`, and through the real dialog. Testing the dialog by setting
 * its store by hand would prove the component renders and prove nothing about
 * whether a refused write ever reaches it, which is the part that can break.
 *
 * The control cases matter most: an ordinary 403 must be left completely alone.
 * A matcher that fired on any forbidden response would tell every user whose
 * role lacks a permission that their own installation is a demonstration.
 */
import { useState } from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query';

import { DemoReadOnlyDialog } from './DemoReadOnlyDialog';
import { apiGet, apiPatch, isDemoReadOnlyRefusal } from '@/shared/lib/api';
import { useDemoReadOnlyStore } from '@/stores/useDemoReadOnlyStore';

/** The English sentence the contract carries for callers that are not this app. */
const SERVER_MESSAGE =
  'This is the public demonstration and it does not keep changes. Install OpenConstructionERP to work with your own data.';

const DEMO_REFUSAL_BODY = { detail: { error: 'demo_read_only', message: SERVER_MESSAGE } };

/** The ordinary permission denial: FastAPI's `detail` as a plain string. */
const PLAIN_FORBIDDEN_BODY = { detail: 'You do not have permission to edit this project.' };

/** A structured 403 that is emphatically some other refusal. */
const OTHER_STRUCTURED_FORBIDDEN_BODY = {
  detail: { error: 'project_locked', message: 'This project is locked for the current period.' },
};

interface Thing {
  name: string;
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/**
 * A screen that reads a value from the server and paints an edit before the
 * answer comes back.
 *
 * The optimism is written into the React Query cache, not into local state,
 * because that is what a page doing an optimistic update actually does and it
 * is what the dialog's refetch is supposed to undo. Optimism held in `useState`
 * would make this assertion pass or fail on the harness rather than on the
 * mechanism under test.
 */
function Screen({ writes = 1 }: { writes?: number }) {
  const queryClient = useQueryClient();
  const [lastError, setLastError] = useState<string>('');
  const { data } = useQuery({
    queryKey: ['thing'],
    queryFn: () => apiGet<Thing>('/v1/thing'),
  });

  const save = async () => {
    // Paint the change first, the way an optimistic screen does.
    queryClient.setQueryData<Thing>(['thing'], { name: 'Edited by the visitor' });
    const attempts = Array.from({ length: writes }, () =>
      apiPatch<Thing>('/v1/thing', { name: 'Edited by the visitor' }).catch((err: unknown) => {
        setLastError(err instanceof Error ? err.message : String(err));
      }),
    );
    await Promise.all(attempts);
  };

  return (
    <div>
      <span data-testid="value">{data?.name ?? 'loading'}</span>
      <span data-testid="last-error">{lastError}</span>
      <button type="button" onClick={() => void save()}>
        Save
      </button>
    </div>
  );
}

function renderScreen(writes = 1) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Screen writes={writes} />
      <DemoReadOnlyDialog />
    </QueryClientProvider>,
  );
}

/**
 * Answer the read with the server's value and the write with `refusal`.
 *
 * The read answers the same thing every time, so a screen that has painted an
 * edit and then refetches lands back on the server's value - which is the
 * assertion, not a coincidence of ordering.
 */
function stubFetch(refusal: { status: number; body: unknown }) {
  const calls: string[] = [];
  const stub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : String(input);
    const method = init?.method ?? 'GET';
    calls.push(`${method} ${url}`);
    if (method === 'GET') return jsonResponse(200, { name: 'What the server holds' });
    return jsonResponse(refusal.status, refusal.body);
  });
  vi.stubGlobal('fetch', stub);
  return calls;
}

beforeEach(() => {
  useDemoReadOnlyStore.setState({ open: false });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('isDemoReadOnlyRefusal', () => {
  it('matches only 403 with detail.error === "demo_read_only"', () => {
    expect(isDemoReadOnlyRefusal(403, DEMO_REFUSAL_BODY)).toBe(true);
  });

  it('does not match the same body on another status', () => {
    // The contract fixes the status too. A 409 or 500 carrying this shape is
    // some other thing, and guessing at it is how a matcher widens by accident.
    expect(isDemoReadOnlyRefusal(409, DEMO_REFUSAL_BODY)).toBe(false);
    expect(isDemoReadOnlyRefusal(500, DEMO_REFUSAL_BODY)).toBe(false);
  });

  it('does not match an ordinary 403, in any of its shapes', () => {
    expect(isDemoReadOnlyRefusal(403, PLAIN_FORBIDDEN_BODY)).toBe(false);
    expect(isDemoReadOnlyRefusal(403, OTHER_STRUCTURED_FORBIDDEN_BODY)).toBe(false);
    expect(isDemoReadOnlyRefusal(403, { detail: [{ msg: 'nope' }] })).toBe(false);
    expect(isDemoReadOnlyRefusal(403, 'Forbidden')).toBe(false);
    expect(isDemoReadOnlyRefusal(403, null)).toBe(false);
    expect(isDemoReadOnlyRefusal(403, undefined)).toBe(false);
    expect(isDemoReadOnlyRefusal(403, {})).toBe(false);
    // `error` at the top level rather than under `detail` is not the contract.
    expect(isDemoReadOnlyRefusal(403, { error: 'demo_read_only' })).toBe(false);
  });
});

describe('a refused write on the public demonstration', () => {
  it('explains itself, and puts the screen back to what the server holds', async () => {
    const user = userEvent.setup();
    const calls = stubFetch({ status: 403, body: DEMO_REFUSAL_BODY });
    renderScreen();

    await screen.findByText('What the server holds');

    await user.click(screen.getByRole('button', { name: 'Save' }));

    // The optimistic edit was painted, refused, and undone: the screen shows
    // the server's value again, not the edit the visitor typed.
    await waitFor(() => {
      expect(screen.getByTestId('value')).toHaveTextContent('What the server holds');
    });
    expect(screen.getByTestId('value')).not.toHaveTextContent('Edited by the visitor');

    // The undo is a refetch, not a guess: the read was asked again.
    expect(calls.filter((c) => c.startsWith('GET')).length).toBeGreaterThanOrEqual(2);

    const dialog = await screen.findByTestId('demo-read-only-dialog');
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText('This is a demonstration')).toBeInTheDocument();
    expect(screen.getByText(/nothing you change here is kept/i)).toBeInTheDocument();
    expect(screen.getByText(/runs on your own machine/i)).toBeInTheDocument();
  });

  it('names every way to install it, and links to where they live', async () => {
    const user = userEvent.setup();
    stubFetch({ status: 403, body: DEMO_REFUSAL_BODY });
    renderScreen();
    await screen.findByText('What the server holds');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByTestId('demo-read-only-dialog');

    expect(screen.getByText(/^Windows:/)).toBeInTheDocument();
    expect(screen.getByText(/^macOS:/)).toBeInTheDocument();
    expect(screen.getByText(/^Linux:/)).toBeInTheDocument();
    expect(screen.getByText(/^Docker:/)).toBeInTheDocument();
    expect(screen.getByText(/^Python:/)).toBeInTheDocument();
    expect(screen.getByText(/^From source:/)).toBeInTheDocument();

    expect(screen.getByTestId('demo-read-only-download')).toHaveAttribute(
      'href',
      'https://openconstructionerp.com/download',
    );
  });

  it('never shows the server\'s English sentence to the reader', async () => {
    const user = userEvent.setup();
    stubFetch({ status: 403, body: DEMO_REFUSAL_BODY });
    renderScreen();
    await screen.findByText('What the server holds');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByTestId('demo-read-only-dialog');

    // `message` is the fallback for callers that are not this screen. This
    // screen has its own translated text, so an English sentence from the
    // server appearing anywhere in the dialog is the defect.
    expect(screen.getByTestId('demo-read-only-dialog')).not.toHaveTextContent(SERVER_MESSAGE);
  });

  it('hands the caller our own sentence, not the server\'s, so a stray toast cannot leak it', async () => {
    const user = userEvent.setup();
    stubFetch({ status: 403, body: DEMO_REFUSAL_BODY });
    renderScreen();
    await screen.findByText('What the server holds');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    // The screen's own catch block toasts `err.message` here, the way ~325
    // call sites across the features do. What it receives has to be the line
    // this app owns and translates, because none of those call sites knows
    // the difference and no future one will either.
    await waitFor(() => {
      expect(screen.getByTestId('last-error')).not.toHaveTextContent('');
    });
    expect(screen.getByTestId('last-error')).not.toHaveTextContent(SERVER_MESSAGE);
    expect(screen.getByTestId('last-error')).toHaveTextContent(
      'This is a demonstration, so that change was not saved.',
    );
  });

  it('shows one dialog for one click, however many writes that click made', async () => {
    const user = userEvent.setup();
    stubFetch({ status: 403, body: DEMO_REFUSAL_BODY });
    renderScreen(3);
    await screen.findByText('What the server holds');

    await user.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByTestId('demo-read-only-dialog');

    expect(screen.getAllByTestId('demo-read-only-dialog')).toHaveLength(1);

    // And one dismissal is enough - three refusals do not queue three dialogs
    // behind each other for the visitor to close one at a time.
    await user.click(screen.getByTestId('demo-read-only-dismiss'));
    await waitFor(() => {
      expect(screen.queryByTestId('demo-read-only-dialog')).not.toBeInTheDocument();
    });
    expect(useDemoReadOnlyStore.getState().open).toBe(false);
  });

  it('can be dismissed with Escape, and explains again on the next refused write', async () => {
    const user = userEvent.setup();
    stubFetch({ status: 403, body: DEMO_REFUSAL_BODY });
    renderScreen();
    await screen.findByText('What the server holds');

    await user.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByTestId('demo-read-only-dialog');

    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByTestId('demo-read-only-dialog')).not.toBeInTheDocument();
    });

    // A visitor who tries to change something else is asking the same
    // question again, and is owed the same answer.
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByTestId('demo-read-only-dialog')).toBeInTheDocument();
  });
});

describe('an ordinary forbidden response', () => {
  it('is left completely alone when detail is a plain string', async () => {
    const user = userEvent.setup();
    stubFetch({ status: 403, body: PLAIN_FORBIDDEN_BODY });
    renderScreen();
    await screen.findByText('What the server holds');

    await user.click(screen.getByRole('button', { name: 'Save' }));

    // The caller still got its error, so its own handling ran.
    await waitFor(() => {
      expect(screen.getByTestId('last-error')).toHaveTextContent(
        'You do not have permission to edit this project.',
      );
    });

    // Assert the store, not just the absent node: the dialog could be absent
    // for some unrelated reason and the flag still be wrongly set.
    expect(useDemoReadOnlyStore.getState().open).toBe(false);
    expect(screen.queryByTestId('demo-read-only-dialog')).not.toBeInTheDocument();
  });

  it('is left completely alone when detail is a structured error of another kind', async () => {
    const user = userEvent.setup();
    stubFetch({ status: 403, body: OTHER_STRUCTURED_FORBIDDEN_BODY });
    renderScreen();
    await screen.findByText('What the server holds');

    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(screen.getByTestId('last-error')).toHaveTextContent(
        'This project is locked for the current period.',
      );
    });

    expect(useDemoReadOnlyStore.getState().open).toBe(false);
    expect(screen.queryByTestId('demo-read-only-dialog')).not.toBeInTheDocument();
  });

  it('does not refetch the screen, so a permission denial costs nothing', async () => {
    const user = userEvent.setup();
    const calls = stubFetch({ status: 403, body: PLAIN_FORBIDDEN_BODY });
    renderScreen();
    await screen.findByText('What the server holds');
    const readsBefore = calls.filter((c) => c.startsWith('GET')).length;

    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      expect(screen.getByTestId('last-error')).not.toHaveTextContent('');
    });

    expect(calls.filter((c) => c.startsWith('GET')).length).toBe(readsBefore);

    // And the optimistic paint is still on screen, untouched.
    //
    // This is what makes the revert in the demonstration case a finding rather
    // than an artefact of the harness: without the refusal, nothing puts the
    // server's value back, so the value that comes back there comes back
    // because of the dialog's refetch and for no other reason.
    expect(screen.getByTestId('value')).toHaveTextContent('Edited by the visitor');
  });
});

describe('the store', () => {
  it('renders nothing until the server has refused something', async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <DemoReadOnlyDialog />
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId('demo-read-only-dialog')).not.toBeInTheDocument();

    // Nothing on this path reads a hostname, an env var or a build flag: the
    // only way the dialog appears is a server response that said so.
    act(() => {
      useDemoReadOnlyStore.getState().raise();
    });
    await waitFor(() => {
      expect(screen.getByTestId('demo-read-only-dialog')).toBeInTheDocument();
    });
  });
});
