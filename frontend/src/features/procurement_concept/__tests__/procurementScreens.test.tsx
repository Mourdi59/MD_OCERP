// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The screens one by one: what each shows, which buttons the server's
// capability flags leave open, what a write sends, and how a refusal reads.

import type { ReactElement } from 'react';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/subcontractors/api', () => ({ listSubcontractors: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    conceptAction: vi.fn(),
    downloadExport: vi.fn(),
    setPackageState: vi.fn(),
    createExecution: vi.fn(),
    putPackage: vi.fn(),
    getThreshold: vi.fn(),
    listCandidates: vi.fn(),
    confirmShortlist: vi.fn(),
    deleteCandidate: vi.fn(),
    confirmSchedule: vi.fn(),
    createFramework: vi.fn(),
    patchFramework: vi.fn(),
    setFrameworkState: vi.fn(),
    getLedger: vi.fn(),
    deleteSounding: vi.fn(),
    createSounding: vi.fn(),
  };
});

import en from '@/app/locales/en';
import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import { AwardSchedule } from '../AwardSchedule';
import { ConceptRecord } from '../ConceptRecord';
import { Frameworks } from '../Frameworks';
import type { LabelContext } from '../labels';
import { MarketSoundings } from '../MarketSoundings';
import { PackageBoard } from '../PackageBoard';
import { PackageDialog } from '../PackageDialog';
import { PrequalPanel } from '../PrequalPanel';
import {
  agreementPackage,
  blockingFinding,
  catalogue,
  concept,
  framework,
  ledger,
  matrix,
  packageView,
  profile,
  schedule,
  soundingTight,
  thresholdCheck,
  unplannedPackage,
  warningFinding,
} from './fixtures';
import { enT } from './i18nMock';

const mocked = vi.mocked(api);
const labels: LabelContext = { t: enT as LabelContext['t'], language: 'en', exists: (k) => k in en.translation };
const refusal = (status: number, code: string, extra: Record<string, unknown> = {}) =>
  new ApiError(status, 'Refused', { detail: { code, message: 'server sentence', ...extra } });
const readOnly = () => concept({ can: { edit: false, approve: false, steer: false } });

function show(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}
const rowOf = (testId: string, attr: string, value: string) =>
  screen.getAllByTestId(testId).find((r) => r.getAttribute(attr) === value) as HTMLElement;

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

