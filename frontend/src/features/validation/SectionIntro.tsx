import { type ReactNode } from 'react';
import { DismissibleInfo } from '@/shared/ui';

/**
 * Contextual intro / help banner for the Quality & Safety section.
 *
 * Thin wrapper over the shared {@link DismissibleInfo} so every page in this
 * section keeps the same API while gaining the collapse-and-remember
 * behaviour used platform-wide. Dismissal is remembered per page via
 * localStorage under `oce.intro.<storageKey>`, so existing preferences carry
 * over unchanged.
 */

export interface SectionLink {
  label: string;
  onClick: () => void;
}

export function SectionIntro({
  storageKey,
  title,
  children,
  links,
}: {
  /** Stable key - collapsed state is remembered under `oce.intro.<storageKey>`. */
  storageKey: string;
  title: string;
  children: ReactNode;
  /** Optional cross-module shortcuts rendered as inline pills. */
  links?: SectionLink[];
}) {
  return (
    <DismissibleInfo storageKey={storageKey} title={title} links={links}>
      {children}
    </DismissibleInfo>
  );
}
