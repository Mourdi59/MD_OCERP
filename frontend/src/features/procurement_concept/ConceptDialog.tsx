// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Starting or changing the concept, in two steps. First the rule catalogue
// is pinned. The laws and the kinds of client are the catalogue's own, so
// they can only be offered once it is pinned: the second step picks them
// from what the server sends back with the concept.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation } from '@tanstack/react-query';

import { Button } from '@/shared/ui/Button';
import { WideModal } from '@/shared/ui/WideModal';

import { setConcept, type CatalogueSummary, type Concept } from './api';
import { CLIENT_TYPE, JURISDICTION, catalogueName, errorText, vocab, type LabelContext } from './labels';
import { FIELD_CLASS, Field, ProblemList, RefusalBox } from './ProcurementBits';
import { catalogueStepInput, gateVerdict, parseAmount, publicClientTypes, rulesStepInput } from './rules';

function catalogueLabel(labels: LabelContext, c: CatalogueSummary): string {
  if (c.name.key && labels.exists(c.name.key)) return labels.t(c.name.key);
  const lang = labels.language.split('-')[0] ?? 'en';
  return c.name.text?.[labels.language] ?? c.name.text?.[lang] ?? c.name.text?.en ?? c.code;
}

export interface ConceptDialogProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
  /** Null when the project has no concept yet. */
  concept: Concept | null;
  catalogues: CatalogueSummary[];
  labels: LabelContext;
  onSaved: () => void;
}