describe('PackageBoard', () => {
  const packages = [packageView(), unplannedPackage, agreementPackage];
  const board = (over: Partial<Parameters<typeof PackageBoard>[0]> = {}) => {
    const props = {
      projectId: 'p1',
      concept: concept(),
      packages,
      labels,
      onPlan: vi.fn(),
      onCandidates: vi.fn(),
      onChanged: vi.fn(),
      ...over,
    };
    show(<PackageBoard {...props} />);
    return props;
  };

  it('says where packages come from when the delivery model has none', () => {
    board({ packages: [] });
    expect(screen.getByText('The delivery model has no package plan yet.')).toBeInTheDocument();
    expect(screen.queryByTestId('package-board')).toBeNull();
  });

  it('shows a planned package with its value, threshold, procedure and state', () => {
    board();
    const row = rowOf('package-row', 'data-package', 'CP-01');
    expect(row).toHaveTextContent('Structural works');
    expect(row).toHaveTextContent('2,400,000');
    expect(within(row).getByTestId('threshold-badge')).toBeInTheDocument();
    expect(within(row).getByTestId('package-state')).toHaveTextContent('Procedure set');
    expect(within(row).getByTestId('package-plan')).toHaveTextContent('Change plan');
  });

  it('offers the first step on a package with no award plan', () => {
    const props = board();
    const row = rowOf('package-row', 'data-package', 'CP-03');
    expect(within(row).getByTestId('package-unplanned')).toBeInTheDocument();
    expect(within(row).queryByTestId('package-hold')).toBeNull();
    fireEvent.click(within(row).getByTestId('package-plan'));
    expect(props.onPlan).toHaveBeenCalledWith('k3');
  });

  it('offers no award plan for a package that is not procured on its own', () => {
    board();
    const row = rowOf('package-row', 'data-package', 'CP-00');
    expect(within(row).getByTestId('not-procured')).toBeInTheDocument();
    expect(within(row).queryByTestId('package-plan')).toBeNull();
    expect(within(row).queryByTestId('package-execution')).toBeNull();
  });

  it('puts a package on hold in one step', async () => {
    mocked.setPackageState.mockResolvedValue(undefined as never);
    const props = board();
    fireEvent.click(within(rowOf('package-row', 'data-package', 'CP-01')).getByTestId('package-hold'));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalled());
    expect(mocked.setPackageState.mock.calls[0]!.slice(0, 3)).toEqual(['p1', 'k1', 'hold']);
  });

  it('asks before cancelling, and sends nothing until the reader agrees', async () => {
    mocked.setPackageState.mockResolvedValue(undefined as never);
    board();
    const row = rowOf('package-row', 'data-package', 'CP-01');
    fireEvent.click(within(row).getByTestId('package-cancel'));
    expect(within(row).getByTestId('package-confirm')).toBeInTheDocument();
    expect(mocked.setPackageState).not.toHaveBeenCalled();
    fireEvent.click(within(row).getByTestId('package-confirm-yes'));
    await waitFor(() => expect(mocked.setPackageState).toHaveBeenCalledTimes(1));
    expect(mocked.setPackageState.mock.calls[0]!.slice(0, 3)).toEqual(['p1', 'k1', 'cancel']);
  });

  it('creates the bid package only after a confirmation', async () => {
    mocked.createExecution.mockResolvedValue(undefined as never);
    board();
    const row = rowOf('package-row', 'data-package', 'CP-01');
    expect(within(row).getByTestId('package-execution')).toHaveTextContent('Create bid package');
    fireEvent.click(within(row).getByTestId('package-execution'));
    expect(mocked.createExecution).not.toHaveBeenCalled();
    fireEvent.click(within(row).getByTestId('package-confirm-yes'));
    await waitFor(() => expect(mocked.createExecution).toHaveBeenCalledWith('p1', 'k1'));
  });

  it('shows the reason of a refused move', async () => {
    mocked.setPackageState.mockRejectedValue(refusal(409, 'concept_locked'));
    board();
    fireEvent.click(within(rowOf('package-row', 'data-package', 'CP-01')).getByTestId('package-hold'));
    expect(await screen.findByTestId('refusal-box')).toHaveAttribute('data-code', 'concept_locked');
  });

  it('keeps every write closed, with the reason, for a reader the server gave no rights', () => {
    board({ concept: readOnly() });
    const row = rowOf('package-row', 'data-package', 'CP-01');
    expect(within(row).getByTestId('package-plan')).toBeDisabled();
    expect(within(row).getByTestId('package-hold')).toBeDisabled();
    expect(within(row).getByTestId('package-cancel')).toBeDisabled();
    expect(screen.getByTestId('board-locked')).toHaveTextContent(en.translation['procurement_concept.errors.not_procurement_owner']!);
    // Reading the candidates stays open.
    expect(within(row).getByTestId('package-candidates')).toBeEnabled();
  });

  it('locks the plan but leaves steering open once the concept is approved', () => {
    board({ concept: concept({ state: 'approved', can: { edit: false, approve: false, steer: true } }) });
    const row = rowOf('package-row', 'data-package', 'CP-01');
    expect(within(row).getByTestId('package-plan')).toBeDisabled();
    expect(within(row).getByTestId('package-hold')).toBeEnabled();
  });
});

