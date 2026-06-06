// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Geo Hub admin page (``/geo/admin``).
 *
 * Hosts the geocode cache admin panel today; reserved for future
 * admin-only Geo Hub surfaces (per-tenant base imagery defaults,
 * terrain source enrollment, etc.). Admin gating is enforced both by
 * ``<AdminOnly>`` on the route and by backend RBAC (``geo_hub.admin``)
 * on every API call.
 */

import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { ArrowLeft, ShieldCheck } from 'lucide-react';

import { AdminOnly } from '@/shared/auth/AdminOnly';
import { Breadcrumb } from '@/shared/ui';

import { GeocodeCacheAdminPanel } from './GeocodeCacheAdminPanel';

export function GeoHubAdminPage() {
  const { t } = useTranslation();
  return (
    <AdminOnly redirectTo="/404">
      <div className="mx-auto max-w-3xl space-y-4">
        <Breadcrumb
          items={[
            { label: t('sidebar.geo_hub', { defaultValue: 'Geo Hub' }), to: '/geo' },
            { label: t('geo_hub.admin_title', { defaultValue: 'Geo Hub — Admin' }) },
          ]}
        />
        <header className="flex items-center gap-3">
          <Link
            to="/geo"
            className={[
              'inline-flex h-8 w-8 items-center justify-center rounded-md',
              'text-content-tertiary hover:bg-surface-secondary hover:text-content-primary',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue',
            ].join(' ')}
            aria-label={t('common.back', { defaultValue: 'Back' })}
          >
            <ArrowLeft size={14} strokeWidth={2} />
          </Link>
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-300">
            <ShieldCheck size={16} strokeWidth={2} />
          </span>
          <div>
            <h1 className="text-base font-semibold text-content-primary leading-tight">
              {t('geo_hub.admin_title', { defaultValue: 'Geo Hub — Admin' })}
            </h1>
            <p className="text-2xs uppercase tracking-[0.14em] text-content-tertiary">
              {t('geo_hub.admin_subtitle', {
                defaultValue: 'Operator-only utilities',
              })}
            </p>
          </div>
        </header>
        <GeocodeCacheAdminPanel />
      </div>
    </AdminOnly>
  );
}

export default GeoHubAdminPage;
