// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Attach a purchase-order line to the bill position it is being bought for.
 *
 * The buyer sees bill positions and never a cost line. What comes back out of
 * this control is a `boq_position_id`, which the server resolves to the cost
 * line when the order line is written; deriving the money link is our job, not
 * theirs. See `backend/app/modules/procurement/cost_spine.py`.
 *
 * Renders nothing at all when the project's cost spine is empty. That is the
 * ordinary state of a project that has never generated one, and an empty
 * dropdown with an explanation under it would put a permanent piece of
 * furniture on the order form for a choice that cannot be made. The same
 * silence covers the case where the cost model module is not installed, since
 * a plugin that is not there answers nothing rather than answering zero.
 *
 * Filtering happens over the loaded list because the endpoint has no search
 * parameter, and the list is loaded whole (paged) for the same reason.
 */

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import {
  billPositionOptions,
  listCostSpineLines,
  matchesQuery,
  type CostSpineLine,
} from './costSpineApi';

/**
 * Above this many positions the plain dropdown stops being usable and the
 * filter box is shown with it. Below it the list is short enough to read, and
 * a search box over eight rows is clutter.
 */
const FILTER_THRESHOLD = 12;

export interface BillPositionPickerProps {
  /** Project whose cost spine is offered. */
  projectId: string;
  /** Currently selected bill position, or null when the line is unattributed. */
  value: string | null;
  /** Called with the chosen position id, or null when the buyer clears it. */
  onChange: (boqPositionId: string | null) => void;
  /**
   * Line number within the order, used for the accessible name. A form with
   * eight identical "Bill position" controls is unusable with a screen reader,
   * so each says which line it belongs to.
   */
  line?: number;
  disabled?: boolean;
}

/** `1.1 - Reinforced concrete C30/37 (m3)`, the way it reads in the bill. */
export function optionLabel(option: CostSpineLine): string {
  const unit = option.unit ? ` (${option.unit})` : '';
  return `${option.code} - ${option.description}${unit}`;
}

export function BillPositionPicker({
  projectId,
  value,
  onChange,
  line,
  disabled = false,
}: BillPositionPickerProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');

  const spine = useQuery({
    queryKey: ['procurement', 'costSpine', projectId],
    queryFn: () => listCostSpineLines(projectId),
    enabled: Boolean(projectId),
    // The spine changes when somebody regenerates it from the bill, which is
    // not something that happens while an order is being typed.
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const options = useMemo(() => billPositionOptions(spine.data ?? []), [spine.data]);
  const visible = useMemo(() => options.filter((o) => matchesQuery(o, query)), [options, query]);

  // Nothing to choose from, so nothing to show. Covers three cases that all
  // mean the same thing to the buyer: the spine has not been generated, the
  // request failed, and the cost model module is not installed.
  if (spine.isLoading || spine.isError || options.length === 0) return null;

  const label = t('procurement.item_position', { defaultValue: 'Bill position' });
  const ariaLabel =
    line === undefined
      ? label
      : t('procurement.item_position_for', {
          defaultValue: 'Bill position for line {{line}}',
          line,
        });

  // A selected position that the filter hides must still be an option, or
  // typing in the filter box would silently clear the buyer's own choice.
  const selected = value ? options.find((o) => o.boq_position_id === value) : undefined;
  const listed =
    selected && !visible.some((o) => o.boq_position_id === value) ? [selected, ...visible] : visible;

  return (
    <div className="flex flex-col gap-1">
      {options.length > FILTER_THRESHOLD && (
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={disabled}
          // The placeholder is the accessible name here on purpose. Giving the
          // filter the same aria-label as the select next to it would put two
          // controls with one name on the form, which is worse for a screen
          // reader than the fallback the placeholder already provides.
          placeholder={label}
          className="w-full rounded border border-border-light px-2 py-1 text-sm"
        />
      )}
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        disabled={disabled}
        aria-label={ariaLabel}
        className="w-full rounded border border-border-light px-2 py-1 text-sm"
      >
        <option value="">
          {t('procurement.item_position_none', { defaultValue: 'Not linked to the estimate' })}
        </option>
        {listed.map((option) => (
          <option key={option.id} value={option.boq_position_id as string}>
            {optionLabel(option)}
          </option>
        ))}
      </select>
    </div>
  );
}
