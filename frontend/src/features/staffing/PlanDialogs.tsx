// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The three writes on the plan itself: starting it from a staffing catalogue,
// changing its two settings (commissioning date, remote site) and moving it
// to another catalogue.

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/shared/ui/Button';
import { ErrorState } from '@/shared/ui/ErrorState';
import { SkeletonTable } from '@/shared/ui/SkeletonLoader';
import { WideModal, WideModalField, WideModalSection } from '@/shared/ui/WideModal';
import { getErrorMessage } from '@/shared/lib/api';

import { changeCatalogue, createPlan, patchPlan, type CatalogueSummary, type StaffingPlan } from './api';
import { useStaffingCatalogues } from './hooks';
import { labelText, type LabelContext } from './labels';
import { FIELD_CLASS, FormError } from './StaffingBits';
import { useSubmit } from './useSubmit';

function CatalogueOptions({ catalogues, labels }: { catalogues: CatalogueSummary[]; labels: LabelContext }) {
  return (
    <>
      {catalogues.map((c) => (
        <option key={`${c.source}:${c.id}`} value={`${c.source}:${c.id}`}>
          {labelText(labels, c.name, c.code)}
        </option>
      ))}
    </>
  );
}

function splitChoice(choice: string): { catalogue_source: 'shipped' | 'tenant'; catalogue_id: string } {
  const at = choice.indexOf(':');
  return { catalogue_source: choice.slice(0, at) as 'shipped' | 'tenant', catalogue_id: choice.slice(at + 1) };
}

function SettingsFields({
  commissioning,
  setCommissioning,
  accommodation,
  setAccommodation,
}: {
  commissioning: string;
  setCommissioning: (v: string) => void;
  accommodation: boolean;
  setAccommodation: (v: boolean) => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <WideModalField
        label={t('staffing.plan.commissioning_date', { defaultValue: 'Planned commissioning' })}
        hint={t('staffing.plan.commissioning_hint', {
          defaultValue: 'Operation roles must start before this date. Leave it empty until it is known.',
        })}
        htmlFor="staffing-commissioning"
      >
        <input
          id="staffing-commissioning"
          type="date"
          className={FIELD_CLASS}
          value={commissioning}
          onChange={(e) => setCommissioning(e.target.value)}
        />
      </WideModalField>
      <WideModalField>
        <label className="flex items-start gap-2 text-sm text-content-primary">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={accommodation}
            onChange={(e) => setAccommodation(e.target.checked)}
            data-testid="plan-accommodation"
          />
          <span>
            {t('staffing.plan.requires_accommodation', { defaultValue: 'Remote site, people need accommodation' })}
            <span className="block text-xs text-content-tertiary">
              {t('staffing.plan.requires_accommodation_hint', {
                defaultValue: 'A confirmed person without a room booked for the start date is then flagged.',
              })}
            </span>
          </span>
        </label>
      </WideModalField>
    </>
  );
}

/** The first step on a project without a plan: choose the catalogue the roles come from. */
export function PlanSetup({ projectId, labels, onDone }: { projectId: string; labels: LabelContext; onDone: () => void }) {
  const { t } = useTranslation();
  const cataloguesQ = useStaffingCatalogues();
  const [choice, setChoice] = useState('');
  const [commissioning, setCommissioning] = useState('');
  const [accommodation, setAccommodation] = useState(false);
  const { busy, error, run } = useSubmit(onDone);

  const catalogues = cataloguesQ.data ?? [];
  useEffect(() => {
    if (!choice && catalogues.length > 0) {
      const first = catalogues.find((c) => c.id === 'neutral') ?? catalogues[0]!;
      setChoice(`${first.source}:${first.id}`);
    }
  }, [catalogues, choice]);

  if (cataloguesQ.isLoading) return <SkeletonTable rows={2} columns={2} />;
  if (cataloguesQ.isError) {
    return (
      <ErrorState
        title={t('staffing.plan.catalogues_failed', { defaultValue: 'The staffing catalogues could not be loaded' })}
        hint={getErrorMessage(cataloguesQ.error)}
        onRetry={() => cataloguesQ.refetch()}
      />
    );
  }

  return (
    <div className="rounded-lg border border-border-light p-4" data-testid="plan-setup">
      <WideModalSection columns={2}>
        <WideModalField
          label={t('staffing.plan.catalogue', { defaultValue: 'Staffing catalogue' })}
          hint={t('staffing.plan.catalogue_hint', {
            defaultValue: 'It brings the roles, the documents each role needs and how long personal data is kept.',
          })}
          htmlFor="staffing-catalogue"
        >
          <select
            id="staffing-catalogue"
            className={FIELD_CLASS}
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
            data-testid="plan-catalogue"
          >
            <CatalogueOptions catalogues={catalogues} labels={labels} />
          </select>
        </WideModalField>
        <SettingsFields
          commissioning={commissioning}
          setCommissioning={setCommissioning}
          accommodation={accommodation}
          setAccommodation={setAccommodation}
        />
      </WideModalSection>
      <div className="mt-4 flex items-center justify-end gap-3">
        <FormError message={error} />
        <Button
          loading={busy}
          disabled={!choice}
          data-testid="plan-create"
          onClick={() =>
            run(() =>
              createPlan(projectId, {
                ...splitChoice(choice),
                requires_accommodation: accommodation,
                commissioning_date: commissioning || null,
              }),
            )
          }
        >
          {t('staffing.plan.create', { defaultValue: 'Create staffing plan' })}
        </Button>
      </div>
    </div>
  );
}

