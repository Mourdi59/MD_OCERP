/**
 * What still links to a document, shown on the menu that deletes it.
 *
 * Twenty-eight columns across twenty-one modules hold a document id that no
 * foreign key constrains, and the delete path removes the row without asking
 * any of them, so the person choosing Delete had no way to know what they
 * were severing.
 *
 * The delete this sits on is the recycle bin one: the row leaves `documents`
 * immediately, which is when the links go dangling, and Restore forces the
 * original id back so they re-attach. The wording therefore says what the
 * delete does now, not what it does forever - the permanent version happens
 * later, in the bin, where the document row is already gone and this endpoint
 * can no longer be asked.
 *
 * This panel is advisory and never blocks: several of those links are
 * documented as deliberately severable, so the call stays with the person.
 * It renders nothing at all when nothing points at the document, which is the
 * common case - a warning that appears every time teaches people to dismiss it.
 *
 * Documents only. The file manager lists eight kinds and the endpoint answers
 * for one of them, so the caller gates on `kind === 'document'` rather than
 * letting seven kinds each draw the failure state.
 *
 * Module names are read from the keys those modules already use for their own
 * headings, so this panel inherits their translations in all locales instead
 * of minting a parallel set of names that would drift from the navigation.
 */
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  fetchDocumentReferences,
  type DocumentReferenceImpact,
  type DocumentReferenceItem,
} from './api';

/** Module key to the i18n key that module already uses for its own name. */
const MODULE_LABEL_KEYS: Record<string, string> = {
  cde: 'cde.title',
  closeout: 'closeout.title',
  construction_control: 'construction_control.title',
  contracts: 'contracts.title',
  correspondence: 'correspondence.title',
  defects_liability: 'defects_liability.title',
  design_options: 'nav.design_options',
  documents: 'documents.title',
  fieldreports: 'fieldreports.title',
  markups: 'markups.title',
  meetings: 'meetings.title',
  plan_room: 'plan_room.title',
  portal: 'portal.title',
  punchlist: 'nav.punchlist',
  qms: 'nav.qms',
  // No page and no nav entry of its own - it is the chunked-upload bookkeeping.
  resumable_uploads: 'documents.references.module_resumable_uploads',
  takeoff: 'takeoff.title',
  tax_withholding: 'nav.tax_withholding',
  temporary_works: 'temporary_works.title',
  transmittals: 'transmittals.title',
  variations: 'nav.variations',
};

/** Heaviest consequence first: what cannot be repaired leads. */
const IMPACT_ORDER: DocumentReferenceImpact[] = ['strands', 'unlinks', 'retains'];

/* The panel is a block in someone else's container, not a floating card: the
   context menu is 192px wide with `overflow-hidden`, so a positioned w-72
   child would be clipped rather than shown. It takes the width it is given. */
const SHELL = 'border-t border-border-light bg-surface-secondary/50 px-3 py-2';

interface DocumentDeleteWarningProps {
  documentId: string;
}

function sumByModule(items: DocumentReferenceItem[]): { module: string; count: number }[] {
  const totals = new Map<string, number>();
  for (const item of items) {
    totals.set(item.module, (totals.get(item.module) ?? 0) + item.count);
  }
  return [...totals.entries()]
    .map(([module, count]) => ({ module, count }))
    .sort((a, b) => b.count - a.count || a.module.localeCompare(b.module));
}

export function DocumentDeleteWarning({ documentId }: DocumentDeleteWarningProps) {
  const { t } = useTranslation();
  const { data, isError } = useQuery({
    // Its own first element, not a branch of ['documents']. That key is the
    // document register, a paged list, and nine call sites invalidate it to
    // mean the register changed; nesting this under it made every one of them
    // drop this answer too, which none of them intended. It also put a
    // single-document read inside the key the envelope guard watches, and that
    // guard reads the first element only, so it reported this panel as a
    // register consumer that had not been migrated to {items, total} when it
    // reads neither items nor a list. ['document-activity', id, limit] is the
    // same shape for the same reason, one document's detail under a name of
    // its own.
    queryKey: ['document-references', documentId],
    queryFn: () => fetchDocumentReferences(documentId),
    // The row is about to be deleted, so a stale count would be the one thing
    // this panel must not show. `staleTime` alone does not buy that: it marks
    // the entry stale so a refetch fires, while React Query still hands the
    // cached value to the first render. Re-opening the menu on the same file
    // would paint the previous count for as long as the round trip takes, and
    // that is the moment the user reaches for Delete. `gcTime: 0` drops the
    // entry when the menu unmounts, so the next open starts with no answer and
    // shows nothing until this one lands. Measured: with the request held for
    // three seconds the old pair still painted the count in 300ms.
    staleTime: 0,
    gcTime: 0,
    retry: false,
  });

  // Say so rather than rendering nothing. An absent panel reads as "nothing
  // links to this file", and a failed check is not that - it is no answer at
  // all. Staying silent here would be the one fallback this panel must never
  // make, because the user acts on it by deleting.
  if (isError) {
    return (
      <div className={SHELL} role="status">
        <div className="flex items-center gap-1.5">
          <AlertTriangle size={12} className="shrink-0 text-semantic-warning" />
          <span className="text-2xs text-content-secondary">
            {t('documents.references.unavailable', {
              defaultValue: 'Could not check what links to this file',
            })}
          </span>
        </div>
      </div>
    );
  }

  if (!data || data.total === 0) return null;

  const headline: Record<DocumentReferenceImpact, string> = {
    strands: t('documents.references.strands', {
      count: data.strands,
      defaultValue_one: '{{count}} record will be left pointing at nothing',
      defaultValue_other: '{{count}} records will be left pointing at nothing',
      defaultValue: '{{count}} records will be left pointing at nothing',
    }),
    unlinks: t('documents.references.unlinks', {
      count: data.unlinks,
      defaultValue_one: '{{count}} record loses the attachment',
      defaultValue_other: '{{count}} records lose the attachment',
      defaultValue: '{{count}} records lose the attachment',
    }),
    retains: t('documents.references.retains', {
      count: data.retains,
      defaultValue_one: '{{count}} record keeps it on file',
      defaultValue_other: '{{count}} records keep it on file',
      defaultValue: '{{count}} records keep it on file',
    }),
  };

  return (
    <div className={SHELL} role="status">
      <div className="mb-1 flex items-center gap-1.5">
        <AlertTriangle size={12} className="shrink-0 text-semantic-warning" />
        <span className="text-2xs font-semibold text-content-primary">
          {t('documents.references.title', { defaultValue: 'What still links to this file' })}
        </span>
      </div>

      {IMPACT_ORDER.map((impact) => {
        const items = data.references.filter((item) => item.impact === impact);
        if (items.length === 0) return null;
        const modules = sumByModule(items);
        return (
          <div key={impact} className="mb-1 last:mb-0">
            <div
              className={
                impact === 'strands'
                  ? 'text-2xs font-medium text-semantic-error'
                  : 'text-2xs font-medium text-content-secondary'
              }
            >
              {headline[impact]}
            </div>
            <div className="mt-0.5 text-2xs text-content-tertiary">
              {modules
                .map(({ module, count }) => {
                  const key = MODULE_LABEL_KEYS[module];
                  const name = key ? t(key, { defaultValue: module }) : module;
                  return `${name} ${count}`;
                })
                .join(' · ')}
            </div>
          </div>
        );
      })}
    </div>
  );
}
