// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Two dialogs around a commitment. The first writes down what was promised to
// whom, by whom and until when. The second moves it along: agreeing or
// withdrawing is a decision under the project's mandates, a breach needs a
// reason, and closing it needs proof that the stakeholder was told.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/shared/ui/Button';
import { ProjectPeopleSelect } from '@/shared/ui/ProjectPeopleSelect';
import { WideModal, WideModalField, WideModalSection } from '@/shared/ui/WideModal';

import {
  createCommitment,
  transitionCommitment,
  updateCommitment,
  type Commitment,
  type CommitmentInput,
  type CommitmentTarget,
  type EngagementEvent,
  type Stakeholder,
} from './api';
import { FIELD_CLASS, RefusalBox, TickList, useWrite } from './StakeholderBits';
import { COMMITMENT_ACTION, COMMITMENT_CATEGORY, vocab, type KeyText } from './labels';
import { TRANSITION_PROBLEM, toTransitionInput, transitionProblems, type TransitionDraft } from './rules';
import { stakeholderName, type Screen } from './screen';

export interface CommitmentDialogProps {
  screen: Screen;
  commitment: Commitment | null;
  stakeholders: Stakeholder[];
  events: EngagementEvent[];
  onClose: () => void;
  onSaved: () => void;
}

export function CommitmentDialog({ screen, commitment, stakeholders, events, onClose, onSaved }: CommitmentDialogProps) {
  const { t } = useTranslation();
  const { projectId, personName } = screen;
  const [draft, setDraft] = useState({
    text: commitment?.text ?? '',
    stakeholders: commitment?.stakeholder_ids ?? [],
    category: commitment?.category ?? 'other',
    owner: commitment?.owner_user_id ?? '',
    due_date: commitment?.due_date ?? '',
    verification: commitment?.verification ?? '',
    cost: commitment?.cost_estimate ?? '',
    currency: commitment?.currency ?? '',
    event: commitment?.source_kind === 'event' ? commitment.source_ref : '',
  });
  const set = <K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) => setDraft((d) => ({ ...d, [key]: value }));

  const write = useWrite(
    (body: CommitmentInput) =>
      commitment ? updateCommitment(projectId, commitment.id, body) : createCommitment(projectId, body),
    onSaved,
  );

  const ready = !!draft.text.trim() && draft.stakeholders.length > 0;

  const submit = () => {
    const body: CommitmentInput = {
      text: draft.text.trim(),
      stakeholder_ids: draft.stakeholders,
      category: draft.category,
      owner_user_id: draft.owner || null,
      due_date: draft.due_date || null,
      verification: draft.verification.trim(),
      cost_estimate: draft.cost.trim() || null,
    };
    if (draft.currency.trim()) body.currency = draft.currency.trim().toUpperCase();
    // The source is fixed once the commitment exists; the server ignores it on an edit.
    if (!commitment) {
      body.source_kind = draft.event ? 'event' : 'manual';
      if (draft.event) body.source_ref = draft.event;
    }
    write.run(body);
  };

  return (
    <WideModal
      open
      onClose={onClose}
      busy={write.busy}
      size="lg"
      testId="commitment-dialog"
      title={
        commitment
          ? t('stakeholders.ui.commitment.edit_title', { defaultValue: 'Edit commitment' })
          : t('stakeholders.ui.commitment.add_title', { defaultValue: 'Record a commitment' })
      }
      subtitle={t('stakeholders.ui.commitment.dialog_subtitle', {
        defaultValue: 'Something the project promised a stakeholder. It starts as proposed and binds once it is agreed.',
      })}
      footer={
        <div className="flex w-full items-center justify-end gap-3">
          <Button variant="ghost" onClick={onClose} disabled={write.busy}>
            {t('stakeholders.ui.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button loading={write.busy} disabled={!ready} onClick={submit} data-testid="commitment-save">
            {t('stakeholders.ui.save', { defaultValue: 'Save' })}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <RefusalBox refusal={write.refusal} />
        <WideModalField
          label={t('stakeholders.ui.commitment.text', { defaultValue: 'What was promised' })}
          required
          htmlFor="commitment-text"
        >
          <textarea
            id="commitment-text"
            rows={3}
            className={FIELD_CLASS}
            value={draft.text}
            onChange={(e) => set('text', e.target.value)}
          />
        </WideModalField>
        <WideModalField label={t('stakeholders.ui.commitment.to', { defaultValue: 'Promised to' })} required>
          <TickList
            testId="commitment-stakeholders"
            label={t('stakeholders.ui.commitment.to', { defaultValue: 'Promised to' })}
            emptyText={t('stakeholders.ui.plan.no_stakeholders', { defaultValue: 'The register has no stakeholders yet.' })}
            options={stakeholders
              .filter((s) => s.status !== 'archived' || draft.stakeholders.includes(s.id))
              .map((s) => ({ id: s.id, label: stakeholderName(t, s) }))}
            value={draft.stakeholders}
            onChange={(next) => set('stakeholders', next)}
          />
        </WideModalField>
        <WideModalSection columns={3}>
          <WideModalField label={t('stakeholders.ui.commitment.category', { defaultValue: 'About' })} htmlFor="commitment-category">
            <select
              id="commitment-category"
              className={FIELD_CLASS}
              value={draft.category}
              onChange={(e) => set('category', e.target.value)}
            >
              {Object.keys(COMMITMENT_CATEGORY).map((c) => (
                <option key={c} value={c}>
                  {vocab(t, COMMITMENT_CATEGORY, c)}
                </option>
              ))}
            </select>
          </WideModalField>
          <WideModalField
            label={t('stakeholders.ui.commitment.owner', { defaultValue: 'Who delivers it' })}
            hint={t('stakeholders.ui.commitment.owner_hint', { defaultValue: 'Needed before it can be agreed.' })}
          >
            <ProjectPeopleSelect
              projectId={projectId}
              value={draft.owner}
              displayValue={personName(draft.owner) ?? ''}
              onChange={(id) => set('owner', id)}
            />
          </WideModalField>
          <WideModalField
            label={t('stakeholders.ui.commitment.due', { defaultValue: 'Due date' })}
            hint={t('stakeholders.ui.commitment.owner_hint', { defaultValue: 'Needed before it can be agreed.' })}
            htmlFor="commitment-due"
          >
            <input
              id="commitment-due"
              type="date"
              className={FIELD_CLASS}
              value={draft.due_date}
              onChange={(e) => set('due_date', e.target.value)}
            />
          </WideModalField>
          <WideModalField
            label={t('stakeholders.ui.commitment.cost', { defaultValue: 'Estimated cost' })}
            hint={t('stakeholders.ui.commitment.cost_hint', { defaultValue: 'Optional. Leave empty when it costs nothing extra.' })}
            htmlFor="commitment-cost"
          >
            <input
              id="commitment-cost"
              inputMode="decimal"
              className={FIELD_CLASS}
              value={draft.cost}
              onChange={(e) => set('cost', e.target.value)}
            />
          </WideModalField>
          <WideModalField
            label={t('stakeholders.ui.commitment.currency', { defaultValue: 'Currency' })}
            hint={t('stakeholders.ui.commitment.currency_hint', { defaultValue: 'Empty means the project currency.' })}
            htmlFor="commitment-currency"
          >
            <input
              id="commitment-currency"
              className={FIELD_CLASS}
              value={draft.currency}
              maxLength={3}
              onChange={(e) => set('currency', e.target.value)}
            />
          </WideModalField>
          {!commitment && (
            <WideModalField
              label={t('stakeholders.ui.commitment.source', { defaultValue: 'Where it was promised' })}
              htmlFor="commitment-source"
            >
              <select
                id="commitment-source"
                className={FIELD_CLASS}
                value={draft.event}
                onChange={(e) => set('event', e.target.value)}
              >
                <option value="">{t('stakeholders.ui.commitment.source_manual', { defaultValue: 'Not at a recorded event' })}</option>
                {events.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.title}
                  </option>
                ))}
              </select>
            </WideModalField>
          )}
        </WideModalSection>
        <WideModalField
          label={t('stakeholders.ui.commitment.verification', { defaultValue: 'How you will know it is done' })}
          htmlFor="commitment-verification"
        >
          <textarea
            id="commitment-verification"
            rows={2}
            className={FIELD_CLASS}
            value={draft.verification}
            onChange={(e) => set('verification', e.target.value)}
          />
        </WideModalField>
      </div>
    </WideModal>
  );
}

