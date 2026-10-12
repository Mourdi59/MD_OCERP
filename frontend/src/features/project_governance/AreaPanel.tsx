// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// One management area: who owns it, whether it applies to the project, and
// its frame documents with the CDE revision in force, the binding badge and
// the change requests raised against them.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowLeft, Lock, GitBranch } from 'lucide-react';

import { Button } from '@/shared/ui/Button';
import { ProjectPeopleSelect } from '@/shared/ui/ProjectPeopleSelect';
import { getErrorMessage } from '@/shared/lib/api';
import { fmtDate } from '@/shared/lib/formatters';
import { useToastStore } from '@/stores/useToastStore';

import {
  createChangeRequest,
  getDocumentHistory,
  governanceKeys,
  submitDocument,
  updateArea,
  type ChangeRequest,
  type ChangeRequestStatus,
  type FrameDocument,
  type GovernanceArea,
  type GovernanceModel,
} from './api';
import { canEditArea, roleAllows, type Viewer } from './access';
import { DOCUMENT_TONE, PersonChip, ReasonedButton, ToneBadge } from './GovernanceBits';
import { useInvalidateGovernance } from './hooks';
import { DOCUMENT_STATUS, catalogueName, vocab, type KeyText, type LabelContext } from './labels';

const CR_STATUS: Record<ChangeRequestStatus, KeyText> = {
  submitted: ['governance.project.cr_status.submitted', 'Submitted'],
  approved: ['governance.project.cr_status.approved', 'Approved'],
  rejected: ['governance.project.cr_status.rejected', 'Rejected'],
  cancelled: ['governance.project.cr_status.cancelled', 'Cancelled'],
};

export const AREA_KEY_MAPS = { CR_STATUS };

export interface AreaPanelProps {
  projectId: string;
  area: GovernanceArea;
  model: GovernanceModel;
  documents: FrameDocument[];
  changeRequests: ChangeRequest[];
  viewer: Viewer;
  labels: LabelContext;
  personName: (userId: string | null | undefined) => string | null;
  onBack: () => void;
}

