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
import { ArrowLeft } from 'lucide-react';

import { AdminOnly } from '@/shared/auth/AdminOnly';
import { Breadcrumb } from '@/shared/ui';
import { PageHeader } from '@/shared/ui/PageHeader';

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
        <PageHeader
          srTitle={t('geo_hub.admin_title', { defaultValue: 'Geo Hub — Admin' })}
          subtitle={t('geo_hub.admin_subtitle', {
            defaultValue: 'Operator-only utilities',
          })}
          actions={
            <Link
              to="/geo"
              className={[
                'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm',
                'text-content-tertiary hover:bg-surface-secondary hover:text-content-primary',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue',
              ].join(' ')}
            >
              <ArrowLeft size={14} strokeWidth={2} />
              {t('common.back', { defaultValue: 'Back' })}
            </Link>
          }
        />
        <GeocodeCacheAdminPanel />
      </div>
    </AdminOnly>
  );
}

export default GeoHubAdminPage;
