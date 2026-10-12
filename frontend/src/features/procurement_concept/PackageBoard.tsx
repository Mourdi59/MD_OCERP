// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The package board: every contract package of the delivery model with what
// it is worth, the threshold that value meets, the procedure chosen and the
// date the award is due. The packages themselves come from the delivery
// model; this screen adds how each one is awarded.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation } from '@tanstack/react-query';
import { Boxes, Info } from 'lucide-react';

import { Button } from '@/shared/ui/Button';
import { EmptyState } from '@/shared/ui/EmptyState';
import { fmtDate } from '@/shared/lib/formatters';

import { createExecution, setPackageState, type Concept, type PackageAction, type PackageView } from './api';
import {
  PACKAGE_KIND,
  PACKAGE_STATE,
  THRESHOLD_STATUS,
  catalogueName,
  errorText,
  vocab,
  type KeyText,
  type LabelContext,
} from './labels';
import { Money, PACKAGE_TONE, ReasonedButton, RefusalBox, THRESHOLD_TONE, ToneBadge } from './ProcurementBits';
import { editVerdict, packageMoves, steerVerdict } from './rules';

type Pending = { id: string; kind: 'cancel' | 'bid_package' | 'rfq' } | null;

export const PACKAGE_ACTION: Record<PackageAction | 'bid_package' | 'rfq', KeyText> = {
  hold: ['procurement_concept.ui.package.hold', 'Put on hold'],
  resume: ['procurement_concept.ui.package.resume', 'Resume'],
  cancel: ['procurement_concept.ui.package.cancel', 'Cancel package'],
  bid_package: ['procurement_concept.actions.create_bid_package', 'Create bid package'],
  rfq: ['procurement_concept.actions.create_rfq', 'Create request for quotation'],
};

export const PACKAGE_CONFIRM: Record<NonNullable<Pending>['kind'], KeyText> = {
  cancel: [
    'procurement_concept.ui.package.confirm_cancel',
    'Cancel this package? A cancelled package cannot be planned again.',
  ],
  bid_package: [
    'procurement_concept.ui.package.confirm_bid_package',
    'Create the bid package for this award? It is created once, with the scope lines of the package, and continues in tendering.',
  ],
  rfq: [
    'procurement_concept.ui.package.confirm_rfq',
    'Create the request for quotation for this award? It is created once, with the scope lines of the package.',
  ],
};

export interface PackageBoardProps {
  projectId: string;
  concept: Concept;
  packages: PackageView[];
  labels: LabelContext;
  onPlan: (packageId: string) => void;
  onCandidates: (packageId: string) => void;
  onChanged: () => void;
}

