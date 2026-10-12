// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// One permit of the roadmap, opened in place: who applies, the dates that
// matter, what has to come first, and every application made for it.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarPlus, FilePlus2, GitBranch, Pencil, Trash2 } from 'lucide-react';

import { Button } from '@/shared/ui/Button';
import { ConfirmDialog } from '@/shared/ui/ConfirmDialog';
import { useToastStore } from '@/stores/useToastStore';

import { deleteRequirement, pushMilestone, type ConditionRow, type Permit, type RequirementRow, type Roadmap } from './api';
import { ApplicationDialog } from './ApplicationDialogs';
import { usePermitAction } from './hooks';
import {
  APPLICANT_ROLE,
  APPLICATION_KIND,
  APPLICATION_STATE,
  CLOCK_REASON,
  DEPENDENCY_ON,
  PERMIT_STATE,
  REQUIREMENT_STATE,
  typeName,
  vocab,
  type LabelContext,
} from './labels';
import {
  APPLICATION_TONE,
  Fact,
  PERMIT_TONE,
  PanelHeader,
  PersonChip,
  REQUIREMENT_TONE,
  Refusal,
  ToneBadge,
  dateText,
} from './PermitBits';
import { DependenciesDialog, RequirementDialog } from './RoadmapDialogs';
import { canStartApplication, type RoadmapRow } from './rules';

export interface RequirementPanelProps {
  projectId: string;
  roadmap: Roadmap;
  row: RoadmapRow;
  all: RequirementRow[];
  permits: Permit[];
  conditions: ConditionRow[];
  labels: LabelContext;
  personName: (userId: string | null | undefined) => string | null;
  onBack: () => void;
  onOpenApplication: (applicationId: string) => void;
}

type Dialog = 'edit' | 'dependencies' | 'application' | 'delete' | null;

