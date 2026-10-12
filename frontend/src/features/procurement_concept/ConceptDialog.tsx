// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Starting or changing the concept: which rule catalogue applies, under which
// procurement law, for what kind of client. These three answers decide every
// threshold test and every procedure the packages may use afterwards.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation } from '@tanstack/react-query';

import { Button } from '@/shared/ui/Button';
import { WideModal } from '@/shared/ui/WideModal';

import { setConcept, type CatalogueSummary, type ClientType, type Concept, type ConceptInput, type Jurisdiction } from './api';
import { CLIENT_TYPE, JURISDICTION, vocab, type LabelContext } from './labels';
import { FIELD_CLASS, Field, ProblemList, RefusalBox } from './ProcurementBits';
import { parseAmount } from './rules';

const JURISDICTIONS: Jurisdiction[] = ['none', 'eu', 'de_national', 'uk', 'us_federal'];
const CLIENT_TYPES: ClientType[] = ['central', 'sub_central', 'utility'];

/** The law a shipped catalogue is written for, offered as the starting choice. The reader can change it. */
const CATALOGUE_JURISDICTION: Record<string, Jurisdiction> = {
  neutral: 'none',
  eu: 'eu',
  de_national: 'de_national',
  uk: 'uk',
  us_federal: 'us_federal',
};

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
  const [catalogue, setCatalogue] = useState(
    concept ? `${concept.catalogue_source}:${concept.catalogue_id}` : 'shipped:neutral',
  );
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction>(concept?.jurisdiction ?? 'none');
  const [publicClient, setPublicClient] = useState(concept?.public_client ?? false);
  const [clientType, setClientType] = useState<ClientType>(
    concept && concept.client_type !== 'private' ? concept.client_type : 'sub_central',
  );
  const [vat, setVat] = useState(concept?.vat_rate_pct ?? '0');

  const vatAmount = parseAmount(vat || '0');
  const vatBad = vatAmount === null || Number(vatAmount) > 100;

  const save = useMutation({
    mutationFn: () => {
      const [source, id] = catalogue.split(':') as ['shipped' | 'tenant', string];
      const body: ConceptInput = {
        jurisdiction,
        public_client: publicClient,
        client_type: publicClient ? clientType : 'private',
        vat_rate_pct: vatAmount ?? '0',
      };
      if (!concept || source !== concept.catalogue_source || id !== concept.catalogue_id) {
        body.catalogue_source = source;
        body.catalogue_id = id;
      }
      return setConcept(projectId, body);
    },
    onSuccess: () => {
      onSaved();
      onClose();
    },
  });

  const pickCatalogue = (value: string) => {
    setCatalogue(value);
    const id = value.split(':')[1] ?? '';
    const suggested = CATALOGUE_JURISDICTION[id];
    if (suggested) {
      setJurisdiction(suggested);
      if (suggested === 'none') setPublicClient(false);
    }
  };

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
          <Button loading={save.isPending} disabled={vatBad} onClick={() => save.mutate()} data-testid="concept-save">
            {concept
              ? t('procurement_concept.ui.save', { defaultValue: 'Save' })
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
          <select id="pc-catalogue" className={FIELD_CLASS} value={catalogue} onChange={(e) => pickCatalogue(e.target.value)}>
            {catalogues.length === 0 && concept && (
              <option value={`${concept.catalogue_source}:${concept.catalogue_id}`}>{concept.catalogue_id}</option>
            )}
            {catalogues.map((c) => (
              <option key={`${c.source}:${c.id}`} value={`${c.source}:${c.id}`}>
                {catalogueLabel(labels, c)}
              </option>
            ))}
          </select>
        </Field>

        <Field label={t('procurement_concept.ui.concept.jurisdiction', { defaultValue: 'Procurement law' })} htmlFor="pc-jurisdiction">
          <select
            id="pc-jurisdiction"
            className={FIELD_CLASS}
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value as Jurisdiction)}
          >
            {JURISDICTIONS.map((j) => (
              <option key={j} value={j}>
                {vocab(labels.t, JURISDICTION, j)}
              </option>
            ))}
          </select>
        </Field>

        <label className="flex items-start gap-2 text-sm text-content-primary">
          <input
            type="checkbox"
            className="mt-1"
            checked={publicClient}
            onChange={(e) => setPublicClient(e.target.checked)}
            data-testid="concept-public-client"
          />
          <span>
            {t('procurement_concept.ui.concept.public_client', { defaultValue: 'The client is a public body' })}
            <span className="block text-xs text-content-tertiary">
              {t('procurement_concept.ui.concept.public_client_hint', {
                defaultValue: 'Thresholds apply to public clients only. A private client keeps the law for reference.',
              })}
            </span>
          </span>
        </label>

        {publicClient && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t('procurement_concept.ui.concept.client_type', { defaultValue: 'Kind of public client' })} htmlFor="pc-client-type">
              <select
                id="pc-client-type"
                className={FIELD_CLASS}
                value={clientType}
                onChange={(e) => setClientType(e.target.value as ClientType)}
              >
                {CLIENT_TYPES.map((c) => (
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
              <input
                id="pc-vat"
                inputMode="decimal"
                className={FIELD_CLASS}
                value={vat}
                onChange={(e) => setVat(e.target.value)}
              />
            </Field>
          </div>
        )}
      </div>
    </WideModal>
  );
}
