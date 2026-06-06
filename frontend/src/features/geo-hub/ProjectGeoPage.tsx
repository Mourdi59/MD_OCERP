// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Project-scoped Geo Hub page — /projects/:projectId/geo.
 *
 * Renders the lazy-loaded Cesium viewer scoped to one project's
 * anchor, imagery, tilesets, overlays and viewpoints. Layout:
 *
 * ```
 *   ┌──── header (title · anchor · scope picker) ──────┐
 *   │                                                  │
 *   │  ┌─ Cesium canvas (full width) ────────────────┐ │
 *   │  │ ┌─ tileset overlay (top-left, self-sized, │ │ │
 *   │  │ │ collapsible) ─┐                         │ │ │
 *   │  │ └────────────────┘                        │ │ │
 *   │  │ HUD + empty state + Cesium controls       │ │ │
 *   │  └─────────────────────────────────────────────┘ │
 *   └──────────────────────────────────────────────────┘
 * ```
 *
 * Three distinct empty states are decided centrally here so the
 * Cesium viewer stays oblivious of project semantics.
 */

import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { MapPinned, AlertTriangle, ServerCrash, Loader2, MapPin } from 'lucide-react';

import { ApiError } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';
import { projectsApi } from '@/features/projects/api';

import { AnchorAdjustPanel } from './AnchorAdjustPanel';
import { useTilesetOverlayState } from './hooks/useTilesetOverlayState';
import {
  createAnchor,
  fetchDiaryPhotoPins,
  fetchHsePins,
  fetchPunchlistPins,
  getMapConfig,
  updateAnchor,
} from './api';
import type { GeoCameraState, GeoCursorCoords } from './CesiumViewer';
import { GeoEmptyState, type GeoEmptyKind } from './GeoEmptyState';
import { GeoModePicker } from './GeoModePicker';
import { PlaceOnMapPicker } from './PlaceOnMapPicker';
import { GeoOverlayHud } from './GeoOverlayHud';
import { MapLayerLegend } from './MapLayerLegend';
import { OverlayLayer } from './OverlayLayer';
import { OverlayPanel, type OverlayEditMode } from './OverlayPanel';
import { TilesetSidebar } from './TilesetSidebar';
import type { GeoPinBundle, Tileset } from './types';

const CesiumViewer = lazy(() =>
  import('./CesiumViewer').then((m) => ({ default: m.CesiumViewer })),
);

// Persisted across reloads so the user's preferred chrome density
// survives navigation. Versioned (`v1`) so a future incompatible rename
// never resurrects with stale boolean semantics.
const TILESETS_COLLAPSED_LS_KEY = 'oe.geo_hub.tilesets_collapsed.v1';

function readTilesetsCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(TILESETS_COLLAPSED_LS_KEY) === '1';
  } catch {
    return false;
  }
}

/**
 * Decide which "empty" overlay should paint over the canvas, if any.
 * Returns null when the map has data to render.
 */
function emptyStateFor(
  hasAnchor: boolean,
  tilesets: Tileset[] | undefined,
): GeoEmptyKind | null {
  if (!hasAnchor) return 'no_anchor';
  const list = tilesets ?? [];
  if (list.length === 0) return 'no_tilesets';
  const allFailed = list.every((t) => t.status === 'failed' || t.status === 'obsolete');
  if (allFailed) return 'all_failed';
  return null;
}