export function ConceptDialog({ open, onClose, projectId, concept, catalogues, labels, onSaved }: ConceptDialogProps) {
  const { t } = useTranslation();
  const pinned = concept ? `${concept.catalogue_source}:${concept.catalogue_id}` : null;
  const [picked, setPicked] = useState<string | null>(pinned);
  // Until the reader picks one, a new concept shows the first catalogue the server lists.
  const first = catalogues[0] ? `${catalogues[0].source}:${catalogues[0].id}` : '';
  const catalogue = picked ?? first;
  // The law and the client can be chosen only from the catalogue that is pinned now.
  const rulesKnown = !!concept && catalogue === pinned;

  const [jurisdiction, setJurisdiction] = useState(concept?.jurisdiction ?? '');
  const [publicClient, setPublicClient] = useState(concept?.public_client ?? false);
  const [clientType, setClientType] = useState(concept?.client_type ?? '');
  const [vat, setVat] = useState(concept?.vat_rate_pct ?? '0');
  const [gate, setGate] = useState(concept?.release_gate_code ?? '');

  const law = concept?.jurisdictions.find((j) => j.code === jurisdiction);
  const publicTypes = publicClientTypes(law);
  const isPublic = publicClient && publicTypes.length > 0;
  const chosenType = publicTypes.includes(clientType) ? clientType : (publicTypes[0] ?? '');
  const vatAmount = parseAmount(vat || '0');
  const vatBad = rulesKnown && (vatAmount === null || Number(vatAmount) > 100);
  const gateOff = concept ? gateVerdict(concept) : null;

  const save = useMutation({
    mutationFn: () => {
      if (!rulesKnown || !concept) return setConcept(projectId, catalogueStepInput(catalogue, concept));
      return setConcept(
        projectId,
        rulesStepInput(concept, {
          jurisdiction,
          public_client: isPublic,
          client_type: chosenType,
          vat_rate_pct: vatAmount ?? '0',
          release_gate_code: gateOff ? null : gate.trim(),
        }),
      );
    },
    onSuccess: () => {
      onSaved();
      // After the catalogue step the dialog stays: the law and the client come next.
      if (rulesKnown) onClose();
    },
  });

  return (
    <WideModal
      open={open}
      onClose={onClose}
      busy={save.isPending}
      size="lg"
      testId="concept-dialog"
      title={
        concept
          ? t('procurement_concept.ui.concept.edit_title', { defaultValue: 'Procurement rules of this project' })
          : t('procurement_concept.ui.concept.start_title', { defaultValue: 'Start the procurement concept' })
      }
      subtitle={t('procurement_concept.ui.concept.dialog_subtitle', {
        defaultValue:
          'These answers decide which thresholds are tested and which procedures the packages may use.',
      })}
      footer={
        <div className="flex w-full flex-wrap items-center justify-end gap-3">
          <ProblemList
            problems={
              vatBad
                ? [['procurement_concept.ui.problem.vat_invalid', 'The VAT rate is a number from 0 to 100.']]
                : []
            }
          />
          <Button variant="ghost" onClick={onClose} disabled={save.isPending}>
            {t('procurement_concept.ui.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button loading={save.isPending} disabled={vatBad || !catalogue} onClick={() => save.mutate()} data-testid="concept-save">
            {rulesKnown
              ? t('procurement_concept.ui.save', { defaultValue: 'Save' })
              : concept
                ? t('procurement_concept.ui.concept.pin', { defaultValue: 'Use this catalogue' })
                : t('procurement_concept.ui.concept.start', { defaultValue: 'Start concept' })}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <RefusalBox error={save.error} />
        <Field
          label={t('procurement_concept.ui.concept.catalogue', { defaultValue: 'Rule catalogue' })}
          htmlFor="pc-catalogue"
          hint={t('procurement_concept.ui.concept.catalogue_hint', {
            defaultValue: 'The catalogue brings the procedures, the thresholds with their sources and the usual lead times.',
          })}
        >
          <select id="pc-catalogue" className={FIELD_CLASS} value={catalogue} onChange={(e) => setPicked(e.target.value)}>
            {pinned && concept && !catalogues.some((c) => `${c.source}:${c.id}` === pinned) && (
              <option value={pinned}>{concept.catalogue_id}</option>
            )}
            {catalogues.map((c) => (
              <option key={`${c.source}:${c.id}`} value={`${c.source}:${c.id}`}>
                {catalogueLabel(labels, c)}
              </option>
            ))}
          </select>
        </Field>

        {!rulesKnown || !concept ? (
          <p className="rounded-md bg-surface-secondary px-3 py-2 text-sm text-content-secondary" data-testid="concept-rules-next">
            {concept
              ? t('procurement_concept.ui.concept.rules_after_pin', {
                  defaultValue:
                    'Another catalogue brings its own laws and kinds of client. Use it first; the project then starts under no public procurement law and you choose again.',
                })
              : t('procurement_concept.ui.concept.rules_next', {
                  defaultValue: 'Next you choose the procurement law and the kind of client from this catalogue.',
                })}
          </p>
        ) : (
          <>
            <Field label={t('procurement_concept.ui.concept.jurisdiction', { defaultValue: 'Procurement law' })} htmlFor="pc-jurisdiction">
              <select id="pc-jurisdiction" className={FIELD_CLASS} value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)}>
                {concept.jurisdictions.map((j) => (
                  <option key={j.code} value={j.code}>
                    {catalogueName(labels, 'jurisdiction', j) || vocab(labels.t, JURISDICTION, j.code)}
                  </option>
                ))}
              </select>
            </Field>

            <label className="flex items-start gap-2 text-sm text-content-primary">
              <input
                type="checkbox"
                className="mt-1"
                checked={isPublic}
                disabled={publicTypes.length === 0}
                onChange={(e) => setPublicClient(e.target.checked)}
                data-testid="concept-public-client"
              />
              <span>
                {t('procurement_concept.ui.concept.public_client', { defaultValue: 'The client is a public body' })}
                <span className="block text-xs text-content-tertiary">
                  {publicTypes.length === 0
                    ? t('procurement_concept.ui.concept.no_public_types', {
                        defaultValue: 'This law knows no public client, so no threshold applies.',
                      })
                    : t('procurement_concept.ui.concept.public_client_hint', {
                        defaultValue: 'Thresholds apply to public clients only. A private client keeps the law for reference.',
                      })}
                </span>
              </span>
            </label>

            {isPublic && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t('procurement_concept.ui.concept.client_type', { defaultValue: 'Kind of public client' })} htmlFor="pc-client-type">
                  <select id="pc-client-type" className={FIELD_CLASS} value={chosenType} onChange={(e) => setClientType(e.target.value)}>
                    {publicTypes.map((c) => (
                      <option key={c} value={c}>
                        {vocab(labels.t, CLIENT_TYPE, c)}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field
                  label={t('procurement_concept.ui.concept.vat', { defaultValue: 'VAT rate in percent' })}
                  htmlFor="pc-vat"
                  hint={t('procurement_concept.ui.concept.vat_hint', {
                    defaultValue: 'Used when a threshold is stated on the other VAT basis than the estimate.',
                  })}
                >
                  <input id="pc-vat" inputMode="decimal" className={FIELD_CLASS} value={vat} onChange={(e) => setVat(e.target.value)} />
                </Field>
              </div>
            )}

            <Field
              label={t('procurement_concept.ui.concept.release_gate', { defaultValue: 'Gate that releases procurement' })}
              htmlFor="pc-gate"
              hint={
                gateOff
                  ? errorText(labels.t, gateOff)
                  : t('procurement_concept.ui.concept.release_gate_hint', {
                      defaultValue: 'The code of a gate of this project. Leave it empty to use the gate the governance catalogue names.',
                    })
              }
            >
              <input id="pc-gate" className={FIELD_CLASS} disabled={!!gateOff} value={gate} onChange={(e) => setGate(e.target.value)} />
            </Field>
          </>
        )}
      </div>
    </WideModal>
  );
}