export function RequirementPanel({
  projectId,
  roadmap,
  row,
  all,
  permits,
  conditions,
  labels,
  personName,
  onBack,
  onOpenApplication,
}: RequirementPanelProps) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const [dialog, setDialog] = useState<Dialog>(null);
  const { requirement: r, timeline: tl, applications } = row;
  const type = typeName(labels, r.permit_type_code, r.name_key);
  const ownPermits = permits.filter((p) => p.requirement_id === r.id);
  const nameOf = (id: string) => {
    const other = all.find((x) => x.id === id);
    return other ? other.title || typeName(labels, other.permit_type_code, other.name_key) : '';
  };

  const remove = usePermitAction(projectId, () => deleteRequirement(projectId, r.id), onBack);
  const milestone = usePermitAction(
    projectId,
    () => pushMilestone(projectId, r.id),
    () =>
      addToast({
        type: 'success',
        title: t('permits.ui.requirement.milestone_done', { defaultValue: 'The expected decision is now a milestone in the schedule.' }),
      }),
  );
  const canOpenNew = canStartApplication(row);
  const conflict = !!tl?.schedule_conflict;

  return (
    <div className="space-y-5" data-testid="requirement-panel">
      <PanelHeader
        title={r.title || type}
        subtitle={r.title ? type : undefined}
        badge={r.state && <ToneBadge tone={REQUIREMENT_TONE[r.state]}>{vocab(t, REQUIREMENT_STATE, r.state)}</ToneBadge>}
        onBack={onBack}
        backLabel={t('permits.ui.back_to_roadmap', { defaultValue: 'Back to the roadmap' })}
        actions={
          <>
            <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => setDialog('edit')} data-testid="requirement-edit">
              {t('permits.ui.edit', { defaultValue: 'Edit' })}
            </Button>
            <Button size="sm" variant="secondary" icon={<GitBranch size={14} />} onClick={() => setDialog('dependencies')} data-testid="requirement-dependencies">
              {t('permits.ui.requirement.dependencies', { defaultValue: 'What comes first' })}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon={<CalendarPlus size={14} />}
              loading={milestone.busy}
              onClick={() => milestone.run(undefined)}
              title={t('permits.ui.requirement.milestone_hint', {
                defaultValue: 'Writes the expected decision date into the project schedule as a milestone.',
              })}
              data-testid="requirement-milestone"
            >
              {t('permits.ui.requirement.milestone', { defaultValue: 'Put in the schedule' })}
            </Button>
            <Button size="sm" variant="ghost" icon={<Trash2 size={14} />} onClick={() => setDialog('delete')} data-testid="requirement-delete">
              {t('permits.ui.remove', { defaultValue: 'Remove' })}
            </Button>
          </>
        }
      />
      {milestone.error && <Refusal testId="milestone-refusal">{milestone.error}</Refusal>}
      {remove.error && <Refusal testId="delete-refusal">{remove.error}</Refusal>}

      {!r.applicable && (
        <p role="status" className="rounded-md border border-border-light bg-surface-secondary px-3 py-2 text-sm text-content-secondary">
          {t('permits.ui.requirement.na_banner', { defaultValue: 'Not needed for this project: {{reason}}', reason: r.applicability_rationale })}
        </p>
      )}
      {conflict && (
        <p
          role="status"
          data-testid="requirement-conflict"
          className="rounded-md border border-semantic-warning/40 bg-semantic-warning-bg px-3 py-2 text-sm text-content-primary"
        >
          {tl?.conflict_accepted
            ? t('permits.ui.requirement.conflict_accepted_banner', {
                defaultValue: 'The decision is forecast after the needed date. This was accepted.',
              })
            : t('permits.ui.requirement.conflict_banner', {
                defaultValue: 'The decision is forecast after the date this permit is needed. File earlier, or accept the delay under Edit.',
              })}
        </p>
      )}

      <dl className="grid gap-4 rounded-lg border border-border-light p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Fact label={t('permits.ui.requirement.applicant_role', { defaultValue: 'Who applies' })}>
          {vocab(t, APPLICANT_ROLE, r.applicant_role)}
          {r.applicant_party && <span className="block text-xs text-content-tertiary">{r.applicant_party}</span>}
        </Fact>
        <Fact label={t('permits.ui.requirement.responsible', { defaultValue: 'Responsible person' })}>
          <PersonChip name={r.responsible_user_id ? personName(r.responsible_user_id) ?? t('permits.ui.unknown_person', { defaultValue: 'Project member' }) : null} />
        </Fact>
        <Fact label={t('permits.ui.requirement.needed_by', { defaultValue: 'Needed by' })}>{dateText(tl?.needed_by ?? r.needed_by_date)}</Fact>
        <Fact label={t('permits.ui.requirement.latest_submit', { defaultValue: 'File by, at the latest' })} testId="fact-latest-submit">
          {dateText(tl?.latest_submit)}
        </Fact>
        <Fact label={t('permits.ui.requirement.planned_submit', { defaultValue: 'Planned filing' })}>{dateText(r.planned_submit_date)}</Fact>
        <Fact label={t('permits.ui.requirement.forecast', { defaultValue: 'Decision expected' })} testId="fact-forecast">
          {dateText(tl?.forecast_decision)}
          {tl?.estimate && tl.forecast_decision && (
            <span className="block text-xs text-content-tertiary">{t('permits.ui.roadmap.estimate', { defaultValue: 'estimate' })}</span>
          )}
          {!tl?.forecast_decision && tl?.forecast_reason && (
            <span className="block text-xs text-content-tertiary">{vocab(t, CLOCK_REASON, tl.forecast_reason)}</span>
          )}
        </Fact>
      </dl>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-content-primary">
          {t('permits.ui.requirement.dependencies', { defaultValue: 'What comes first' })}
        </h3>
        {r.depends_on.length === 0 ? (
          <p className="text-sm text-content-tertiary">
            {t('permits.ui.requirement.dependencies_none', { defaultValue: 'This permit waits for no other permit.' })}
          </p>
        ) : (
          <ul className="space-y-1 text-sm text-content-secondary" data-testid="dependency-list">
            {r.depends_on.map((d) => (
              <li key={d.id}>
                <span className="font-medium text-content-primary">{nameOf(d.id)}</span> {vocab(t, DEPENDENCY_ON, d.on)}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-content-primary">{t('permits.ui.requirement.applications', { defaultValue: 'Applications' })}</h3>
          {r.applicable && (canOpenNew || ownPermits.length > 0) && (
            <Button size="sm" icon={<FilePlus2 size={14} />} onClick={() => setDialog('application')} data-testid="application-open">
              {t('permits.ui.application.submit_new', { defaultValue: 'Open application' })}
            </Button>
          )}
        </div>
        {applications.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border-light p-4 text-sm text-content-tertiary" data-testid="applications-empty">
            {t('permits.ui.requirement.applications_none', {
              defaultValue: 'No application yet. Open one when the team starts preparing the documents for the authority.',
            })}
          </p>
        ) : (
          <ul className="space-y-1.5" data-testid="application-list">
            {applications.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => onOpenApplication(a.id)}
                  className="flex w-full flex-wrap items-center gap-3 rounded-lg border border-border-light p-3 text-left text-sm hover:border-border"
                  data-testid="application-entry"
                >
                  <span className="font-medium text-content-primary">{vocab(t, APPLICATION_KIND, a.kind)}</span>
                  <ToneBadge tone={APPLICATION_TONE[a.state]}>{vocab(t, APPLICATION_STATE, a.state)}</ToneBadge>
                  <span className="text-content-secondary">{[a.authority_name, a.authority_reference].filter(Boolean).join(' / ')}</span>
                  {a.submitted_at && (
                    <span className="ml-auto text-xs text-content-tertiary">
                      {t('permits.ui.application.filed_on', { defaultValue: 'Filed {{date}}', date: dateText(a.submitted_at) })}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {ownPermits.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-content-primary">{t('permits.ui.requirement.permits', { defaultValue: 'Permits granted' })}</h3>
          <ul className="space-y-1.5">
            {ownPermits.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-border-light p-3 text-sm">
                <span className="font-medium text-content-primary">{p.reference || type}</span>
                <ToneBadge tone={PERMIT_TONE[p.state]}>{vocab(t, PERMIT_STATE, p.state)}</ToneBadge>
                {p.valid_until && (
                  <span className="text-xs text-content-tertiary">
                    {t('permits.ui.permit.valid_until', { defaultValue: 'Start works by {{date}}', date: dateText(p.valid_until) })}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <RequirementDialog
        open={dialog === 'edit'}
        onClose={() => setDialog(null)}
        projectId={projectId}
        roadmap={roadmap}
        requirement={r}
        labels={labels}
        personName={personName}
      />
      <DependenciesDialog
        open={dialog === 'dependencies'}
        onClose={() => setDialog(null)}
        projectId={projectId}
        requirement={r}
        all={all}
        labels={labels}
      />
      <ApplicationDialog
        open={dialog === 'application'}
        onClose={() => setDialog(null)}
        projectId={projectId}
        requirementId={r.id}
        application={null}
        canOpenNew={canOpenNew}
        permits={ownPermits}
        conditions={conditions}
        labels={labels}
        onCreated={(a) => onOpenApplication(a.id)}
      />
      <ConfirmDialog
        open={dialog === 'delete'}
        onCancel={() => setDialog(null)}
        onConfirm={() => {
          setDialog(null);
          remove.run(undefined);
        }}
        title={t('permits.ui.requirement.delete_title', { defaultValue: 'Remove this permit from the roadmap?' })}
        message={t('permits.ui.requirement.delete_body', {
          defaultValue: 'A permit that already has a filed application cannot be removed. Mark it as not needed under Edit to keep the record.',
        })}
        confirmLabel={t('permits.ui.requirement.delete_confirm', { defaultValue: 'Remove from roadmap' })}
        variant="danger"
        loading={remove.busy}
      />
    </div>
  );
}