export function ProjectGeoPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const { projectId } = useParams<{ projectId: string }>();
  // Deep-link context — ``?model=<bim_model_or_federation_id>`` focuses the
  // camera onto the matching tileset's boundingSphere once it loads.
  // ``?plot=<plot_id>``, ``?dev_id=<development_id>``, ``?phase=...`` and
  // ``?block=...`` further scope what the viewer should highlight.
  const [searchParams] = useSearchParams();
  const focusedModelId = searchParams.get('model');
  const focusedPlotId = searchParams.get('plot');
  const focusedDevId = searchParams.get('dev_id') ?? searchParams.get('development');
  const phaseFilter = searchParams.get('phase');
  const blockFilter = searchParams.get('block');

  const { data, error, isLoading } = useQuery({
    queryKey: ['geo-hub', 'map-config', projectId],
    queryFn: () => getMapConfig(projectId!),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });

  // Cross-module pin layers — three independent queries so a hiccup on
  // one module doesn't black out the others. Each falls back to an
  // empty list on failure so the map still renders the tilesets.
  const hsePinsQuery = useQuery({
    queryKey: ['geo-hub', 'hse-pins', projectId],
    queryFn: () => fetchHsePins(projectId!),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });
  const punchlistPinsQuery = useQuery({
    queryKey: ['geo-hub', 'punchlist-pins', projectId],
    queryFn: () => fetchPunchlistPins(projectId!),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });
  const diaryPinsQuery = useQuery({
    queryKey: ['geo-hub', 'diary-photo-pins', projectId],
    queryFn: () => fetchDiaryPhotoPins(projectId!),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });
  // Project record for the drift indicator — we need the typed
  // address text to compare against the cached anchor.address. Stale
  // for 5 minutes (project addresses don't change every render and
  // re-fetching here would race the anchor refetch on edits).
  const projectQuery = useQuery({
    queryKey: ['projects', 'detail', projectId],
    queryFn: () => projectsApi.get(projectId!),
    enabled: Boolean(projectId),
    staleTime: 5 * 60_000,
  });
  const projectAddressText = useMemo<string | null>(() => {
    const addr = projectQuery.data?.address;
    if (!addr) return null;
    const parts = [
      addr.street,
      addr.city,
      addr.state,
      addr.postal_code,
      addr.country,
    ];
    const line = parts
      .filter((p): p is string => typeof p === 'string' && p.trim() !== '')
      .join(', ');
    return line || null;
  }, [projectQuery.data?.address]);

  const pins = useMemo<GeoPinBundle>(
    () => ({
      hse: hsePinsQuery.data ?? [],
      punchlist: punchlistPinsQuery.data ?? [],
      diary: diaryPinsQuery.data ?? [],
    }),
    [hsePinsQuery.data, punchlistPinsQuery.data, diaryPinsQuery.data],
  );

  // Per-tileset visibility + opacity (localStorage-backed; per-project).
  // The hook is the single source of truth — both the sidebar (eye + slider)
  // and the Cesium viewer (``tileset.show`` + ``Cesium3DTileStyle``) read
  // from the same state, so toggles are coherent across UI + render.
  const tilesetOverlay = useTilesetOverlayState(projectId);
  // Derive the legacy ``hiddenIds`` Set from the overlay state so the
  // existing sidebar contract (which expects a Set + a toggler) keeps
  // working unchanged.
  const hiddenIds = useMemo(() => {
    const s = new Set<string>();
    for (const [id, entry] of Object.entries(tilesetOverlay.state)) {
      if (entry.visible === false) s.add(id);
    }
    return s;
  }, [tilesetOverlay.state]);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [panelCollapsed, setPanelCollapsed] = useState<boolean>(
    readTilesetsCollapsed,
  );
  // Raster overlay editing state — lifted here so OverlayPanel and
  // OverlayLayer agree on which overlay is being edited and in which mode.
  const [activeOverlayId, setActiveOverlayId] = useState<string | null>(
    null,
  );
  const [overlayEditMode, setOverlayEditMode] =
    useState<OverlayEditMode>('idle');
  // "Drag to adjust" toggle for the anchor — when on, the page captures
  // the next click on the map and PATCHes the anchor's lat/lon.
  const [anchorDragMode, setAnchorDragMode] = useState<boolean>(false);
  // "Place on map" picker — lists project files (BIM models + PDFs) and
  // drops the chosen one onto the map. Opened from the header button and
  // from the ``no_tilesets`` empty state.
  const [pickerOpen, setPickerOpen] = useState<boolean>(false);
  // After a PDF drawing is placed we fly the camera straight to its
  // centroid. ``key`` is a nonce so re-placing the same drawing re-flies
  // (the viewer's flyToTarget effect keys on it). 3D models use the
  // ``?model=`` deep-link + focusedTilesetId path instead.
  const [overlayFlyTarget, setOverlayFlyTarget] = useState<{
    key: string;
    lat: number;
    lon: number;
  } | null>(null);
  // Cesium runtime ref, populated by ``CesiumViewer.onViewerReady`` so
  // the overlay layer can attach its imagery + interaction handlers.
  const [cesiumRuntime, setCesiumRuntime] = useState<
    { cesium: unknown; viewer: unknown } | null
  >(null);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(
        TILESETS_COLLAPSED_LS_KEY,
        panelCollapsed ? '1' : '0',
      );
    } catch {
      /* localStorage disabled / quota full — UX still works in-memory */
    }
  }, [panelCollapsed]);
  // Live HUD state, fed by ``CesiumViewer`` via ``onMouseMove`` /
  // ``onCameraChange``. ``null`` cursor → HUD shows em-dashes; ``null``
  // camera → north arrow stays at 0°.
  const [cursorCoords, setCursorCoords] = useState<GeoCursorCoords | null>(
    null,
  );
  const [cameraState, setCameraState] = useState<GeoCameraState | null>(null);

  // Pin clicks in the project view jump to the source module so the
  // documented "click a pin to inspect" interaction works. HSE / punch
  // pins open their module pages scoped to this project; diary photos
  // open the project's daily diary.
  const handlePinSelect = useCallback(
    (sel: { tag: string }) => {
      const { tag } = sel;
      const kind = tag.split(':')[0];
      if (!projectId) return;
      if (kind === 'hse') {
        navigate(`/projects/${projectId}/safety`);
      } else if (kind === 'punch') {
        navigate('/punchlist');
      } else if (kind === 'diary') {
        navigate(`/projects/${projectId}/daily-diary`);
      }
    },
    [navigate, projectId],
  );

  // "Drag to adjust" map-click handler — PATCHes the anchor's lat/lon to
  // the clicked surface coordinate, refreshes the map config, exits drag
  // mode and toasts. Mirrors the AnchorAdjustPanel docstring's promise
  // that the parent wires click-on-map -> PATCH.
  const handleAnchorMapClick = useCallback(
    async (coords: { lat: number; lon: number }) => {
      const anchorId = data?.anchor?.id;
      const metadata = {
        ...(data?.anchor?.metadata ?? {}),
        geocode_source: 'manual',
        geocode_precision: 'address',
      };
      try {
        if (anchorId) {
          // Existing persisted anchor -> move it in place.
          await updateAnchor(anchorId, {
            lat: coords.lat.toFixed(8),
            lon: coords.lon.toFixed(8),
            // Mark the anchor as manually placed so the source attribution
            // and drift indicator reflect the user's deliberate override.
            metadata,
          });
        } else if (projectId) {
          // Anchor was DERIVED from the project address (id is null and
          // not yet persisted). The first drag confirms + persists it so
          // the "drag to confirm" nudge actually saves a real GeoAnchor
          // instead of silently no-oping. ``createAnchor`` is idempotent
          // server-side (overwrites the project's single anchor row).
          await createAnchor({
            project_id: projectId,
            lat: coords.lat.toFixed(8),
            lon: coords.lon.toFixed(8),
            metadata,
          });
        } else {
          return;
        }
        addToast({
          type: 'success',
          title: anchorId
            ? t('geo_hub.adjust.moved_success', { defaultValue: 'Anchor moved' })
            : t('geo_hub.adjust.saved_success', {
                defaultValue: 'Location saved',
              }),
        });
        await queryClient.invalidateQueries({
          queryKey: ['geo-hub', 'map-config', projectId],
        });
        // Refresh the layer legend so its derived-anchor nudge clears.
        await queryClient.invalidateQueries({
          queryKey: ['geo-hub', 'map-summary', projectId],
        });
      } catch {
        addToast({
          type: 'error',
          title: t('geo_hub.adjust.moved_failed', {
            defaultValue: 'Could not move the anchor',
          }),
        });
      } finally {
        setAnchorDragMode(false);
      }
    },
    [data?.anchor?.id, data?.anchor?.metadata, addToast, t, queryClient, projectId],
  );

  // Apply optional ?phase / ?block / ?dev_id deep-link filters to the
  // tileset list. The map-config endpoint already returns the project's
  // full set; we narrow client-side so deep-links from PropDev or BIM
  // can show just the relevant slice. Each filter is matched against
  // ``Tileset.metadata`` keys; falls through to "no match" when fields
  // are absent. When none of the filters are present this is a no-op.
  const allTilesets = data?.tilesets;
  const tilesets = useMemo(() => {
    if (!allTilesets) return allTilesets;
    if (!phaseFilter && !blockFilter && !focusedDevId) return allTilesets;
    return allTilesets.filter((ts) => {
      const meta = ts.metadata as Record<string, unknown> | undefined;
      if (!meta || typeof meta !== 'object') return false;
      if (phaseFilter && meta['phase_id'] !== phaseFilter) return false;
      if (blockFilter && meta['block_id'] !== blockFilter) return false;
      if (focusedDevId && meta['development_id'] !== focusedDevId) return false;
      return true;
    });
  }, [allTilesets, phaseFilter, blockFilter, focusedDevId]);
  const emptyKind = useMemo(
    () => emptyStateFor(Boolean(data?.anchor), tilesets),
    [data?.anchor, tilesets],
  );

  // Resolve ``?model=...`` to a Tileset.id by matching either the
  // polymorphic ``source_id`` (bim_model / federation) or the
  // ``metadata.cad_import_id`` stamped by the canonical-tileset
  // packager. Also honors ``?plot=...`` by matching ``metadata.plot_id``.
  // Falls back to ``null`` so the viewer skips flyTo() when no deep link
  // is in flight.
  const focusedTilesetId = useMemo<string | null>(() => {
    const list = tilesets;
    if (!list || list.length === 0) return null;
    if (!focusedModelId && !focusedPlotId) return null;
    const hit = list.find((ts) => {
      if (focusedModelId) {
        if (ts.source_id === focusedModelId) return true;
        const meta = ts.metadata as Record<string, unknown> | undefined;
        if (meta && typeof meta === 'object') {
          const cad = meta['cad_import_id'];
          if (typeof cad === 'string' && cad === focusedModelId) return true;
          const fed = meta['federation_id'];
          if (typeof fed === 'string' && fed === focusedModelId) return true;
        }
      }
      if (focusedPlotId) {
        const meta = ts.metadata as Record<string, unknown> | undefined;
        if (meta && typeof meta === 'object') {
          if (meta['plot_id'] === focusedPlotId) return true;
        }
      }
      return false;
    });
    return hit?.id ?? null;
  }, [focusedModelId, focusedPlotId, tilesets]);

  // 404 from /api/v1/geo-hub/map-config means either project doesn't
  // exist (user follows a broken deep-link) or backend is stale. Either
  // way the actionable hint is different from the generic error — we
  // expose it so the page can render the right banner.
  const isStaleBackend =
    error instanceof ApiError && error.status === 404;

  // Compose the viewer's map config with the filtered tileset list so
  // the Cesium scene only loads what the deep-link asked for. Cheap —
  // we only override one field on the existing bundle when filtered.
  const viewerMapConfig = useMemo(() => {
    if (!data) return data;
    if (tilesets === allTilesets) return data;
    return { ...data, tilesets: tilesets ?? [] };
  }, [data, tilesets, allTilesets]);

  if (!projectId) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-sm text-semantic-error">
        {t('geo_hub.missing_project', {
          defaultValue: 'Project id missing from URL.',
        })}
      </div>
    );
  }

  return (
    // Full-bleed layout — negate AppLayout's <main> padding (px-4 pt-6 pb-4 sm:px-7)
    // so the map fills the viewport, then claim exactly viewport-minus-header
    // height so the Cesium canvas never spills past the visible browser area.
    // ``100dvh`` (not ``100vh``) so iOS Safari's collapsing URL bar
    // doesn't paint the Cesium canvas behind the dynamic toolbar — the
    // global Geo Hub already uses ``100dvh`` (since v4.7.2); the project-
    // scoped view shipped with the legacy ``100vh`` and was clipped on
    // first paint on every iOS phone. Fix is mechanical: prefer ``dvh``
    // and rely on browsers without ``dvh`` support to fall back via the
    // separate ``vh`` rule (Cesium target browsers — Safari >= 15.4 +
    // Chrome >= 108 — all support ``dvh``, so no fallback chain needed).
    <div className="-mx-4 -mt-6 -mb-4 flex h-[calc(100dvh-var(--oe-header-height,52px))] w-[calc(100%+2rem)] flex-col sm:-mx-7 sm:w-[calc(100%+3.5rem)]">
      <header
        className={[
          'flex items-center gap-4 border-b border-border bg-surface-primary',
          'px-5 py-3',
        ].join(' ')}
      >
        <div className="flex items-center gap-2.5">
          <span
            className={[
              'inline-flex h-8 w-8 items-center justify-center rounded-md',
              'bg-oe-blue/10 text-oe-blue',
            ].join(' ')}
          >
            <MapPinned size={16} strokeWidth={2} />
          </span>
          <div>
            <h1 className="text-base font-semibold leading-tight text-content-primary">
              {t('geo_hub.project_title', { defaultValue: 'Project map' })}
            </h1>
            <p className="text-2xs uppercase tracking-[0.14em] text-content-tertiary">
              {data?.anchor
                ? t('geo_hub.anchor_set', { defaultValue: 'Anchored' })
                : t('geo_hub.anchor_missing', { defaultValue: 'Not yet anchored' })}
            </p>
          </div>
        </div>
        {data?.anchor && (
          <div className="hidden items-center gap-3 text-xs text-content-secondary md:flex">
            <span className="font-mono tabular-nums">
              {Number(data.anchor.lat).toFixed(4)},{' '}
              {Number(data.anchor.lon).toFixed(4)}
            </span>
            <span className="text-content-tertiary">
              EPSG:{data.anchor.epsg_code}
            </span>
          </div>
        )}
        <p className="hidden flex-1 truncate text-xs text-content-tertiary md:block">
          {t('geo_hub.project_subtitle', {
            defaultValue:
              'Drag to rotate · scroll to zoom · click a pin to inspect',
          })}
        </p>
        <div className="ml-auto flex items-center gap-2">
          {data?.anchor && (
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              data-testid="geo-place-on-map"
              className="inline-flex items-center gap-1.5 rounded-md bg-oe-blue px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-oe-blue/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
            >
              <MapPin size={14} strokeWidth={2.25} />
              {t('geo_hub.place.header_cta', { defaultValue: 'Place on map' })}
            </button>
          )}
          <GeoModePicker current="project" projectId={projectId} />
        </div>
      </header>
      {/* Full-width canvas — the tileset rail is overlay-mounted on top
          (via CesiumViewer's ``overlay`` slot) so the map gets the full
          viewport width. Empty / loading / error states share that slot
          so they also paint above the canvas. */}
      <main className="relative flex-1 overflow-hidden bg-slate-900">
        {error && (
          <div className="absolute inset-0 z-30 flex items-center justify-center p-6">
            {isStaleBackend ? (
              <div className="inline-flex max-w-md items-start gap-3 rounded-lg border border-amber-300/40 bg-amber-950/60 px-4 py-3 text-sm text-amber-100 shadow-md backdrop-blur-md">
                <ServerCrash size={16} className="mt-0.5 shrink-0 text-amber-300" />
                <span>
                  {t('geo_hub.project_stale_backend', {
                    defaultValue:
                      'The geo service is starting up or out of date. Reload in a moment, or contact your admin to restart the backend.',
                  })}
                </span>
              </div>
            ) : (
              <div className="inline-flex max-w-md items-start gap-3 rounded-lg border border-red-300/40 bg-red-950/60 px-4 py-3 text-sm text-red-100 shadow-md backdrop-blur-md">
                <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-300" />
                <span>
                  {t('geo_hub.load_failed', {
                    defaultValue: 'Could not load geo data for this project.',
                  })}
                </span>
              </div>
            )}
          </div>
        )}
        {!error && isLoading && (
          <div
            className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 text-xs text-slate-300"
            role="status"
            aria-live="polite"
          >
            {/* Skeleton placeholder for the tileset rail so the empty
                glass surface doesn't read as "no projects". Two muted
                bars approximate the panel chrome the user is about to
                see — same width + position as the real overlay. */}
            <div
              aria-hidden
              className="absolute top-3 left-3 hidden w-72 flex-col gap-2 rounded-xl border border-white/10 bg-slate-900/40 p-3 backdrop-blur-md md:flex"
            >
              <div className="h-3 w-1/2 rounded bg-slate-700/60 animate-pulse" />
              <div className="h-2 w-2/3 rounded bg-slate-700/50 animate-pulse" />
              <div className="mt-2 space-y-1.5">
                <div className="h-8 rounded bg-slate-800/60 animate-pulse" />
                <div className="h-8 rounded bg-slate-800/60 animate-pulse" />
                <div className="h-8 rounded bg-slate-800/60 animate-pulse" />
              </div>
            </div>
            <Loader2 size={20} className="animate-spin text-emerald-300" />
            <span className="font-medium">
              {t('geo_hub.loading_config', {
                defaultValue: 'Loading geo configuration...',
              })}
            </span>
          </div>
        )}
        {!error && data && (
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center text-sm text-slate-300">
                {t('geo_hub.loading_viewer', {
                  defaultValue: 'Loading Cesium viewer (~3 MB)...',
                })}
              </div>
            }
          >
            <CesiumViewer
              mode="project"
              mapConfig={viewerMapConfig}
              pins={pins}
              focusedTilesetId={focusedTilesetId}
              flyToTarget={overlayFlyTarget}
              tilesetOverlayState={tilesetOverlay.state}
              anchorDragMode={anchorDragMode}
              onMapClick={handleAnchorMapClick}
              onPinSelect={handlePinSelect}
              onMouseMove={setCursorCoords}
              onCameraChange={setCameraState}
              onViewerReady={setCesiumRuntime}
              overlay={
                <>
                  <GeoOverlayHud
                    cursorLat={cursorCoords?.lat ?? null}
                    cursorLon={cursorCoords?.lon ?? null}
                    altitudeM={cameraState?.cameraAltitudeM ?? null}
                    headingDeg={cameraState?.headingDeg ?? null}
                    active
                  />
                  <TilesetSidebar
                    variant="overlay"
                    collapsed={panelCollapsed}
                    onToggleCollapsed={() => setPanelCollapsed((v) => !v)}
                    tilesets={tilesets}
                    isLoading={isLoading}
                    hiddenIds={hiddenIds}
                    focusedId={focusedId}
                    onToggleVisibility={tilesetOverlay.toggleVisible}
                    onFocus={(ts) => setFocusedId(ts.id)}
                    getOpacity={tilesetOverlay.getOpacity}
                    onChangeOpacity={tilesetOverlay.setOpacity}
                  />
                  <OverlayPanel
                    projectId={projectId}
                    activeOverlayId={activeOverlayId}
                    editMode={overlayEditMode}
                    onSelectOverlay={(id) => {
                      setActiveOverlayId(id);
                      if (id === null) setOverlayEditMode('idle');
                    }}
                    onChangeEditMode={setOverlayEditMode}
                  />
                  <OverlayLayer
                    projectId={projectId}
                    cesium={cesiumRuntime?.cesium ?? null}
                    viewer={cesiumRuntime?.viewer ?? null}
                    activeOverlayId={activeOverlayId}
                    editMode={overlayEditMode}
                    onSelectOverlay={setActiveOverlayId}
                    onChangeEditMode={setOverlayEditMode}
                  />
                  {emptyKind && (
                    <GeoEmptyState
                      kind={emptyKind}
                      projectId={projectId}
                      onPlaceOnMap={() => setPickerOpen(true)}
                    />
                  )}
                  {data?.anchor && !emptyKind && (
                    <AnchorAdjustPanel
                      projectId={projectId}
                      anchor={data.anchor}
                      dragMode={anchorDragMode}
                      onToggleDragMode={() => setAnchorDragMode((v) => !v)}
                      projectAddressText={projectAddressText}
                    />
                  )}
                  {/* Layer legend — feature counts + breakdowns per layer,
                      with deep-links into the source module for empty
                      layers. Only meaningful once the project is locatable
                      (a real or address-derived anchor); the no-anchor
                      empty state owns the canvas otherwise. */}
                  {data?.anchor && !emptyKind && (
                    <MapLayerLegend projectId={projectId} />
                  )}
                </>
              }
            />
          </Suspense>
        )}
      </main>
      <PlaceOnMapPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        projectId={projectId}
        hasAnchor={Boolean(data?.anchor)}
        onPlaced={(placed) => {
          // Close the picker so the map (and the thing we just placed) is
          // actually visible — leaving the modal open over the canvas was
          // the "placed but I see nothing" report.
          setPickerOpen(false);
          if (placed.kind === 'model') {
            // Focus the camera on the model once the map config refetches
            // and the new tileset appears (?model resolves to the tileset
            // via source_id, then the viewer flies to its bounding sphere).
            navigate(`/projects/${projectId}/geo?model=${placed.modelId}`, {
              replace: true,
            });
          } else {
            // PDF overlay — fly straight to its centroid. A fresh nonce each
            // time so re-placing the same drawing always re-flies.
            setOverlayFlyTarget({
              key: `overlay-${Date.now()}`,
              lat: placed.lat,
              lon: placed.lon,
            });
          }
        }}
      />
    </div>
  );
}

export default ProjectGeoPage;
