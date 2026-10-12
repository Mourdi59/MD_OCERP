// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The panels and their dialogs against fixtures: which buttons a state shows,
// what a form refuses to send, what goes to the server, and how a refusal reads.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({ ProjectPeopleSelect: () => null }));
vi.mock('../api', async (importOriginal) => (await import('./apiMock')).apiMock(importOriginal));

import { ApiError } from '@/shared/lib/api';

import * as api from '../api';
import { SHELL, concept, matrix, page, progress, proof, unit } from './fixtures';
import { emptyProject, renderPage } from './harness';

const mocked = vi.mocked(api);

beforeEach(() => {
  vi.resetAllMocks();
  emptyProject(mocked);
});
afterEach(cleanup);

describe('concept tab', () => {
  it('keeps submit closed while the server says the concept is incomplete and lists why', async () => {
    mocked.getConcept.mockResolvedValue(
      concept({
        findings: [
          { code: 'standards_basis_missing', severity: 'error', ref: '', params: {} },
          { code: 'stage_without_owner', severity: 'warning', ref: 'factory_test', params: {} },
        ],
      }),
    );
    renderPage();
    expect(await screen.findByTestId('concept-submit')).toBeDisabled();
    expect(screen.getByTestId('concept-state')).toHaveTextContent('Draft');
    expect(screen.getByText('Open points: 1 stop the submission, 2 in all')).toBeInTheDocument();
    expect(screen.getByText('No standard is named yet')).toBeInTheDocument();
    expect(screen.getByText('Stage Factory acceptance test has no owner')).toBeInTheDocument();
    expect(screen.queryByTestId('plan-locked')).toBeNull();
  });

  it('submits when the server allows it and shows the refusal with every violation', async () => {
    mocked.getConcept.mockResolvedValue(concept({ can_submit: true }));
    mocked.submitConcept.mockRejectedValue(
      new ApiError(422, 'Unprocessable', {
        detail: {
          code: 'concept_incomplete',
          message: 'The concept is not complete.',
          violations: [{ code: 'package_without_proofs', severity: 'error', ref: 'pkg-shell', params: {} }],
        },
      }),
    );
    renderPage();
    fireEvent.click(await screen.findByTestId('concept-submit'));
    const note = await screen.findByTestId('refusal-note');
    expect(mocked.submitConcept).toHaveBeenCalledWith('p1');
    expect(note).toHaveTextContent('The concept is not complete.');
    expect(within(note).getByTestId('finding')).toHaveAttribute('data-code', 'package_without_proofs');
  });

  it('locks the plan in review and offers only the way back', async () => {
    mocked.getConcept.mockResolvedValue(concept({ state: 'in_review', revision_no: 1 }));
    mocked.conceptAction.mockResolvedValue(concept());
    renderPage();
    expect(await screen.findByTestId('plan-locked')).toBeInTheDocument();
    expect(screen.queryByTestId('concept-submit')).toBeNull();
    expect(screen.getByTestId('scope-edit')).toBeDisabled();
    fireEvent.click(screen.getByTestId('concept-return'));
    await waitFor(() => expect(mocked.conceptAction).toHaveBeenCalledWith('p1', 'return'));
  });

  it('offers no approval on this page in any state', async () => {
    mocked.getConcept.mockResolvedValue(concept({ state: 'approved' }));
    renderPage();
    expect(await screen.findByTestId('concept-revise')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /approve/i })).toBeNull();
  });

  it('refuses a package scope with a repeated reference and saves a clean one', async () => {
    mocked.patchConcept.mockResolvedValue(concept());
    renderPage();
    fireEvent.click(await screen.findByTestId('scope-edit'));
    fireEvent.click(screen.getByTestId('package-add'));
    const refs = screen.getAllByTestId('package-ref');
    fireEvent.change(refs[0]!, { target: { value: 'pkg-shell' } });
    fireEvent.change(refs[1]!, { target: { value: 'pkg-shell' } });
    expect(screen.getByTestId('form-problem')).toHaveTextContent('A reference is used twice');
    expect(screen.getByTestId('form-submit')).toBeDisabled();

    fireEvent.change(refs[1]!, { target: { value: 'pkg-roof' } });
    fireEvent.click(screen.getByTestId('form-submit'));
    await waitFor(() => expect(mocked.patchConcept).toHaveBeenCalled());
    expect(mocked.patchConcept.mock.calls[0]![1]).toEqual({
      packages: [
        { ref: 'pkg-shell', code: '', title: '', no_proofs_rationale: '' },
        { ref: 'pkg-roof', code: '', title: '', no_proofs_rationale: '' },
      ],
      holidays: [],
    });
  });
});

