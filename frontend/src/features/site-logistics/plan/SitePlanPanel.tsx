// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The site plan as a drawing in metres of the local site frame: the outline
// of an area, the route of a transport or a permit, the point of a utility
// connection. The drawing only records corners. What an outline measures and
// which areas overlap is computed by the server and shown as it answers.

import { useMemo, useState, type MouseEvent } from 'react';
import { AlertTriangle, MapPinned, Undo2 } from 'lucide-react';

import { Button } from '@/shared/ui/Button';
import { useToastStore } from '@/stores/useToastStore';

import { updateItem, type Body, type ResourceKind } from './api';
import { m2 } from './format';
import {
  centre,
  closeRing,
  linePoints,
  moveVertex,
  openRing,
  pointOf,
  removeVertex,
  screenToMetres,
  svgPoints,
  toLine,
  toPoint,
  viewBox,
  viewOf,
  type Pt,
} from './geometry';
import {
  useAreas,
  useBalance,
  useInvalidatePlan,
  useMedia,
  usePermits,
  useReportProblem,
  useStages,
  useTransports,
  useWords,
} from './hooks';
import { Loaded, PanelHead, PlanEmpty } from './PlanBits';
import { codeLabel } from './rules';
import { stageName, type PanelProps } from './SitePanels';
import { tx } from './texts';

type Kind = 'area' | 'transport' | 'permit' | 'media';
type Shape = 'outline' | 'route' | 'point';

const SHAPE: Record<Kind, Shape> = { area: 'outline', transport: 'route', permit: 'route', media: 'point' };
const LEAST: Record<Shape, number> = { outline: 3, route: 2, point: 1 };

interface Target {
  kind: Kind;
  id: string;
  label: string;
  points: Pt[];
}

interface Draft {
  points: Pt[];
  /** An outline is closed once its ring is shut; a route and a point never are. */
  closed: boolean;
}

