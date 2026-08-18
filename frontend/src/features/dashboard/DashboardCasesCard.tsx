// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// DashboardCasesCard - the "Cases" entry block at the top of the dashboard.
//
// More than a link: it surfaces a few cases the user can jump straight into,
// ranked so that anything half-finished comes first (so you can resume), then
// cases that match the role and company the user picked on the Cases hub, then
// the rest by order. Each chip drops the user directly into that case; the
// header and the browse button go to the full hub. Always visible, outside the
// customizable widget grid, so the guided playbooks are never more than one
// click away.

import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import clsx from 'clsx';
import { GraduationCap, ArrowRight, PlayCircle, Sparkles } from 'lucide-react';
import { PLAYBOOKS } from '@/features/cases/playbooks';
import { useCasesStore } from '@/features/cases/useCasesStore';
import { completedCount } from '@/features/cases/progress';
import { tintFor } from '@/features/cases/categories';
import { dealCaseFaces } from '@/features/cases/caseFaces';

import { HEX_PORTRAIT_CLIP } from '@/shared/lib/honeycomb';
import { rolesForPlaybook, ROLE_BY_ID } from '@/features/cases/roles';
import { iconFor } from '@/features/cases/icons';
import { CaseArt } from '@/features/cases/CaseArt';

// How many cases to preview as picture tiles. Ten fills one compact row on a
// wide dashboard (ten across, plus the "all cases" tile) and reflows to fewer
// columns as it narrows, a small gallery of the case library rather than a thin
// strip of chips.
const PREVIEW_COUNT = 10;