describe('proofs tab', () => {
  it('sends the reader to name the packages first', async () => {
    renderPage('proofs');
    expect(await screen.findByText('No proofs planned yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Name the packages' }));
    expect(await screen.findByTestId('concept-panel')).toBeInTheDocument();
  });

  it('accepts a delivered proof and never an open one', async () => {
    mocked.getConcept.mockResolvedValue(concept({ packages: [SHELL], applicable_packages: [SHELL] }));
    mocked.listProofs.mockResolvedValue(
      page([proof({ id: 'open' }), proof({ id: 'done', state: 'delivered', counted: 1 })]),
    );
    mocked.proofAction.mockResolvedValue(proof());
    renderPage('proofs');
    const rows = await screen.findAllByTestId('proof-entry');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).queryByTestId('proof-action-accept')).toBeNull();
    expect(within(rows[0]!).getByText('Pressure test')).toBeInTheDocument();
    fireEvent.click(within(rows[1]!).getByTestId('proof-action-accept'));
    await waitFor(() => expect(mocked.proofAction).toHaveBeenCalledWith('p1', 'done', 'accept'));
  });

  it('asks for a reason before a waiver is requested', async () => {
    mocked.listProofs.mockResolvedValue(page([proof()]));
    mocked.requestWaiver.mockResolvedValue(proof());
    renderPage('proofs');
    fireEvent.click(await screen.findByTestId('proof-action-request_waiver'));
    expect(screen.getByTestId('form-submit')).toBeDisabled();
    fireEvent.change(screen.getByTestId('waiver-reason'), { target: { value: ' Not part of this contract ' } });
    fireEvent.click(screen.getByTestId('form-submit'));
    await waitFor(() => expect(mocked.requestWaiver).toHaveBeenCalledWith('p1', 'pr1', 'Not part of this contract'));
  });

  it('turns a requested waiver into a decision', async () => {
    mocked.listProofs.mockResolvedValue(page([proof({ requested_by: 'u2', decision_rationale: 'Out of scope' })]));
    mocked.decideWaiver.mockResolvedValue(proof());
    renderPage('proofs');
    expect(await screen.findByTestId('waiver-pending')).toHaveTextContent('Waiver requested: Out of scope');
    expect(screen.queryByTestId('proof-action-request_waiver')).toBeNull();
    fireEvent.click(screen.getByTestId('proof-action-approve_waiver'));
    await waitFor(() => expect(mocked.decideWaiver).toHaveBeenCalledWith('p1', 'pr1', true));
  });
});

describe('stages tab', () => {
  it('says what a blocked stage waits for', async () => {
    mocked.getStageMatrix.mockResolvedValue(matrix([progress()]));
    renderPage('stages');
    fireEvent.click(await screen.findByTestId('matrix-cell'));
    const detail = screen.getByTestId('stage-detail');
    expect(detail).toHaveTextContent('Ventilation plant: Factory acceptance test');
    expect(within(detail).getByTestId('precondition')).toHaveAttribute('data-met', 'false');
    expect(detail).toHaveTextContent('Required proofs delivered');
    expect(detail).toHaveTextContent('Proofs are still missing');
    expect(within(detail).queryByTestId('stage-action-open_test')).toBeNull();
    expect(within(detail).queryByTestId('stage-action-request_release')).toBeNull();
  });

  it('asks for the release of a passed stage and says where it is decided', async () => {
    mocked.getStageMatrix.mockResolvedValue(
      matrix([progress({ state: 'passed', computed_state: 'passed', preconditions: [] })]),
    );
    mocked.requestStageRelease.mockResolvedValue({
      progress_id: 'sp1',
      hold_gate: { id: 'g1', gate_number: 4, required_party_role: 'qa', status: 'open' },
    });
    renderPage('stages');
    fireEvent.click(await screen.findByTestId('matrix-cell'));
    fireEvent.click(screen.getByTestId('stage-action-request_release'));
    const note = await screen.findByTestId('release-requested');
    expect(mocked.requestStageRelease).toHaveBeenCalledWith('p1', 'sp1');
    expect(note).toHaveTextContent('Client quality assurance');
  });

  it('wants a reason before a stage is marked not applicable', async () => {
    mocked.getStageMatrix.mockResolvedValue(matrix([progress()]));
    mocked.markStageNotApplicable.mockResolvedValue(progress());
    renderPage('stages');
    fireEvent.click(await screen.findByTestId('matrix-cell'));
    fireEvent.click(screen.getByTestId('stage-action-not_applicable'));
    expect(screen.getByTestId('form-submit')).toBeDisabled();
    fireEvent.change(screen.getByTestId('stage-na-reason'), { target: { value: 'No factory test for this plant' } });
    fireEvent.click(screen.getByTestId('form-submit'));
    await waitFor(() =>
      expect(mocked.markStageNotApplicable).toHaveBeenCalledWith('p1', 'sp1', 'No factory test for this plant'),
    );
  });
});

