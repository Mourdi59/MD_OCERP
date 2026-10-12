// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// What must be true before a release is asked for.
//
// A precondition is either ticked by a person (a signed brief, a permit) or
// read from the module that knows (a decided gate, a binding frame document,
// an approved funding application). The second kind shows its state and has
// no tick box; it is added by picking the record it reads, and the row names
// that record, never its code or id.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation } from '@tanstack/react-query';
import { CheckCircle2, Circle } from 'lucide-react';

import { Button } from '@/shared/ui/Button';
import { fmtDate } from '@/shared/lib/formatters';

import {
  addPrecondition,
  confirmPrecondition,
  type CommitmentItem,
  type Precondition,
  type PreconditionKind,
} from './api';
import type { Verdict } from './access';
import { FIELD_CLASS, ReasonedButton, RefusalBox, refusalText } from './CommitmentBits';
import { useLabelContext, useReferences } from './hooks';
import { PRECONDITION_KIND, vocab } from './labels';
import { preconditionRefName, refOptions } from './references';
import { ADDABLE_PRECONDITIONS, REF_PRECONDITIONS, TICKABLE_PRECONDITIONS } from './rules';

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
  const [refId, setRefId] = useState('');
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null);
  const [evidence, setEvidence] = useState('');

  // The pick lists are needed to name a record a precondition points at, and to offer one.
  const labels = useLabelContext();
  const refsQ = useReferences(projectId, adding || item.preconditions.some((pre) => !!pre.ref_id));
  const refKinds = REF_PRECONDITIONS.filter((k) => refOptions(k, refsQ.data, labels).length > 0);
  const picksRecord = REF_PRECONDITIONS.includes(kind);
  const records = refOptions(kind, refsQ.data, labels);

  const add = useMutation({
    mutationFn: () =>
      addPrecondition(
        projectId,
        item.id,
        picksRecord ? { kind, ref_id: refId, text: '' } : { kind, text: text.trim() },
      ),
    onSuccess: () => {
      setAdding(false);
      setText('');
      setRefId('');
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
                    <p className="text-content-primary" data-testid="precondition-title">
                      {preconditionRefName(pre, refsQ.data, labels) || pre.text || vocab(t, PRECONDITION_KIND, pre.kind)}
                    </p>
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
              data-testid="precondition-kind"
              onChange={(e) => {
                setKind(e.target.value as PreconditionKind);
                setRefId('');
              }}
            >
              {[...ADDABLE_PRECONDITIONS, ...refKinds].map((k) => (
                <option key={k} value={k}>
                  {vocab(t, PRECONDITION_KIND, k)}
                </option>
              ))}
            </select>
            {picksRecord ? (
              <select
                aria-label={t('commitment.preconditions.record', { defaultValue: 'Which one' })}
                className={FIELD_CLASS}
                value={refId}
                data-testid="precondition-ref"
                onChange={(e) => setRefId(e.target.value)}
              >
                <option value="">{t('commitment.preconditions.record_choose', { defaultValue: 'Choose from the project' })}</option>
                {records.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                aria-label={t('commitment.preconditions.text', { defaultValue: 'What must be true' })}
                placeholder={t('commitment.preconditions.text', { defaultValue: 'What must be true' })}
                className={FIELD_CLASS}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            )}
          </div>
          {refsQ.isSuccess && refKinds.length === 0 && (
            <p className="text-xs text-content-tertiary" data-testid="precondition-no-records">
              {t('commitment.preconditions.no_records', {
                defaultValue:
                  'A gate, a frame document or a funding application can be made a precondition once the project has one.',
              })}
            </p>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              loading={add.isPending}
              disabled={picksRecord ? !refId : kind === 'manual' && !text.trim()}
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