export function DashboardCasesCard() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const runs = useCasesStore((s) => s.runs);
  const roles = useCasesStore((s) => s.roles);
  const companyTypes = useCasesStore((s) => s.companyTypes);

  // Best progress a case reached across any run (unscoped or per sample
  // project), used both to rank and to show a resume hint.
  const picks = useMemo(() => {
    const scored = PLAYBOOKS.map((pb) => {
      let best = 0;
      for (const [k, prog] of Object.entries(runs)) {
        if (k === pb.id || k.startsWith(`${pb.id}::`)) {
          best = Math.max(best, completedCount(prog, pb));
        }
      }
      const total = pb.steps.length;
      const inProgress = best > 0 && best < total;
      // Both hub filters hold a list, so count the overlap rather than test a
      // single id: a case that fits all three of someone's roles should outrank
      // one that fits a single role, and a boolean cannot say that.
      const pbRoles = rolesForPlaybook(pb);
      const roleMatches = roles.filter((r) => pbRoles.includes(r)).length;
      const companyMatches = companyTypes.filter((c) =>
        pb.companyTypes.includes(c),
      ).length;
      return { pb, best, total, inProgress, roleMatches, companyMatches };
    });
    scored.sort((a, b) => {
      if (a.inProgress !== b.inProgress) return a.inProgress ? -1 : 1;
      const am = a.roleMatches * 2 + a.companyMatches;
      const bm = b.roleMatches * 2 + b.companyMatches;
      if (am !== bm) return bm - am;
      return a.pb.order - b.pb.order;
    });
    return scored.slice(0, PREVIEW_COUNT);
  }, [runs, roles, companyTypes]);

  // Name every role the user picked, joined the way their language joins a
  // list. Printing only the first would drop the others silently, which is the
  // same thing the hub filters were fixed for.
  const roleLabel = useMemo(() => {
    const names = roles.map((r) =>
      t(ROLE_BY_ID[r]?.labelKey ?? '', { defaultValue: ROLE_BY_ID[r]?.labelDefault ?? '' }),
    );
    if (names.length === 0) return '';
    return new Intl.ListFormat(i18n.language, {
      style: 'long',
      type: 'conjunction',
    }).format(names);
  }, [roles, t, i18n.language]);

  // Frame the preview chips by what they actually are: something half-finished
  // to resume, a role-tuned pick, or - the default on a fresh workspace - the
  // most popular cases to start from. The ranking in `picks` is unchanged; this
  // only labels it.
  const anyInProgress = picks.some((p) => p.inProgress);
  const framingLabel = anyInProgress
    ? t('cases.dashboard_card.resume_hint', { defaultValue: 'Pick up where you left off' })
    : roles.length > 0
      ? t('cases.dashboard_card.for_role', { defaultValue: 'Picked for you' })
      : t('cases.dashboard_card.popular', { defaultValue: 'Popular starting points' });

  // Dealt from the same helper the Cases hub uses, so a case wears the same
  // person in both places rather than two different ones.
  const faces = useMemo(() => dealCaseFaces(picks.map(({ pb }) => pb)), [picks]);

  return (
    <div
      data-testid="dashboard-cases-card"
      className="rounded-xl border border-oe-blue/30 bg-gradient-to-r from-oe-blue/[0.07] via-oe-blue/[0.03] to-transparent p-4 shadow-xs animate-card-in"
      style={{ animationDelay: '120ms' }}
    >
      <div className="flex flex-wrap items-start gap-4">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-oe-blue/10 text-oe-blue ring-1 ring-inset ring-oe-blue/20">
          <GraduationCap size={20} strokeWidth={1.9} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-content-primary">
              {t('cases.dashboard_card.title', { defaultValue: 'Start here - learn by example' })}
            </p>
            {/* Total library size, so the card advertises the full breadth of
                guided cases even while it only previews a handful. */}
            <span className="inline-flex shrink-0 items-center rounded-full bg-oe-blue/10 px-2 py-0.5 text-2xs font-semibold text-oe-blue ring-1 ring-inset ring-oe-blue/20">
              {t('cases.dashboard_card.total', {
                defaultValue: '{{count}} cases in total',
                count: PLAYBOOKS.length,
              })}
            </span>
          </div>
          <p className="mt-0.5 text-xs leading-relaxed text-content-secondary">
            {roles.length === 1
              ? t('cases.dashboard_card.body_role', {
                  defaultValue: 'Guided playbooks picked for a {{role}}, step by step across the modules.',
                  role: roleLabel,
                })
              : roles.length > 1
                ? t('cases.dashboard_card.body_roles', {
                    defaultValue:
                      'Guided playbooks picked for {{roles}}, step by step across the modules.',
                    roles: roleLabel,
                  })
                : t('cases.dashboard_card.body', {
                    defaultValue:
                      'Follow a guided playbook from a PDF to a priced, validated estimate, step by step across the modules.',
                  })}
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/cases')}
          className="group inline-flex shrink-0 items-center gap-2 rounded-lg bg-oe-blue px-4 py-2.5 text-sm font-semibold text-content-inverse shadow-sm transition-all hover:bg-oe-blue-hover hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
        >
          {t('cases.dashboard_card.cta_all', {
            defaultValue: 'Browse all {{count}} cases',
            count: PLAYBOOKS.length,
          })}
          <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
        </button>
      </div>

      {/* Quick-launch: jump straight into a case */}
      {picks.length > 0 && (
        <div className="mt-3">
          {/* Adaptive eyebrow: resume / role-tuned / popular starting points. */}
          <div className="mb-1.5 flex items-center gap-1 text-2xs font-medium text-content-tertiary">
            {anyInProgress ? (
              <PlayCircle size={11} className="text-oe-blue" aria-hidden="true" />
            ) : (
              <Sparkles size={11} className="text-oe-blue" aria-hidden="true" />
            )}
            {framingLabel}
          </div>
          {/* Picture gallery: each case leads with its line-art illustration on
              an always-light tile (the same art the Cases hub uses), so the
              block previews the library visually. Ten compact tiles plus the
              "all cases" tile land as a single row on a wide dashboard,
              reflowing to six, four or two on narrower screens. */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-11">
          {picks.map(({ pb, best, total, inProgress }) => {
            const face = faces.get(pb.id);
            const Icon = iconFor(pb.icon);
            const tint = tintFor(pb.category);
            const title = t(pb.titleKey, { defaultValue: pb.titleDefault });
            return (
              <button
                key={pb.id}
                type="button"
                onClick={() => navigate(`/cases/${pb.id}`)}
                title={title}
                className="group relative isolate flex flex-col overflow-hidden rounded-lg border border-border-light bg-surface-primary text-left shadow-xs transition duration-200 hover:-translate-y-0.5 hover:border-oe-blue/40 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
              >
                {/* Faint discipline wash behind the whole tile. */}
                <span
                  aria-hidden="true"
                  className={clsx('pointer-events-none absolute inset-0 -z-10', tint.softBg)}
                />
                {/* Line-art banner on an always-light tile so the linework reads
                    the same in light and dark theme. */}
                <div className="relative aspect-[16/9] w-full overflow-hidden border-b border-border-light bg-white ring-1 ring-inset ring-slate-900/[0.04]">
                  {/* Nudged off the inline-start edge so the portrait below sits
                      beside the drawing rather than on top of it. */}
                  <CaseArt
                    id={pb.id}
                    category={pb.category}
                    fallbackIcon={Icon}
                    fallbackClass={tint.text}
                    alt={title}
                    className={face ? 'ps-[14%]' : undefined}
                  />
                  {/* The specialist the case is written for, cut to the same
                      honeycomb cell the Cases hub and the marketing site use.
                      It sits over a corner rather than beside the diagram:
                      these tiles are a sixth of a row wide, and a band would
                      leave the drawing too narrow to read at all. Decorative -
                      the case title below carries the meaning. */}
                  {face && (
                    <span
                      aria-hidden="true"
                      className="pointer-events-none absolute bottom-1 start-1 block w-[30%] max-w-[2.75rem]"
                    >
                      <span
                        className="block aspect-[7/8] bg-white/90 p-[2px] shadow-sm shadow-slate-900/20"
                        style={{ clipPath: HEX_PORTRAIT_CLIP }}
                      >
                        <img
                          src={face}
                          alt=""
                          loading="lazy"
                          decoding="async"
                          draggable={false}
                          className="h-full w-full object-cover object-[50%_18%]"
                          style={{ clipPath: HEX_PORTRAIT_CLIP }}
                        />
                      </span>
                    </span>
                  )}
                  {inProgress && (
                    <span
                      className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full bg-oe-blue shadow-sm ring-2 ring-white"
                      title={t('cases.card.in_progress', { defaultValue: 'In progress' })}
                      aria-hidden="true"
                    />
                  )}
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5 px-2 py-1.5">
                  <span className="truncate text-xs font-semibold leading-snug text-content-primary">
                    {title}
                  </span>
                  <span className="mt-auto flex items-center gap-1 text-2xs text-content-tertiary">
                    {inProgress ? (
                      <>
                        <PlayCircle size={10} className="text-oe-blue" aria-hidden="true" />
                        {t('cases.dashboard_card.resume', {
                          defaultValue: 'Resume {{done}}/{{total}}',
                          done: best,
                          total,
                        })}
                      </>
                    ) : (
                      t('cases.card.steps', { defaultValue: '{{count}} steps', count: total })
                    )}
                  </span>
                </div>
              </button>
            );
          })}
          {/* Final tile: a compact call to open the whole library, so the row
              always ends on an obvious way to see more cases. */}
          <button
            type="button"
            onClick={() => navigate('/cases')}
            title={t('cases.dashboard_card.cta_all', {
              defaultValue: 'Browse all {{count}} cases',
              count: PLAYBOOKS.length,
            })}
            className="group relative isolate flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-oe-blue/40 bg-oe-blue/[0.05] px-2 py-3 text-center transition duration-200 hover:-translate-y-0.5 hover:border-oe-blue/60 hover:bg-oe-blue/10 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-oe-blue/10 text-oe-blue ring-1 ring-inset ring-oe-blue/20 transition-transform group-hover:scale-105">
              <ArrowRight size={18} strokeWidth={2} aria-hidden="true" />
            </span>
            <span className="text-xs font-semibold leading-snug text-oe-blue-text">
              {t('cases.dashboard_card.more_tile', {
                defaultValue: 'All {{count}} cases',
                count: PLAYBOOKS.length,
              })}
            </span>
          </button>
          </div>
        </div>
      )}
    </div>
  );
}
