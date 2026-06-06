import { useState, useCallback, type ReactNode, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Info, X } from 'lucide-react';

/**
 * Contextual info / help card used across every module page.
 *
 * It explains - in the UI itself - what a page is for and how it connects to
 * the rest of the platform, while staying out of the way of power users. It is
 * a light, notion-style help card (NOT a loud alert) with TWO states only:
 *
 *  - Expanded: a soft, translucent card with an info chip, a title and the
 *    body. Clicking anywhere on the card - or on the X - collapses it.
 *  - Collapsed: a bare inline line (NO background, NO border, NO card): a small
 *    Info icon plus the muted label "Module information". It takes minimal
 *    vertical space and re-expands with one click. It is a real button, so it
 *    is keyboard accessible and carries aria-expanded=false for AT.
 *
 * There is no longer a dismissed / render-null state. The X now simply
 * collapses, so the line "Module information" is always reachable.
 *
 * Persistence lives under ``oce.intro.<storageKey>`` in localStorage:
 *
 *   - missing / "0" -> expanded
 *   - "1"           -> collapsed
 *   - "2"           -> collapsed (LEGACY "dismissed" value: users who pressed
 *                      the old X now see the collapsed line instead of nothing)
 *
 * Use the SAME ``storageKey`` you would pass to the old SectionIntro so
 * existing preferences carry over. The public API (storageKey, title,
 * children, links, className) is consumed by 18+ pages and must not change.
 */

export interface DismissibleInfoLink {
  label: string;
  onClick: () => void;
}

/** Persisted display states for an info card. */
type IntroState = 'expanded' | 'collapsed';

function readState(lsKey: string): IntroState {
  try {
    const raw = localStorage.getItem(lsKey);
    // Both "1" (collapsed) and the legacy "2" (old dismissed) now resolve to
    // collapsed, so previously-hidden cards reappear as the bare line.
    if (raw === '1' || raw === '2') return 'collapsed';
    return 'expanded';
  } catch {
    return 'expanded';
  }
}

const STATE_TO_RAW: Record<IntroState, string> = {
  expanded: '0',
  collapsed: '1',
};

export function DismissibleInfo({
  storageKey,
  title,
  children,
  links,
  className,
}: {
  /** Stable key - display state is remembered under `oce.intro.<storageKey>`. */
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

  const [state, setState] = useState<IntroState>(() => readState(lsKey));

  const persist = useCallback(
    (next: IntroState) => {
      setState(next);
      try {
        localStorage.setItem(lsKey, STATE_TO_RAW[next]);
      } catch {
        /* private mode / quota - non-fatal, state just resets next load */
      }
    },
    [lsKey],
  );

  const collapse = useCallback(() => persist('collapsed'), [persist]);
  const expand = useCallback(() => persist('expanded'), [persist]);

  const onCollapsedKeyDown = useCallback(
    (e: KeyboardEvent<HTMLElement>) => {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
        e.preventDefault();
        expand();
      }
    },
    [expand],
  );

  if (state === 'collapsed') {
    // Collapsed: a bare inline line - no card chrome at all. It is a native
    // button so it is keyboard accessible and announces aria-expanded=false.
    return (
      <button
        type="button"
        onClick={expand}
        onKeyDown={onCollapsedKeyDown}
        aria-expanded={false}
        className={`group inline-flex cursor-pointer items-center gap-1.5 rounded-sm bg-transparent text-content-tertiary transition-colors hover:text-content-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus ${
          className ?? 'mb-3'
        }`}
      >
        <Info size={13} className="shrink-0" />
        <span className="text-xs">
          {t('common.module_info', { defaultValue: 'Module information' })}
        </span>
      </button>
    );
  }

  // Expanded: a soft, translucent card. The X and the link pills are
  // interactive, so they cannot live inside a role=button (nesting interactive
  // content is invalid ARIA). Instead the outer row is a plain div with a
  // click/keyboard handler (whole-card toggle), and a dedicated header BUTTON
  // carries the aria-expanded semantics for AT.
  const wrapper = `group rounded-xl border border-border-light border-l-2 border-l-oe-blue/70 bg-oe-blue-subtle/25 shadow-sm animate-fade-in ${
    className ?? 'mb-5'
  }`;

  return (
    <div className={wrapper}>
      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions, jsx-a11y/click-events-have-key-events */}
      <div
        onClick={collapse}
        className="flex cursor-pointer items-start gap-3 rounded-xl px-4 py-4 transition-colors hover:bg-surface-secondary/30"
      >
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-oe-blue-subtle/70">
          <Info size={16} className="text-oe-blue-text" />
        </span>
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={(e) => {
              // The header button is the keyboard/AT toggle (Enter/Space fire
              // a native click). The outer div also handles pointer clicks, so
              // swallow this one to avoid a double-toggle when the pointer
              // lands on the title.
              e.stopPropagation();
              collapse();
            }}
            aria-expanded
            title={t('common.collapse', { defaultValue: 'Collapse' })}
            className="block rounded-sm text-left text-base font-medium leading-snug text-content-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus"
          >
            {title}
          </button>
          {children != null && (
            <div className="mt-1.5 text-sm leading-relaxed text-content-secondary/90">{children}</div>
          )}
          {links && links.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {links.map((l) => (
                <button
                  key={l.label}
                  type="button"
                  onClick={(e) => {
                    // Inner pills must never toggle the card.
                    e.stopPropagation();
                    l.onClick();
                  }}
                  className="inline-flex items-center gap-1 rounded-full border border-oe-blue/30 bg-surface-primary px-2.5 py-1 text-xs font-medium text-oe-blue-text transition-colors hover:bg-oe-blue hover:text-content-inverse"
                >
                  {l.label}
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={(e) => {
            // The X now simply collapses - it must not bubble into the card
            // toggle (which would double-fire), and it no longer hides forever.
            e.stopPropagation();
            collapse();
          }}
          aria-label={t('common.collapse', { defaultValue: 'Collapse' })}
          title={t('common.collapse', { defaultValue: 'Collapse' })}
          className="-mr-1 -mt-1 shrink-0 rounded-md p-1.5 text-content-tertiary opacity-60 transition-all hover:bg-surface-secondary hover:text-content-primary hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus"
        >
          <X size={15} />
        </button>
      </div>
    </div>
  );
}