describe('ConceptRecord', () => {
  const record = (over: Partial<Parameters<typeof ConceptRecord>[0]> = {}) => {
    const props = {
      projectId: 'p1',
      concept: concept(),
      findings: [blockingFinding, warningFinding],
      findingsLoading: false,
      labels,
      refLabel: (ref: string) => ref,
      onEdit: vi.fn(),
      onChanged: vi.fn(),
      ...over,
    };
    show(<ConceptRecord {...props} />);
    return props;
  };

  it('lists what blocks approval before the warnings', () => {
    record();
    expect(screen.getByTestId('concept-findings')).toHaveTextContent('Blocking approval: 1. Warnings: 1.');
    const items = within(screen.getByTestId('finding-list')).getAllByRole('listitem');
    expect(items.map((i) => i.getAttribute('data-blocking'))).toEqual(['yes', 'no']);
    expect(items[0]).toHaveTextContent(en.translation['procurement_concept.findings.package_without_procedure_plan']!);
  });

  it('says so when the rule check found nothing', () => {
    record({ findings: [] });
    expect(screen.getByTestId('concept-findings')).toHaveTextContent('Nothing found.');
  });

  it('submits a draft for review', async () => {
    mocked.conceptAction.mockResolvedValue(concept({ state: 'in_review' }) as never);
    const props = record();
    fireEvent.click(screen.getByTestId('concept-submit'));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalled());
    expect(mocked.conceptAction.mock.calls[0]!.slice(0, 2)).toEqual(['p1', 'submit']);
  });

  it('a refused approval lists every finding the server named', async () => {
    mocked.conceptAction.mockRejectedValue(refusal(409, 'blocking_findings', { violations: [blockingFinding] }));
    record({ concept: concept({ state: 'in_review', can: { edit: false, approve: true, steer: true } }) });
    fireEvent.click(screen.getByTestId('concept-approve'));
    const box = await screen.findByTestId('refusal-box');
    expect(box).toHaveAttribute('data-code', 'blocking_findings');
    expect(within(box).getByTestId('refusal-violations').querySelector('[data-finding="package_without_procedure_plan"]')).not.toBeNull();
  });

  it('keeps approve closed for a reviewer the server did not allow', () => {
    record({ concept: concept({ state: 'in_review', can: { edit: false, approve: false, steer: true } }) });
    expect(screen.getByTestId('concept-approve')).toBeDisabled();
    expect(screen.getByTestId('concept-return')).toBeEnabled();
  });

  it('reopens only with a reason', async () => {
    mocked.conceptAction.mockResolvedValue(concept({ state: 'reopened' }) as never);
    record({ concept: concept({ state: 'approved', can: { edit: false, approve: false, steer: true } }) });
    fireEvent.click(screen.getByTestId('concept-reopen'));
    expect(mocked.conceptAction).not.toHaveBeenCalled();
    expect(screen.getByTestId('concept-reopen-confirm')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Why the concept is reopened (required)'), { target: { value: ' Scope of the facade changed ' } });
    fireEvent.click(screen.getByTestId('concept-reopen-confirm'));
    await waitFor(() => expect(mocked.conceptAction).toHaveBeenCalledWith('p1', 'reopen', 'Scope of the facade changed'));
  });

  it('offers no lifecycle step on a binding concept', () => {
    record({ concept: concept({ state: 'binding', can: { edit: false, approve: false, steer: true } }) });
    for (const action of ['submit', 'approve', 'return', 'reopen']) expect(screen.queryByTestId(`concept-${action}`)).toBeNull();
    expect(screen.getByTestId('concept-edit')).toBeDisabled();
  });

  it('downloads the printable record', async () => {
    mocked.downloadExport.mockResolvedValue(undefined as never);
    record();
    fireEvent.click(screen.getByTestId('export-concept'));
    await waitFor(() => expect(mocked.downloadExport).toHaveBeenCalledWith('p1', 'concept', 'pdf'));
  });
});

