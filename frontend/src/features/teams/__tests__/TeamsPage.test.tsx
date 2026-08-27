// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <TeamsPage /> - teams and per-record visibility.
//
// The two things worth pinning on an access screen are the ones that are
// invisible from anywhere else in the app:
//
//   1. The stranded team. A team that holds record restrictions but has
//      nobody on it is the shape of "we locked everyone out of a record", and
//      the record's own screen cannot show it. Both halves of the condition
//      matter, so the fixture carries the three near misses as well: an empty
//      team with no restrictions, a staffed team with restrictions, and a team
//      whose restriction count the API did not compute at all (`null`).
//   2. Visibility only ever subtracts. That is a claim about the payload, not
//      about the copy - the explainer literally says "only ever subtracts", so
//      matching prose would pass for the wrong reason. What the editor is
//      allowed to send is: the union of the teams left ticked, an empty list
//      when the last box is cleared (which lifts the restriction and returns
//      the record to the whole project), and never a team that is not on this
//      project in the first place.
//
// What this suite cannot see, measured on 2026-08-27. The
// `vi.mock('react-i18next')` below is declared at file scope, and a file-level
// mock overrides one installed from a setup file. So this suite never sees the
// shared stub in src/test/setup.ts, and it never sees whatever a repo-wide i18n
// instrument installs there either. That was measured with a stand-in `t` that
// returns a value no defaultValue can equal: loaded from an extra setup file it
// turned four of four green tests red in
// src/features/bim/BIMConverterVerifyGate.test.tsx and left this file at eight
// of eight, because it never reached this file at all. Eight of eight under a
// global i18n instrument is therefore not evidence about this suite. It is
// evidence the instrument was overridden.
//
// The consequence worth knowing is the local mock's own reach. It renders the
// same string for `t(key, 'English')` and for `t(key, { defaultValue:
// 'English' })`, which is deliberate and is what lets the assertions below
// quote English prose. It also means a change in TeamsPage.tsx that only swaps
// one of those call forms for the other passes here untouched, so this suite is
// not what will tell you such a change was right. Nothing below is a statement
// about real i18next behaviour; that has to be checked against the page itself
// under a non-English locale.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

/* ── i18n ──────────────────────────────────────────────────────────────────
   This page calls `t(key, 'English default')` and `t(key, 'x {{count}}', opts)`,
   while the shared chrome it renders inside (RequiresProject, EmptyState,
   PageHeader) calls `t(key, { defaultValue })`. The shared setup stub only
   understands the second form, so both arities are handled here; without it
   half the page renders bare `teams.*` keys and every scoped query below goes
   looking in the wrong place. `initReactI18next` / `Trans` / `I18nextProvider`
   ride along because replacing the module wholesale hides every export the
   stub omits, and the @/shared/ui chain reaches the real i18n singleton. */

vi.mock('react-i18next', () => {
  type Opts = Record<string, unknown>;
  const fill = (template: string, opts?: Opts): string => {
    if (!opts) return template;
    const scope = (opts.replace as Opts | undefined) ?? opts;
    return template.replace(/\{\{(\w+)\}\}/g, (_match, name: string) =>
      scope[name] === undefined ? `{{${name}}}` : String(scope[name]),
    );
  };
  return {
    useTranslation: () => ({
      t: (key: string, second?: string | Opts, third?: Opts) => {
        if (typeof second === 'string') return fill(second, third);
        const dflt = second?.defaultValue;
        return fill(typeof dflt === 'string' ? dflt : key, second);
      },
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
    Trans: ({ children }: { children?: unknown }) => children ?? null,
    initReactI18next: { type: '3rdParty', init: () => undefined },
    I18nextProvider: ({ children }: { children?: unknown }) => children ?? null,
  };
});

/* ── Feature api ───────────────────────────────────────────────────────────
   Spread the real module: `ALL_TEAM_ROLES` and `TEAM_KINDS` are runtime
   constants the page maps over, and a hand-written export list that forgets
   one of them fails as `undefined.map is not a function`, not as a type
   error. */

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    listTeams: vi.fn(),
    createTeam: vi.fn(),
    updateTeam: vi.fn(),
    deleteTeam: vi.fn(),
    listMembers: vi.fn(),
    addMember: vi.fn(),
    updateMemberRole: vi.fn(),
    removeMember: vi.fn(),
    listEntityTypes: vi.fn(),
    listRestrictedEntities: vi.fn(),
    setEntityVisibility: vi.fn(),
    getAccessMatrix: vi.fn(),
    validateProjectTeams: vi.fn(),
  };
});