export function PlanSettingsDialog({
  open,
  projectId,
  plan,
  onClose,
  onDone,
}: {
  open: boolean;
  projectId: string;
  plan: StaffingPlan;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const [commissioning, setCommissioning] = useState(plan.commissioning_date ?? '');
  const [accommodation, setAccommodation] = useState(plan.requires_accommodation);
  const { busy, error, run, reset } = useSubmit(() => {
    onDone();
    onClose();
  });
  useEffect(() => {
    if (open) {
      setCommissioning(plan.commissioning_date ?? '');
      setAccommodation(plan.requires_accommodation);
      reset();
    }
    // Reset only when the dialog opens; the plan may refetch while it is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, reset]);

  return (
    <WideModal
      open={open}
      onClose={onClose}
      busy={busy}
      size="sm"
      testId="plan-settings-dialog"
      title={t('staffing.plan.settings', { defaultValue: 'Plan settings' })}
      footer={
        <div className="flex w-full items-center justify-end gap-2">
          <FormError message={error} />
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            loading={busy}
            data-testid="plan-settings-save"
            onClick={() =>
              run(() =>
                patchPlan(projectId, {
                  requires_accommodation: accommodation,
                  commissioning_date: commissioning || null,
                }),
              )
            }
          >
            {t('common.save', { defaultValue: 'Save' })}
          </Button>
        </div>
      }
    >
      <WideModalSection columns={1}>
        <SettingsFields
          commissioning={commissioning}
          setCommissioning={setCommissioning}
          accommodation={accommodation}
          setAccommodation={setAccommodation}
        />
      </WideModalSection>
    </WideModal>
  );
}

/**
 * Move the plan to another staffing catalogue.
 *
 * The server keeps every position whose role the new catalogue also has and
 * turns the others into custom roles that keep their name, so nothing is lost.
 */
export function ChangeCatalogueDialog({
  open,
  projectId,
  plan,
  labels,
  onClose,
  onDone,
}: {
  open: boolean;
  projectId: string;
  plan: StaffingPlan;
  labels: LabelContext;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const cataloguesQ = useStaffingCatalogues(open);
  const current = `${plan.catalogue_source}:${plan.catalogue_id}`;
  const [choice, setChoice] = useState('');
  const { busy, error, run, reset } = useSubmit(() => {
    onDone();
    onClose();
  });
  useEffect(() => {
    if (open) {
      setChoice('');
      reset();
    }
  }, [open, reset]);

  const others = (cataloguesQ.data ?? []).filter((c) => `${c.source}:${c.id}` !== current);

  return (
    <WideModal
      open={open}
      onClose={onClose}
      busy={busy}
      size="sm"
      testId="change-catalogue-dialog"
      title={t('staffing.plan.change_catalogue', { defaultValue: 'Change catalogue' })}
      subtitle={t('staffing.plan.change_catalogue_hint', {
        defaultValue:
          'Positions whose role the new catalogue also has stay as they are. The others become custom roles and keep their name.',
      })}
      footer={
        <div className="flex w-full items-center justify-end gap-2">
          <FormError message={error} />
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            loading={busy}
            disabled={!choice}
            data-testid="change-catalogue-save"
            onClick={() => run(() => changeCatalogue(projectId, { ...splitChoice(choice), role_mapping: {} }))}
          >
            {t('staffing.plan.change_catalogue', { defaultValue: 'Change catalogue' })}
          </Button>
        </div>
      }
    >
      {cataloguesQ.isLoading ? (
        <SkeletonTable rows={2} columns={1} />
      ) : others.length === 0 ? (
        <p className="text-sm text-content-secondary" data-testid="no-other-catalogue">
          {t('staffing.plan.no_other_catalogue', { defaultValue: 'There is no other staffing catalogue to change to.' })}
        </p>
      ) : (
        <WideModalSection columns={1}>
          <WideModalField label={t('staffing.plan.new_catalogue', { defaultValue: 'New catalogue' })} htmlFor="staffing-new-catalogue">
            <select
              id="staffing-new-catalogue"
              className={FIELD_CLASS}
              value={choice}
              onChange={(e) => setChoice(e.target.value)}
            >
              <option value="">{t('staffing.choose', { defaultValue: 'Choose' })}</option>
              <CatalogueOptions catalogues={others} labels={labels} />
            </select>
          </WideModalField>
        </WideModalSection>
      )}
    </WideModal>
  );
}