describe('PackageDialog', () => {
  const dialog = (view = packageView()) => {
    const props = {
      open: true,
      onClose: vi.fn(),
      projectId: 'p1',
      view,
      catalogue,
      frameworks: [framework],
      profiles: [profile],
      labels,
      onSaved: vi.fn(),
    };
    show(<PackageDialog {...props} />);
    return props;
  };

  it('asks for the value first on a package without an award plan, and does not ask the server for a check', () => {
    dialog(unplannedPackage);
    expect(screen.getByTestId('threshold-pending')).toBeInTheDocument();
    expect(mocked.getThreshold).not.toHaveBeenCalled();
    // The catalogue's procedures are offered until the check narrows them.
    expect(screen.getAllByTestId('procedure-option')).toHaveLength(2);
  });

  it('shows the threshold check and marks the procedures it rules out', async () => {
    mocked.getThreshold.mockResolvedValue(thresholdCheck);
    dialog();
    expect(await screen.findByTestId('threshold-status')).toBeInTheDocument();
    expect(mocked.getThreshold.mock.calls[0]!.slice(0, 2)).toEqual(['p1', 'k1']);
    const options = screen.getAllByTestId('procedure-option');
    expect(options.map((o) => o.getAttribute('data-allowed'))).toEqual(['yes', 'no']);
    expect(within(screen.getByTestId('threshold-rows')).getByText(/5,538,000/)).toBeInTheDocument();
  });

  it('sends only what changed, the amount as a string', async () => {
    mocked.getThreshold.mockResolvedValue(thresholdCheck);
    mocked.putPackage.mockResolvedValue(packageView() as never);
    const props = dialog();
    fireEvent.change(document.getElementById('pk-value') as HTMLInputElement, { target: { value: '2500000.50' } });
    fireEvent.click(screen.getByTestId('package-save'));
    await waitFor(() => expect(props.onSaved).toHaveBeenCalledWith(false));
    expect(mocked.putPackage).toHaveBeenCalledWith('p1', 'k1', { estimated_value: '2500000.50' });
  });

  it('refuses a value that is not a number before anything is sent', () => {
    dialog(unplannedPackage);
    fireEvent.change(document.getElementById('pk-value') as HTMLInputElement, { target: { value: 'about two million' } });
    expect(screen.getByTestId('package-save')).toBeDisabled();
    expect(screen.getByTestId('form-problems')).toBeInTheDocument();
  });

  it('shows the server reason when the save is refused', async () => {
    mocked.putPackage.mockRejectedValue(refusal(422, 'procedure_not_allowed'));
    dialog(unplannedPackage);
    fireEvent.change(document.getElementById('pk-value') as HTMLInputElement, { target: { value: '100' } });
    fireEvent.change(document.getElementById('pk-currency') as HTMLInputElement, { target: { value: 'eur' } });
    fireEvent.click(screen.getByTestId('package-save'));
    expect(await screen.findByTestId('refusal-box')).toHaveAttribute('data-code', 'procedure_not_allowed');
    expect(mocked.putPackage).toHaveBeenCalledWith('p1', 'k3', { estimated_value: '100', currency: 'EUR' });
  });
});

describe('PrequalPanel', () => {
  const panel = (over: Partial<Parameters<typeof PrequalPanel>[0]> = {}) => {
    const props = {
      projectId: 'p1',
      concept: concept(),
      packages: [packageView(), unplannedPackage],
      profiles: [profile],
      catalogue,
      packageId: null,
      labels,
      onSelectPackage: vi.fn(),
      onGoToPackages: vi.fn(),
      onChanged: vi.fn(),
      ...over,
    };
    show(<PrequalPanel {...props} />);
    return props;
  };

  it('sends the reader to the packages while none has an award plan', () => {
    const props = panel({ packages: [unplannedPackage] });
    expect(screen.getByText('No package has an award plan yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Packages' }));
    expect(props.onGoToPackages).toHaveBeenCalled();
    expect(mocked.listCandidates).not.toHaveBeenCalled();
  });

  it('shows the candidates with their scores, and what the short list still lacks', async () => {
    mocked.listCandidates.mockResolvedValue(matrix());
    panel();
    expect(await screen.findByTestId('candidate-matrix')).toBeInTheDocument();
    const rows = screen.getAllByTestId('candidate-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByTestId('candidate-total')).toHaveTextContent('82.8');
    expect(within(rows[1]!).getByTestId('candidate-unregistered')).toBeInTheDocument();
    expect(screen.getByTestId('shortlist-check').querySelector('[data-finding="shortlist_below_min_bidders"]')).not.toBeNull();
  });

  it('confirms the short list of the package on screen', async () => {
    mocked.listCandidates.mockResolvedValue(matrix({ findings: [] }));
    mocked.confirmShortlist.mockResolvedValue(undefined as never);
    const props = panel();
    fireEvent.click(await screen.findByTestId('shortlist-confirm'));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalled());
    expect(mocked.confirmShortlist).toHaveBeenCalledWith('p1', 'k1');
  });

  it('shows why the short list was refused', async () => {
    mocked.listCandidates.mockResolvedValue(matrix());
    mocked.confirmShortlist.mockRejectedValue(
      refusal(409, 'shortlist_not_confirmable', { violations: [{ code: 'shortlist_below_min_bidders', severity: 'error', ref: 'CP-01', blocks_approval: true }] }),
    );
    panel();
    fireEvent.click(await screen.findByTestId('shortlist-confirm'));
    expect(await screen.findByTestId('refusal-box')).toHaveAttribute('data-code', 'shortlist_not_confirmable');
  });

  it('asks before removing a candidate', async () => {
    mocked.listCandidates.mockResolvedValue(matrix());
    mocked.deleteCandidate.mockResolvedValue(undefined as never);
    panel();
    await screen.findByTestId('candidate-matrix');
    fireEvent.click(screen.getAllByTestId('candidate-remove')[1]!);
    expect(mocked.deleteCandidate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('candidate-remove-yes'));
    await waitFor(() => expect(mocked.deleteCandidate).toHaveBeenCalledWith('p1', 'cand2'));
  });

  it('keeps the confirmation closed for a reader the server gave no rights', async () => {
    mocked.listCandidates.mockResolvedValue(matrix());
    panel({ concept: readOnly() });
    expect(await screen.findByTestId('shortlist-confirm')).toBeDisabled();
  });
});

