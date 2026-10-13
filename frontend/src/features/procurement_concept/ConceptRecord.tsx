// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The concept record: the rules the project procures under, where the concept
// stands (draft, in review, approved, binding), what still blocks approval,
// and the printable record. The concept is submitted here and approved by
// the governance gate; a refused submit lists every finding that blocks it.

import { useTranslation } from 'react-i18next';
import { useMutation } from '@tanstack/react-query';
import { CheckCircle2, Download, Info, Pencil } from 'lucide-react';

import { Button } from '@/shared/ui/Button';
import { fmtDate } from '@/shared/lib/formatters';

import { conceptAction, downloadExport, type Concept, type ConceptAction, type ExportFormat, type ExportPart, type Finding } from './api';
import { useRefusalToast } from './hooks';
import { CLIENT_TYPE, CONCEPT_STATE, JURISDICTION, catalogueName, vocab, type KeyText, type LabelContext } from './labels';
import { CONCEPT_TONE, FindingList, ReasonedButton, RefusalBox, ToneBadge } from './ProcurementBits';
import { conceptSteps, editVerdict, splitFindings } from './rules';

export const CONCEPT_ACTION: Record<ConceptAction, KeyText> = {
  submit: ['procurement_concept.actions.submit', 'Submit for the gate'],
  return: ['procurement_concept.actions.return', 'Return to draft'],
};

export const CONCEPT_STATE_HINT: Record<Concept['state'], KeyText> = {
  draft: [
    'procurement_concept.ui.record.hint_draft',
    'The plan is open. Set a procedure for every package, then submit the concept for the gate.',
  ],
  in_review: [
    'procurement_concept.ui.record.hint_in_review',
    'The concept is submitted and the plan is locked. Return it to draft to change it.',
  ],
  approved: [
    'procurement_concept.ui.record.hint_approved',
    'The gate approved the concept and the plan is locked. It changes through a change request on its frame document.',
  ],
  binding: [
    'procurement_concept.ui.record.hint_binding',
    'The concept is binding through its frame document. It changes only through a change request there.',
  ],
  reopened: [
    'procurement_concept.ui.record.hint_reopened',
    'A change request is open on the frame document. Change the plan, then submit the concept for the gate again.',
  ],
};

const EXPORTS: Array<{ part: ExportPart; format: ExportFormat; label: KeyText }> = [
  { part: 'concept', format: 'pdf', label: ['procurement_concept.ui.export.concept_pdf', 'Concept record (PDF)'] },
  { part: 'packages', format: 'xlsx', label: ['procurement_concept.ui.export.packages_xlsx', 'Package list (XLSX)'] },
  { part: 'schedule', format: 'xlsx', label: ['procurement_concept.ui.export.schedule_xlsx', 'Award schedule (XLSX)'] },
];

export const RECORD_KEY_MAPS = { CONCEPT_ACTION, CONCEPT_STATE_HINT, EXPORT: Object.fromEntries(EXPORTS.map((e) => [e.part, e.label])) };

export interface ConceptRecordProps {
  projectId: string;
  concept: Concept;
  findings: Finding[];
  findingsLoading: boolean;
  labels: LabelContext;
  refLabel: (ref: string) => string;
  onEdit: () => void;
  onChanged: () => void;
}

