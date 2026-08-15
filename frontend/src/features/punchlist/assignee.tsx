// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Who a punch item is assigned to, in a form a reader can use.
 *
 * `assigned_to` is a free-text column and both a typed-in name and a contact
 * id are legitimate contents - the demo seeder, and the integrations that
 * follow it, store an id. Every screen printed the column as it stood, so a
 * row read "Assigned To 3f2b8c1e-9a44-..." and the avatar beside it took its
 * initial from a hex digit. The API now resolves ids against the contacts
 * register and sends `assigned_to_name` beside the raw value; this module
 * decides what to paint from the pair, so the list, the kanban card, the
 * drawer and the insights charts all say the same thing.
 *
 * An id that resolved to nothing is deliberately not shown as "Unassigned".
 * The snag does have an owner, we simply cannot name them, and telling a site
 * manager it is unassigned invites a second assignment.
 */

import { useTranslation } from 'react-i18next';
import clsx from 'clsx';

const CONTACT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type Assignee =
  /** Nobody is named on the item. */
  | { kind: 'none' }
  /** Someone is named, and this is their name. */
  | { kind: 'named'; name: string }
  /** An id is stored that no contact answers to. */
  | { kind: 'unresolved' };

/**
 * Decide what an assignee field says.
 *
 * @param raw - The stored column value: a name, a contact id, or nothing.
 * @param resolved - The name the API found for that id, when it found one.
 */
export function resolveAssignee(
  raw: string | null | undefined,
  resolved?: string | null,
): Assignee {
  const name = resolved?.trim();
  if (name) return { kind: 'named', name };
  const value = raw?.trim();
  if (!value) return { kind: 'none' };
  // Anything that is not an id is what someone typed, and what they typed is
  // the answer - an email address and a surname are both usable as they are.
  return CONTACT_ID.test(value) ? { kind: 'unresolved' } : { kind: 'named', name: value };
}

type Variant = 'card' | 'row' | 'plain';

const AVATAR: Record<Variant, string> = {
  card: 'h-5 w-5 text-2xs',
  row: 'h-6 w-6 text-xs',
  plain: '',
};

const NAME: Record<Variant, string> = {
  card: 'truncate max-w-[80px]',
  row: 'text-sm text-content-secondary truncate max-w-[100px]',
  plain: '',
};

const MUTED: Record<Variant, string> = {
  card: 'text-content-quaternary',
  row: 'text-sm text-content-quaternary',
  plain: 'text-content-quaternary',
};

/**
 * Paint the assignee of one punch item.
 *
 * @param raw - `item.assigned_to`.
 * @param name - `item.assigned_to_name`.
 * @param variant - Which surface is painting: a kanban card, a table row, or
 *   a drawer field that carries its own label and needs no avatar.
 */
export function AssigneeLabel({
  raw,
  name,
  variant = 'row',
}: {
  raw: string | null | undefined;
  name?: string | null;
  variant?: Variant;
}) {
  const { t } = useTranslation();
  const assignee = resolveAssignee(raw, name);

  if (assignee.kind !== 'named') {
    return (
      <span className={MUTED[variant]}>
        {assignee.kind === 'none'
          ? t('punch.unassigned', { defaultValue: 'Unassigned' })
          : t('common.unknown', { defaultValue: 'Unknown' })}
      </span>
    );
  }

  if (variant === 'plain') return <>{assignee.name}</>;

  return (
    <>
      <div
        className={clsx(
          'rounded-full bg-oe-blue/10 text-oe-blue flex items-center justify-center font-semibold shrink-0',
          AVATAR[variant],
        )}
      >
        {assignee.name.charAt(0).toUpperCase()}
      </div>
      <span className={NAME[variant]}>{assignee.name}</span>
    </>
  );
}