describe('AwardSchedule', () => {
  const view = (over: Partial<Parameters<typeof AwardSchedule>[0]> = {}) => {
    const props = { projectId: 'p1', concept: concept(), schedule, labels, onGoToPackages: vi.fn(), onChanged: vi.fn(), ...over };
    show(<AwardSchedule {...props} />);
    return props;
  };

  it('explains what feeds the schedule when there is nothing to plan', () => {
    view({ schedule: { ...schedule, items: [], total: 0 } });
    expect(screen.getByText('No award dates to plan yet')).toBeInTheDocument();
  });

  it('shows the proposal, and says what a row without dates still needs', () => {
    view();
    const ready = rowOf('schedule-row', 'data-package', 'CP-01');
    expect(within(ready).getByTestId('schedule-proposed')).toBeInTheDocument();
    expect(ready).toHaveTextContent('83 days');
    const open = rowOf('schedule-row', 'data-package', 'CP-03');
    expect(within(open).getByTestId('schedule-incomplete')).toBeInTheDocument();
    expect(within(open).getByRole('checkbox')).toBeDisabled();
    expect(within(open).getByTestId('schedule-findings').querySelector('[data-finding="need_date_missing"]')).not.toBeNull();
  });

  it('writes nothing to the project schedule until the reader confirms, then only the rows picked', async () => {
    mocked.confirmSchedule.mockResolvedValue({ items: [schedule.items[0]!], total: 1, offset: 0, limit: 1 } as never);
    const props = view();
    expect(mocked.confirmSchedule).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('schedule-confirm'));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalled());
    expect(mocked.confirmSchedule).toHaveBeenCalledWith('p1', ['k1']);
    expect(await screen.findByTestId('schedule-confirmed')).toHaveTextContent('Packages: 1.');
  });

  it('has nothing to confirm once every row is unpicked', () => {
    view();
    fireEvent.click(within(rowOf('schedule-row', 'data-package', 'CP-01')).getByRole('checkbox'));
    expect(screen.getByTestId('schedule-confirm')).toBeDisabled();
  });

  it('marks a row whose milestones are already in the schedule and does not pick it again', () => {
    const done = { ...schedule.items[0]!, start_activity_id: 'a1', award_activity_id: 'a2' };
    view({ schedule: { ...schedule, items: [done] } });
    expect(screen.getByTestId('schedule-in')).toBeInTheDocument();
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });

  it('shows the reason of a refused confirmation', async () => {
    mocked.confirmSchedule.mockRejectedValue(refusal(403, 'not_procurement_owner'));
    view();
    fireEvent.click(screen.getByTestId('schedule-confirm'));
    expect(await screen.findByTestId('refusal-box')).toHaveAttribute('data-code', 'not_procurement_owner');
    expect(screen.queryByTestId('schedule-confirmed')).toBeNull();
  });
});

