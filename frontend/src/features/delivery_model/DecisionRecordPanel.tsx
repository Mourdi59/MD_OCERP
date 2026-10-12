// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The decision record: which form was proposed, why, against which
// alternatives, and where it stands. This module never approves. The decision
// is approved by the governance gate of the contracts area, so a proposed
// decision points the reader there. Earlier decisions stay listed below.

import { useTranslation } from 'react-i18next';
import { useMutation } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { CheckCircle2, Circle, FileSignature } from 'lucide-react';

import { EmptyState } from '@/shared/ui/EmptyState';
import { fmtDate, fmtNumber } from '@/shared/lib/formatters';

import { canReopen, canWithdraw, type Viewer } from './access';
import { reopenModel, withdrawDecision, type Decision, type DeliveryModel, type Readiness } from './api';
import { DECISION_TONE, FindingList, ReasonedButton, ToneBadge } from './DeliveryBits';
import { ExportButtons } from './ExportButtons';
import { useRefusalToast } from './hooks';
import { DECISION_STATUS, formName, humanizeCode, vocab, type KeyText, type LabelContext } from './labels';

const READINESS: Record<'decision_present' | 'risks_allocated' | 'no_errors', KeyText> = {
  decision_present: ['delivery_model.evidence.decision_proposed', 'Delivery form decision proposed'],
  risks_allocated: ['delivery_model.evidence.risks_allocated', 'Every risk category allocated'],
  no_errors: ['delivery_model.evidence.no_errors', 'No delivery model errors open'],
};

const APPROVAL_SOURCE: Record<'gate' | 'change_request', KeyText> = {
  gate: ['delivery_model.ui.decision.source.gate', 'Approved at the governance gate'],
  change_request: ['delivery_model.ui.decision.source.change_request', 'Approved through a change request'],
};

export const DECISION_KEY_MAPS: Record<string, Record<string, KeyText>> = { READINESS, APPROVAL_SOURCE };

export interface DecisionRecordPanelProps {
  projectId: string;
  model: DeliveryModel;
  decisions: Decision[];
  readiness: Readiness | null;
  viewer: Viewer;
  labels: LabelContext;
  personName: (userId: string | null | undefined) => string | null;
  onChanged: () => void;
  onOpenComparison: () => void;
}

/** A date with the person's name when the screen knows it, else the date alone. */
function Stamp({ label, at, by }: { label: string; at: string | null; by: string | null }) {
  const { t } = useTranslation();
  if (!at) return null;
  return (
    <div>
      <dt className="text-xs text-content-tertiary">{label}</dt>
      <dd className="text-sm text-content-primary">
        {by
          ? t('delivery_model.ui.decision.date_by', { defaultValue: '{{date}} by {{name}}', date: fmtDate(at), name: by })
          : fmtDate(at)}
      </dd>
    </div>
  );
}

