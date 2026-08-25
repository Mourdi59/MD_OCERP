// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// CompanyHive - the kinds of company a case is written for, as a honeycomb.
//
// The case page already draws its modules as a comb (ModuleHive.tsx). This is
// the other half of the same question: a case has a REACH across the product,
// and it has an AUDIENCE. Both are short lists the reader should be able to
// take in at a glance, so both are the same drawing. `Hive` is shared verbatim;
// only the cargo differs, which is why there is no second layout here to drift
// from the first one.
//
// THREE DIFFERENCES FROM THE MODULE COMB, all of them in the data:
//
//   TINT IS PER CELL. A case's modules share the case's discipline colour,
//   because they are that one case's route through the product. Company types
//   are not the case's property - they exist across the whole catalogue and
//   each carries its own colour on the hub's "I work as..." selector. A comb
//   that repainted them in the case's discipline would be inventing a
//   relationship the palette elsewhere denies.
//
//   THE CELLS CARRY PHOTOGRAPHS. There is a company scene on disk for each of
//   these (caseFaces.ts), the same picture the hub's selector uses, so the
//   cell can be the firm rather than a glyph standing in for it. It is washed
//   back behind the glyph and the name: decorative, and out of the accessible
//   tree, because the label is what a reader has to be able to act on.
//
//   THE CELLS ARE BIGGER. Four company names are a smaller band than a dozen
//   module names, and at module size a band of three read as an unfinished
//   comb rather than a small complete one. The count problem is answered by
//   the size of the cells, not by padding the comb out with cells for company
//   types the case was not written for - a hexagon nobody can act on reads as
//   disabled, and five of those beside three live ones is a worse answer than
//   three alone. The denominator is a fact and it is in the caption, in words.

import type { ReactElement } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Hive, type HiveCell } from './ModuleHive';
import { COMPANY_TYPE_BY_ID, COMPANY_TYPE_META } from './companyTypes';
import { companyThumbFor } from './caseFaces';
import { useCasesStore } from './useCasesStore';
import type { CompanyType, Playbook } from './types';

export interface CaseCompanyHiveProps {
  playbook: Playbook;
}

/**
 * The company comb for one case: the kinds of firm this case was written for,
 * each in its own colour, each a way into the rest of the catalogue.
 *
 * Activating a cell narrows the case library to that kind of company and opens
 * it - the same filter the hub's "I work as..." selector sets, written to the
 * same store, so the hub comes up already answering "what else is here for a
 * firm like mine". Renders nothing for a case that names no company type,
 * the same as the module comb does for a case that reaches no module.
 */
export function CaseCompanyHive({ playbook }: CaseCompanyHiveProps): ReactElement | null {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const setCompanyTypes = useCasesStore((s) => s.setCompanyTypes);

  // Unknown ids are dropped rather than drawn: a company type renamed in
  // `types.ts` and left behind in a case file has no label, no colour and no
  // hub filter to lead to, and a cell for it would be all three of those
  // failures at once.
  const cells: HiveCell[] = playbook.companyTypes.flatMap((id: CompanyType) => {
    const meta = COMPANY_TYPE_BY_ID[id];
    if (!meta) return [];
    return [
      {
        id: meta.id,
        label: t(meta.labelKey, { defaultValue: meta.labelDefault }),
        icon: meta.icon,
        tint: meta.tint,
        image: companyThumbFor(meta.id) ?? undefined,
      },
    ];
  });
  if (cells.length === 0) return null;

  const heading = t('cases.company_hive.title', {
    defaultValue: 'Written for these kinds of company',
  });

  // Same rule the module comb uses: a band deep enough to stay compact once
  // there are more than six cells, a single zigzag strip below that.
  const rows = cells.length > 6 ? 2 : 1;

  return (
    <section
      aria-label={heading}
      className="w-fit max-w-full rounded-xl border border-border-light bg-surface-primary p-4"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-5">
        <div className="min-w-0 sm:w-36 sm:shrink-0">
          <p className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
            {heading}
          </p>
          {/* The denominator is real here, unlike the module comb's: the
              company types are a closed union in `types.ts`, so "3 of 8" is a
              fact about the catalogue rather than a number somebody chose.

              `count` is bound to the TOTAL and the subset rides in `shown`,
              which reads backwards until you know why. i18next picks the
              plural form from `count`, and in "3 of 8 company types" the noun
              is governed by the eight, not the three: the languages that
              inflect it want the form the TOTAL asks for. Bound to the subset,
              every one of them would agree with the wrong number while the
              English output went on looking perfectly correct. */}
          <p className="text-xs text-content-tertiary">
            {t('cases.company_hive.count', {
              defaultValue: '{{shown}} of {{count}} company types',
              defaultValue_other: '{{shown}} of {{count}} company types',
              shown: cells.length,
              count: COMPANY_TYPE_META.length,
            })}
          </p>
        </div>
        <Hive
          cells={cells}
          label={heading}
          onSelect={(id) => {
            setCompanyTypes([id as CompanyType]);
            navigate('/cases');
          }}
          cellWidth={136}
          rows={rows}
        />
      </div>
    </section>
  );
}
