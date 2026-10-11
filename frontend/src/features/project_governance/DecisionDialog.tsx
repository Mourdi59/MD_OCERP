// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Recording a gate decision. The outcome comes first, because it decides what
// else the record must carry: a reason for anything but a plain go, at least
// one condition with an owner and a date for a go with conditions, a resume
// date for a hold. The submit button stays disabled and lists what is missing
// until the draft is complete; the server repeats every check.

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Trash2 } from 'lucide-react';
import clsx from 'clsx';

import { Button } from '@/shared/ui/Button';
import { WideModal } from '@/shared/ui/WideModal';
import { ProjectPeopleSelect } from '@/shared/ui/ProjectPeopleSelect';

import type { GateDetail, Outcome, Severity, Violation } from './api';
import {
  DECISION_PROBLEM,
  atRiskCandidates,
  decisionProblems,
  needsRationale,
  notApplicableAreas,
  toDecisionInput,
  type ConditionDraft,
  type DecisionDraft,
} from './decisionRules';
import { OUTCOME, OUTCOME_HINT, SEVERITY, catalogueName, errorText, vocab, type LabelContext } from './labels';
import type { DecisionInput } from './api';

const OUTCOMES: Outcome[] = ['go', 'go_with_conditions', 'hold', 'recycle', 'stop'];
const SEVERITIES: Severity[] = ['critical', 'essential', 'recommended'];

let rowSeq = 0;
function newCondition(): ConditionDraft {
  rowSeq += 1;
  return { rowId: `c${rowSeq}`, text: '', severity: 'essential', area_code: '', owner_user_id: '', due_date: '' };
}

export interface DecisionDialogProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
  detail: GateDetail;
  catalogueId: string;
  labels: LabelContext;
  today: string;
  busy: boolean;
  /** Blockers the server answered with on the last attempt, shown at the top. */
  serverViolations: Violation[];
  serverError: string | null;
  onSubmit: (input: DecisionInput) => void;
}