function DocumentRow({
  projectId,
  doc,
  catalogueId,
  labels,
  changeRequests,
  viewer,
  onChanged,
}: {
  projectId: string;
  doc: FrameDocument;
  catalogueId: string;
  labels: LabelContext;
  changeRequests: ChangeRequest[];
  viewer: Viewer;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const [open, setOpen] = useState(false);
  const [crOpen, setCrOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [impact, setImpact] = useState('');
  const history = useQuery({
    queryKey: governanceKeys.history(projectId, doc.id),
    queryFn: () => getDocumentHistory(projectId, doc.id),
    enabled: open,
  });
  const submit = useMutation({
    mutationFn: () => submitDocument(projectId, doc.id),
    onSuccess: onChanged,
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });
  const raise = useMutation({
    mutationFn: () => createChangeRequest(projectId, doc.id, { reason: reason.trim(), impact: impact.trim() }),
    onSuccess: () => {
      setCrOpen(false);
      setReason('');
      setImpact('');
      onChanged();
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });
  const editVerdict = roleAllows(viewer.role, 'edit') ? null : 'role_edit';
  const inForce = history.data?.revisions.find((r) => r.in_force);
  const crs = changeRequests.filter((c) => c.document_id === doc.id);

  return (
    <li className="rounded-lg border border-border-light p-3" data-testid="area-document">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-content-primary">
          {catalogueName(labels, { kind: 'doc', code: doc.doc_type, catalogueId, label: doc.name })}
        </span>
        <ToneBadge tone={DOCUMENT_TONE[doc.status]}>{vocab(t, DOCUMENT_STATUS, doc.status)}</ToneBadge>
        {doc.status === 'binding' && (
          <span className="inline-flex items-center gap-1 text-2xs font-medium text-semantic-success" data-testid="binding-badge">
            <Lock size={12} aria-hidden />
            {t('governance.project.area.binding_hint', { defaultValue: 'Binding, changes through a change request' })}
          </span>
        )}
        {doc.read_only && (
          <span className="text-2xs text-content-tertiary">
            {t('governance.project.area.read_only', { defaultValue: 'Read-only' })}
          </span>
        )}
        <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {t('governance.project.area.revisions', { defaultValue: 'Revisions' })}
        </Button>
      </div>
      {!doc.container_id && (
        <p className="mt-1 text-xs text-content-tertiary">
          {t('governance.project.area.attach_hint', {
            defaultValue: 'No CDE container attached yet. Attach one in the CDE, then the revisions show here.',
          })}
        </p>
      )}

      {open && (
        <div className="mt-2 rounded-md bg-surface-secondary p-2 text-xs">
          {history.isLoading && <p className="text-content-tertiary">{t('governance.project.loading', { defaultValue: 'Loading...' })}</p>}
          {history.isError && <p className="text-semantic-error">{getErrorMessage(history.error)}</p>}
          {history.data && history.data.revisions.length === 0 && (
            <p className="text-content-tertiary">
              {t('governance.project.area.no_revisions', { defaultValue: 'The container has no revision yet.' })}
            </p>
          )}
          {history.data && history.data.revisions.length > 0 && (
            <ul className="space-y-0.5">
              {history.data.revisions.map((r) => (
                <li key={r.id} className="flex flex-wrap gap-2">
                  <span className="font-mono">{r.revision_code || r.revision_number}</span>
                  <span className="text-content-secondary">{r.file_name}</span>
                  <span className="text-content-tertiary">{fmtDate(r.created_at)}</span>
                  {r.in_force && (
                    <span className="font-medium text-semantic-success">
                      {t('governance.project.area.in_force', { defaultValue: 'In force' })}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {inForce && doc.bound_content_hash && (
            <p className="mt-1 font-mono text-2xs text-content-tertiary">{doc.bound_content_hash.slice(0, 16)}</p>
          )}
        </div>
      )}

      {crs.length > 0 && (
        <ul className="mt-2 space-y-1">
          {crs.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-2 text-xs" data-testid="change-request">
              <GitBranch size={12} className="text-content-tertiary" aria-hidden />
              <span className="text-content-primary">{c.reason}</span>
              <ToneBadge tone={c.status === 'approved' ? 'success' : c.status === 'submitted' ? 'blue' : 'neutral'}>
                {vocab(t, CR_STATUS, c.status)}
              </ToneBadge>
              <span className="text-content-tertiary">{fmtDate(c.created_at)}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        {doc.status === 'draft' && !doc.read_only && (
          <ReasonedButton size="sm" variant="secondary" verdict={editVerdict} loading={submit.isPending} onClick={() => submit.mutate()}>
            {t('governance.project.area.submit_document', { defaultValue: 'Submit for gate review' })}
          </ReasonedButton>
        )}
        {doc.status === 'binding' && !crOpen && (
          <ReasonedButton size="sm" variant="secondary" verdict={editVerdict} onClick={() => setCrOpen(true)}>
            {t('governance.project.area.raise_change', { defaultValue: 'Raise change request' })}
          </ReasonedButton>
        )}
      </div>
      {crOpen && (
        <div className="mt-2 space-y-2 rounded-md bg-surface-secondary p-2">
          <textarea
            rows={2}
            className="w-full rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm"
            aria-label={t('governance.project.area.cr_reason', { defaultValue: 'Reason for the change (required)' })}
            placeholder={t('governance.project.area.cr_reason', { defaultValue: 'Reason for the change (required)' })}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <textarea
            rows={2}
            className="w-full rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm"
            aria-label={t('governance.project.area.cr_impact', { defaultValue: 'Impact on cost, time or scope' })}
            placeholder={t('governance.project.area.cr_impact', { defaultValue: 'Impact on cost, time or scope' })}
            value={impact}
            onChange={(e) => setImpact(e.target.value)}
          />
          <div className="flex gap-2">
            <Button size="sm" disabled={!reason.trim()} loading={raise.isPending} onClick={() => raise.mutate()}>
              {t('governance.project.area.cr_send', { defaultValue: 'Send for approval' })}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setCrOpen(false)}>
              {t('governance.project.cancel', { defaultValue: 'Cancel' })}
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

export function AreaPanel({
  projectId,
  area,
  model,
  documents,
  changeRequests,
  viewer,
  labels,
  personName,
  onBack,
}: AreaPanelProps) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const invalidate = useInvalidateGovernance(projectId);
  const verdict = canEditArea(model);
  const [naRationale, setNaRationale] = useState(area.na_rationale);
  const catalogueId = model.catalogue_id;
  const name = catalogueName(labels, {
    kind: 'area',
    code: area.code,
    catalogueId,
    label: area.name,
    override: area.name_override,
  });

  const patch = useMutation({
    mutationFn: (body: Parameters<typeof updateArea>[2]) => updateArea(projectId, area.id, body),
    onSuccess: invalidate,
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const docs = documents.filter((d) => d.area_id === area.id);
  const ownerLabel = (id: string | null) =>
    id ? personName(id) ?? t('governance.project.unknown_person', { defaultValue: 'Project member' }) : null;

  return (
    <div className="space-y-5" data-testid="area-panel">
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="ghost" icon={<ArrowLeft size={14} />} onClick={onBack}>
          {t('governance.project.back_to_matrix', { defaultValue: 'Back to matrix' })}
        </Button>
        <h2 className="text-lg font-semibold text-content-primary">{name}</h2>
      </div>

      <section className="grid gap-4 md:grid-cols-2">
        {(['owner_user_id', 'deputy_user_id'] as const).map((field) => (
          <div key={field} className="rounded-lg border border-border-light p-3">
            <p className="mb-2 text-xs font-semibold text-content-secondary">
              {field === 'owner_user_id'
                ? t('governance.project.area.owner', { defaultValue: 'Owner' })
                : t('governance.project.area.deputy', { defaultValue: 'Deputy' })}
            </p>
            <div className="mb-2">
              {field === 'deputy_user_id' && !area.deputy_user_id ? (
                <span className="text-xs text-content-tertiary">
                  {t('governance.project.area.no_deputy', { defaultValue: 'No deputy' })}
                </span>
              ) : (
                <PersonChip name={ownerLabel(area[field])} />
              )}
            </div>
            {verdict ? (
              <ReasonedButton size="sm" variant="secondary" verdict={verdict}>
                {t('governance.project.area.assign', { defaultValue: 'Assign' })}
              </ReasonedButton>
            ) : (
              <ProjectPeopleSelect
                projectId={projectId}
                value={area[field] ?? ''}
                displayValue={ownerLabel(area[field]) ?? undefined}
                onChange={(userId) => patch.mutate({ [field]: userId || null })}
                placeholder={t('governance.project.area.choose_person', { defaultValue: 'Choose a project member' })}
              />
            )}
          </div>
        ))}
      </section>
      {area.owner_user_id === null && (
        <p className="text-xs text-content-secondary">
          {t('governance.project.area.owner_explainer', {
            defaultValue: 'The owner confirms readiness at each gate. Changing the owner resets this area on gates not yet decided.',
          })}
        </p>
      )}

      <section className="rounded-lg border border-border-light p-3">
        <label className="flex items-center gap-2 text-sm font-medium text-content-primary">
          <input
            type="checkbox"
            checked={area.applicable}
            disabled={!!verdict || patch.isPending || (area.applicable && !naRationale.trim())}
            onChange={(e) =>
              patch.mutate(e.target.checked ? { applicable: true } : { applicable: false, na_rationale: naRationale.trim() })
            }
          />
          {t('governance.project.area.applicable', { defaultValue: 'Applies to this project' })}
        </label>
        <textarea
          rows={2}
          className="mt-2 w-full rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm"
          aria-label={t('governance.project.area.na_rationale', {
            defaultValue: 'Why the area does not apply (required to switch it off)',
          })}
          placeholder={t('governance.project.area.na_rationale', {
            defaultValue: 'Why the area does not apply (required to switch it off)',
          })}
          value={naRationale}
          disabled={!!verdict}
          onChange={(e) => setNaRationale(e.target.value)}
        />
        {verdict && <ReasonedButton size="sm" variant="ghost" verdict={verdict}>{t('governance.project.save', { defaultValue: 'Save' })}</ReasonedButton>}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-content-primary">
          {t('governance.project.area.documents_title', { defaultValue: 'Frame documents' })}
        </h3>
        {docs.length === 0 ? (
          <p className="text-sm text-content-tertiary">
            {t('governance.project.area.no_documents', {
              defaultValue: 'No frame document is tracked for this area yet. The phase model adds the required ones per gate.',
            })}
          </p>
        ) : (
          <ul className="space-y-2">
            {docs.map((d) => (
              <DocumentRow
                key={d.id}
                projectId={projectId}
                doc={d}
                catalogueId={catalogueId}
                labels={labels}
                changeRequests={changeRequests}
                viewer={viewer}
                onChanged={invalidate}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
