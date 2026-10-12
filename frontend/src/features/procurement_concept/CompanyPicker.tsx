// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// One picker over the two company registers: subcontractors and vendors. A
// bidder candidate and the supplier of a framework agreement are both "a
// registered company", so they share it. The value is `subcontractor:id`,
// `vendor:id`, or empty for a company that is not registered yet.

import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';

import { listSubcontractors } from '@/features/subcontractors/api';
import { listVendors } from '@/features/supplier-catalogs/api';

import { FIELD_CLASS, Field } from './ProcurementBits';

export interface RegisteredCompany {
  value: string;
  name: string;
}

/** Both registers, read once the form that needs them is open. */
export function useCompanyRegister(enabled: boolean) {
  const subcontractorsQ = useQuery({
    queryKey: ['procurement-concept-company', 'subcontractors'],
    queryFn: () => listSubcontractors({ limit: 200, active_only: true }).then((p) => p.items),
    enabled,
    staleTime: 60_000,
  });
  const vendorsQ = useQuery({
    queryKey: ['procurement-concept-company', 'vendors'],
    queryFn: () => listVendors({ status: 'active', limit: 200 }).then((p) => p.items),
    enabled,
    staleTime: 60_000,
  });
  const subcontractors: RegisteredCompany[] = (subcontractorsQ.data ?? []).map((s) => ({
    value: `subcontractor:${s.id}`,
    name: s.trade_name || s.legal_name,
  }));
  const vendors: RegisteredCompany[] = (vendorsQ.data ?? []).map((v) => ({ value: `vendor:${v.id}`, name: v.name }));
  return {
    subcontractors,
    vendors,
    loading: subcontractorsQ.isLoading || vendorsQ.isLoading,
    /** One register could not be read, so the list may miss companies. */
    partial: subcontractorsQ.isError || vendorsQ.isError,
    nameOf: (value: string) => [...subcontractors, ...vendors].find((c) => c.value === value)?.name ?? null,
  };
}

export function CompanyPicker({
  id,
  label,
  value,
  keptName,
  register,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  /** The name of the linked company when it is not among the ones the registers list now. */
  keptName?: string;
  register: ReturnType<typeof useCompanyRegister>;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const { subcontractors, vendors, loading, partial } = register;
  const known = subcontractors.some((c) => c.value === value) || vendors.some((c) => c.value === value);
  const hint = loading
    ? t('procurement_concept.ui.candidate.company_loading', { defaultValue: 'Reading the subcontractor and vendor registers' })
    : partial
      ? t('procurement_concept.ui.candidate.company_partial', {
          defaultValue: 'Part of the company register could not be read, so this list may be incomplete.',
        })
      : subcontractors.length + vendors.length === 0
        ? t('procurement_concept.ui.candidate.company_none', {
            defaultValue: 'No subcontractor or vendor is registered yet. Type the company name instead.',
          })
        : undefined;
  return (
    <Field label={label} htmlFor={id} hint={hint}>
      <select id={id} className={FIELD_CLASS} value={value} aria-busy={loading} onChange={(e) => onChange(e.target.value)} data-testid="company-picker">
        <option value="">{t('procurement_concept.ui.candidate.not_registered', { defaultValue: 'Not registered yet' })}</option>
        {value && !known && (
          <option value={value}>{keptName || t('procurement_concept.ui.candidate.company_kept', { defaultValue: 'The company linked before' })}</option>
        )}
        {subcontractors.length > 0 && (
          <optgroup label={t('procurement_concept.ui.candidate.group_subcontractors', { defaultValue: 'Subcontractors' })}>
            {subcontractors.map((c) => (
              <option key={c.value} value={c.value}>
                {c.name}
              </option>
            ))}
          </optgroup>
        )}
        {vendors.length > 0 && (
          <optgroup label={t('procurement_concept.ui.candidate.group_vendors', { defaultValue: 'Vendors' })}>
            {vendors.map((c) => (
              <option key={c.value} value={c.value}>
                {c.name}
              </option>
            ))}
          </optgroup>
        )}
      </select>
    </Field>
  );
}