export function ConceptRecord({
  projectId,
  concept,
  findings,
  findingsLoading,
  labels,
  refLabel,
  onEdit,
  onChanged,
}: ConceptRecordProps) {
  const { t } = useTranslation();
  const toastRefusal = useRefusalToast();
  const { blocking, warnings } = splitFindings(findings);

  const step = useMutation({
    mutationFn: (action: ConceptAction) => conceptAction(projectId, action),
    onSuccess: onChanged,
  });
  const exportFile = useMutation({
    mutationFn: (e: { part: ExportPart; format: ExportFormat }) => downloadExport(projectId, e.part, e.format),
    onError: toastRefusal,
  });
  const privateType = concept.jurisdictions.find((j) => j.code === concept.jurisdiction)?.private_client_type ?? 'private';

  const facts: Array<[string, string]> = [
    [
      t('procurement_concept.ui.concept.catalogue', { defaultValue: 'Rule catalogue' }),
      t('procurement_concept.ui.record.catalogue_value', {
        defaultValue: '{{name}}, version {{version}}',
        name: labels.exists(`procurement_concept.catalogue.${concept.catalogue_id}.name`)
          ? labels.t(`procurement_concept.catalogue.${concept.catalogue_id}.name`)
          : concept.catalogue_id,
        version: concept.catalogue_version,
      }),
    ],
    [
      t('procurement_concept.ui.concept.jurisdiction', { defaultValue: 'Procurement law' }),
      catalogueName(labels, 'jurisdiction', concept.jurisdictions.find((j) => j.code === concept.jurisdiction)) ||
        vocab(labels.t, JURISDICTION, concept.jurisdiction),
    ],
    [
      t('procurement_concept.ui.record.client', { defaultValue: 'Client' }),
      concept.public_client && concept.client_type !== privateType
        ? vocab(labels.t, CLIENT_TYPE, concept.client_type)
        : t('procurement_concept.client_type.private', { defaultValue: 'Private client' }),
    ],
    [
      t('procurement_concept.ui.record.release_gate', { defaultValue: 'Gate that releases procurement' }),
      concept.resolved_release_gate_code ??
        (concept.released_from_start
          ? t('procurement_concept.ui.record.released_from_start', {
              defaultValue: 'None, procurement is open from the project start',
            })
          : concept.gates_in_use === false
            ? t('procurement_concept.ui.record.gates_not_used', { defaultValue: 'None, this project does not use gates' })
            : t('procurement_concept.ui.record.release_gate_unresolved', { defaultValue: 'Not known yet' })),
    ],
  ];
  if (concept.approved_at) {
    facts.push([
      t('procurement_concept.ui.record.approved_on', { defaultValue: 'Approved on' }),
      fmtDate(concept.approved_at),
    ]);
  }

  return (
    <div className="space-y-5" data-testid="concept-record">
      <section className="rounded-lg border border-border-light p-4">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold text-content-primary">
                {t('procurement_concept.ui.record.status_title', { defaultValue: 'Where the concept stands' })}
              </h2>
              <ToneBadge tone={CONCEPT_TONE[concept.state]} testId="concept-state">
                {vocab(labels.t, CONCEPT_STATE, concept.state)}
              </ToneBadge>
            </div>
            <p className="mt-1 text-sm text-content-secondary">{vocab(labels.t, CONCEPT_STATE_HINT, concept.state)}</p>
          </div>
          <div className="flex flex-wrap items-start gap-3">
            {conceptSteps(concept).map((s) => (
              <ReasonedButton
                key={s.action}
                verdict={s.verdict}
                variant={s.primary ? 'primary' : 'secondary'}
                loading={step.isPending && step.variables === s.action}
                onClick={() => step.mutate(s.action)}
                data-testid={`concept-${s.action}`}
              >
                {vocab(labels.t, CONCEPT_ACTION, s.action)}
              </ReasonedButton>
            ))}
          </div>
        </div>

        <p className="mt-3 flex items-start gap-2 rounded-md bg-surface-secondary px-3 py-2 text-sm text-content-secondary" data-testid="approval-by-gate">
          <Info size={15} className="mt-0.5 shrink-0" aria-hidden />
          {t('procurement_concept.approval.by_gate', {
            defaultValue: 'The governance gate approves the concept. Submit it, then decide the gate.',
          })}
        </p>
        {concept.four_eyes_violated && (
          <p className="mt-2 rounded-md border border-semantic-warning/40 bg-semantic-warning-bg px-3 py-2 text-xs text-content-primary" role="note" data-testid="four-eyes">
            {t('procurement_concept.ui.record.four_eyes', {
              defaultValue: 'The person who submitted the concept also approved it. A second person should have decided.',
            })}
          </p>
        )}
        {step.error ? (
          <div className="mt-3">
            <RefusalBox error={step.error} refLabel={refLabel} />
          </div>
        ) : null}
      </section>

      <section className="rounded-lg border border-border-light p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-content-primary">
            {t('procurement_concept.ui.record.rules_title', { defaultValue: 'Rules this project procures under' })}
          </h2>
          <ReasonedButton
            size="sm"
            variant="secondary"
            icon={<Pencil size={14} />}
            verdict={editVerdict(concept)}
            onClick={onEdit}
            data-testid="concept-edit"
          >
            {t('procurement_concept.ui.record.change_rules', { defaultValue: 'Change rules' })}
          </ReasonedButton>
        </div>
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
          {facts.map(([term, value]) => (
            <div key={term}>
              <dt className="text-xs text-content-tertiary">{term}</dt>
              <dd className="text-content-primary">{value}</dd>
            </div>
          ))}
        </dl>
        {concept.review_status !== 'verified' && (
          <p className="mt-3 rounded-md border border-semantic-warning/40 bg-semantic-warning-bg px-3 py-2 text-xs text-content-primary" role="note">
            {t('procurement_concept.ui.record.catalogue_unconfirmed', {
              defaultValue:
                'Parts of this catalogue are not yet confirmed on their primary source. Check a threshold against its source before relying on it.',
            })}
          </p>
        )}
      </section>

      <section className="rounded-lg border border-border-light p-4" data-testid="concept-findings">
        <h2 className="text-base font-semibold text-content-primary">
          {t('procurement_concept.ui.record.findings_title', { defaultValue: 'What the rule check found' })}
        </h2>
        {findingsLoading ? (
          <p className="mt-2 text-sm text-content-tertiary">
            {t('procurement_concept.ui.record.findings_loading', { defaultValue: 'Checking the plan against the rules' })}
          </p>
        ) : findings.length === 0 ? (
          <p className="mt-2 flex items-center gap-2 text-sm text-content-secondary">
            <CheckCircle2 size={16} className="text-semantic-success" aria-hidden />
            {t('procurement_concept.ui.record.findings_none', {
              defaultValue: 'Nothing found. The plan meets every rule of the catalogue.',
            })}
          </p>
        ) : (
          <>
            <p className="mb-3 mt-1 text-sm text-content-secondary">
              {t('procurement_concept.ui.record.findings_summary', {
                defaultValue: 'Blocking approval: {{blocking}}. Warnings: {{warnings}}.',
                blocking: blocking.length,
                warnings: warnings.length,
              })}
            </p>
            <FindingList findings={findings} refLabel={refLabel} />
          </>
        )}
      </section>

      <section className="rounded-lg border border-border-light p-4">
        <h2 className="mb-1 text-base font-semibold text-content-primary">
          {t('procurement_concept.ui.export.title', { defaultValue: 'Printable record' })}
        </h2>
        <p className="mb-3 text-sm text-content-secondary">
          {t('procurement_concept.ui.export.body', {
            defaultValue: 'The record as it stands now, for the file or for the steering meeting.',
          })}
        </p>
        <div className="flex flex-wrap gap-2">
          {EXPORTS.map((e) => (
            <Button
              key={e.part}
              size="sm"
              variant="secondary"
              icon={<Download size={14} />}
              loading={exportFile.isPending && exportFile.variables?.part === e.part}
              onClick={() => exportFile.mutate({ part: e.part, format: e.format })}
              data-testid={`export-${e.part}`}
            >
              {t(e.label[0], { defaultValue: e.label[1] })}
            </Button>
          ))}
        </div>
      </section>
    </div>
  );
}
