// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The permits the project holds: what each one covers, whether it is in
// force, and the date by which work has to start before it lapses.

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, FileCheck2 } from 'lucide-react';

import { Button } from '@/shared/ui/Button';
import { EmptyState } from '@/shared/ui/EmptyState';
import { fmtCurrency } from '@/shared/lib/formatters';

import { localToday, notifyStart, transitionPermit, type ConditionRow, type Permit, type PermitTarget, type RequirementRow } from './api';
import { ConditionDialog } from './ConditionDialogs';
import { usePermitAction } from './hooks';
import { PERMIT_STATE, PERMIT_STEP, SCOPE, typeName, vocab, type LabelContext } from './labels';
import { Fact, Field, FormDialog, PERMIT_TONE, ToneBadge, dateText, fieldClass } from './PermitBits';
import { canNotifyStart, permitTargets } from './rules';

/* ── Notice of the start of works ─────────────────────────────────────── */

function StartNoticeDialog({ open, onClose, projectId, permit }: { open: boolean; onClose: () => void; projectId: string; permit: Permit }) {
  const { t } = useTranslation();
  const [onDate, setOnDate] = useState('');
  useEffect(() => {
    if (open) setOnDate(localToday());
  }, [open]);
  const action = usePermitAction(projectId, () => notifyStart(projectId, permit.id, onDate), onClose);
  useEffect(() => {
    if (!open) action.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  return (
    <FormDialog
      open={open}
      onClose={onClose}
      testId="start-notice-dialog"
      title={t('permits.ui.permit.start_title', { defaultValue: 'Record the start of works' })}
      subtitle={t('permits.ui.permit.start_subtitle', {
        defaultValue: 'Once work has started under the permit, it no longer lapses for not being used.',
      })}
      submitLabel={t('permits.ui.permit.start_submit', { defaultValue: 'Record start' })}
      busy={action.busy}
      error={action.error}
      problems={onDate ? [] : [t('permits.ui.permit.start_problem', { defaultValue: 'Enter the day work started.' })]}
      onSubmit={() => action.run(undefined)}
    >
      <Field label={t('permits.ui.permit.start_date', { defaultValue: 'Work started on' })} required>
        {(id) => (
          <input id={id} type="date" max={localToday()} className={`${fieldClass} max-w-xs`} value={onDate} onChange={(e) => setOnDate(e.target.value)} />
        )}
      </Field>
    </FormDialog>
  );
}

/* ── A change the authority made to the permit ────────────────────────── */

function PermitTransitionDialog({ open, onClose, projectId, permit }: { open: boolean; onClose: () => void; projectId: string; permit: Permit }) {
  const { t } = useTranslation();
  const targets = permitTargets(permit);
  const [target, setTarget] = useState<PermitTarget | ''>('');
  const [reason, setReason] = useState('');
  useEffect(() => {
    if (!open) return;
    setTarget('');
    setReason('');
  }, [open]);
  const action = usePermitAction(
    projectId,
    () => transitionPermit(projectId, permit.id, { target: target as PermitTarget, reason: reason.trim() }),
    onClose,
  );
  useEffect(() => {
    if (!open) action.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  const problems: string[] = [];
  if (!target) problems.push(t('permits.ui.permit.change_problem_target', { defaultValue: 'Choose what happened to the permit.' }));
  if (!reason.trim()) {
    problems.push(t('permits.ui.permit.change_problem_reason', { defaultValue: 'Give the reason, or the reference of the letter.' }));
  }
  return (
    <FormDialog
      open={open}
      onClose={onClose}
      testId="permit-transition-dialog"
      danger={target === 'revoked'}
      title={t('permits.ui.permit.change_title', { defaultValue: 'Record a change to the permit' })}
      subtitle={t('permits.ui.permit.change_subtitle', {
        defaultValue: 'A suspended or revoked permit no longer covers the works. Site readiness follows at once.',
      })}
      submitLabel={t('permits.ui.permit.change_submit', { defaultValue: 'Record change' })}
      busy={action.busy}
      error={action.error}
      problems={problems}
      onSubmit={() => action.run(undefined)}
    >
      <fieldset className="space-y-1.5">
        <legend className="mb-1 text-sm font-medium text-content-primary">
          {t('permits.ui.permit.change_target', { defaultValue: 'What happened' })}
        </legend>
        {targets.map((x) => (
          <label key={x} className="flex items-center gap-2 rounded-md border border-border-light p-2.5 text-sm">
            <input type="radio" name="permit-target" checked={target === x} onChange={() => setTarget(x)} />
            {vocab(t, PERMIT_STEP, x)}
          </label>
        ))}
      </fieldset>
      <Field label={t('permits.ui.permit.change_reason', { defaultValue: 'Reason' })} required>
        {(id) => <textarea id={id} rows={2} className={fieldClass} value={reason} onChange={(e) => setReason(e.target.value)} />}
      </Field>
    </FormDialog>
  );
}

/* ── The register ─────────────────────────────────────────────────────── */

export interface PermitsRegisterProps {
  projectId: string;
  permits: Permit[];
  requirements: RequirementRow[];
  conditions: ConditionRow[];
  labels: LabelContext;
  personName: (userId: string | null | undefined) => string | null;
  onOpenRequirement: (requirementId: string) => void;
  onShowConditions: () => void;
}

type Open = { permit: Permit; kind: 'start' | 'change' | 'condition' } | null;

export function PermitsRegister({
  projectId,
  permits,
  requirements,
  conditions,
  labels,
  personName,
  onOpenRequirement,
  onShowConditions,
}: PermitsRegisterProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<Open>(null);

  if (permits.length === 0) {
    return (
      <EmptyState
        icon={<FileCheck2 size={28} />}
        title={t('permits.ui.permit.empty_title', { defaultValue: 'No permit granted yet' })}
        description={t('permits.ui.permit.empty_body', {
          defaultValue:
            'A permit appears here when the decision on its application is recorded as granted. Open the permit on the roadmap and record the decision there.',
        })}
      />
    );
  }

  return (
    <>
      <ul className="space-y-2" data-testid="permit-list">
        {permits.map((p) => {
          const req = requirements.find((r) => r.id === p.requirement_id);
          const type = typeName(labels, p.permit_type_code, req?.name_key);
          const own = conditions.filter((c) => c.permit_id === p.id && c.confirmed);
          const openCount = own.filter((c) => c.state === 'open' || c.state === 'evidence_submitted' || c.state === 'breach').length;
          const targets = permitTargets(p);
          const warn = p.lapse_warning;
          return (
            <li key={p.id} className="space-y-3 rounded-lg border border-border-light p-4" data-testid="permit-entry">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      className="text-left font-medium text-oe-blue-text hover:underline"
                      onClick={() => onOpenRequirement(p.requirement_id)}
                    >
                      {req?.title || type}
                    </button>
                    <ToneBadge tone={PERMIT_TONE[p.state]} testId="permit-state">
                      {vocab(t, PERMIT_STATE, p.state)}
                    </ToneBadge>
                  </div>
                  {req?.title && <p className="text-xs text-content-tertiary">{type}</p>}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {canNotifyStart(p) && (
                    <Button size="sm" onClick={() => setOpen({ permit: p, kind: 'start' })} data-testid="permit-start">
                      {t('permits.ui.permit.start_submit', { defaultValue: 'Record start' })}
                    </Button>
                  )}
                  {p.state === 'in_force' && (
                    <Button size="sm" variant="secondary" onClick={() => setOpen({ permit: p, kind: 'condition' })} data-testid="permit-add-condition">
                      {t('permits.ui.condition.submit_new', { defaultValue: 'Add condition' })}
                    </Button>
                  )}
                  {targets.length > 0 && (
                    <Button size="sm" variant="ghost" onClick={() => setOpen({ permit: p, kind: 'change' })} data-testid="permit-change">
                      {t('permits.ui.permit.change_submit', { defaultValue: 'Record change' })}
                    </Button>
                  )}
                </div>
              </div>
              {warn && (
                <p
                  role="status"
                  data-testid="lapse-warning"
                  className="flex items-start gap-2 rounded-md border border-semantic-warning/40 bg-semantic-warning-bg px-3 py-2 text-sm text-content-primary"
                >
                  <AlertTriangle size={16} className="mt-0.5 shrink-0 text-semantic-warning" aria-hidden />
                  {warn.level === 'lapsed'
                    ? t('permits.ui.permit.lapsed_warning', {
                        defaultValue: 'Work did not start by {{date}}, so the permit has lapsed. It returns only through an extension decision.',
                        date: dateText(p.valid_until),
                      })
                    : t('permits.ui.permit.lapse_warning', {
                        count: warn.days,
                        date: dateText(p.valid_until),
                        defaultValue_one: 'The permit lapses in {{count}} day, on {{date}}, unless work starts.',
                        defaultValue_other: 'The permit lapses in {{count}} days, on {{date}}, unless work starts.',
                      })}
                </p>
              )}
              <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
                <Fact label={t('permits.ui.permit.reference', { defaultValue: 'Reference' })}>{p.reference || '-'}</Fact>
                <Fact label={t('permits.ui.permit.scope', { defaultValue: 'Covers' })}>{vocab(t, SCOPE, p.scope)}</Fact>
                <Fact label={t('permits.ui.permit.start_by', { defaultValue: 'Work must start by' })}>{dateText(p.valid_until)}</Fact>
                <Fact label={t('permits.ui.permit.started', { defaultValue: 'Work started' })}>{dateText(p.start_notified_at)}</Fact>
                {p.security_amount && (
                  <Fact label={t('permits.ui.permit.security', { defaultValue: 'Security' })} testId="permit-security">
                    {fmtCurrency(p.security_amount, p.security_currency)}
                  </Fact>
                )}
              </dl>
              {own.length > 0 && (
                <button type="button" className="text-sm text-oe-blue-text hover:underline" onClick={onShowConditions} data-testid="permit-conditions-link">
                  {t('permits.ui.permit.conditions', {
                    defaultValue: 'Conditions: {{total}}, still open: {{open}}',
                    total: own.length,
                    open: openCount,
                  })}
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {open && (
        <>
          <StartNoticeDialog open={open.kind === 'start'} onClose={() => setOpen(null)} projectId={projectId} permit={open.permit} />
          <PermitTransitionDialog open={open.kind === 'change'} onClose={() => setOpen(null)} projectId={projectId} permit={open.permit} />
          <ConditionDialog
            open={open.kind === 'condition'}
            onClose={() => setOpen(null)}
            projectId={projectId}
            permitId={open.permit.id}
            condition={null}
            personName={personName}
          />
        </>
      )}
    </>
  );
}