const TRANSITION_HINT: Record<CommitmentTarget, KeyText> = {
  agreed: [
    'stakeholders.ui.transition.hint.agreed',
    'Agreeing binds the project. It is a decision of whoever decides commitments to stakeholders, and may go through an approval first.',
  ],
  in_progress: ['stakeholders.ui.transition.hint.in_progress', 'Work on the commitment has started.'],
  fulfilled: ['stakeholders.ui.transition.hint.fulfilled', 'What was promised is done. It still has to be verified and reported back.'],
  verified: [
    'stakeholders.ui.transition.hint.verified',
    'Closes the commitment. The stakeholder must have been told the outcome, or you say why that is not needed.',
  ],
  withdrawn: [
    'stakeholders.ui.transition.hint.withdrawn',
    'The project takes the commitment back. This is a decision under the mandates and needs a reason.',
  ],
  breached: [
    'stakeholders.ui.transition.hint.breached',
    'Confirms that the commitment was not kept. The reason goes on record.',
  ],
};

export const TRANSITION_KEY_MAPS = { TRANSITION_HINT };

export interface TransitionDialogProps {
  screen: Screen;
  commitment: Commitment;
  target: CommitmentTarget;
  onClose: () => void;
  onDone: (result: Commitment) => void;
}

export function TransitionDialog({ screen, commitment, target, onClose, onDone }: TransitionDialogProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<TransitionDraft>({
    target,
    rationale: '',
    toldOn: '',
    loopNotRequired: '',
    createRisk: false,
  });
  const problems = transitionProblems(draft, commitment);
  const write = useWrite(() => transitionCommitment(screen.projectId, commitment.id, toTransitionInput(draft)), onDone);
  const needsReason = target === 'withdrawn' || target === 'breached';

  return (
    <WideModal
      open
      onClose={onClose}
      busy={write.busy}
      size="md"
      testId="transition-dialog"
      title={vocab(t, COMMITMENT_ACTION, target)}
      subtitle={commitment.text}
      footer={
        <div className="flex w-full flex-wrap items-center justify-end gap-3">
          {problems.length > 0 && (
            <ul className="mr-auto space-y-0.5 text-xs text-semantic-error" data-testid="transition-problems">
              {problems.map((p) => (
                <li key={p} data-problem={p}>
                  {t(TRANSITION_PROBLEM[p][0], { defaultValue: TRANSITION_PROBLEM[p][1] })}
                </li>
              ))}
            </ul>
          )}
          <Button variant="ghost" onClick={onClose} disabled={write.busy}>
            {t('stakeholders.ui.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant={needsReason ? 'danger' : 'primary'}
            loading={write.busy}
            disabled={problems.length > 0}
            onClick={() => write.run(undefined)}
            data-testid="transition-submit"
          >
            {vocab(t, COMMITMENT_ACTION, target)}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <RefusalBox refusal={write.refusal} />
        <p className="text-sm text-content-secondary">{t(TRANSITION_HINT[target][0], { defaultValue: TRANSITION_HINT[target][1] })}</p>

        {target === 'verified' && (
          <WideModalSection columns={1}>
            <WideModalField
              label={t('stakeholders.ui.transition.told_on', { defaultValue: 'Day the stakeholder was told' })}
              htmlFor="transition-told"
            >
              <input
                id="transition-told"
                type="date"
                className={FIELD_CLASS}
                value={draft.toldOn}
                onChange={(e) => setDraft((d) => ({ ...d, toldOn: e.target.value }))}
              />
            </WideModalField>
            <WideModalField
              label={t('stakeholders.ui.transition.loop_not_required', { defaultValue: 'Or why telling them is not needed' })}
              htmlFor="transition-loop"
            >
              <textarea
                id="transition-loop"
                rows={2}
                className={FIELD_CLASS}
                value={draft.loopNotRequired}
                onChange={(e) => setDraft((d) => ({ ...d, loopNotRequired: e.target.value }))}
              />
            </WideModalField>
          </WideModalSection>
        )}

        {target !== 'verified' && (
          <WideModalField
            label={t('stakeholders.ui.transition.rationale', { defaultValue: 'Reason' })}
            required={needsReason}
            htmlFor="transition-rationale"
          >
            <textarea
              id="transition-rationale"
              rows={3}
              className={FIELD_CLASS}
              value={draft.rationale}
              onChange={(e) => setDraft((d) => ({ ...d, rationale: e.target.value }))}
            />
          </WideModalField>
        )}

        {target === 'breached' && !commitment.risk_id && (
          <label className="flex items-center gap-2 text-sm text-content-primary">
            <input
              type="checkbox"
              checked={draft.createRisk}
              onChange={(e) => setDraft((d) => ({ ...d, createRisk: e.target.checked }))}
              data-testid="transition-create-risk"
            />
            {t('stakeholders.ui.transition.create_risk', { defaultValue: 'Open a risk for this breach in the risk register' })}
          </label>
        )}
      </div>
    </WideModal>
  );
}
