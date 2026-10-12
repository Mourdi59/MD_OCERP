// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Why the closed buttons of a record are closed, as text beside them. A
// tooltip alone is invisible on a touch screen and to anyone who does not
// hover, so the server's reason is also written out, once per reason.

import { useTranslation } from 'react-i18next';

import type { Capable } from './api';
import { humanizeCode } from './labels';
import { closedReasons } from './rules';

export function ClosedReasons({ row, actions }: { row: Capable | null | undefined; actions: readonly string[] }) {
  const { t } = useTranslation();
  const codes = closedReasons(row, actions);
  if (codes.length === 0) return null;
  return (
    <p className="w-full basis-full text-xs text-content-tertiary" data-testid="closed-reason">
      {codes.map((code) => (
        <span key={code} className="block">
          {t(`quality_concept.errors.${code}`, { defaultValue: humanizeCode(code) })}
        </span>
      ))}
    </p>
  );
}
