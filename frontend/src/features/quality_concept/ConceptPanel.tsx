// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The concept itself: where it stands, what still stops it from going to
// approval, which packages it covers and which standards and requirements it
// rests on. Submitting is the one primary action; approval then happens at
// the governance gate, never here.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Send, Trash2 } from 'lucide-react';

import { Button } from '@/shared/ui/Button';
import { fmtDate } from '@/shared/lib/formatters';

import { conceptAction, patchConcept, submitConcept, type Finding } from './api';
import { useQcWrite, useRevisions } from './hooks';
import { CONCEPT_STATE, PACKAGE_PROBLEM, catalogueName, nameIn, vocab, type TFn } from './labels';
import { packageName, type PanelProps } from './panel';
import {
  CONCEPT_TONE,
  Field,
  FindingList,
  FormDialog,
  Hint,
  RefusalNote,
  ReviewBadge,
  Section,
  StateBadge,
  inputCls,
} from './QualityBits';
import { CONCEPT_ACTIONS, filledPackages, packageScopeProblem, type PackageDraft } from './rules';
import { StandardsSection } from './StandardsSection';

let rowSeq = 0;
type PackageRow = PackageDraft & { rowId: string };
function newRow(from?: PackageDraft): PackageRow {
  rowSeq += 1;
  return { rowId: `p${rowSeq}`, ref: '', code: '', title: '', no_proofs_rationale: '', ...from };
}