export function SitePlanPanel({ projectId, catalogue, readOnly = false }: PanelProps & { readOnly?: boolean }) {
  const words = useWords();
  const { t } = words;
  const areas = useAreas(projectId);
  const stages = useStages(projectId).data ?? [];
  const balance = useBalance(projectId).data ?? [];
  const transports = useTransports(projectId).data ?? [];
  const permits = usePermits(projectId).data ?? [];
  const media = useMedia(projectId).data ?? [];
  const invalidate = useInvalidatePlan(projectId);
  const report = useReportProblem(catalogue);
  const addToast = useToastStore((s) => s.addToast);

  const [stagePick, setStagePick] = useState('');
  const [targetKey, setTargetKey] = useState('');
  const [draft, setDraft] = useState<Draft>({ points: [], closed: false });
  const [history, setHistory] = useState<Draft[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const stageId = stagePick || stages.find((s) => s.state === 'active')?.id || stages[0]?.id || '';
  const areaRows = areas.data ?? [];

  const targets = useMemo<Target[]>(
    () => [
      ...areaRows
        .filter((a) => a.frame === 'local')
        .map((a) => ({ kind: 'area' as const, id: a.id, label: a.name || a.code, points: openRing(a.geometry) })),
      ...transports.map((x) => ({ kind: 'transport' as const, id: x.id, label: x.title, points: linePoints(x.route_geojson) })),
      ...permits.map((p) => ({
        kind: 'permit' as const,
        id: p.id,
        label: p.reference || codeLabel(words, 'permit_kinds', p.permit_kind, catalogue),
        points: linePoints(p.route_geojson),
      })),
      ...media.map((c) => {
        const at = pointOf(c.connection_point_geometry);
        return {
          kind: 'media' as const,
          id: c.id,
          label: codeLabel(words, 'media_kinds', c.media_kind, catalogue),
          points: at ? [at] : [],
        };
      }),
    ],
    [areaRows, transports, permits, media, words, catalogue],
  );
  const target = targets.find((x) => `${x.kind}:${x.id}` === targetKey) ?? null;
  const shape: Shape | null = target ? SHAPE[target.kind] : null;

  // The areas the chosen stage uses: these are the ones the server balances and tests for overlap.
  const stageAreas = areaRows.filter((a) => a.allocations.some((al) => al.stage_id === stageId));
  const overlaps = balance.find((b) => b.stage.id === stageId)?.overlaps ?? [];
  const overlapping = new Set(overlaps.flat());
  const nameOf = (id: string) => {
    const a = areaRows.find((x) => x.id === id);
    return a ? a.name || a.code : id;
  };

  const background = targets.filter(
    (x) => x !== target && x.points.length > 0 && (x.kind !== 'area' || stageAreas.some((a) => a.id === x.id)),
  );
  // The sheet does not move while a corner is dragged: it is laid out from the saved drawing only.
  const view = viewOf([...background.map((x) => x.points), ...(target ? [target.points] : [])]);
  const unit = Math.max(view.width, view.height) / 100;

  const begin = (key: string) => {
    const next = targets.find((x) => `${x.kind}:${x.id}` === key) ?? null;
    setTargetKey(key);
    setDraft({ points: next?.points ?? [], closed: !!next && next.kind === 'area' && next.points.length >= 3 });
    setHistory([]);
    setSelected(null);
  };
  const change = (next: Draft) => {
    setHistory((h) => [...h, draft]);
    setDraft(next);
  };
  const undo = () => {
    const last = history[history.length - 1];
    if (!last) return;
    setHistory(history.slice(0, -1));
    setDraft(last);
    setSelected(null);
  };

  const at = (e: MouseEvent<SVGSVGElement>): Pt =>
    screenToMetres([e.clientX, e.clientY], e.currentTarget.getBoundingClientRect(), view);

  const editable = !readOnly && !!target;
  const onSheet = (e: MouseEvent<SVGSVGElement>) => {
    // Only a click on the bare sheet adds a point; a click that ends on a corner is the end of a drag.
    if (!editable || !shape || (e.target as Element).getAttribute('data-sheet') === null) return;
    if (shape === 'point') change({ points: [at(e)], closed: false });
    else if (!draft.closed) change({ points: [...draft.points, at(e)], closed: false });
    else setSelected(null);
  };
  const onCorner = (e: MouseEvent, i: number) => {
    if (!editable) return;
    e.stopPropagation();
    if (shape === 'outline' && !draft.closed && i === 0 && draft.points.length >= 3) {
      change({ points: draft.points, closed: true });
      return;
    }
    setSelected(i);
    setHistory((h) => [...h, draft]);
    setDragging(i);
  };
  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    if (dragging !== null) setDraft((d) => ({ ...d, points: moveVertex(d.points, dragging, at(e)) }));
  };

  const body = (): Body | null => {
    if (!target || !shape) return null;
    if (shape === 'outline') {
      const geometry = draft.closed ? closeRing(draft.points) : null;
      return geometry ? { geometry, frame: 'local' } : null;
    }
    if (shape === 'route') {
      const route = toLine(draft.points);
      return route ? { route_geojson: route } : null;
    }
    const first = draft.points[0];
    return first ? { connection_point_geometry: toPoint(first) } : null;
  };
  const ready = body() !== null;

  const send = async (payload: Body) => {
    if (!target) return;
    setSaving(true);
    try {
      await updateItem(projectId, target.kind as ResourceKind, target.id, payload);
      addToast({ type: 'success', title: tx(t, 'siteplan.saved'), message: target.label });
      await invalidate();
      setTargetKey('');
      setHistory([]);
    } catch (err) {
      report(err);
    } finally {
      setSaving(false);
    }
  };
  const save = () => {
    const payload = body();
    if (payload) void send(payload);
  };
  const remove = () =>
    void send(
      shape === 'outline' ? { geometry: null } : shape === 'route' ? { route_geojson: null } : { connection_point_geometry: null },
    );

  const nothing = targets.length === 0;
  const hint =
    shape === 'outline'
      ? draft.closed
        ? 'siteplan.hint_outline_closed'
        : 'siteplan.hint_outline_open'
      : shape === 'route'
        ? 'siteplan.hint_route'
        : 'siteplan.hint_point';

  return (
    <section className="space-y-3" data-testid="plan-siteplan">
      <PanelHead title="tab.siteplan" />
      <Loaded query={areas}>
        {() =>
          nothing ? (
            <PlanEmpty icon={<MapPinned size={28} />} title="siteplan.empty_title" body="siteplan.empty_body" />
          ) : (
            <>
              <p className="text-sm text-content-secondary">{tx(t, 'siteplan.lead')}</p>
              <div className="flex flex-wrap items-end gap-3">
                <label className="text-xs font-medium text-content-secondary">
                  {tx(t, 'siteplan.stage')}
                  <select
                    className="mt-1 block h-9 rounded-lg border border-border bg-surface-primary px-2 text-sm text-content-primary"
                    value={stageId}
                    onChange={(e) => setStagePick(e.target.value)}
                    data-testid="siteplan-stage"
                  >
                    {stages.map((s) => (
                      <option key={s.id} value={s.id}>
                        {stageName(s)}
                      </option>
                    ))}
                  </select>
                </label>
                {!readOnly && (
                  <label className="text-xs font-medium text-content-secondary">
                    {tx(t, 'siteplan.draw')}
                    <select
                      className="mt-1 block h-9 rounded-lg border border-border bg-surface-primary px-2 text-sm text-content-primary"
                      value={targetKey}
                      onChange={(e) => begin(e.target.value)}
                      data-testid="siteplan-target"
                    >
                      <option value="">{tx(t, 'siteplan.pick')}</option>
                      {(['area', 'transport', 'permit', 'media'] as const).map((kind) => {
                        const rows = targets.filter((x) => x.kind === kind);
                        return rows.length === 0 ? null : (
                          <optgroup key={kind} label={tx(t, `siteplan.kind.${kind}`)}>
                            {rows.map((x) => (
                              <option key={x.id} value={`${x.kind}:${x.id}`}>
                                {x.label}
                              </option>
                            ))}
                          </optgroup>
                        );
                      })}
                    </select>
                  </label>
                )}
                {editable && (
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="ghost" disabled={history.length === 0} onClick={undo} data-testid="siteplan-undo">
                      <Undo2 size={14} className="mr-1" />
                      {tx(t, 'siteplan.undo')}
                    </Button>
                    {shape === 'outline' && !draft.closed && (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={draft.points.length < 3}
                        onClick={() => change({ points: draft.points, closed: true })}
                        data-testid="siteplan-close"
                      >
                        {tx(t, 'siteplan.close_ring')}
                      </Button>
                    )}
                    {shape !== 'point' && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={selected === null || !shape || draft.points.length <= LEAST[shape]}
                        onClick={() => {
                          if (selected === null || !shape) return;
                          change({ ...draft, points: removeVertex(draft.points, selected, LEAST[shape]) });
                          setSelected(null);
                        }}
                        data-testid="siteplan-delete-corner"
                      >
                        {tx(t, 'siteplan.delete_corner')}
                      </Button>
                    )}
                    {target && target.points.length > 0 && (
                      <Button size="sm" variant="ghost" disabled={saving} onClick={remove} data-testid="siteplan-remove">
                        {tx(t, 'siteplan.remove')}
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" disabled={saving} onClick={() => begin('')}>
                      {tx(t, 'cancel')}
                    </Button>
                    <Button size="sm" disabled={!ready} loading={saving} onClick={save} data-testid="siteplan-save">
                      {tx(t, 'siteplan.save')}
                    </Button>
                  </div>
                )}
              </div>
              {editable && (
                <p className="text-xs text-content-secondary" data-testid="siteplan-hint">
                  {tx(t, hint)}
                </p>
              )}
              <svg
                viewBox={viewBox(view)}
                role="img"
                aria-label={tx(t, 'siteplan.sheet')}
                className={`h-[28rem] w-full rounded-lg border border-border-light bg-surface-secondary ${editable ? 'cursor-crosshair' : ''}`}
                onClick={onSheet}
                onMouseMove={onMove}
                onMouseUp={() => setDragging(null)}
                onMouseLeave={() => setDragging(null)}
                data-testid="siteplan-sheet"
              >
                <rect data-sheet="" x={view.minX} y={-(view.minY + view.height)} width={view.width} height={view.height} fill="transparent" />
                <g pointerEvents="none">
                  {background.map((x) => {
                    const mid = centre(x.points);
                    const warn = x.kind === 'area' && overlapping.has(x.id);
                    const area = x.kind === 'area' ? areaRows.find((a) => a.id === x.id) : undefined;
                    return (
                      <g key={`${x.kind}:${x.id}`} data-testid={`siteplan-shape-${x.kind}`} data-overlap={warn || undefined}>
                        {x.kind === 'area' ? (
                          <polygon
                            points={svgPoints(x.points)}
                            className={warn ? 'fill-semantic-warning/20 stroke-semantic-warning' : 'fill-oe-blue/10 stroke-oe-blue'}
                            strokeWidth={unit * 0.3}
                          />
                        ) : x.kind === 'media' ? (
                          <circle cx={x.points[0]?.[0]} cy={-(x.points[0]?.[1] ?? 0)} r={unit} className="fill-semantic-success" />
                        ) : (
                          <polyline
                            points={svgPoints(x.points)}
                            fill="none"
                            className="stroke-content-secondary"
                            strokeWidth={unit * 0.4}
                            strokeDasharray={`${unit} ${unit}`}
                          />
                        )}
                        {mid && (
                          <text x={mid[0]} y={-mid[1]} fontSize={unit * 2} textAnchor="middle" className="fill-content-primary">
                            {x.label}
                            {area?.area_m2 ? ` ${m2(t, area.area_m2)}` : ''}
                          </text>
                        )}
                      </g>
                    );
                  })}
                  {target &&
                    draft.points.length > 0 &&
                    (shape === 'outline' && draft.closed ? (
                      <polygon points={svgPoints(draft.points)} className="fill-oe-blue/20 stroke-oe-blue" strokeWidth={unit * 0.4} />
                    ) : (
                      <polyline points={svgPoints(draft.points)} fill="none" className="stroke-oe-blue" strokeWidth={unit * 0.4} />
                    ))}
                </g>
                {target &&
                  draft.points.map((p, i) => (
                    <circle
                      key={i}
                      cx={p[0]}
                      cy={-p[1]}
                      r={unit * 1.2}
                      role="button"
                      aria-label={tx(t, 'siteplan.corner', { n: i + 1 })}
                      aria-pressed={selected === i}
                      className={selected === i ? 'cursor-move fill-oe-blue stroke-white' : 'cursor-move fill-white stroke-oe-blue'}
                      strokeWidth={unit * 0.3}
                      onMouseDown={(e) => onCorner(e, i)}
                      data-testid="siteplan-corner"
                    />
                  ))}
              </svg>
              <p className="text-xs text-content-tertiary">{tx(t, 'siteplan.metres')}</p>

              {overlaps.length > 0 && (
                <ul className="space-y-1" data-testid="siteplan-overlaps">
                  {overlaps.map((pair, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-sm text-content-primary">
                      <AlertTriangle size={14} className="mt-0.5 shrink-0 text-semantic-warning" aria-hidden />
                      {tx(t, 'siteplan.overlap', { a: nameOf(pair[0] ?? ''), b: nameOf(pair[1] ?? '') })}
                    </li>
                  ))}
                </ul>
              )}

              <div>
                <h4 className="text-sm font-semibold text-content-primary">{tx(t, 'siteplan.areas_title')}</h4>
                {stageAreas.length === 0 ? (
                  <p className="mt-1 text-sm text-content-secondary">{tx(t, 'siteplan.no_stage_areas')}</p>
                ) : (
                  <ul className="mt-1 divide-y divide-border-light">
                    {stageAreas.map((a) => (
                      <li key={a.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-1.5 text-sm" data-testid="siteplan-area-row">
                        <span className="font-medium text-content-primary">{a.name || a.code}</span>
                        <span className="text-content-secondary">
                          {a.frame !== 'local'
                            ? tx(t, 'siteplan.other_frame')
                            : a.geometry
                              ? (m2(t, a.area_m2) ?? tx(t, 'siteplan.drawn'))
                              : tx(t, 'siteplan.no_outline')}
                        </span>
                        {!readOnly && a.frame === 'local' && (
                          <button
                            type="button"
                            className="ml-auto text-xs font-medium text-oe-blue hover:underline"
                            onClick={() => begin(`area:${a.id}`)}
                          >
                            {tx(t, a.geometry ? 'siteplan.edit_outline' : 'siteplan.draw_outline')}
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )
        }
      </Loaded>
    </section>
  );
}
