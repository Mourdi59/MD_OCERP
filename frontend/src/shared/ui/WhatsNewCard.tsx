/**
 * WhatsNewCard — friendly "what's new in vX.Y.Z" release-notes card.
 *
 * Compact single-row variant (audit 2026-05-23 — user feedback "сделай
 * компактней не два ряда а в один и что если пользователь один раз его
 * закроет показывай только кнопкой"):
 *
 *   - One horizontal row: sparkle badge → version headline → short tagline
 *     → 6 chip pills (one per category, icon + label) → tour CTA + close.
 *   - Each chip is a `<button>` that toggles a small inline popover with
 *     the previous bullet content. Hover (desktop) or tap (mobile) opens
 *     it; click outside or another chip closes it.
 *   - Total height ~80–100 px on a 13" laptop. Chips wrap to a second row
 *     only on narrow viewports (sm and below) — acceptable degradation.
 *
 * Dismissal & reopen:
 *
 *   - First visit on a new major.minor → card auto-shown.
 *   - Click X / Dismiss → card hidden, a small "What's new" pill renders
 *     in its place. `localStorage.oe.last_seen_version` persists the
 *     dismissal for the version (next major.minor bump resets it).
 *   - Click the pill → card re-appears for this session only. Dismissing
 *     again hides it back to the pill. Reloading keeps it as the pill.
 *   - A separate session-only flag (`oe.whatsnew_reopened`) is used to
 *     track the in-tab "I clicked the pill" state; it is NOT persisted.
 *
 * Tour wiring is preserved: the "Take a quick tour" affordance dispatches
 * `window.CustomEvent('oe:start-tour')` exactly as before.
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Sparkles,
  X,
  ArrowRight,
  Clock,
  Gauge,
  ShieldCheck,
  FileText,
  Bot,
  Camera,
  type LucideIcon,
} from 'lucide-react';
import { APP_VERSION } from '@/shared/lib/version';

/** localStorage key that records which release the user has acknowledged. */
const LAST_SEEN_KEY = 'oe.last_seen_version';

/**
 * Compare versions on the major.minor axis only. Patch bumps (4.5.0 → 4.5.1)
 * do not re-show the card — those are hotfixes and the user has already seen
 * the headline content for the minor. Only feature releases re-trigger.
 */
function shouldShow(current: string, lastSeen: string | null): boolean {
  if (!current) return false;
  if (!lastSeen) return true;
  const cur = current.split('.').map((x) => parseInt(x, 10) || 0);
  const prev = lastSeen.split('.').map((x) => parseInt(x, 10) || 0);
  const a = cur[0] ?? 0;
  const b = cur[1] ?? 0;
  const pa = prev[0] ?? 0;
  const pb = prev[1] ?? 0;
  if (a > pa) return true;
  if (a < pa) return false;
  return b > pb;
}

interface Section {
  /** Stable identifier used for React keys + i18n key suffix. */
  id: string;
  /** lucide icon constructor — rendered with the card's accent treatment. */
  icon: LucideIcon;
  /** Translation key for the chip label (with English fallback). */
  titleKey: string;
  titleDefault: string;
  /** Compact 1–2 word chip label (shown on the pill itself). */
  chipKey: string;
  chipDefault: string;
  /** Short popover bullets (1–3 plain-language sentences). */
  bullets: { key: string; default: string }[];
}

/* ── v6.10.0 release content ────────────────────────────────────────────
   Six chips for the v6.10 wave: field time & payroll, project controls,
   compliance gates, owner billing, the agent builder and jobsite photo
   intelligence. Bullets surface only when the chip is expanded. */