export function ConceptPanel(props: PanelProps) {
  const { projectId, concept, catalogue, labels, editable, openTab } = props;
  const { t } = useTranslation();
  const write = useQcWrite(projectId);
  const revisions = useRevisions(projectId);
  const [scopeOpen, setScopeOpen] = useState(false);

  const actions = CONCEPT_ACTIONS[concept.state] ?? [];
  const blocking = concept.findings.filter((f) => f.severity === 'error');
  const refName = (f: Finding) =>
    f.code.startsWith('stage_')
      ? nameIn(labels, catalogue?.commissioning_stages, f.ref)
      : packageName(concept, f.ref) || f.ref;

  return (
    <div className="space-y-4" data-testid="concept-panel">
      <RefusalNote refusal={write.refusal} violations={write.violations} refName={refName} />

      <Section
        testId="concept-status"
        title={t('qualityConcept.concept.status_title', { defaultValue: 'Where the concept stands' })}
        description={t('qualityConcept.concept.status_body', {
          defaultValue:
            'A draft is yours to edit. Once it is complete you submit it, and it is approved at the project governance gate.',
        })}
        action={
          <div className="flex flex-wrap items-start gap-2">
            {actions.includes('submit') && (
              <Button
                icon={<Send size={14} />}
                disabled={!concept.can_submit}
                loading={write.pending}
                onClick={() => write.send(() => submitConcept(projectId))}
                data-testid="concept-submit"
              >
                {t('qualityConcept.actions.submit', { defaultValue: 'Submit for approval' })}
              </Button>
            )}
            {actions.includes('return') && (
              <Button
                variant="secondary"
                loading={write.pending}
                onClick={() => write.send(() => conceptAction(projectId, 'return'))}
                data-testid="concept-return"
              >
                {t('qualityConcept.concept.return', { defaultValue: 'Take back to draft' })}
              </Button>
            )}
            {actions.includes('revise') && (
              <Button
                variant="secondary"
                loading={write.pending}
                onClick={() => write.send(() => conceptAction(projectId, 'revise'))}
                data-testid="concept-revise"
              >
                {t('qualityConcept.concept.revise', { defaultValue: 'Start a revision' })}
              </Button>
            )}
          </div>
        }
      >
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <StateBadge map={CONCEPT_STATE} tones={CONCEPT_TONE} code={concept.state} testId="concept-state" />
          <span className="text-content-secondary">
            {t('qualityConcept.concept.catalogue', {
              defaultValue: 'Catalogue: {{name}}',
              name:
                catalogueName(labels, {
                  code: concept.catalogue_id,
                  name_key: concept.catalogue_label.key ?? undefined,
                  labels: concept.catalogue_label.text,
                }) || concept.catalogue_id,
            })}
          </span>
          <ReviewBadge status={concept.catalogue_review_status} />
          {concept.revision_no > 0 && (
            <span className="text-content-tertiary">
              {t('qualityConcept.concept.revision', { defaultValue: 'Revision {{no}}', no: concept.revision_no })}
            </span>
          )}
        </div>
        <p className="mt-2 text-sm text-content-secondary" data-testid="concept-next-step">
          {concept.state === 'in_review'
            ? t('qualityConcept.concept.next_in_review', {
                defaultValue:
                  'The concept is with the approver. It is approved as a frame document at the governance gate, not on this page.',
              })
            : concept.state === 'approved'
              ? t('qualityConcept.concept.next_approved', {
                  defaultValue: 'The concept is approved. It becomes binding when the governance gate is decided.',
                })
              : concept.state === 'binding'
                ? t('qualityConcept.concept.next_binding', {
                    defaultValue:
                      'The concept is binding. It changes only through a change request on its frame document.',
                  })
                : concept.can_submit
                  ? t('qualityConcept.concept.next_ready', {
                      defaultValue: 'Nothing is missing. You can submit the concept for approval.',
                    })
                  : t('qualityConcept.concept.next_incomplete', {
                      defaultValue: 'Clear the open points below, then submit the concept for approval.',
                    })}
        </p>
        {concept.findings.length > 0 && (
          <div className="mt-3">
            <p className="mb-1 text-xs font-semibold text-content-secondary">
              {t('qualityConcept.concept.open_points', {
                defaultValue: 'Open points: {{blocking}} stop the submission, {{total}} in all',
                blocking: blocking.length,
                total: concept.findings.length,
              })}
            </p>
            <FindingList findings={concept.findings} refName={refName} />
          </div>
        )}
      </Section>

      <Section
        testId="concept-scope"
        title={t('qualityConcept.packages.title', { defaultValue: 'Packages in scope' })}
        description={t('qualityConcept.packages.body', {
          defaultValue:
            'The work packages this concept covers. Every package needs its proofs and an acceptance, or a reason why it needs none.',
        })}
        action={
          <Button variant="secondary" size="sm" disabled={!editable} onClick={() => setScopeOpen(true)} data-testid="scope-edit">
            {t('qualityConcept.packages.edit', { defaultValue: 'Edit packages' })}
          </Button>
        }
      >
        {concept.applicable_packages.length === 0 ? (
          <Hint testId="scope-empty">
            {t('qualityConcept.packages.empty', {
              defaultValue:
                'No packages yet. Name the work packages first: proofs are planned per package on the Proofs tab.',
            })}
          </Hint>
        ) : (
          <ul className="divide-y divide-border-light" data-testid="scope-list">
            {concept.applicable_packages.map((p) => (
              <li key={p.ref} className="flex flex-wrap items-baseline gap-2 py-1.5 text-sm">
                <span className="font-medium text-content-primary">{packageName(concept, p.ref)}</span>
                {p.no_proofs_rationale && (
                  <span className="text-xs text-content-secondary">
                    {t('qualityConcept.packages.no_proofs_because', {
                      defaultValue: 'No proofs needed: {{reason}}',
                      reason: p.no_proofs_rationale,
                    })}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <Field
            label={t('qualityConcept.concept.documentation_set', { defaultValue: 'Handover documentation set' })}
            hint={t('qualityConcept.concept.documentation_set_hint', {
              defaultValue: 'Decides which documents the handover to operation expects.',
            })}
          >
            <select
              className={inputCls}
              disabled={!editable || write.pending}
              value={concept.documentation_set_code ?? ''}
              data-testid="documentation-set"
              onChange={(e) =>
                write.send(() => patchConcept(projectId, { documentation_set_code: e.target.value || null }))
              }
            >
              <option value="">{t('qualityConcept.common.none', { defaultValue: 'None' })}</option>
              {(catalogue?.documentation_sets ?? []).map((d) => (
                <option key={d.code} value={d.code}>
                  {catalogueName(labels, d)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        {concept.applicable_packages.length > 0 && (
          <div className="mt-3">
            <Button variant="ghost" size="sm" onClick={() => openTab('proofs')}>
              {t('qualityConcept.packages.to_proofs', { defaultValue: 'Plan the proofs per package' })}
            </Button>
          </div>
        )}
      </Section>

      <StandardsSection {...props} />

      <Section
        testId="concept-revisions"
        title={t('qualityConcept.revisions.title', { defaultValue: 'Revisions' })}
        description={t('qualityConcept.revisions.body', {
          defaultValue: 'Every submission keeps a snapshot of the concept as it was sent.',
        })}
      >
        {(revisions.data ?? []).length === 0 ? (
          <Hint>
            {t('qualityConcept.revisions.empty', {
              defaultValue: 'No revision yet. The first one is recorded when the concept is submitted.',
            })}
          </Hint>
        ) : (
          <ul className="space-y-1 text-sm" data-testid="revision-list">
            {(revisions.data ?? []).map((r) => (
              <li key={r.id} className="flex flex-wrap gap-3">
                <span className="font-medium text-content-primary">
                  {t('qualityConcept.concept.revision', { defaultValue: 'Revision {{no}}', no: r.revision_no })}
                </span>
                {r.created_at && <span className="text-content-tertiary">{fmtDate(r.created_at)}</span>}
              </li>
            ))}
          </ul>
        )}
      </Section>

      {scopeOpen && (
        <ScopeDialog
          {...props}
          onClose={() => setScopeOpen(false)}
        />
      )}
    </div>
  );
}

function ScopeDialog({ projectId, concept, onClose }: PanelProps & { onClose: () => void }) {
  const { t } = useTranslation();
  const write = useQcWrite(projectId);
  const [rows, setRows] = useState<PackageRow[]>(() =>
    concept.packages.length > 0 ? concept.packages.map((p) => newRow(p)) : [newRow()],
  );
  const [holidays, setHolidays] = useState<string[]>(concept.holidays);
  const [day, setDay] = useState('');
  const problem = packageScopeProblem(rows);
  const set = (rowId: string, patch: Partial<PackageDraft>) =>
    setRows((all) => all.map((r) => (r.rowId === rowId ? { ...r, ...patch } : r)));

  return (
    <FormDialog
      open
      size="lg"
      testId="scope-dialog"
      title={t('qualityConcept.packages.dialog_title', { defaultValue: 'Packages in scope' })}
      subtitle={t('qualityConcept.packages.dialog_body', {
        defaultValue:
          'One line per work package. The reference is how proofs and acceptances point at the package, so keep it short and stable.',
      })}
      onClose={onClose}
      busy={write.pending}
      refusal={write.refusal}
      violations={write.violations}
      problem={problem ? vocab(t as TFn, PACKAGE_PROBLEM, problem) : null}
      submitLabel={t('qualityConcept.common.save', { defaultValue: 'Save' })}
      onSubmit={() =>
        write.send(() => patchConcept(projectId, { packages: filledPackages(rows), holidays }), onClose)
      }
    >
      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r.rowId} className="grid gap-2 rounded-md bg-surface-secondary p-2 md:grid-cols-12" data-testid="package-row">
            <input
              className={`${inputCls} md:col-span-2`}
              value={r.ref}
              aria-label={t('qualityConcept.packages.ref', { defaultValue: 'Reference' })}
              placeholder={t('qualityConcept.packages.ref', { defaultValue: 'Reference' })}
              onChange={(e) => set(r.rowId, { ref: e.target.value })}
              data-testid="package-ref"
            />
            <input
              className={`${inputCls} md:col-span-2`}
              value={r.code}
              aria-label={t('qualityConcept.packages.code', { defaultValue: 'Code' })}
              placeholder={t('qualityConcept.packages.code', { defaultValue: 'Code' })}
              onChange={(e) => set(r.rowId, { code: e.target.value })}
            />
            <input
              className={`${inputCls} md:col-span-3`}
              value={r.title}
              aria-label={t('qualityConcept.packages.name', { defaultValue: 'Name of the package' })}
              placeholder={t('qualityConcept.packages.name', { defaultValue: 'Name of the package' })}
              onChange={(e) => set(r.rowId, { title: e.target.value })}
            />
            <input
              className={`${inputCls} md:col-span-4`}
              value={r.no_proofs_rationale}
              aria-label={t('qualityConcept.packages.no_proofs', { defaultValue: 'Why no proofs are needed (optional)' })}
              placeholder={t('qualityConcept.packages.no_proofs', { defaultValue: 'Why no proofs are needed (optional)' })}
              onChange={(e) => set(r.rowId, { no_proofs_rationale: e.target.value })}
            />
            <Button
              variant="ghost"
              size="sm"
              className="md:col-span-1"
              icon={<Trash2 size={14} />}
              aria-label={t('qualityConcept.common.remove', { defaultValue: 'Remove' })}
              onClick={() => setRows((all) => all.filter((x) => x.rowId !== r.rowId))}
            />
          </div>
        ))}
        <Button variant="ghost" size="sm" icon={<Plus size={14} />} onClick={() => setRows((all) => [...all, newRow()])} data-testid="package-add">
          {t('qualityConcept.packages.add', { defaultValue: 'Add package' })}
        </Button>
      </div>

      <div>
        <p className="text-xs font-medium text-content-secondary">
          {t('qualityConcept.concept.holidays', { defaultValue: 'Non-working days' })}
        </p>
        <p className="mb-1 text-2xs text-content-tertiary">
          {t('qualityConcept.concept.holidays_hint', {
            defaultValue: 'Deadlines counted in working days skip these days.',
          })}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="date"
            className={`${inputCls} w-auto`}
            value={day}
            aria-label={t('qualityConcept.concept.holidays', { defaultValue: 'Non-working days' })}
            onChange={(e) => setDay(e.target.value)} />
          <Button
            variant="secondary"
            size="sm"
            disabled={!day || holidays.includes(day)}
            onClick={() => {
              setHolidays((all) => [...all, day].sort());
              setDay('');
            }}
          >
            {t('qualityConcept.common.add', { defaultValue: 'Add' })}
          </Button>
          {holidays.map((h) => (
            <button
              key={h}
              type="button"
              className="rounded-full border border-border-light px-2 py-0.5 text-xs text-content-secondary"
              title={t('qualityConcept.common.remove', { defaultValue: 'Remove' })}
              onClick={() => setHolidays((all) => all.filter((x) => x !== h))}
            >
              {fmtDate(h)}
            </button>
          ))}
        </div>
      </div>
    </FormDialog>
  );
}