export function DecisionDialog({
  open,
  onClose,
  projectId,
  detail,
  catalogueId,
  labels,
  today,
  busy,
  serverViolations,
  serverError,
  onSubmit,
}: DecisionDialogProps) {
  const { t } = useTranslation();
  const naAreas = useMemo(() => notApplicableAreas(detail), [detail]);
  const riskAreas = useMemo(() => atRiskCandidates(detail), [detail]);
  const [draft, setDraft] = useState<DecisionDraft>({
    outcome: null,
    rationale: '',
    conditions: [],
    proceedAtRisk: [],
    acceptedNotApplicable: [],
    holdResumeDate: '',
  });
  const problems = decisionProblems(draft, detail, today);
  const areaName = (code: string) => catalogueName(labels, { kind: 'area', code, catalogueId });

  const setOutcome = (outcome: Outcome) =>
    setDraft((d) => ({
      ...d,
      outcome,
      conditions: outcome === 'go_with_conditions' && d.conditions.length === 0 ? [newCondition()] : d.conditions,
    }));
  const patchCondition = (rowId: string, patch: Partial<ConditionDraft>) =>
    setDraft((d) => ({ ...d, conditions: d.conditions.map((c) => (c.rowId === rowId ? { ...c, ...patch } : c)) }));
  const toggle = (field: 'proceedAtRisk' | 'acceptedNotApplicable', code: string) =>
    setDraft((d) => ({
      ...d,
      [field]: d[field].includes(code) ? d[field].filter((c) => c !== code) : [...d[field], code],
    }));

  const fieldClass =
    'w-full rounded-md border border-border-light bg-surface-primary px-2.5 py-1.5 text-sm text-content-primary focus:border-oe-blue focus:outline-none';

  return (
    <WideModal
      open={open}
      onClose={onClose}
      busy={busy}
      size="xl"
      testId="decision-dialog"
      title={t('governance.project.decision.title', { defaultValue: 'Record gate decision' })}
      subtitle={t('governance.project.decision.subtitle', {
        defaultValue: 'The decision is final for this attempt. It freezes the approved document revisions and readiness checks.',
      })}
      footer={
        <div className="flex w-full flex-wrap items-center justify-end gap-3">
          {problems.length > 0 && draft.outcome && (
            <ul className="mr-auto space-y-0.5 text-xs text-semantic-error" data-testid="decision-problems">
              {problems.map((p) => (
                <li key={p} data-problem={p}>
                  {t(DECISION_PROBLEM[p][0], { defaultValue: DECISION_PROBLEM[p][1] })}
                </li>
              ))}
            </ul>
          )}
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {t('governance.project.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant={draft.outcome === 'stop' ? 'danger' : 'primary'}
            loading={busy}
            disabled={problems.length > 0}
            onClick={() => onSubmit(toDecisionInput(draft))}
            data-testid="decision-submit"
          >
            {t('governance.project.decision.submit', { defaultValue: 'Record decision' })}
          </Button>
        </div>
      }
    >
      <div className="space-y-5">
        {(serverError || serverViolations.length > 0) && (
          <div role="alert" className="rounded-md border border-semantic-error/30 bg-semantic-error-bg p-3 text-sm">
            {serverError && <p className="font-medium text-content-primary">{serverError}</p>}
            {serverViolations.length > 0 && (
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-content-secondary">
                {serverViolations.map((v, i) => (
                  <li key={`${v.code}-${v.area_code ?? ''}-${v.ref ?? ''}-${i}`}>
                    {errorText(t, v.code, v.message)}
                    {v.area_code && <span className="text-content-tertiary"> ({areaName(v.area_code)})</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {detail.blockers.length > 0 && (
          <div className="rounded-md border border-semantic-warning/40 bg-semantic-warning-bg p-3 text-sm">
            <p className="font-medium text-content-primary">
              {t('governance.project.decision.open_blockers', {
                defaultValue: 'This gate has {{count}} open blockers. A plain go is refused until they are resolved or turned into conditions.',
                count: detail.blockers.length,
              })}
            </p>
          </div>
        )}

        <fieldset>
          <legend className="mb-2 text-sm font-semibold text-content-primary">
            {t('governance.project.decision.outcome', { defaultValue: 'Outcome' })}
          </legend>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5" role="radiogroup">
            {OUTCOMES.map((o) => (
              <label
                key={o}
                className={clsx(
                  'flex cursor-pointer flex-col gap-1 rounded-lg border p-3 text-sm transition-colors',
                  draft.outcome === o
                    ? o === 'stop'
                      ? 'border-semantic-error bg-semantic-error-bg'
                      : 'border-oe-blue bg-oe-blue-subtle'
                    : 'border-border-light hover:border-border',
                )}
              >
                <span className="flex items-center gap-2 font-medium text-content-primary">
                  <input
                    type="radio"
                    name="outcome"
                    value={o}
                    checked={draft.outcome === o}
                    onChange={() => setOutcome(o)}
                  />
                  {vocab(t, OUTCOME, o)}
                </span>{' '}
                <span className="text-xs text-content-secondary">{vocab(t, OUTCOME_HINT, o)}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div>
          <label htmlFor="decision-rationale" className="mb-1 block text-sm font-semibold text-content-primary">
            {t('governance.project.decision.rationale', { defaultValue: 'Rationale' })}
            {needsRationale(draft.outcome) && (
              <span className="ml-1 text-xs font-normal text-semantic-error">
                {t('governance.project.required', { defaultValue: 'required' })}
              </span>
            )}
          </label>
          <textarea
            id="decision-rationale"
            rows={3}
            className={fieldClass}
            value={draft.rationale}
            onChange={(e) => setDraft((d) => ({ ...d, rationale: e.target.value }))}
            placeholder={t('governance.project.decision.rationale_placeholder', {
              defaultValue: 'Why this outcome, and what it rests on. It stays on the record.',
            })}
          />
        </div>

        {draft.outcome === 'hold' && (
          <div>
            <label htmlFor="decision-resume" className="mb-1 block text-sm font-semibold text-content-primary">
              {t('governance.project.decision.resume_date', { defaultValue: 'Resume on' })}
            </label>
            <input
              id="decision-resume"
              type="date"
              min={today}
              className={clsx(fieldClass, 'max-w-xs')}
              value={draft.holdResumeDate}
              onChange={(e) => setDraft((d) => ({ ...d, holdResumeDate: e.target.value }))}
            />
          </div>
        )}

        {draft.outcome === 'go_with_conditions' && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-content-primary">
                {t('governance.project.decision.conditions', { defaultValue: 'Conditions' })}
              </h3>
              <Button
                size="sm"
                variant="secondary"
                icon={<Plus size={14} />}
                onClick={() => setDraft((d) => ({ ...d, conditions: [...d.conditions, newCondition()] }))}
              >
                {t('governance.project.decision.add_condition', { defaultValue: 'Add condition' })}
              </Button>
            </div>
            {draft.conditions.map((c, idx) => (
              <div
                key={c.rowId}
                data-testid="condition-row"
                className="grid gap-2 rounded-lg border border-border-light p-3 md:grid-cols-[2fr_1fr_1fr_1fr_1fr_auto]"
              >
                <input
                  aria-label={t('governance.project.decision.condition_text', { defaultValue: 'What must be done' })}
                  placeholder={t('governance.project.decision.condition_text', { defaultValue: 'What must be done' })}
                  className={fieldClass}
                  value={c.text}
                  onChange={(e) => patchCondition(c.rowId, { text: e.target.value })}
                />
                <select
                  aria-label={t('governance.project.decision.condition_area', { defaultValue: 'Area' })}
                  className={fieldClass}
                  value={c.area_code ?? ''}
                  onChange={(e) => patchCondition(c.rowId, { area_code: e.target.value })}
                >
                  <option value="">{t('governance.project.decision.whole_gate', { defaultValue: 'Whole gate' })}</option>
                  {detail.areas.map((a) => (
                    <option key={a.area_id} value={a.code}>
                      {areaName(a.code)}
                    </option>
                  ))}
                </select>
                <ProjectPeopleSelect
                  projectId={projectId}
                  value={c.owner_user_id ?? ''}
                  onChange={(userId) => patchCondition(c.rowId, { owner_user_id: userId })}
                  placeholder={t('governance.project.decision.condition_owner', { defaultValue: 'Owner' })}
                />
                <input
                  type="date"
                  aria-label={t('governance.project.decision.condition_due', { defaultValue: 'Due date' })}
                  className={fieldClass}
                  value={c.due_date ?? ''}
                  onChange={(e) => patchCondition(c.rowId, { due_date: e.target.value })}
                />
                <select
                  aria-label={t('governance.project.decision.condition_severity', { defaultValue: 'Severity' })}
                  className={fieldClass}
                  value={c.severity}
                  onChange={(e) => patchCondition(c.rowId, { severity: e.target.value as Severity })}
                >
                  {SEVERITIES.map((s) => (
                    <option key={s} value={s}>
                      {vocab(t, SEVERITY, s)}
                    </option>
                  ))}
                </select>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Trash2 size={14} />}
                  aria-label={t('governance.project.decision.remove_condition', {
                    defaultValue: 'Remove condition {{n}}',
                    n: idx + 1,
                  })}
                  onClick={() =>
                    setDraft((d) => ({ ...d, conditions: d.conditions.filter((x) => x.rowId !== c.rowId) }))
                  }
                />
              </div>
            ))}
            {riskAreas.length > 0 && (
              <fieldset className="rounded-lg border border-border-light p-3">
                <legend className="px-1 text-xs font-semibold text-content-secondary">
                  {t('governance.project.decision.proceed_at_risk', {
                    defaultValue: 'Proceed at risk (only areas whose readiness blocks)',
                  })}
                </legend>
                {riskAreas.map((code) => (
                  <label key={code} className="mr-4 inline-flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={draft.proceedAtRisk.includes(code)}
                      onChange={() => toggle('proceedAtRisk', code)}
                    />
                    {areaName(code)}
                  </label>
                ))}
              </fieldset>
            )}
          </div>
        )}

        {naAreas.length > 0 && (
          <fieldset className="rounded-lg border border-border-light p-3">
            <legend className="px-1 text-xs font-semibold text-content-secondary">
              {t('governance.project.decision.accept_na', {
                defaultValue: 'Accept as not applicable',
              })}
            </legend>
            {naAreas.map((code) => {
              const area = detail.areas.find((a) => a.code === code);
              const why = area?.check?.na_rationale;
              return (
                <label key={code} className="flex items-start gap-1.5 py-0.5 text-sm">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={draft.acceptedNotApplicable.includes(code)}
                    onChange={() => toggle('acceptedNotApplicable', code)}
                  />
                  <span>
                    {areaName(code)}
                    {why && <span className="block text-xs text-content-tertiary">{why}</span>}
                  </span>
                </label>
              );
            })}
          </fieldset>
        )}
      </div>
    </WideModal>
  );
}