export function DecisionRecordPanel({
  projectId,
  model,
  decisions,
  readiness,
  viewer,
  labels,
  personName,
  onChanged,
  onOpenComparison,
}: DecisionRecordPanelProps) {
  const { t } = useTranslation();
  const onError = useRefusalToast();
  const current = decisions.find((d) => d.is_current) ?? null;
  const earlier = decisions.filter((d) => !d.is_current);
  const withdraw = useMutation({ mutationFn: () => withdrawDecision(projectId), onSuccess: onChanged, onError });
  const reopen = useMutation({ mutationFn: () => reopenModel(projectId), onSuccess: onChanged, onError });
  const nameOf = (d: Decision) => formName(labels, d.snapshot?.form ?? null, d.form_code);

  const readinessRows: Array<[keyof typeof READINESS, boolean]> = readiness?.in_use
    ? [
        ['decision_present', !!readiness.decision_present],
        ['risks_allocated', !!readiness.risks_allocated],
        ['no_errors', readiness.errors.length === 0],
      ]
    : [];

  if (!current && earlier.length === 0) {
    return (
      <EmptyState
        icon={<FileSignature size={28} />}
        title={t('delivery_model.ui.decision.empty_title', { defaultValue: 'No decision yet' })}
        description={t('delivery_model.ui.decision.empty_body', {
          defaultValue: 'Compare at least two forms, score them and propose one. The proposal and its reasons are recorded here.',
        })}
        action={{ label: t('delivery_model.ui.decision.go_compare', { defaultValue: 'Go to the comparison' }), onClick: onOpenComparison }}
      />
    );
  }

  return (
    <div className="space-y-5" data-testid="decision-record-panel">
      {current && (
        <section className="space-y-3 rounded-xl border border-border-light p-4" data-testid="current-decision">
          <div className="flex flex-wrap items-start gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-xs text-content-tertiary">{t('delivery_model.ui.decision.form', { defaultValue: 'Delivery form' })}</p>
              <h2 className="text-lg font-semibold text-content-primary">{nameOf(current)}</h2>
            </div>
            <ToneBadge tone={DECISION_TONE[current.status]} testId="decision-status">
              {vocab(labels.t, DECISION_STATUS, current.status)}
            </ToneBadge>
            <ExportButtons projectId={projectId} what="decision" />
          </div>

          <div>
            <p className="text-xs text-content-tertiary">{t('delivery_model.ui.propose.rationale', { defaultValue: 'Why this form' })}</p>
            <p className="whitespace-pre-line text-sm text-content-primary" data-testid="decision-rationale">
              {current.rationale}
            </p>
          </div>

          <dl className="grid gap-3 sm:grid-cols-2">
            <Stamp
              label={t('delivery_model.ui.decision.proposed', { defaultValue: 'Proposed' })}
              at={current.proposed_at}
              by={personName(current.proposed_by)}
            />
            <Stamp
              label={t('delivery_model.ui.decision.approved', { defaultValue: 'Approved' })}
              at={current.approved_at}
              by={personName(current.approved_by)}
            />
          </dl>
          {current.approval_source && (
            <p className="text-sm text-content-secondary">{vocab(labels.t, APPROVAL_SOURCE, current.approval_source)}</p>
          )}
          {current.four_eyes_violated && (
            <p className="rounded-md border border-semantic-error/30 bg-semantic-error-bg px-3 py-2 text-sm" role="alert" data-testid="four-eyes-warning">
              {t('delivery_model.ui.decision.four_eyes', {
                defaultValue: 'The same person proposed and approved this decision. The four-eyes rule asks for two different people.',
              })}
            </p>
          )}

          {(current.snapshot?.options ?? []).length > 0 && (
            <div>
              <p className="mb-1 text-xs text-content-tertiary">
                {t('delivery_model.ui.decision.compared', { defaultValue: 'Compared forms and their weighted totals' })}
              </p>
              <ul className="divide-y divide-border-light rounded-lg border border-border-light text-sm" data-testid="decision-alternatives">
                {(current.snapshot.options ?? []).map((o) => (
                  <li key={o.id} className="flex items-center justify-between gap-3 px-3 py-1.5">
                    <span className={o.form_code === current.form_code ? 'font-medium text-content-primary' : 'text-content-secondary'}>
                      {formName(labels, o.form, o.form_code)}
                    </span>
                    <span className="tabular-nums text-content-secondary">
                      {o.weighted_total === null ? '' : fmtNumber(o.weighted_total, 2)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {current.status === 'proposed' && (
            <div className="rounded-lg bg-oe-purple-subtle p-3 text-sm" data-testid="approve-at-gate">
              <p className="text-content-primary">
                {t('delivery_model.ui.decision.gate_body', {
                  defaultValue:
                    'This proposal is approved at the governance gate of the contracts area, not here. Once the gate approves it, the form becomes binding.',
                })}
              </p>
              <Link to={`/projects/${projectId}/governance`} className="mt-1 inline-block font-medium text-oe-blue-text underline">
                {t('delivery_model.ui.decision.gate_link', { defaultValue: 'Approve at the gate' })}
              </Link>
            </div>
          )}

          <div className="flex flex-wrap items-start gap-3">
            {current.status === 'proposed' && (
              <ReasonedButton
                variant="secondary"
                verdict={canWithdraw(viewer, model)}
                loading={withdraw.isPending}
                onClick={() => withdraw.mutate()}
                data-testid="withdraw-button"
              >
                {t('delivery_model.ui.decision.withdraw', { defaultValue: 'Withdraw proposal' })}
              </ReasonedButton>
            )}
            {model.status === 'binding' && (
              <ReasonedButton
                variant="secondary"
                verdict={canReopen(viewer, model)}
                loading={reopen.isPending}
                onClick={() => reopen.mutate()}
                data-testid="reopen-button"
                title={t('delivery_model.ui.decision.reopen_hint', {
                  defaultValue: 'Needs an open change request on the frame document of the contracts area.',
                })}
              >
                {t('delivery_model.ui.decision.reopen', { defaultValue: 'Reopen the decision' })}
              </ReasonedButton>
            )}
          </div>
        </section>
      )}

      {readinessRows.length > 0 && (
        <section className="space-y-2" data-testid="gate-readiness">
          <h2 className="text-sm font-semibold text-content-primary">
            {t('delivery_model.ui.decision.readiness', { defaultValue: 'What the gate checks here' })}
          </h2>
          <ul className="space-y-1 text-sm">
            {readinessRows.map(([key, met]) => (
              <li key={key} className="flex items-center gap-2" data-met={met}>
                {met ? <CheckCircle2 size={15} className="text-semantic-success" aria-hidden /> : <Circle size={15} className="text-content-tertiary" aria-hidden />}
                <span className={met ? 'text-content-primary' : 'text-content-secondary'}>{vocab(labels.t, READINESS, key)}</span>
              </li>
            ))}
          </ul>
          <FindingList findings={readiness?.errors ?? []} refName={humanizeCode} testId="readiness-errors" />
        </section>
      )}

      {earlier.length > 0 && (
        <section className="space-y-2" data-testid="decision-history">
          <h2 className="text-sm font-semibold text-content-primary">
            {t('delivery_model.ui.decision.history', { defaultValue: 'Earlier decisions' })}
          </h2>
          <ul className="space-y-2">
            {earlier.map((d) => (
              <li key={d.id} className="rounded-lg border border-border-light p-3 text-sm" data-testid="earlier-decision">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-content-primary">{nameOf(d)}</span>
                  <ToneBadge tone={DECISION_TONE[d.status]}>{vocab(labels.t, DECISION_STATUS, d.status)}</ToneBadge>
                  {d.proposed_at && <span className="ml-auto text-xs text-content-tertiary">{fmtDate(d.proposed_at)}</span>}
                </div>
                <p className="mt-1 whitespace-pre-line text-xs text-content-secondary">{d.rationale}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
