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
import { MAY_SUBMIT, NOT_MANAGER, PLAN_CLOSED, SHELL, concept, matrix, page, progress, proof, unit } from './fixtures';
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
    expect(await screen.findByText('Stage Factory acceptance test has no owner')).toBeInTheDocument();
    expect(screen.getByTestId('concept-next-step')).toHaveTextContent('Clear the open points below');
    expect(screen.queryByTestId('plan-locked')).toBeNull();
  });

  it('submits when the server allows it and shows the refusal with every violation', async () => {
    mocked.getConcept.mockResolvedValue(concept({ can: MAY_SUBMIT }));
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
    mocked.getConcept.mockResolvedValue(concept({ state: 'in_review', revision_no: 1, can: PLAN_CLOSED }));
    mocked.conceptAction.mockResolvedValue(concept());
    renderPage();
    expect(await screen.findByTestId('plan-locked')).toBeInTheDocument();
    expect(screen.queryByTestId('concept-submit')).toBeNull();
    expect(screen.getByTestId('scope-edit')).toBeDisabled();
    fireEvent.click(screen.getByTestId('concept-return'));
    await waitFor(() => expect(mocked.conceptAction).toHaveBeenCalledWith('p1', 'return'));
  });

  it('offers no approval on this page in any state', async () => {
    mocked.getConcept.mockResolvedValue(concept({ state: 'approved', can: PLAN_CLOSED }));
    renderPage();
    expect(await screen.findByTestId('concept-next-step')).toHaveTextContent('The concept is approved.');
    expect(screen.queryByRole('button', { name: /approv|revis|reopen/i })).toBeNull();
    expect(screen.queryByTestId('concept-submit')).toBeNull();
    expect(screen.queryByTestId('concept-return')).toBeNull();
  });

  it('follows the server when the reader may not manage the plan', async () => {
    mocked.getConcept.mockResolvedValue(concept({ can: NOT_MANAGER }));
    renderPage();
    expect(await screen.findByTestId('concept-submit')).toBeDisabled();
    expect(screen.getByTestId('concept-next-step')).toHaveTextContent(
      'Only a manager or the owner of the quality area can submit the concept.',
    );
    expect(screen.getByTestId('plan-locked')).toHaveTextContent('can change the plan');
    expect(screen.getByTestId('scope-edit')).toBeDisabled();
    expect(await screen.findByTestId('standard-add')).toBeDisabled();
  });

  it('creates the handover documents of the chosen set and says how many', async () => {
    mocked.getConcept.mockResolvedValue(concept({ documentation_set_code: 'residential' }));
    mocked.applyDocumentationSet.mockResolvedValue({ slots_added: ['om_manual', 'warranties'], fm_data_added: ['asset_dataset'] });
    renderPage();
    fireEvent.click(await screen.findByTestId('documentation-set-apply'));
    expect(await screen.findByTestId('documentation-set-applied')).toHaveTextContent(
      'Handover documents and data deliverables created: 3',
    );
    expect(mocked.applyDocumentationSet).toHaveBeenCalledWith('p1');
  });

  it('keeps that step closed until a set is chosen', async () => {
    renderPage();
    expect(await screen.findByTestId('documentation-set-apply')).toBeDisabled();
  });

  it('refuses a package scope with a repeated reference and saves a clean one', async () => {
    mocked.patchConcept.mockResolvedValue(concept());
    renderPage();
    fireEvent.click(await screen.findByTestId('scope-edit'));
    fireEvent.click(screen.getByTestId('package-add'));
    const refs = screen.getAllByTestId('package-ref');
    fireEvent.change(refs[0]!, { target: { value: 'pkg-shell' } });
    fireEvent.change(refs[1]!, { target: { value: 'pkg-shell' } });
    expect(screen.getByTestId('form-problem')).toHaveTextContent('A package reference appears twice');
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

  it('shows an unreadable precondition as not applicable, never as passed', async () => {
    mocked.getStageMatrix.mockResolvedValue(
      matrix([
        progress({
          preconditions: [
            { code: 'plant_item_delivered', met: true, reason: 'no_plant_register', params: { not_applicable: true } },
          ],
        }),
      ]),
    );
    renderPage('stages');
    fireEvent.click(await screen.findByTestId('matrix-cell'));
    const row = screen.getByTestId('precondition');
    expect(row).toHaveAttribute('data-met', 'not-applicable');
    expect(row).toHaveTextContent('Equipment delivered');
    expect(row).toHaveTextContent('Not applicable');
    expect(row).toHaveTextContent('No equipment register is installed');
  });

  it('brings a stage back that was marked not applicable', async () => {
    mocked.getStageMatrix.mockResolvedValue(
      matrix([progress({ state: 'not_applicable', computed_state: 'not_applicable', rationale: 'Bought as a unit' })]),
    );
    mocked.reinstateStage.mockResolvedValue(progress());
    renderPage('stages');
    fireEvent.click(await screen.findByTestId('matrix-cell'));
    expect(screen.getByTestId('stage-detail')).toHaveTextContent('Bought as a unit');
    fireEvent.click(screen.getByTestId('stage-action-reinstate'));
    await waitFor(() => expect(mocked.reinstateStage).toHaveBeenCalledWith('p1', 'sp1'));
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

  it('offers an effect again once its confirmation was revoked', async () => {
    const revoked = {
      id: 'e1',
      unit_id: 'u1',
      effect: 'risk_transfer',
      effective_date: '2027-03-02',
      source_url: null,
      review_status: 'unconfirmed',
      confirmed_by: 'u9',
      confirmed_at: '2027-03-03T08:00:00Z',
      outcome: { revoked_at: '2027-03-05T08:00:00Z' },
    };
    mocked.listUnits.mockResolvedValue(
      page([
        unit({
          state: 'accepted',
          effects_applied: [revoked],
          effects_proposed: [{ effect: 'risk_transfer', review_status: 'unconfirmed' }],
        }),
      ]),
    );
    renderPage('acceptance');
    expect(await screen.findByTestId('effect-proposed')).toHaveTextContent('Risk passes to the client');
    expect(screen.queryByTestId('effect-applied')).toBeNull();
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
    mocked.confirmEffect.mockResolvedValue({
      id: 'e1',
      unit_id: 'u1',
      effect: 'risk_transfer',
      effective_date: '2027-03-02',
      source_url: null,
      review_status: 'unconfirmed',
      confirmed_by: 'u9',
      confirmed_at: '2027-03-03T08:00:00Z',
      outcome: {},
    });
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

describe('a reader who may not manage the plan', () => {
  beforeEach(() => {
    mocked.getConcept.mockResolvedValue(concept({ can: NOT_MANAGER }));
  });

  it('can request an acceptance and record dates, and nothing that changes the plan', async () => {
    mocked.listUnits.mockResolvedValue(page([unit({ state: 'requested' }), unit({ id: 'u2', code: 'AU-2' })]));
    renderPage('acceptance');
    const cards = await screen.findAllByTestId('acceptance-unit');
    expect(screen.getByTestId('unit-add')).toBeDisabled();
    expect(within(cards[0]!).getByTestId('unit-action-record_dates')).toBeEnabled();
    expect(within(cards[0]!).getByTestId('unit-action-refuse')).toBeDisabled();
    expect(within(cards[0]!).getByTestId('unit-action-schedule_inspection')).toBeDisabled();
    expect(within(cards[0]!).getByTestId('unit-action-withdraw')).toBeDisabled();
    expect(within(cards[1]!).getByTestId('unit-action-request')).toBeEnabled();
  });

  it('gets no add button on an empty acceptance plan', async () => {
    renderPage('acceptance');
    expect(await screen.findByText('No acceptance planned yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add acceptance unit' })).toBeNull();
  });

  it('can run a stage test but not take the stage out of the plan', async () => {
    mocked.getStageMatrix.mockResolvedValue(
      matrix([progress({ state: 'ready', computed_state: 'ready', preconditions: [] })]),
    );
    renderPage('stages');
    fireEvent.click(await screen.findByTestId('matrix-cell'));
    expect(screen.getByTestId('stage-action-open_test')).toBeEnabled();
    expect(screen.getByTestId('stage-action-not_applicable')).toBeDisabled();
    expect(screen.getByTestId('stage-depends')).toBeDisabled();
  });

  it('is not offered the catalogue stages on an empty stage plan', async () => {
    renderPage('stages');
    expect(await screen.findByText('No commissioning stages yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Use the catalogue stages' })).toBeNull();
  });

  it('cannot add a certification target', async () => {
    renderPage('certification');
    expect(await screen.findByText('No certification target')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add certification target' })).toBeNull();
  });
});
