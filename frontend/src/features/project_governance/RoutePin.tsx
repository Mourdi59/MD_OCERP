// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Which approval route the project's gate decisions run on.
//
// A gate goes to review on an approval route for phase gates, and the people
// on the route's last step are the ones entitled to decide. Left alone, the
// project uses the first active route it finds: its own before a shared one.
// Pinning names the route, so a second route added later cannot change who
// decides. A pinned route that was switched off blocks every submit, which
// the section says in words.

import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Route as RouteIcon } from 'lucide-react';

import { listRoutes } from '@/features/approval-routes/api';
import { Button } from '@/shared/ui/Button';
import { getErrorMessage } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';

import { governanceKeys, updateModelSettings, type GovernanceModel } from './api';
import { canManage } from './access';
import { VerdictReason } from './GovernanceBits';
import { refusalText } from './labels';

/** The approval-route target kind of a gate decision, as the backend names it. */
export const GATE_ROUTE_KIND = 'phase_gate';

const ROUTES_PAGE = '/governance?tab=approvals';

export interface RoutePinProps {
  projectId: string;
  model: GovernanceModel;
  onDone: () => void;
}

export function RoutePin({ projectId, model, onDone }: RoutePinProps) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const verdict = canManage(model);
  const routes = useQuery({
    queryKey: governanceKeys.routes(projectId),
    queryFn: () => listRoutes({ projectId, targetKind: GATE_ROUTE_KIND, includeInactive: false }),
  });
  const pin = useMutation({
    mutationFn: (routeId: string | null) => updateModelSettings(projectId, { decision_route_id: routeId }),
    onSuccess: (_model, routeId) => {
      addToast({
        type: 'success',
        title: routeId
          ? t('governance.project.route.pinned', { defaultValue: 'Approval route pinned' })
          : t('governance.project.route.unpinned', { defaultValue: 'The project uses its default route again' }),
      });
      onDone();
    },
    onError: (err) => addToast({ type: 'error', title: refusalText(t, err) }),
  });

  const list = routes.data ?? [];
  const pinned = model.decision_route_id;
  const pinnedMissing = !!pinned && routes.isSuccess && !list.some((r) => r.id === pinned);

  return (
    <section className="rounded-lg border border-border-light p-3" data-testid="route-pin">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-content-primary">
        <RouteIcon size={15} className="text-content-tertiary" aria-hidden />
        {t('governance.project.route.title', { defaultValue: 'Approval route for gate decisions' })}
      </h3>
      <p className="mt-1 text-xs text-content-secondary">
        {t('governance.project.route.body', {
          defaultValue:
            'A gate goes to review on this route. The people on its last step are the ones who may record the decision.',
        })}
      </p>

      {routes.isLoading && (
        <p className="mt-2 text-xs text-content-tertiary">{t('governance.project.loading', { defaultValue: 'Loading...' })}</p>
      )}
      {routes.isError && (
        <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-semantic-error" role="alert">
          {t('governance.project.route.load_failed', { defaultValue: 'The approval routes could not be loaded.' })}{' '}
          {getErrorMessage(routes.error)}
          <Button size="sm" variant="ghost" onClick={() => routes.refetch()}>
            {t('governance.project.retry', { defaultValue: 'Try again' })}
          </Button>
        </p>
      )}
      {routes.isSuccess && list.length === 0 && (
        <p className="mt-2 text-sm text-content-secondary" data-testid="route-pin-empty">
          {t('governance.project.route.empty', {
            defaultValue:
              'There is no active approval route for phase gates yet, so no gate can be submitted for review. Create one and put the deciders on its last step.',
          })}{' '}
          <Link to={ROUTES_PAGE} className="font-medium text-oe-blue hover:underline">
            {t('governance.project.route.open_routes', { defaultValue: 'Open approval routes' })}
          </Link>
        </p>
      )}
      {pinnedMissing && (
        <p className="mt-2 text-sm text-semantic-error" role="alert" data-testid="route-pin-missing">
          {t('governance.project.route.pinned_missing', {
            defaultValue:
              'The pinned route is no longer active, so no gate can be submitted for review. Choose another route or go back to the project default.',
          })}{' '}
          <Button size="sm" variant="secondary" disabled={!!verdict} loading={pin.isPending} onClick={() => pin.mutate(null)}>
            {t('governance.project.route.use_default', { defaultValue: 'Use the project default' })}
          </Button>
        </p>
      )}
      {routes.isSuccess && (list.length > 0 || pinnedMissing) && (
        <div className="mt-2 flex flex-col items-start gap-1">
          <select
            aria-label={t('governance.project.route.title', { defaultValue: 'Approval route for gate decisions' })}
            className="min-w-[16rem] rounded-md border border-border-light bg-surface-primary px-2.5 py-1.5 text-sm text-content-primary disabled:opacity-60"
            value={pinnedMissing ? '' : pinned ?? ''}
            disabled={!!verdict || pin.isPending}
            onChange={(e) => pin.mutate(e.target.value || null)}
          >
            <option value="">
              {t('governance.project.route.default_option', { defaultValue: 'Project default (first active route)' })}
            </option>
            {list.map((r) => (
              <option key={r.id} value={r.id}>
                {r.project_id
                  ? r.name
                  : t('governance.project.route.shared_option', { defaultValue: '{{name}} (shared)', name: r.name })}
              </option>
            ))}
          </select>
          <VerdictReason verdict={verdict} />
        </div>
      )}
    </section>
  );
}