export function PackageBoard({ projectId, concept, packages, labels, onPlan, onCandidates, onChanged }: PackageBoardProps) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<Pending>(null);
  const edit = editVerdict(concept);
  const steer = steerVerdict(concept);

  const move = useMutation({
    mutationFn: (m: { id: string; action: PackageAction | 'bid_package' | 'rfq' }) =>
      m.action === 'bid_package' || m.action === 'rfq'
        ? createExecution(projectId, m.id).then(() => undefined)
        : setPackageState(projectId, m.id, m.action).then(() => undefined),
    onSuccess: () => {
      setPending(null);
      onChanged();
    },
  });
  const start = (p: Pending) => {
    move.reset();
    setPending(p);
  };

  if (packages.length === 0) {
    return (
      <EmptyState
        icon={<Boxes size={28} />}
        title={t('procurement_concept.empty.no_plan', { defaultValue: 'The delivery model has no package plan yet.' })}
        description={t('procurement_concept.ui.package.empty_body', {
          defaultValue:
            'Award packages follow the contract packages of the delivery model. Split the project into contract packages there first; each one then appears here to get a value, a procedure and a need date.',
        })}
      />
    );
  }

  return (
    <div className="space-y-3">
      {edit && (
        <p className="flex items-start gap-2 rounded-md bg-surface-secondary px-3 py-2 text-sm text-content-secondary" data-testid="board-locked">
          <Info size={15} className="mt-0.5 shrink-0" aria-hidden />
          {errorText(labels.t, edit)}
        </p>
      )}
      {move.error ? <RefusalBox error={move.error} /> : null}
      <div className="overflow-x-auto rounded-lg border border-border-light">
        <table className="w-full text-left text-sm" data-testid="package-board">
          <thead className="bg-surface-secondary text-xs text-content-tertiary">
            <tr>
              <th className="px-3 py-2 font-medium">{t('procurement_concept.ui.package.col_package', { defaultValue: 'Package' })}</th>
              <th className="px-3 py-2 font-medium">{t('procurement_concept.ui.package.col_value', { defaultValue: 'Estimated value' })}</th>
              <th className="px-3 py-2 font-medium">{t('procurement_concept.ui.package.col_procedure', { defaultValue: 'Procedure' })}</th>
              <th className="px-3 py-2 font-medium">{t('procurement_concept.ui.package.col_dates', { defaultValue: 'Award due' })}</th>
              <th className="px-3 py-2 font-medium">{t('procurement_concept.ui.package.col_state', { defaultValue: 'State' })}</th>
              <th className="px-3 py-2 font-medium">
                <span className="sr-only">{t('procurement_concept.ui.actions', { defaultValue: 'Actions' })}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {packages.map((view) => {
              const cp = view.contract_package;
              const a = view.award;
              const moves = packageMoves(view);
              const confirm = pending?.id === cp.id ? pending : null;
              return (
                <tr key={cp.id} className="border-t border-border-light align-top" data-testid="package-row" data-package={cp.code}>
                  <td className="px-3 py-2.5">
                    <div className="font-medium text-content-primary">
                      <span className="font-mono text-xs text-content-tertiary">{cp.code}</span> {cp.title}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-content-tertiary">
                      {view.package_kind ? (
                        vocab(labels.t, PACKAGE_KIND, view.package_kind)
                      ) : (
                        <span data-testid="not-procured">
                          {t('procurement_concept.ui.package.not_procured', {
                            defaultValue: 'Not awarded as a package of its own',
                          })}
                        </span>
                      )}
                      {a?.is_advance && (
                        <ToneBadge tone="purple" testId="advance-badge">
                          {t('procurement_concept.ui.package.advance', { defaultValue: 'Advance package' })}
                        </ToneBadge>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <Money value={a?.estimated_value} currency={a?.currency} />
                    {view.threshold && (
                      <div className="mt-1">
                        <ToneBadge tone={THRESHOLD_TONE[view.threshold.status]} testId="threshold-badge">
                          {vocab(labels.t, THRESHOLD_STATUS, view.threshold.status)}
                        </ToneBadge>
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-content-primary">
                    {a?.procedure_code ? (
                      catalogueName(labels, 'procedure', a.procedure_code)
                    ) : (
                      <span className="text-content-tertiary">{t('procurement_concept.ui.not_set', { defaultValue: 'Not set' })}</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-content-primary">
                    {view.schedule?.award_date ? (
                      <>
                        {fmtDate(view.schedule.award_date)}
                        {view.schedule.start_date && (
                          <div className="text-xs text-content-tertiary">
                            {t('procurement_concept.ui.package.start_by', {
                              defaultValue: 'start by {{date}}',
                              date: fmtDate(view.schedule.start_date),
                            })}
                          </div>
                        )}
                      </>
                    ) : (
                      <span className="text-content-tertiary">-</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    {a ? (
                      <ToneBadge tone={PACKAGE_TONE[a.state]} testId="package-state">
                        {vocab(labels.t, PACKAGE_STATE, a.state)}
                      </ToneBadge>
                    ) : view.package_kind ? (
                      <span className="text-xs text-content-tertiary" data-testid="package-unplanned">
                        {t('procurement_concept.ui.package.unplanned', { defaultValue: 'No award plan yet' })}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2.5">
                    {confirm ? (
                      <div className="max-w-xs space-y-2" data-testid="package-confirm">
                        <p className="text-xs text-content-primary">{vocab(labels.t, PACKAGE_CONFIRM, confirm.kind)}</p>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant={confirm.kind === 'cancel' ? 'danger' : 'primary'}
                            loading={move.isPending}
                            onClick={() => move.mutate({ id: cp.id, action: confirm.kind })}
                            data-testid="package-confirm-yes"
                          >
                            {vocab(labels.t, PACKAGE_ACTION, confirm.kind)}
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setPending(null)}>
                            {t('procurement_concept.ui.keep', { defaultValue: 'Not now' })}
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-wrap justify-end gap-1.5">
                        {moves.edit && (
                          <ReasonedButton quiet size="sm" variant={a ? 'secondary' : 'primary'} verdict={edit} onClick={() => onPlan(cp.id)} data-testid="package-plan">
                            {a
                              ? t('procurement_concept.ui.package.plan_edit', { defaultValue: 'Change plan' })
                              : t('procurement_concept.ui.package.plan_first', { defaultValue: 'Plan award' })}
                          </ReasonedButton>
                        )}
                        {moves.candidates && (
                          <Button size="sm" variant="ghost" onClick={() => onCandidates(cp.id)} data-testid="package-candidates">
                            {t('procurement_concept.ui.package.candidates', { defaultValue: 'Candidates' })}
                          </Button>
                        )}
                        {moves.execution && (
                          <ReasonedButton quiet size="sm" variant="ghost" verdict={steer} onClick={() => start({ id: cp.id, kind: moves.execution as 'bid_package' | 'rfq' })} data-testid="package-execution">
                            {vocab(labels.t, PACKAGE_ACTION, moves.execution)}
                          </ReasonedButton>
                        )}
                        {moves.hold && (
                          <ReasonedButton quiet size="sm" variant="ghost" verdict={steer} loading={move.isPending && move.variables?.id === cp.id} onClick={() => move.mutate({ id: cp.id, action: 'hold' })} data-testid="package-hold">
                            {vocab(labels.t, PACKAGE_ACTION, 'hold')}
                          </ReasonedButton>
                        )}
                        {moves.resume && (
                          <ReasonedButton quiet size="sm" variant="secondary" verdict={steer} loading={move.isPending && move.variables?.id === cp.id} onClick={() => move.mutate({ id: cp.id, action: 'resume' })} data-testid="package-resume">
                            {vocab(labels.t, PACKAGE_ACTION, 'resume')}
                          </ReasonedButton>
                        )}
                        {moves.cancel && (
                          <ReasonedButton quiet size="sm" variant="ghost" verdict={steer} onClick={() => start({ id: cp.id, kind: 'cancel' })} data-testid="package-cancel">
                            {vocab(labels.t, PACKAGE_ACTION, 'cancel')}
                          </ReasonedButton>
                        )}
                        {cp.execution_link && (
                          <span className="text-xs text-content-tertiary" data-testid="execution-linked">
                            {cp.execution_link.kind === 'rfq'
                              ? t('procurement_concept.ui.package.linked_rfq', { defaultValue: 'Request for quotation created' })
                              : t('procurement_concept.ui.package.linked_bid_package', { defaultValue: 'Bid package created' })}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