describe('Frameworks', () => {
  const view = (frameworks = [framework]) => {
    const props = { frameworks, labels, onChanged: vi.fn() };
    show(<Frameworks {...props} />);
    return props;
  };

  it('says what a framework agreement is for and offers to add the first one', () => {
    view([]);
    expect(screen.getByText('No framework agreements yet')).toBeInTheDocument();
    expect(screen.getByTestId('framework-add')).toBeInTheDocument();
  });

  it('shows an agreement with its ceiling, period and what it covers', () => {
    view();
    const entry = screen.getByTestId('framework-entry');
    expect(entry).toHaveTextContent('FW-SUPPLY-01');
    expect(entry).toHaveTextContent('2,500,000');
    expect(within(entry).getByTestId('framework-state')).toHaveTextContent('Active');
  });

  it('opens the call-offs with what is used and what remains', async () => {
    mocked.getLedger.mockResolvedValue(ledger);
    view();
    fireEvent.click(screen.getByTestId('framework-ledger-toggle'));
    expect(await screen.findByTestId('ledger-remaining')).toHaveTextContent('2,190,000');
    expect(screen.getByTestId('ledger-called-off')).toHaveTextContent('310,000');
    expect(screen.getAllByTestId('ledger-entry')).toHaveLength(1);
    expect(mocked.getLedger.mock.calls[0]![0]).toBe('fw1');
  });

  it('asks before closing an agreement for good', async () => {
    mocked.setFrameworkState.mockResolvedValue(framework as never);
    view();
    fireEvent.click(screen.getByTestId('framework-move-terminated'));
    expect(mocked.setFrameworkState).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('framework-close-yes'));
    await waitFor(() => expect(mocked.setFrameworkState).toHaveBeenCalledWith('fw1', 'terminated'));
  });

  it('shows the reason when the server refuses the move', async () => {
    mocked.setFrameworkState.mockRejectedValue(refusal(403, 'permission_denied'));
    view();
    fireEvent.click(screen.getByTestId('framework-move-exhausted'));
    expect(await screen.findByTestId('refusal-box')).toHaveAttribute('data-code', 'permission_denied');
  });

  it('creates an agreement with its ceiling as a string', async () => {
    mocked.createFramework.mockResolvedValue(framework as never);
    const props = view([]);
    fireEvent.click(screen.getByTestId('framework-add'));
    expect(screen.getByTestId('framework-save')).toBeDisabled();
    const type = (id: string, value: string) => fireEvent.change(document.getElementById(id) as HTMLInputElement, { target: { value } });
    type('fw-code', ' FW-02 ');
    type('fw-title', 'Scaffolding framework');
    type('fw-max', '750000');
    type('fw-currency', 'eur');
    type('fw-start', '2026-11-01');
    type('fw-end', '2028-10-31');
    fireEvent.click(screen.getByTestId('framework-save'));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalled());
    const body = mocked.createFramework.mock.calls[0]![0];
    expect(body).toMatchObject({ code: 'FW-02', max_value: '750000', currency: 'EUR', start_date: '2026-11-01', end_date: '2028-10-31' });
    expect(typeof body.max_value).toBe('string');
  });
});

describe('MarketSoundings', () => {
  const view = (soundings = [soundingTight]) => {
    const props = { projectId: 'p1', soundings, packages: [packageView()], labels, onChanged: vi.fn() };
    show(<MarketSoundings {...props} />);
    return props;
  };

  it('says what a market sounding is for and offers to record the first one', () => {
    view([]);
    expect(screen.getByTestId('market-soundings')).toBeInTheDocument();
    expect(screen.getByTestId('sounding-add')).toBeInTheDocument();
    expect(screen.queryByTestId('sounding-entry')).toBeNull();
  });

  it('flags a tight market that has no answer yet', () => {
    view();
    const entry = screen.getByTestId('sounding-entry');
    expect(entry).toHaveTextContent('Structural steel');
    expect(entry).toHaveTextContent('CP-01');
    expect(within(entry).getByTestId('sounding-unmitigated')).toBeInTheDocument();
  });

  it('does not flag a sounding the server counts as answered', () => {
    view([{ ...soundingTight, mitigation: 'Split the steel into two lots', unmitigated: false }]);
    expect(screen.queryByTestId('sounding-unmitigated')).toBeNull();
  });

  it('asks before removing a sounding', async () => {
    mocked.deleteSounding.mockResolvedValue(undefined as never);
    const props = view();
    fireEvent.click(screen.getByTestId('sounding-remove'));
    expect(mocked.deleteSounding).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('sounding-remove-yes'));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalled());
    expect(mocked.deleteSounding).toHaveBeenCalledWith('p1', 'ms1');
  });
});