vi.mock('@/stores/useProjectContextStore', () => {
  const state = { activeProjectId: 'proj-1' };
  return {
    useProjectContextStore: (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state,
  };
});

import {
  getAccessMatrix,
  listEntityTypes,
  listMembers,
  listRestrictedEntities,
  listTeams,
  setEntityVisibility,
  validateProjectTeams,
  type RestrictedEntityRow,
  type Team,
  type TeamsValidationReport,
} from '../api';
import { TeamsPage } from '../TeamsPage';

/* ── Fixtures ──────────────────────────────────────────────────────────── */

function makeTeam(over: Partial<Team> = {}): Team {
  return {
    id: 'team-a',
    project_id: 'proj-1',
    name: 'Client QS',
    name_translations: null,
    description: '',
    kind: 'client',
    sort_order: 0,
    is_default: false,
    is_active: true,
    metadata: {},
    memberships: [],
    member_count: 0,
    restricted_record_count: 0,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...over,
  };
}

/** Four teams: one stranded, and the three near misses around it. */
const TEAMS: Team[] = [
  // Holds two restricted records and has nobody on it. Locked out.
  makeTeam({ id: 'team-a', name: 'Client QS', member_count: 0, restricted_record_count: 2 }),
  // Empty, but restricts nothing. An unstaffed team is not itself a problem.
  makeTeam({ id: 'team-b', name: 'Groundworks', member_count: 0, restricted_record_count: 0 }),
  // Restricts records and has people who can read them. The normal case.
  makeTeam({ id: 'team-c', name: 'Cost team', member_count: 3, restricted_record_count: 2 }),
  // The API did not count restrictions for this shape at all.
  makeTeam({ id: 'team-d', name: 'Site staff', member_count: 0, restricted_record_count: null }),
];

function makeRestrictedRow(over: Partial<RestrictedEntityRow> = {}): RestrictedEntityRow {
  return {
    entity_type: 'file',
    entity_id: 'file-1',
    team_ids: ['team-a'],
    team_names: ['Client QS'],
    viewer_count: 0,
    enforced: true,
    ...over,
  };
}

function makeValidation(over: Partial<TeamsValidationReport> = {}): TeamsValidationReport {
  return {
    project_id: 'proj-1',
    // `skipped` with no findings renders nothing at all, which keeps the
    // banner out of the way of the assertions below.
    status: 'skipped',
    score: null,
    error_count: 0,
    warning_count: 0,
    findings: [],
    ...over,
  };
}

/* ── Harness ───────────────────────────────────────────────────────────── */

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/teams']}>
        <TeamsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The <Card> a team is drawn in - the explainer above uses the same words. */
function teamCard(name: string): HTMLElement {
  const heading = screen.getByRole('button', { name });
  const card = heading.closest('div')?.parentElement;
  expect(card, `no card around "${name}"`).toBeTruthy();
  return card as HTMLElement;
}

const STRANDED = /holds restrictions but has no members/;

/** The page opens on People, so the team cards are one tab away from a render. */
async function openTeamsTab() {
  fireEvent.click(await screen.findByRole('button', { name: 'Teams' }));
}

async function openRestrictedTab() {
  fireEvent.click(await screen.findByRole('button', { name: 'Restricted records' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Change who sees this' }));
  // The editor is open once the per-team boxes are on screen.
  await screen.findByRole('checkbox', { name: /Client QS/ });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listTeams).mockResolvedValue(TEAMS);
  vi.mocked(listMembers).mockResolvedValue([]);
  vi.mocked(listRestrictedEntities).mockResolvedValue([makeRestrictedRow()]);
  vi.mocked(listEntityTypes).mockResolvedValue([
    { key: 'file', label: 'File', module: 'files', enforced: true },
  ]);
  vi.mocked(validateProjectTeams).mockResolvedValue(makeValidation());
  vi.mocked(getAccessMatrix).mockResolvedValue({
    project_id: 'proj-1',
    restricted_record_count: 1,
    members: [],
  });
  vi.mocked(setEntityVisibility).mockResolvedValue({
    entity_type: 'file',
    entity_id: 'file-1',
    project_id: 'proj-1',
    restricted: false,
    teams: [],
    viewer_count: 0,
    enforced: true,
    caller_can_see: true,
  });
});

afterEach(() => cleanup());

/* ── Tests ─────────────────────────────────────────────────────────────── */

describe('TeamsPage stranded teams', () => {
  it('calls out a team that holds restrictions but has nobody on it', async () => {
    renderPage();
    await openTeamsTab();
    await screen.findByRole('button', { name: 'Client QS' });

    const card = teamCard('Client QS');
    expect(within(card).getByText(STRANDED)).toBeInTheDocument();
    // Drawn as a failure, not as a neutral fact: the restriction count and the
    // warning both carry the error colour.
    expect(card.querySelectorAll('.text-semantic-error').length).toBeGreaterThan(0);
  });

  it('leaves an empty team that restricts nothing alone', async () => {
    renderPage();
    await openTeamsTab();
    await screen.findByRole('button', { name: 'Groundworks' });

    // Without the "and it restricts something" half of the condition, every
    // team nobody has joined yet would scream.
    const card = teamCard('Groundworks');
    expect(within(card).queryByText(STRANDED)).toBeNull();
    expect(card.querySelector('.text-semantic-error')).toBeNull();
  });

  it('leaves a staffed team that restricts records alone', async () => {
    renderPage();
    await openTeamsTab();
    await screen.findByRole('button', { name: 'Cost team' });

    const card = teamCard('Cost team');
    expect(within(card).queryByText(STRANDED)).toBeNull();
    expect(card.querySelector('.text-semantic-error')).toBeNull();
    // The restriction count is still reported, just not as a problem.
    expect(within(card).getByText('Restricted records: 2')).toBeInTheDocument();
  });

  it('does not treat an uncounted restriction total as a lockout', async () => {
    renderPage();
    await openTeamsTab();
    await screen.findByRole('button', { name: 'Site staff' });

    // `restricted_record_count: null` means "not computed for this shape", not
    // "zero" and certainly not "many". Reading it as a number would make every
    // empty team on that response look stranded.
    const card = teamCard('Site staff');
    expect(within(card).queryByText(STRANDED)).toBeNull();
    expect(within(card).queryByText(/Restricted records:/)).toBeNull();
  });
});

describe('TeamsPage record visibility', () => {
  it('sends the union of the ticked teams, not just the one that changed', async () => {
    renderPage();
    await openRestrictedTab();

    // The record already belongs to Client QS. Adding the cost team must not
    // quietly take it away from the team that had it.
    fireEvent.click(screen.getByRole('checkbox', { name: /Cost team/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(setEntityVisibility).toHaveBeenCalledWith('proj-1', 'file', 'file-1', [
        'team-a',
        'team-c',
      ]);
    });
  });

  it('clears every team to lift the restriction rather than skipping the call', async () => {
    renderPage();
    await openRestrictedTab();

    fireEvent.click(screen.getByRole('checkbox', { name: /Client QS/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    // An empty list is the widest state this screen can produce: the record
    // returns to everyone on the project. Sending nothing at all, or resending
    // the original teams, would make a restriction impossible to lift here.
    await waitFor(() => {
      expect(setEntityVisibility).toHaveBeenCalledWith('proj-1', 'file', 'file-1', []);
    });
  });

  it('offers only the teams on this project, so nothing can be granted outward', async () => {
    renderPage();
    await openRestrictedTab();

    // One box per team on the project and no other - there is no control here
    // that could hand the record to somebody who is not already on it.
    expect(screen.getAllByRole('checkbox')).toHaveLength(TEAMS.length);
    expect(listTeams).toHaveBeenCalledWith('proj-1');
  });

  it('says out loud when a restricted record is readable by nobody', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Restricted records' }));

    // viewer_count 0: the record is narrowed to a team with no members, which
    // is the same lockout as the stranded team seen from the record's side.
    const line = await screen.findByText(/Nobody except the project owner/);
    expect(line.className).toContain('text-semantic-error');
  });
});
