// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Two lists of an item that the reader works on directly: what must be true
// before a release is asked for, and which documents count as committed.
//
// A precondition is either ticked by a person (a signed brief, a permit) or
// read from the module that knows (a decided gate, an approved funding
// application). The second kind shows its state and has no tick box. A
// linked document shows the amount it counts with, which can differ from the
// amount on the document, and the row says why.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueries, useQuery } from '@tanstack/react-query';
import { CheckCircle2, Circle, Link2, Trash2 } from 'lucide-react';

import { Button } from '@/shared/ui/Button';
import { fmtDate } from '@/shared/lib/formatters';

import {
  addLink,
  addPrecondition,
  commitmentKeys,
  confirmPrecondition,
  removeLink,
  type CommitmentItem,
  type LinkKind,
  type Precondition,
  type PreconditionKind,
} from './api';
import type { Verdict } from './access';
import { Amount, FIELD_CLASS, ReasonedButton, RefusalBox, refusalText } from './CommitmentBits';
import { PICKABLE_KINDS, listDocuments } from './documents';
import { LINK_KIND, LINK_NOTE, PRECONDITION_KIND, vocab } from './labels';
import { ADDABLE_PRECONDITIONS, TICKABLE_PRECONDITIONS } from './rules';

interface PartProps {
  projectId: string;
  item: CommitmentItem;
  /** Whether the viewer may change the item; null means yes. */
  editVerdict: Verdict;
  personName: (userId: string | null | undefined) => string | null;
  onChanged: () => void;
}

