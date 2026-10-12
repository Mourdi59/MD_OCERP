// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Small pieces the permit screens share: the colour of each state, a person
// chip, a labelled fact, and the one dialog frame every write goes through.

import { useEffect, useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft } from 'lucide-react';

import { Badge, type BadgeVariant } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { WideModal } from '@/shared/ui/WideModal';
import { fmtDate } from '@/shared/lib/formatters';

import type { ApplicationState, ConditionState, Outcome, PermitState, ReadinessStatus, RequirementState } from './api';

export const fieldClass =
  'w-full rounded-md border border-border-light bg-surface-primary px-2.5 py-1.5 text-sm text-content-primary';

export const REQUIREMENT_TONE: Record<RequirementState, BadgeVariant> = {
  not_started: 'neutral',
  in_progress: 'blue',
  granted: 'success',
  partially_granted: 'warning',
  refused: 'error',
  blocked: 'warning',
  not_applicable: 'neutral',
  not_in_force: 'error',
  expired: 'error',
  lapsed: 'error',
};

export const APPLICATION_TONE: Record<ApplicationState, BadgeVariant> = {
  planned: 'neutral',
  preparing: 'blue',
  internal_review: 'purple',
  submitted: 'blue',
  validated: 'blue',
  under_review: 'purple',
  info_requested: 'warning',
  decided: 'success',
  withdrawn: 'neutral',
};

export const PERMIT_TONE: Record<PermitState, BadgeVariant> = {
  in_force: 'success',
  suspended: 'warning',
  lapsed: 'error',
  revoked: 'error',
  superseded: 'neutral',
  expired: 'neutral',
};

export const CONDITION_TONE: Record<ConditionState, BadgeVariant> = {
  open: 'blue',
  evidence_submitted: 'purple',
  discharge_applied: 'purple',
  discharged: 'success',
  in_compliance: 'success',
  breach: 'error',
  not_triggered: 'neutral',
  waived: 'neutral',
  superseded: 'neutral',
};

export const OUTCOME_TONE: Record<Outcome, BadgeVariant> = {
  granted: 'success',
  granted_with_conditions: 'success',
  partially_granted: 'warning',
  refused: 'error',
  deemed_granted: 'success',
  withdrawn: 'neutral',
};

export const READINESS_TONE: Record<ReadinessStatus, BadgeVariant> = {
  ready: 'success',
  at_risk: 'warning',
  not_ready: 'error',
  no_roadmap: 'neutral',
};

export function ToneBadge({ tone, children, testId }: { tone: BadgeVariant; children: ReactNode; testId?: string }) {
  return (
    <span data-testid={testId}>
      <Badge variant={tone} size="sm">
        {children}
      </Badge>
    </span>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0]!.charAt(0) + parts[parts.length - 1]!.charAt(0) : name.slice(0, 2);
  return letters.toUpperCase();
}

/** An owner shown as initials and name, or a clear "no owner" when the slot is empty. */
export function PersonChip({ name }: { name: string | null }) {
  const { t } = useTranslation();
  if (!name) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-semantic-error" data-testid="owner-missing">
        <span className="flex h-5 w-5 items-center justify-center rounded-full border border-dashed border-semantic-error/60 text-2xs">
          ?
        </span>
        {t('permits.ui.owner_missing', { defaultValue: 'No owner' })}
      </span>
    );
  }
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 text-xs text-content-secondary" title={name}>
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-oe-blue-subtle text-2xs font-semibold text-oe-blue-text">
        {initials(name)}
      </span>
      <span className="truncate">{name}</span>
    </span>
  );
}

/** A date for reading, or a dash when there is none. */
export function dateText(value: string | null | undefined): string {
  return value ? fmtDate(value) : '-';
}

/** One labelled value of a record. */
export function Fact({ label, children, testId }: { label: string; children: ReactNode; testId?: string }) {
  return (
    <div className="min-w-0" data-testid={testId}>
      <dt className="text-2xs uppercase tracking-wide text-content-tertiary">{label}</dt>
      <dd className="mt-0.5 text-sm text-content-primary">{children}</dd>
    </div>
  );
}

/** The heading of a record opened in place, with the way back to the list. */
export function PanelHeader({
  title,
  subtitle,
  badge,
  onBack,
  backLabel,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  badge?: ReactNode;
  onBack: () => void;
  backLabel: string;
  actions?: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Button variant="ghost" size="sm" icon={<ArrowLeft size={14} />} onClick={onBack} data-testid="panel-back">
        {backLabel}
      </Button>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold text-content-primary">{title}</h2>
            {badge}
          </div>
          {subtitle && <p className="mt-0.5 text-sm text-content-secondary">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-start gap-2">{actions}</div>}
      </div>
    </div>
  );
}

/** A refusal or a load failure said where the reader is looking. */
export function Refusal({ children, testId = 'refusal' }: { children: ReactNode; testId?: string }) {
  if (!children) return null;
  return (
    <p
      role="alert"
      data-testid={testId}
      className="rounded-md border border-semantic-error/30 bg-semantic-error-bg px-3 py-2 text-sm text-content-primary"
    >
      {children}
    </p>
  );
}

export function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: (id: string) => ReactNode;
}) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-content-primary">
        {label}
        {required && (
          <span className="ml-1 text-xs font-normal text-semantic-error">
            {t('permits.ui.required', { defaultValue: 'required' })}
          </span>
        )}
      </label>
      {children(id)}
      {hint && <p className="mt-1 text-xs text-content-tertiary">{hint}</p>}
    </div>
  );
}

export interface FormDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: ReactNode;
  submitLabel: string;
  busy: boolean;
  /** The server's refusal of the last attempt, as a sentence. */
  error: string | null;
  /** What the draft still lacks. Shown once the reader has tried to send it. */
  problems?: string[];
  onSubmit: () => void;
  children: ReactNode;
  testId: string;
  size?: 'md' | 'lg' | 'xl';
  danger?: boolean;
}

/**
 * The frame of every write: what is being recorded, the fields, what is still
 * missing, the server's refusal, and one button that sends it.
 */
export function FormDialog({
  open,
  onClose,
  title,
  subtitle,
  submitLabel,
  busy,
  error,
  problems = [],
  onSubmit,
  children,
  testId,
  size = 'md',
  danger = false,
}: FormDialogProps) {
  const { t } = useTranslation();
  const [tried, setTried] = useState(false);
  useEffect(() => {
    if (!open) setTried(false);
  }, [open]);
  const send = () => {
    setTried(true);
    if (problems.length === 0) onSubmit();
  };
  return (
    <WideModal
      open={open}
      onClose={onClose}
      title={title}
      subtitle={subtitle}
      size={size}
      busy={busy}
      testId={testId}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {t('permits.ui.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button variant={danger ? 'danger' : 'primary'} loading={busy} onClick={send} data-testid={`${testId}-submit`}>
            {submitLabel}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Refusal testId={`${testId}-error`}>{error}</Refusal>}
        {tried && problems.length > 0 && (
          <ul
            role="alert"
            data-testid={`${testId}-problems`}
            className="list-disc space-y-0.5 rounded-md border border-semantic-warning/40 bg-semantic-warning-bg py-2 pl-7 pr-3 text-sm text-content-primary"
          >
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        )}
        {children}
      </div>
    </WideModal>
  );
}