const SECTIONS_V6100: Section[] = [
  {
    id: 'field',
    icon: Clock,
    titleKey: 'whatsnew.v6100.field.title',
    titleDefault: 'Field time and payroll',
    chipKey: 'whatsnew.v6100.field.chip',
    chipDefault: 'Field time',
    bullets: [
      {
        key: 'whatsnew.v6100.field.b1',
        default:
          'Crews log time on the jobsite from the field app, online or offline.',
      },
      {
        key: 'whatsnew.v6100.field.b2',
        default:
          'Approved timesheets flow straight into payroll runs with rates and allowances.',
      },
      {
        key: 'whatsnew.v6100.field.b3',
        default:
          'A subcontractor payment portal lets trades submit and track their payments.',
      },
    ],
  },
  {
    id: 'controls',
    icon: Gauge,
    titleKey: 'whatsnew.v6100.controls.title',
    titleDefault: 'Project controls dashboard',
    chipKey: 'whatsnew.v6100.controls.chip',
    chipDefault: 'Controls',
    bullets: [
      {
        key: 'whatsnew.v6100.controls.b1',
        default:
          'One dashboard ties cost, schedule and earned-value signals together.',
      },
      {
        key: 'whatsnew.v6100.controls.b2',
        default:
          'Takt planning lays out repetitive work as zones moving on a steady beat.',
      },
      {
        key: 'whatsnew.v6100.controls.b3',
        default:
          'An equipment maintenance forecast flags upcoming service before it bites.',
      },
    ],
  },
  {
    id: 'compliance',
    icon: ShieldCheck,
    titleKey: 'whatsnew.v6100.compliance.title',
    titleDefault: 'Compliance gates and ITP hold points',
    chipKey: 'whatsnew.v6100.compliance.chip',
    chipDefault: 'Gates',
    bullets: [
      {
        key: 'whatsnew.v6100.compliance.b1',
        default:
          'Compliance gates block a step until its required checks pass.',
      },
      {
        key: 'whatsnew.v6100.compliance.b2',
        default:
          'ITP hold points stop work until an inspection is signed off.',
      },
      {
        key: 'whatsnew.v6100.compliance.b3',
        default:
          'Every gate links back to the document or inspection that cleared it.',
      },
    ],
  },
  {
    id: 'owner',
    icon: FileText,
    titleKey: 'whatsnew.v6100.owner.title',
    titleDefault: 'Owner billing and progress reports',
    chipKey: 'whatsnew.v6100.owner.chip',
    chipDefault: 'Owner billing',
    bullets: [
      {
        key: 'whatsnew.v6100.owner.b1',
        default:
          'AIA G702 and G703 owner billing for US, Canada and Australia.',
      },
      {
        key: 'whatsnew.v6100.owner.b2',
        default:
          'Retention, stored materials and prior payments roll up automatically.',
      },
      {
        key: 'whatsnew.v6100.owner.b3',
        default:
          'Client progress reports share status and photos with the owner.',
      },
    ],
  },
  {
    id: 'agents',
    icon: Bot,
    titleKey: 'whatsnew.v6100.agents.title',
    titleDefault: 'No-code agent builder',
    chipKey: 'whatsnew.v6100.agents.chip',
    chipDefault: 'Agents',
    bullets: [
      {
        key: 'whatsnew.v6100.agents.b1',
        default:
          'Build agents from triggers and actions without writing code.',
      },
      {
        key: 'whatsnew.v6100.agents.b2',
        default:
          'Triggers fire on events like a new RFI, an overdue task or a failed check.',
      },
      {
        key: 'whatsnew.v6100.agents.b3',
        default:
          'Suggestions stay human-confirmed, so nothing acts on your behalf unasked.',
      },
    ],
  },
  {
    id: 'photos',
    icon: Camera,
    titleKey: 'whatsnew.v6100.photos.title',
    titleDefault: 'Jobsite photo intelligence',
    chipKey: 'whatsnew.v6100.photos.chip',
    chipDefault: 'Photos',
    bullets: [
      {
        key: 'whatsnew.v6100.photos.b1',
        default:
          'Jobsite photos are read for context and tagged to the right location.',
      },
      {
        key: 'whatsnew.v6100.photos.b2',
        default:
          'Findings link photos to inspections, punch items and the daily diary.',
      },
      {
        key: 'whatsnew.v6100.photos.b3',
        default:
          'Every suggestion is yours to confirm before it lands on a record.',
      },
    ],
  },
];

export interface WhatsNewCardProps {
  /** When true, ignores localStorage and forces the card to render. Used by
   *  the Settings → "Show release highlights" action and tests. */
  forceShow?: boolean;
  /** Override the persisted version (test seam). */
  versionOverride?: string;
}

type Mode = 'card' | 'pill';

