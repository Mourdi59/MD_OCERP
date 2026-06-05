import { useState, useCallback, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Info, X, ChevronDown } from 'lucide-react';

/**
 * Collapsible contextual info / help banner used across every module page.
 *
 * It explains - in the UI itself - what a page is for and how it connects to
 * the rest of the platform, while staying out of the way of power users:
 *
 *  - Expanded: a light-background card with an info icon, a title and the body.
 *  - Collapsed: a compact one-line header (icon + title + chevron) that still
 *    shows there is help here and can be re-opened with one click.
 *
 * The collapsed/expanded choice is remembered per page under
 * ``oce.intro.<storageKey>`` in localStorage, so once a user collapses the
 * block on a page it stays collapsed there on the next visit. Clicking the
 * header toggles it; the X collapses it. Use the SAME ``storageKey`` you would
 * pass to the old SectionIntro so existing preferences carry over.
 */

export interface DismissibleInfoLink {
  label: string;
  onClick: () => void;
}

export function DismissibleInfo({
  storageKey,
  title,
  children,
  links,
  className,
}: {
  /** Stable key - collapsed state is remembered under `oce.intro.<storageKey>`. */
  storageKey: string;
  title: string;
  children?: ReactNode;
  /** Optional cross-module shortcuts rendered as inline pills. */
  links?: DismissibleInfoLink[];
  /** Extra classes for the outer wrapper (e.g. margin overrides). */
  className?: string;
}) {
  const { t } = useTranslation();
  const lsKey = `oce.intro.${storageKey}`;

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(lsKey) === '1';
    } catch {
      return false;
    }
  });

  const persist = useCallback(
    (value: boolean) => {
      setCollapsed(value);
      try {
        localStorage.setItem(lsKey, value ? '1' : '0');
      } catch {
        /* private mode / quota - non-fatal, state just resets next load */
      }
    },
    [lsKey],
  );

  const toggle = useCallback(() => persist(!collapsed), [collapsed, persist]);

  const wrapper = `rounded-xl border border-oe-blue/20 bg-oe-blue-subtle/50 animate-fade-in ${
    className ?? 'mb-5'
  }`;

  if (collapsed) {
    return (
      <div className={wrapper}>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={false}
          className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left"
          title={t('common.expand', { defaultValue: 'Expand' })}
        >
          <Info size={15} className="shrink-0 text-oe-blue" />
          <span className="min-w-0 flex-1 truncate text-sm font-semibold text-content-primary">
            {title}
          </span>
          <ChevronDown size={15} className="shrink-0 text-content-tertiary" />
        </button>
      </div>
    );
  }

  return (
    <div className={wrapper}>
      <div className="flex items-start gap-3 px-4 py-3.5">
        <button
          type="button"
          onClick={toggle}
          aria-expanded
          className="mt-0.5 shrink-0"
          title={t('common.collapse', { defaultValue: 'Collapse' })}
        >
          <Info size={16} className="text-oe-blue" />
        </button>
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={toggle}
            aria-expanded
            className="block w-full text-left"
            title={t('common.collapse', { defaultValue: 'Collapse' })}
          >
            <span className="text-sm font-semibold text-content-primary">{title}</span>
          </button>
          {children != null && (
            <div className="mt-1 text-sm leading-relaxed text-content-secondary">{children}</div>
          )}
          {links && links.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {links.map((l) => (
                <button
                  key={l.label}
                  type="button"
                  onClick={l.onClick}
                  className="inline-flex items-center gap-1 rounded-full border border-oe-blue/30 bg-surface-primary px-2.5 py-1 text-xs font-medium text-oe-blue transition-colors hover:bg-oe-blue hover:text-content-inverse"
                >
                  {l.label}
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => persist(true)}
          aria-label={t('common.collapse', { defaultValue: 'Collapse' })}
          title={t('common.collapse', { defaultValue: 'Collapse' })}
          className="shrink-0 rounded-md p-1 text-content-tertiary transition-colors hover:bg-surface-secondary hover:text-content-primary"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