describe('acceptance tab', () => {
  it('explains the screen while nothing is planned', async () => {
    renderPage('acceptance');
    expect(await screen.findByText('No acceptance planned yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add acceptance unit' })).toBeInTheDocument();
  });

  it('requests an acceptance with the open points carried as reservations', async () => {
    mocked.listUnits.mockResolvedValue(page([unit({ unmet: [{ kind: 'defects', ref: 'd1' }] })]));
    mocked.requestAcceptance.mockResolvedValue(unit({ state: 'requested' }));
    renderPage('acceptance');
    const card = await screen.findByTestId('acceptance-unit');
    expect(within(card).getByTestId('unit-state')).toHaveTextContent('Planned');
    expect(within(card).queryByRole('button', { name: /^accept$/i })).toBeNull();
    fireEvent.click(within(card).getByTestId('unit-action-request'));
    const dialog = screen.getByTestId('unit-request-dialog');
    expect(dialog).toHaveTextContent('Open defect');
    fireEvent.click(screen.getByTestId('request-with-reservations'));
    fireEvent.click(screen.getByTestId('form-submit'));
    await waitFor(() => expect(mocked.requestAcceptance).toHaveBeenCalledWith('p1', 'u1', true));
  });

  it('shows the reason of the server inside the dialog when a request is refused', async () => {
    mocked.listUnits.mockResolvedValue(page([unit()]));
    mocked.requestAcceptance.mockRejectedValue(
      new ApiError(409, 'Conflict', {
        detail: {
          code: 'acceptance_preconditions_unmet',
          message_key: 'quality_concept.errors.acceptance_preconditions_unmet',
          message: 'Server text',
        },
      }),
    );
    renderPage('acceptance');
    fireEvent.click(await screen.findByTestId('unit-action-request'));
    fireEvent.click(screen.getByTestId('form-submit'));
    expect(await screen.findByTestId('refusal-note')).toHaveTextContent(
      'Acceptance cannot be requested: preconditions are not met.',
    );
    expect(screen.getByTestId('unit-request-dialog')).toBeInTheDocument();
  });

  it('lets an accepted unit confirm what the regime proposes, one effect at a time', async () => {
    mocked.listUnits.mockResolvedValue(
      page([
        unit({
          state: 'accepted',
          accepted_on: '2027-03-02',
          effects_proposed: [{ effect: 'risk_transfer', review_status: 'unconfirmed' }],
        }),
      ]),
    );
    mocked.confirmEffect.mockResolvedValue(unit());
    renderPage('acceptance');
    const row = await screen.findByTestId('effect-proposed');
    expect(row).toHaveTextContent('Risk passes to the client');
    expect(screen.queryByTestId('unit-action-request')).toBeNull();
    fireEvent.click(within(row).getByTestId('effect-confirm'));
    fireEvent.click(screen.getByTestId('form-submit'));
    await waitFor(() => expect(mocked.confirmEffect).toHaveBeenCalled());
    expect(mocked.confirmEffect.mock.calls[0]![2]).toMatchObject({ effect: 'risk_transfer' });
  });
});