export function WhatsNewCard({ forceShow = false, versionOverride }: WhatsNewCardProps = {}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const version = versionOverride ?? APP_VERSION;
  /** What we render in the slot: full card, just the reopen pill, or nothing. */
  const [mode, setMode] = useState<Mode | null>(null);
  /** Drives the entrance transition for the full card. */
  const [mounted, setMounted] = useState<boolean>(false);
  /** Which chip's popover (if any) is currently expanded. */
  const [openChipId, setOpenChipId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Decide initial visibility. Wrapped in try/catch so a hardened browser
  // without localStorage (Safari private mode, locked-down kiosks) still
  // renders the dashboard rather than crashing the whole tree.
  useEffect(() => {
    let show = forceShow;
    let alreadyAcked = false;
    if (!show) {
      try {
        const lastSeen = window.localStorage.getItem(LAST_SEEN_KEY);
        show = shouldShow(version, lastSeen);
        alreadyAcked = !show && lastSeen != null;
      } catch {
        show = false;
      }
    }
    if (show) {
      setMode('card');
      // Trigger the entry animation on the next frame so the card actually
      // slides in instead of appearing pre-positioned.
      const id = window.requestAnimationFrame(() => setMounted(true));
      return () => window.cancelAnimationFrame(id);
    }
    // Already acknowledged this version → show the reopen pill in place of
    // the full card. We do NOT show the pill if there's no version match
    // to begin with (e.g. localStorage unavailable) — quiet by default.
    if (alreadyAcked) {
      setMode('pill');
    } else {
      setMode(null);
    }
    return undefined;
  }, [forceShow, version]);

  // Close the chip popover when clicking outside the card.
  //
  // The expanded chip's detail popover is rendered through a portal to
  // document.body (see ChipWithPopover), so it lives OUTSIDE containerRef.
  // A naive `!root.contains(target)` check therefore treats clicks inside
  // the popover as "outside" and closes it on mousedown — which unmounts
  // the popover before an inner control (e.g. the "Read more" link) can
  // fire its onClick. Guard against that by also ignoring events that
  // originate inside any portaled chip popover. True outside clicks still
  // close the popover with the same mousedown semantics.
  useEffect(() => {
    if (mode !== 'card' || !openChipId) return undefined;
    const onClick = (ev: MouseEvent) => {
      const root = containerRef.current;
      if (!root) return;
      const target = ev.target as HTMLElement | null;
      if (root.contains(target)) return;
      if (target?.closest('[id^="whatsnew-chip-"][id$="-popover"]')) return;
      setOpenChipId(null);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [mode, openChipId]);

  const handleDismiss = useCallback(() => {
    setMounted(false);
    setOpenChipId(null);
    // Persist the version so the next dashboard visit stays quiet.
    try {
      window.localStorage.setItem(LAST_SEEN_KEY, version);
    } catch {
      /* localStorage unavailable — silent */
    }
    // Wait for the leave animation to complete before swapping to the pill.
    window.setTimeout(() => setMode('pill'), 200);
  }, [version]);

  const handleReopen = useCallback(() => {
    setMode('card');
    setOpenChipId(null);
    // Re-trigger the entry animation just like the initial render.
    setMounted(false);
    window.requestAnimationFrame(() => setMounted(true));
  }, []);

  const handleTour = useCallback(() => {
    try {
      window.dispatchEvent(
        new CustomEvent('oe:start-tour', { detail: { from: 'whatsnew' } }),
      );
    } catch {
      /* CustomEvent unsupported — silent */
    }
    handleDismiss();
  }, [handleDismiss]);

  const handleChangelog = useCallback(() => {
    handleDismiss();
    // AboutPage already exposes a `data-changelog-anchor` element that the
    // page's own "Changelog" link scrolls to via #changelog. Use the same
    // hash so the in-app behaviour stays consistent with the rest of the
    // About page.
    navigate('/about#changelog');
  }, [navigate, handleDismiss]);

  const sections = useMemo(() => SECTIONS_V6100, []);

  if (mode === null) return null;

  if (mode === 'pill') {
    return (
      <div className="flex">
        <button
          type="button"
          onClick={handleReopen}
          aria-label={t('whatsnew.reopen', { defaultValue: "What's new" })}
          className={[
            'inline-flex items-center gap-2 rounded-full',
            'border border-sky-400/50 ring-1 ring-sky-500/20',
            'dark:border-sky-500/40 dark:ring-sky-400/15',
            'bg-white/65 dark:bg-slate-900/50 backdrop-blur-md',
            'px-4 py-2 text-[13px] font-medium',
            'text-blue-700 hover:text-blue-800 dark:text-sky-200 dark:hover:text-sky-100',
            'hover:bg-sky-500/10 dark:hover:bg-sky-400/10',
            'hover:ring-sky-500/40 hover:shadow-md hover:shadow-sky-500/20',
            'shadow-sm shadow-sky-500/10 transition-all',
          ].join(' ')}
        >
          <Sparkles size={16} strokeWidth={2.25} />
          <span>
            {t('whatsnew.reopen', { defaultValue: "What's new" })}
          </span>
          <span className="text-blue-600/70 dark:text-sky-300/70">v{version}</span>
        </button>
      </div>
    );
  }

  // mode === 'card'
  return (
    <div
      ref={containerRef}
      role="region"
      aria-label={t('whatsnew.title', {
        defaultValue: "What's new in v{{version}}",
        version,
      })}
      className={[
        'relative overflow-visible rounded-xl border ring-1',
        'border-sky-400/50 ring-sky-500/10',
        'dark:border-sky-500/40 dark:ring-sky-400/10',
        'bg-gradient-to-br from-sky-50/90 via-blue-50/85 to-cyan-50/80',
        'dark:from-sky-950/40 dark:via-blue-950/30 dark:to-cyan-950/20',
        'backdrop-blur-md shadow-md shadow-sky-500/10',
        'transition-all duration-300 ease-out',
        mounted ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2',
      ].join(' ')}
    >
      <div className="flex flex-wrap items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2.5">
        {/* Sparkle badge */}
        <div className="relative shrink-0">
          <span
            aria-hidden="true"
            className="absolute inset-0 rounded-lg bg-sky-500/30 animate-ping"
          />
          <div className="relative flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-blue-600 text-white shadow-sm shadow-blue-500/30">
            <Sparkles size={13} strokeWidth={2.5} />
          </div>
        </div>

        {/* Headline + tagline (single line on desktop) */}
        <div className="flex min-w-0 items-baseline gap-2">
          <h2 className="truncate text-[13px] sm:text-sm font-semibold text-blue-900 dark:text-sky-100 leading-tight">
            {t('whatsnew.title', {
              defaultValue: "What's new in v{{version}}",
              version,
            })}
          </h2>
          <span className="hidden md:inline truncate text-[12px] text-blue-700/75 dark:text-sky-300/70">
            {t('whatsnew.tagline', {
              defaultValue: 'Tap a chip for details.',
            })}
          </span>
        </div>

        {/* Chip row — flex-grow pushes the trailing buttons to the right.
         *  Each chip's popover is rendered through a portal (`ChipPopover`
         *  below) because the parent card uses `backdrop-blur-md`, which
         *  creates a stacking context. An absolutely-positioned popover
         *  inside that context cannot escape it via z-index — it always
         *  paints below sibling widgets on the dashboard. Portaling to
         *  document.body removes that constraint. */}
        <div className="flex flex-1 flex-wrap items-center gap-1.5 min-w-0">
          {sections.map((s) => {
            const Icon = s.icon;
            const expanded = openChipId === s.id;
            return (
              <ChipWithPopover
                key={s.id}
                section={s}
                expanded={expanded}
                onToggle={() => setOpenChipId(expanded ? null : s.id)}
                onReadMore={handleChangelog}
                Icon={Icon}
                t={t}
              />
            );
          })}
        </div>

        {/* Trailing actions: tour CTA, changelog link, close */}
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={handleTour}
            className="inline-flex items-center gap-1 rounded-full bg-gradient-to-br from-sky-500 to-blue-600 hover:from-sky-600 hover:to-blue-700 px-2.5 py-1 text-[11px] font-semibold text-white shadow-sm shadow-blue-500/30 ring-1 ring-blue-500/20 transition-all"
          >
            <Sparkles size={11} />
            <span className="hidden sm:inline">
              {t('whatsnew.tour_cta', { defaultValue: 'Take a quick tour' })}
            </span>
            <span className="sm:hidden">
              {t('whatsnew.tour_cta_short', { defaultValue: 'Tour' })}
            </span>
          </button>
          <button
            type="button"
            onClick={handleChangelog}
            className="hidden sm:inline-flex items-center gap-0.5 rounded-full px-2 py-1 text-[11px] font-medium text-blue-700 hover:text-blue-800 dark:text-sky-300 dark:hover:text-sky-200 hover:bg-sky-500/10 dark:hover:bg-sky-400/10 transition-colors"
          >
            {t('whatsnew.changelog_link', {
              defaultValue: 'Full release notes',
            })}
            <ArrowRight size={11} />
          </button>
          <button
            type="button"
            onClick={handleDismiss}
            aria-label={t('whatsnew.dismiss', { defaultValue: 'Dismiss' })}
            className="flex h-7 w-7 items-center justify-center rounded-md text-sky-600/70 hover:text-blue-700 hover:bg-sky-500/10 dark:text-sky-300/70 dark:hover:text-sky-100 dark:hover:bg-sky-400/10 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default WhatsNewCard;

/* ── ChipWithPopover ───────────────────────────────────────────────────────
 *  A chip that, when expanded, renders its detail popover through a portal
 *  attached to `document.body`. This is the only way to make the popover
 *  paint above the rest of the dashboard: the WhatsNewCard root uses
 *  `backdrop-blur-md`, and any `filter`-style property creates a CSS
 *  stacking context that traps `position:absolute` descendants — even with
 *  `z-50` they still render below sibling widgets that live outside the
 *  card. A portal escapes that context entirely.
 *
 *  Position is measured from the chip button's `getBoundingClientRect()`
 *  on mount and re-measured on scroll / resize so the popover tracks the
 *  chip if the page moves while it is open.
 */

interface ChipWithPopoverProps {
  section: Section;
  expanded: boolean;
  onToggle: () => void;
  onReadMore: () => void;
  Icon: LucideIcon;
  t: (key: string, options?: { defaultValue: string }) => string;
}

function ChipWithPopover({
  section: s,
  expanded,
  onToggle,
  onReadMore,
  Icon,
  t,
}: ChipWithPopoverProps) {
  const chipRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  // Re-measure the chip's screen position so the portaled popover stays
  // anchored. useLayoutEffect prevents a one-frame flicker at (0,0).
  useLayoutEffect(() => {
    if (!expanded) {
      setPos(null);
      return undefined;
    }
    const measure = () => {
      const el = chipRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      // Default-align under the chip; clamp right edge so a chip near the
      // right viewport edge doesn't push the 400px popover off-screen.
      const POPOVER_WIDTH = 400;
      const MARGIN = 8;
      const maxLeft = window.innerWidth - POPOVER_WIDTH - MARGIN;
      const left = Math.max(MARGIN, Math.min(r.left, maxLeft));
      setPos({ top: r.bottom + 6, left });
    };
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [expanded]);

  // Outside-click handler runs against BOTH the chip and the portaled
  // popover so clicking inside the popover doesn't close it.
  useEffect(() => {
    if (!expanded) return undefined;
    const onMouseDown = (ev: MouseEvent) => {
      const target = ev.target as Node;
      if (chipRef.current?.contains(target)) return;
      if (popoverRef.current?.contains(target)) return;
      onToggle();
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [expanded, onToggle]);

  return (
    <>
      <button
        ref={chipRef}
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={`whatsnew-chip-${s.id}-popover`}
        title={t(s.titleKey, { defaultValue: s.titleDefault })}
        className={[
          'inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-medium',
          'ring-1 transition-colors',
          expanded
            ? 'bg-gradient-to-br from-sky-500 to-blue-600 text-white ring-blue-500/40 shadow-sm shadow-blue-500/30'
            : 'bg-white/65 dark:bg-slate-900/45 text-blue-900 dark:text-sky-100 ring-sky-500/25 hover:bg-sky-500/15 dark:hover:bg-sky-400/15',
        ].join(' ')}
      >
        <Icon size={11} strokeWidth={2.25} />
        <span>{t(s.chipKey, { defaultValue: s.chipDefault })}</span>
      </button>
      {expanded && pos
        ? createPortal(
            <div
              ref={popoverRef}
              id={`whatsnew-chip-${s.id}-popover`}
              role="dialog"
              aria-label={t(s.titleKey, { defaultValue: s.titleDefault })}
              style={{
                position: 'fixed',
                top: pos.top,
                left: pos.left,
                width: 400,
                // z-[1000] sits above the sticky AppLayout header (z-30),
                // dashboard widget cards, and any module floating UI we ship.
                // Modal overlays use z-[2000]+ so this still ducks under them.
                zIndex: 1000,
              }}
              className={[
                'rounded-lg border border-sky-300/60 ring-1 ring-sky-500/10',
                'dark:border-sky-700/50 dark:ring-sky-400/10',
                'bg-white/95 dark:bg-slate-900/95 backdrop-blur-md',
                'shadow-lg shadow-sky-500/20 p-3',
              ].join(' ')}
            >
              <h3 className="text-[12px] font-semibold text-blue-900 dark:text-sky-100 leading-snug mb-1.5 line-clamp-4">
                {t(s.titleKey, { defaultValue: s.titleDefault })}
              </h3>
              <ul className="space-y-0.5">
                {s.bullets.map((b) => (
                  <li
                    key={b.key}
                    className="flex items-start gap-1.5 text-xs leading-snug text-blue-900/85 dark:text-sky-100/85"
                  >
                    <span
                      aria-hidden="true"
                      className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-sky-500/70"
                    />
                    <span>{t(b.key, { defaultValue: b.default })}</span>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                onClick={onReadMore}
                className="mt-2 inline-flex items-center gap-0.5 text-[11px] font-medium text-blue-700 hover:text-blue-800 dark:text-sky-300 dark:hover:text-sky-100 transition-colors"
              >
                {t('whatsnew.read_more', { defaultValue: 'Read more' })}
                <ArrowRight size={11} />
              </button>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