export function PreconditionList({ projectId, item, editVerdict, personName, onChanged }: PartProps) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<PreconditionKind>('manual');
  const [text, setText] = useState('');
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null);
  const [evidence, setEvidence] = useState('');

  const add = useMutation({
    mutationFn: () => addPrecondition(projectId, item.id, { kind, text: text.trim() }),
    onSuccess: () => {
      setAdding(false);
      setText('');
      onChanged();
    },
  });
  const confirm = useMutation({
    mutationFn: (v: { id: string; met: boolean; evidence: string }) =>
      confirmPrecondition(projectId, item.id, v.id, { met: v.met, evidence_ref: v.evidence }),
    onSuccess: () => {
      setEvidenceFor(null);
      setEvidence('');
      onChanged();
    },
  });

  const tick = (pre: Precondition) => {
    if (pre.state === 'met') {
      confirm.mutate({ id: pre.id, met: false, evidence: '' });
      return;
    }
    // An appropriation is only met with its reference; the others may carry one.
    setEvidenceFor(pre.id);
    setEvidence(pre.evidence_ref ?? '');
  };

  return (
    <section data-testid="preconditions">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-content-primary">
          {t('commitment.drawer.preconditions', { defaultValue: 'Preconditions' })}
        </h3>
        {!adding && (
          <ReasonedButton size="sm" variant="secondary" verdict={editVerdict} onClick={() => setAdding(true)}>
            {t('commitment.preconditions.add', { defaultValue: 'Add precondition' })}
          </ReasonedButton>
        )}
      </div>

      {confirm.isError && <RefusalBox message={refusalText(t, confirm.error)} />}

      {item.preconditions.length === 0 && !adding ? (
        <p className="text-sm text-content-tertiary">
          {t('commitment.preconditions.empty', {
            defaultValue: 'Nothing has to be true before this release is asked for. Add a precondition when something does, for example a signed brief or a permit.',
          })}
        </p>
      ) : (
        <ul className="space-y-1.5">
          {item.preconditions.map((pre) => {
            const met = pre.state === 'met';
            const tickable = TICKABLE_PRECONDITIONS.includes(pre.kind);
            return (
              <li
                key={pre.id}
                data-testid="precondition-row"
                data-state={met ? 'met' : 'open'}
                className="rounded-lg border border-border-light p-2.5 text-sm"
              >
                <div className="flex flex-wrap items-start gap-2">
                  {met ? (
                    <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-semantic-success" aria-hidden />
                  ) : (
                    <Circle size={16} className="mt-0.5 shrink-0 text-content-tertiary" aria-hidden />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-content-primary">{pre.text || vocab(t, PRECONDITION_KIND, pre.kind)}</p>
                    <p className="flex flex-wrap gap-x-3 text-xs text-content-tertiary">
                      <span>{vocab(t, PRECONDITION_KIND, pre.kind)}</span>
                      <span>
                        {met
                          ? t('commitment.preconditions.met', { defaultValue: 'Met' })
                          : t('commitment.preconditions.open', { defaultValue: 'Open' })}
                      </span>
                      {met && pre.confirmed_at && (
                        <span>
                          {t('commitment.preconditions.confirmed', {
                            defaultValue: 'confirmed {{date}} by {{name}}',
                            date: fmtDate(pre.confirmed_at),
                            name:
                              personName(pre.confirmed_by) ??
                              t('commitment.unknown_person', { defaultValue: 'Project member' }),
                          })}
                        </span>
                      )}
                      {pre.evidence_ref && (
                        <span>
                          {t('commitment.preconditions.evidence', {
                            defaultValue: 'Evidence: {{ref}}',
                            ref: pre.evidence_ref,
                          })}
                        </span>
                      )}
                    </p>
                  </div>
                  {tickable ? (
                    evidenceFor !== pre.id && (
                      <ReasonedButton
                        size="sm"
                        variant={met ? 'ghost' : 'secondary'}
                        verdict={editVerdict}
                        loading={confirm.isPending && confirm.variables?.id === pre.id}
                        onClick={() => tick(pre)}
                        data-testid="precondition-tick"
                      >
                        {met
                          ? t('commitment.preconditions.reopen', { defaultValue: 'Reopen' })
                          : t('commitment.preconditions.mark_met', { defaultValue: 'Mark as met' })}
                      </ReasonedButton>
                    )
                  ) : (
                    <span className="max-w-[14rem] text-xs text-content-tertiary" data-testid="precondition-computed">
                      {t('commitment.preconditions.computed', {
                        defaultValue: 'Read from its own module. It changes there.',
                      })}
                    </span>
                  )}
                </div>
                {evidenceFor === pre.id && (
                  <div className="mt-2 flex flex-wrap items-end gap-2 rounded-md bg-surface-secondary p-2">
                    <div className="min-w-[14rem] flex-1">
                      <label htmlFor={`evidence-${pre.id}`} className="mb-1 block text-xs text-content-secondary">
                        {t('commitment.preconditions.evidence_label', {
                          defaultValue: 'What shows it is met (document number, date, link)',
                        })}
                      </label>
                      <input
                        id={`evidence-${pre.id}`}
                        className={FIELD_CLASS}
                        value={evidence}
                        onChange={(e) => setEvidence(e.target.value)}
                      />
                    </div>
                    <Button
                      size="sm"
                      loading={confirm.isPending}
                      onClick={() => confirm.mutate({ id: pre.id, met: true, evidence: evidence.trim() })}
                      data-testid="precondition-confirm"
                    >
                      {t('commitment.preconditions.mark_met', { defaultValue: 'Mark as met' })}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEvidenceFor(null)}>
                      {t('commitment.cancel', { defaultValue: 'Cancel' })}
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {adding && (
        <div className="mt-2 space-y-2 rounded-lg bg-surface-secondary p-3" data-testid="precondition-add-form">
          {add.isError && <RefusalBox message={refusalText(t, add.error)} />}
          <div className="grid gap-2 sm:grid-cols-[1fr_2fr]">
            <select
              aria-label={t('commitment.preconditions.kind', { defaultValue: 'Kind of precondition' })}
              className={FIELD_CLASS}
              value={kind}
              onChange={(e) => setKind(e.target.value as PreconditionKind)}
            >
              {ADDABLE_PRECONDITIONS.map((k) => (
                <option key={k} value={k}>
                  {vocab(t, PRECONDITION_KIND, k)}
                </option>
              ))}
            </select>
            <input
              aria-label={t('commitment.preconditions.text', { defaultValue: 'What must be true' })}
              placeholder={t('commitment.preconditions.text', { defaultValue: 'What must be true' })}
              className={FIELD_CLASS}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              loading={add.isPending}
              disabled={kind === 'manual' && !text.trim()}
              onClick={() => add.mutate()}
              data-testid="precondition-add-send"
            >
              {t('commitment.preconditions.add', { defaultValue: 'Add precondition' })}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
              {t('commitment.cancel', { defaultValue: 'Cancel' })}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}

export function LinkList({ projectId, item, editVerdict, onChanged }: Omit<PartProps, 'personName'>) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<LinkKind>('contract');
  const [documentId, setDocumentId] = useState('');

  // The item view carries document ids only; the names come from the module
  // that owns each kind of document.
  const kinds = [...new Set(item.links.map((l) => l.kind))];
  const nameQueries = useQueries({
    queries: kinds.map((k) => ({
      queryKey: commitmentKeys.documents(projectId, k),
      queryFn: () => listDocuments(projectId, k),
      staleTime: 60_000,
    })),
  });
  const names = new Map<string, string>();
  for (const q of nameQueries) for (const d of q.data ?? []) names.set(d.id, d.label);

  const optionsQ = useQuery({
    queryKey: commitmentKeys.documents(projectId, kind),
    queryFn: () => listDocuments(projectId, kind),
    enabled: adding,
    staleTime: 60_000,
  });
  const linked = new Set(item.links.map((l) => l.document_id));
  const options = (optionsQ.data ?? []).filter((d) => !linked.has(d.id));

  const add = useMutation({
    mutationFn: () => addLink(projectId, item.id, kind, documentId),
    onSuccess: () => {
      setAdding(false);
      setDocumentId('');
      onChanged();
    },
  });
  const remove = useMutation({
    mutationFn: (linkId: string) => removeLink(projectId, item.id, linkId),
    onSuccess: onChanged,
  });

  return (
    <section data-testid="links">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-content-primary">
          {t('commitment.drawer.links', { defaultValue: 'Linked documents' })}
        </h3>
        {!adding && (
          <ReasonedButton
            size="sm"
            variant="secondary"
            icon={<Link2 size={14} />}
            verdict={editVerdict}
            onClick={() => setAdding(true)}
          >
            {t('commitment.links.add', { defaultValue: 'Link a document' })}
          </ReasonedButton>
        )}
      </div>

      {remove.isError && <RefusalBox message={refusalText(t, remove.error)} />}

      {item.links.length === 0 && !adding ? (
        <p className="text-sm text-content-tertiary">
          {t('commitment.links.empty', {
            defaultValue: 'No document is linked, so nothing counts as committed yet. Link the contract or the purchase order once it exists.',
          })}
        </p>
      ) : (
        <ul className="space-y-1.5">
          {item.links.map((link) => (
            <li
              key={link.link_id}
              data-testid="link-row"
              className="flex flex-wrap items-start gap-3 rounded-lg border border-border-light p-2.5 text-sm"
            >
              <div className="min-w-0 flex-1">
                <p className="text-content-primary">
                  {names.get(link.document_id) ??
                    (link.found
                      ? vocab(t, LINK_KIND, link.kind)
                      : t('commitment.links.not_found', { defaultValue: 'This document no longer exists' }))}
                </p>
                <p className="flex flex-wrap gap-x-3 text-xs text-content-tertiary">
                  <span>{vocab(t, LINK_KIND, link.kind)}</span>
                  {link.closed && <span>{t('commitment.links.closed', { defaultValue: 'Completed' })}</span>}
                </p>
                {link.notes.map((note) => {
                  const entry = LINK_NOTE[note.split(':')[0] ?? ''];
                  return entry ? (
                    <p key={note} className="text-xs text-content-secondary">
                      {t(entry[0], { defaultValue: entry[1] })}
                    </p>
                  ) : null;
                })}
              </div>
              <div className="text-right">
                <p className="font-medium tabular-nums text-content-primary">
                  {link.counts ? (
                    <Amount value={link.counted_amount} currency={link.currency} />
                  ) : (
                    <span className="text-content-tertiary">
                      {t('commitment.links.not_counted', { defaultValue: 'Not counted' })}
                    </span>
                  )}
                </p>
                {link.counts && link.document_amount !== link.counted_amount && (
                  <p className="text-xs text-content-tertiary">
                    {t('commitment.links.document_amount', { defaultValue: 'On the document' })}{' '}
                    <Amount value={link.document_amount} currency={link.currency} />
                  </p>
                )}
              </div>
              {!editVerdict && (
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Trash2 size={14} />}
                  loading={remove.isPending && remove.variables === link.link_id}
                  aria-label={t('commitment.links.remove', { defaultValue: 'Remove this link' })}
                  onClick={() => remove.mutate(link.link_id)}
                  data-testid="link-remove"
                />
              )}
            </li>
          ))}
        </ul>
      )}

      {adding && (
        <div className="mt-2 space-y-2 rounded-lg bg-surface-secondary p-3" data-testid="link-add-form">
          {add.isError && <RefusalBox message={refusalText(t, add.error)} />}
          <div className="grid gap-2 sm:grid-cols-[1fr_2fr]">
            <select
              aria-label={t('commitment.links.kind', { defaultValue: 'Kind of document' })}
              className={FIELD_CLASS}
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as LinkKind);
                setDocumentId('');
              }}
            >
              {PICKABLE_KINDS.map((k) => (
                <option key={k} value={k}>
                  {vocab(t, LINK_KIND, k)}
                </option>
              ))}
            </select>
            <select
              aria-label={t('commitment.links.document', { defaultValue: 'Document' })}
              className={FIELD_CLASS}
              value={documentId}
              disabled={optionsQ.isLoading}
              onChange={(e) => setDocumentId(e.target.value)}
            >
              <option value="">
                {optionsQ.isLoading
                  ? t('commitment.links.loading', { defaultValue: 'Loading documents' })
                  : t('commitment.links.choose', { defaultValue: 'Choose a document' })}
              </option>
              {options.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>
          {optionsQ.isError && <RefusalBox message={refusalText(t, optionsQ.error)} />}
          {optionsQ.isSuccess && options.length === 0 && (
            <p className="text-xs text-content-tertiary" data-testid="link-no-documents">
              {t('commitment.links.none_of_kind', {
                defaultValue: 'This project has no document of this kind that is not linked already.',
              })}
            </p>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              loading={add.isPending}
              disabled={!documentId}
              onClick={() => add.mutate()}
              data-testid="link-add-send"
            >
              {t('commitment.links.add', { defaultValue: 'Link a document' })}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
              {t('commitment.cancel', { defaultValue: 'Cancel' })}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
