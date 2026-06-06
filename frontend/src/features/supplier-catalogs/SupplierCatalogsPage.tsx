import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  ShoppingCart,
  Boxes,
  ClipboardList,
  FileCheck,
  Warehouse as WarehouseIcon,
  Search,
  Plus,
  Loader2,
  Star,
  AlertOctagon,
  Truck,
} from 'lucide-react';
import {
  Button,
  Card,
  Badge,
  EmptyState,
  Breadcrumb,
  SkeletonTable,
} from '@/shared/ui';
import {
  WideModal,
  WideModalSection,
  WideModalField,
} from '@/shared/ui/WideModal';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { PipelineBanner } from './PipelineBanner';
import { getErrorMessage, apiGet } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';
import { usePreferencesStore } from '@/stores/usePreferencesStore';
import {
  listVendors,
  listCatalogItems,
  listWarehouses,
  listWarehouseBalances,
  comparePrices,
  createVendor,
  createCatalogItem,
  createWarehouse,
  createPR,
  createPO,
  type Vendor,
  type CatalogItem,
  type Warehouse,
  type StockBalance,
  type PriceComparisonRow,
  type VendorStatus,
} from './api';

type Tab = 'vendors' | 'catalog' | 'prs' | 'pos' | 'match' | 'warehouses';

const VENDOR_VARIANT: Record<VendorStatus, 'neutral' | 'blue' | 'success' | 'warning' | 'error'> = {
  active: 'success',
  suspended: 'warning',
  blacklisted: 'error',
  pending: 'neutral',
};

const inputCls =
  'h-9 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

interface ProjectStub {
  id: string;
  name: string;
  currency?: string;
}

function listProjectsLite(): Promise<ProjectStub[]> {
  return apiGet<ProjectStub[]>('/v1/projects/?limit=200').catch(
    () => [] as ProjectStub[],
  );
}

export function SupplierCatalogsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('vendors');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [priceItem, setPriceItem] = useState<CatalogItem | null>(null);
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string>('');

  const vendorsQ = useQuery({
    queryKey: ['sc', 'vendors', statusFilter],
    queryFn: () => listVendors({ status: statusFilter || undefined, limit: 200 }),
    enabled: tab === 'vendors' || tab === 'catalog' || tab === 'prs' || tab === 'pos' || tab === 'match',
  });
  const itemsQ = useQuery({
    queryKey: ['sc', 'items', search],
    queryFn: () => listCatalogItems({ search: search || undefined, limit: 200 }),
    enabled: tab === 'catalog',
  });
  const warehousesQ = useQuery({
    queryKey: ['sc', 'warehouses'],
    queryFn: () => listWarehouses(),
    enabled: tab === 'warehouses',
  });
  // The select visually defaults to the first warehouse, so balances must
  // fetch for it even before the user explicitly picks one (otherwise the
  // first warehouse looks selected but its stock never loads).
  const effectiveWarehouseId =
    selectedWarehouseId ||
    (Array.isArray(warehousesQ.data) ? (warehousesQ.data[0]?.id ?? '') : '');
  const balancesQ = useQuery({
    queryKey: ['sc', 'balances', effectiveWarehouseId],
    queryFn: () => listWarehouseBalances(effectiveWarehouseId),
    enabled: tab === 'warehouses' && !!effectiveWarehouseId,
  });

  // PRs / POs / invoices: backend lacks list endpoints today.  We compute
  // synthetic empty lists and show an EmptyState.  The create-flow still
  // works.  This keeps the surface honest about what the API supports.
  // Defensive coerce — the offline-cache layer can occasionally hydrate
  // the query with a non-array value (e.g. a stale FastAPI error envelope
  // from a previous session), which would crash ``.filter()`` below.
  const vendorsArr = Array.isArray(vendorsQ.data) ? vendorsQ.data : [];
  const itemsArr = Array.isArray(itemsQ.data) ? itemsQ.data : [];
  const warehousesArr = Array.isArray(warehousesQ.data) ? warehousesQ.data : [];
  const balancesArr = Array.isArray(balancesQ.data) ? balancesQ.data : [];
  const filteredVendors = useMemo(
    () => filterByText(vendorsArr, search, (v) => `${v.code} ${v.name} ${v.country_code ?? ''}`),
    [vendorsArr, search],
  );
  const filteredItems = itemsArr;

  const isLoading =
    (tab === 'vendors' && vendorsQ.isLoading) ||
    (tab === 'catalog' && itemsQ.isLoading) ||
    (tab === 'warehouses' && (warehousesQ.isLoading || balancesQ.isLoading));

  // Surface fetch failures explicitly — a failed query must NOT render as
  // an empty success ("No vendors yet"), which silently hides outages.
  const activeError =
    tab === 'vendors'
      ? vendorsQ.error
      : tab === 'catalog'
        ? itemsQ.error
        : tab === 'warehouses'
          ? (warehousesQ.error ?? balancesQ.error)
          : null;
  const refetchActive = () => {
    if (tab === 'vendors') void vendorsQ.refetch();
    else if (tab === 'catalog') void itemsQ.refetch();
    else if (tab === 'warehouses') {
      void warehousesQ.refetch();
      if (effectiveWarehouseId) void balancesQ.refetch();
    }
  };

  return (
    <div className="space-y-5">
      <Breadcrumb items={[{ label: t('nav.supplier_catalogs', { defaultValue: 'Supplier Catalogs' }) }]} />

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">
            {t('supplier_catalogs.title', { defaultValue: 'Supplier Catalogs' })}
          </h1>
          <p className="mt-1 text-sm text-content-secondary">
            {t('supplier_catalogs.subtitle', {
              defaultValue: 'Vendors, item catalogs, price comparison, requisitions, POs and warehouses.',
            })}
          </p>
        </div>
        <Button variant="primary" icon={<Plus size={14} />} onClick={() => setCreateOpen(true)}>
          {createLabel(tab, t)}
        </Button>
      </div>

      <PipelineBanner
        intro={t('supplier_catalogs.pipeline_intro', {
          defaultValue:
            'The buying chain: register vendors and their priced catalogs, raise a requisition, convert it to a purchase order, then three-way match the invoice on receipt. Catalog prices feed the cost database.',
        })}
        steps={[
          {
            label: t('supplier_catalogs.step_costs', {
              defaultValue: 'Cost Database',
            }),
            to: '/costs',
          },
          {
            label: t('supplier_catalogs.step_catalog', {
              defaultValue: 'Supplier Catalogs',
            }),
            current: true,
          },
          {
            label: t('supplier_catalogs.step_procurement', {
              defaultValue: 'Procurement',
            }),
            to: '/procurement',
          },
        ]}
      />

      <div className="border-b border-border-light">
        <nav className="flex gap-1 -mb-px overflow-x-auto">
          {tabsDef(t).map((it) => {
            const Icon = it.icon;
            return (
              <button
                key={it.id}
                type="button"
                onClick={() => {
                  setTab(it.id);
                  setStatusFilter('');
                  setSearch('');
                }}
                className={clsx(
                  'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
                  tab === it.id
                    ? 'border-oe-blue text-oe-blue'
                    : 'border-transparent text-content-secondary hover:text-content-primary',
                )}
              >
                <Icon size={14} />
                {it.label}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-content-tertiary" />
          <input
            type="text"
            placeholder={t('common.search', { defaultValue: 'Search…' })}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={clsx(inputCls, 'pl-8')}
          />
        </div>
        {tab === 'vendors' && (
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className={clsx(inputCls, 'max-w-[180px]')}
          >
            <option value="">{t('common.all_statuses', { defaultValue: 'All statuses' })}</option>
            {(['active', 'suspended', 'blacklisted', 'pending'] as VendorStatus[]).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        )}
        {tab === 'warehouses' && warehousesArr.length > 0 && (
          <select
            value={effectiveWarehouseId}
            onChange={(e) => setSelectedWarehouseId(e.target.value)}
            className={clsx(inputCls, 'max-w-[280px]')}
          >
            {warehousesArr.map((w) => (
              <option key={w.id} value={w.id}>
                {w.code} — {w.name}
              </option>
            ))}
          </select>
        )}
      </div>

      <Card padding="none">
        {activeError ? (
          <EmptyState
            icon={<AlertOctagon size={22} />}
            title={t('supplier_catalogs.load_failed', {
              defaultValue: 'Could not load data',
            })}
            description={getErrorMessage(activeError)}
            action={{
              label: t('common.retry', { defaultValue: 'Retry' }),
              onClick: refetchActive,
            }}
          />
        ) : isLoading ? (
          <div className="p-4">
            <SkeletonTable rows={8} columns={5} />
          </div>
        ) : tab === 'vendors' ? (
          <VendorTable rows={filteredVendors} onAction={() => setCreateOpen(true)} />
        ) : tab === 'catalog' ? (
          <CatalogTable rows={filteredItems} onSelectPrice={(it) => setPriceItem(it)} onAction={() => setCreateOpen(true)} />
        ) : tab === 'prs' ? (
          <PREmptyOrTable onAction={() => setCreateOpen(true)} />
        ) : tab === 'pos' ? (
          <POEmptyOrTable onAction={() => setCreateOpen(true)} />
        ) : tab === 'match' ? (
          <MatchEmptyState />
        ) : (
          <WarehousePanel
            warehouses={warehousesArr}
            selectedId={effectiveWarehouseId}
            balances={balancesArr}
            onAction={() => setCreateOpen(true)}
          />
        )}
      </Card>

      {createOpen && (
        <CreateModal kind={tab} vendors={vendorsQ.data ?? []} onClose={() => setCreateOpen(false)} />
      )}
      {priceItem && (
        <PriceComparisonModal
          item={priceItem}
          vendors={vendorsQ.data ?? []}
          onClose={() => setPriceItem(null)}
        />
      )}
    </div>
  );
}

function tabsDef(t: (k: string, opts?: Record<string, unknown>) => string) {
  return [
    { id: 'vendors' as const, label: t('supplier_catalogs.tab_vendors', { defaultValue: 'Vendors' }), icon: Truck },
    { id: 'catalog' as const, label: t('supplier_catalogs.tab_catalog', { defaultValue: 'Catalog' }), icon: Boxes },
    { id: 'prs' as const, label: t('supplier_catalogs.tab_prs', { defaultValue: 'PRs' }), icon: ClipboardList },
    { id: 'pos' as const, label: t('supplier_catalogs.tab_pos', { defaultValue: 'POs' }), icon: ShoppingCart },
    { id: 'match' as const, label: t('supplier_catalogs.tab_match', { defaultValue: '3-Way Match' }), icon: FileCheck },
    { id: 'warehouses' as const, label: t('supplier_catalogs.tab_warehouses', { defaultValue: 'Warehouses' }), icon: WarehouseIcon },
  ];
}

function createLabel(tab: Tab, t: (k: string, opts?: Record<string, unknown>) => string): string {
  switch (tab) {
    case 'vendors':
      return t('supplier_catalogs.new_vendor', { defaultValue: 'New Vendor' });
    case 'catalog':
      return t('supplier_catalogs.new_item', { defaultValue: 'New Item' });
    case 'prs':
      return t('supplier_catalogs.new_pr', { defaultValue: 'New Requisition' });
    case 'pos':
      return t('supplier_catalogs.new_po', { defaultValue: 'New PO' });
    case 'match':
      return t('supplier_catalogs.match_invoice', { defaultValue: 'Match Invoice' });
    case 'warehouses':
      return t('supplier_catalogs.new_warehouse', { defaultValue: 'New Warehouse' });
  }
}

function filterByText<T>(rows: T[], search: string, getter: (r: T) => string): T[] {
  if (!search.trim()) return rows;
  const q = search.toLowerCase();
  return rows.filter((r) => getter(r).toLowerCase().includes(q));
}

/* ── Stars ─────────────────────────────────────────────────────────────── */

function StarRating({ rating }: { rating: number | null }) {
  const value = rating ?? 0;
  return (
    <div className="inline-flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          size={12}
          className={
            i <= value
              ? 'fill-[#f59e0b] text-[#f59e0b]'
              : 'fill-transparent text-content-quaternary'
          }
        />
      ))}
      <span className="ml-1 text-2xs text-content-tertiary tabular-nums">{value}/5</span>
    </div>
  );
}

/* ── Tables ────────────────────────────────────────────────────────────── */

function VendorTable({ rows, onAction }: { rows: Vendor[]; onAction: () => void }) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<Truck size={22} />}
        title={t('supplier_catalogs.empty_vendors', { defaultValue: 'No vendors yet' })}
        description={t('supplier_catalogs.empty_vendors_desc', {
          defaultValue: 'Register suppliers with payment terms and category coverage to buy from.',
        })}
        action={{ label: t('supplier_catalogs.new_vendor', { defaultValue: 'New Vendor' }), onClick: onAction }}
      />
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.code', { defaultValue: 'Code' })}</th>
            <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.name', { defaultValue: 'Name' })}</th>
            <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.country', { defaultValue: 'Country' })}</th>
            <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.rating', { defaultValue: 'Rating' })}</th>
            <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.payment_terms', { defaultValue: 'Terms' })}</th>
            <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.status', { defaultValue: 'Status' })}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-border-light hover:bg-surface-secondary">
              <td className="px-4 py-2 font-mono text-xs text-content-secondary">{r.code}</td>
              <td className="px-4 py-2 font-medium text-content-primary truncate max-w-[320px]">{r.name}</td>
              <td className="px-4 py-2 text-content-secondary text-xs">{r.country_code || '—'}</td>
              <td className="px-4 py-2">
                <StarRating rating={r.rating} />
              </td>
              <td className="px-4 py-2 text-content-secondary text-xs tabular-nums">
                {r.payment_terms_days}d · {r.currency}
              </td>
              <td className="px-4 py-2">
                <Badge variant={VENDOR_VARIANT[r.status] || 'neutral'} dot>
                  {r.status}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CatalogTable({
  rows,
  onSelectPrice,
  onAction,
}: {
  rows: CatalogItem[];
  onSelectPrice: (item: CatalogItem) => void;
  onAction: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<Boxes size={22} />}
        title={t('supplier_catalogs.empty_catalog', { defaultValue: 'No catalog items yet' })}
        description={t('supplier_catalogs.empty_catalog_desc', {
          defaultValue: 'SKUs you order — pipe, fittings, materials. Tie to multiple vendors for price comparison.',
        })}
        action={{ label: t('supplier_catalogs.new_item', { defaultValue: 'New Item' }), onClick: onAction }}
      />
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.sku', { defaultValue: 'SKU' })}</th>
            <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.name', { defaultValue: 'Name' })}</th>
            <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.uom', { defaultValue: 'UoM' })}</th>
            <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.manufacturer', { defaultValue: 'Manufacturer' })}</th>
            <th className="px-4 py-2.5 text-right">{t('supplier_catalogs.reorder', { defaultValue: 'Reorder' })}</th>
            <th className="px-4 py-2.5 text-right">{t('supplier_catalogs.actions', { defaultValue: 'Actions' })}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-border-light hover:bg-surface-secondary">
              <td className="px-4 py-2 font-mono text-xs text-content-secondary">{r.sku}</td>
              <td className="px-4 py-2 font-medium text-content-primary truncate max-w-[320px]">{r.name}</td>
              <td className="px-4 py-2 text-content-secondary text-xs">{r.unit_of_measure}</td>
              <td className="px-4 py-2 text-content-secondary text-xs">{r.manufacturer || '—'}</td>
              <td className="px-4 py-2 text-right text-xs tabular-nums">{String(r.reorder_point)}</td>
              <td className="px-4 py-2 text-right">
                <Button variant="ghost" size="sm" onClick={() => onSelectPrice(r)}>
                  {t('supplier_catalogs.compare_prices', { defaultValue: 'Compare prices' })}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProcurementHandoff() {
  const { t } = useTranslation();
  return (
    <Link
      to="/procurement"
      className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-border-light px-3 py-1.5 text-xs font-medium text-content-secondary hover:text-oe-blue hover:border-oe-blue transition-colors"
    >
      {t('supplier_catalogs.open_procurement', {
        defaultValue: 'Track requisitions & POs in Procurement',
      })}
    </Link>
  );
}

function PREmptyOrTable({ onAction }: { onAction: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center">
      <EmptyState
        icon={<ClipboardList size={22} />}
        title={t('supplier_catalogs.prs_empty', {
          defaultValue: 'Create a requisition',
        })}
        description={t('supplier_catalogs.prs_empty_desc', {
          defaultValue:
            'Raise a PR with line items here; its full lifecycle (approval → conversion to PO → receipt) is tracked in the Procurement module.',
        })}
        action={{
          label: t('supplier_catalogs.new_pr', { defaultValue: 'New Requisition' }),
          onClick: onAction,
        }}
      />
      <ProcurementHandoff />
    </div>
  );
}

function POEmptyOrTable({ onAction }: { onAction: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center">
      <EmptyState
        icon={<ShoppingCart size={22} />}
        title={t('supplier_catalogs.pos_empty', {
          defaultValue: 'Create a purchase order',
        })}
        description={t('supplier_catalogs.pos_empty_desc', {
          defaultValue:
            'Issue a PO to a vendor here; the draft → sent → acknowledged → received → closed flow is managed in the Procurement module.',
        })}
        action={{
          label: t('supplier_catalogs.new_po', { defaultValue: 'New PO' }),
          onClick: onAction,
        }}
      />
      <ProcurementHandoff />
    </div>
  );
}

function MatchEmptyState() {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={<AlertOctagon size={22} />}
      title={t('supplier_catalogs.match_empty', { defaultValue: 'No match exceptions' })}
      description={t('supplier_catalogs.match_empty_desc', {
        defaultValue:
          'Invoices that fail PO/GR/quantity tolerance checks land here for review. Auto-matched invoices are hidden.',
      })}
    />
  );
}

function WarehousePanel({
  warehouses,
  selectedId,
  balances,
  onAction,
}: {
  warehouses: Warehouse[];
  selectedId: string;
  balances: StockBalance[];
  onAction: () => void;
}) {
  const { t } = useTranslation();
  // StockBalance carries no currency field; warehouses themselves are
  // currency-agnostic. Fall back to the user's preferred currency so
  // the column shows a unit instead of a post-Wave2 em-dash.
  const prefCurrency = usePreferencesStore((s) => s.currency);
  if (warehouses.length === 0) {
    return (
      <EmptyState
        icon={<WarehouseIcon size={22} />}
        title={t('supplier_catalogs.empty_warehouses', { defaultValue: 'No warehouses yet' })}
        description={t('supplier_catalogs.empty_warehouses_desc', {
          defaultValue: 'Register storage locations to track stock on hand, reservations and movements.',
        })}
        action={{
          label: t('supplier_catalogs.new_warehouse', { defaultValue: 'New Warehouse' }),
          onClick: onAction,
        }}
      />
    );
  }
  const selected = warehouses.find((w) => w.id === selectedId) || warehouses[0];
  return (
    <div>
      <div className="px-5 py-3 border-b border-border-light flex items-center gap-3 flex-wrap">
        <div>
          <p className="text-xs uppercase tracking-wide text-content-tertiary">
            {t('supplier_catalogs.warehouse', { defaultValue: 'Warehouse' })}
          </p>
          <p className="text-sm font-semibold text-content-primary">
            {selected?.code} — {selected?.name}
          </p>
        </div>
        {selected?.address && (
          <div>
            <p className="text-xs uppercase tracking-wide text-content-tertiary">
              {t('supplier_catalogs.address', { defaultValue: 'Address' })}
            </p>
            <p className="text-xs text-content-secondary truncate max-w-[320px]">{selected.address}</p>
          </div>
        )}
      </div>
      {balances.length === 0 ? (
        <div className="p-6 text-center text-sm text-content-tertiary">
          {t('supplier_catalogs.no_stock', { defaultValue: 'No stock balances recorded.' })}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
              <tr>
                <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.item', { defaultValue: 'Item' })}</th>
                <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.batch', { defaultValue: 'Batch' })}</th>
                <th className="px-4 py-2.5 text-right">{t('supplier_catalogs.on_hand', { defaultValue: 'On hand' })}</th>
                <th className="px-4 py-2.5 text-right">{t('supplier_catalogs.reserved', { defaultValue: 'Reserved' })}</th>
                <th className="px-4 py-2.5 text-right">{t('supplier_catalogs.unit_cost_avg', { defaultValue: 'Avg cost' })}</th>
                <th className="px-4 py-2.5 text-left">{t('supplier_catalogs.last_moved', { defaultValue: 'Last moved' })}</th>
              </tr>
            </thead>
            <tbody>
              {balances.map((b) => (
                <tr key={b.id} className="border-t border-border-light hover:bg-surface-secondary">
                  <td className="px-4 py-2 font-mono text-xs text-content-secondary truncate max-w-[280px]">
                    {b.catalog_item_id.slice(0, 8)}
                  </td>
                  <td className="px-4 py-2 text-content-secondary text-xs">{b.batch_lot || '—'}</td>
                  <td className="px-4 py-2 text-right text-xs tabular-nums">{String(b.quantity_on_hand)}</td>
                  <td className="px-4 py-2 text-right text-xs tabular-nums">{String(b.quantity_reserved)}</td>
                  <td className="px-4 py-2 text-right text-xs tabular-nums">
                    <MoneyDisplay amount={Number(b.unit_cost_avg) || 0} currency={prefCurrency} />
                  </td>
                  <td className="px-4 py-2 text-xs text-content-secondary">
                    {b.last_movement_at ? <DateDisplay value={b.last_movement_at} /> : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ── Price comparison modal ────────────────────────────────────────────── */

function PriceComparisonModal({
  item,
  vendors,
  onClose,
}: {
  item: CatalogItem;
  vendors: Vendor[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ['sc', 'price-compare', item.id],
    queryFn: () => comparePrices(item.id),
  });
  const rows = q.data ?? [];
  // Money bug fix: each vendor price list carries its own ISO currency, so a
  // raw Number(unit_price) comparison across rows would crown e.g. 100 JPY
  // "cheaper" than 5 EUR. We may only pick a single cheapest when every
  // compared row shares one currency. When currencies differ we never crown a
  // cross-currency winner — the UI shows a "mixed currencies" note instead.
  const distinctCurrencies = useMemo(
    () => new Set(rows.map((r) => r.currency)),
    [rows],
  );
  const singleCurrency = distinctCurrencies.size <= 1;
  const cheapest = useMemo(() => {
    if (rows.length === 0) return null;
    // Only a same-currency comparison is meaningful; otherwise no winner.
    if (!singleCurrency) return null;
    return rows.reduce<PriceComparisonRow | null>((best, r) => {
      if (!best) return r;
      // Decimal-serialized strings: wrap in Number() before comparing.
      return Number(r.unit_price) < Number(best.unit_price) ? r : best;
    }, null);
  }, [rows, singleCurrency]);

  return (
    <WideModal
      open
      onClose={onClose}
      title={t('supplier_catalogs.price_comparison', { defaultValue: 'Price Comparison' })}
      subtitle={`${item.sku} · ${item.name} · ${item.unit_of_measure}`}
      size="xl"
    >
      <div>
        {q.isLoading ? (
          <SkeletonTable rows={5} columns={4} />
        ) : q.isError ? (
          <EmptyState
            icon={<AlertOctagon size={20} />}
            title={t('supplier_catalogs.load_failed', { defaultValue: 'Could not load data' })}
            description={getErrorMessage(q.error)}
            action={{
              label: t('common.retry', { defaultValue: 'Retry' }),
              onClick: () => void q.refetch(),
            }}
          />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<Boxes size={20} />}
            title={t('supplier_catalogs.no_prices', { defaultValue: 'No vendor prices for this item' })}
            description={t('supplier_catalogs.no_prices_desc', {
              defaultValue: 'Import a price list against a vendor or add a catalog entry.',
            })}
          />
        ) : (
          <>
            {/* Money bug fix: when vendors quote in different ISO currencies we
                cannot rank them by raw number, so we suppress the "Cheapest"
                crown and tell the buyer the prices are not directly comparable. */}
            {!singleCurrency && rows.length > 1 && (
              <div className="mt-1 mb-3 flex items-start gap-2 rounded-lg border border-semantic-warning/40 bg-semantic-warning/10 px-3 py-2 text-xs text-content-secondary">
                <AlertOctagon size={14} className="mt-0.5 shrink-0 text-semantic-warning" />
                <span>
                  {t('supplier_catalogs.mixed_currencies', {
                    defaultValue:
                      'Vendors quote in different currencies — prices are not directly comparable, so no cheapest is highlighted.',
                  })}
                </span>
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {rows.map((r) => {
              const vendor = vendors.find((v) => v.id === r.vendor_id);
              const isCheapest = cheapest && cheapest.vendor_id === r.vendor_id && rows.length > 1;
              return (
                <div
                  key={r.vendor_id + r.price_list_id}
                  className={clsx(
                    'rounded-xl border bg-surface-primary p-4 transition-all',
                    isCheapest ? 'border-semantic-success ring-2 ring-semantic-success/30' : 'border-border-light',
                  )}
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="min-w-0">
                      <p className="text-xs font-mono text-content-tertiary">{r.vendor_code}</p>
                      <p className="font-semibold text-content-primary truncate">{r.vendor_name}</p>
                    </div>
                    {isCheapest && (
                      <Badge variant="success">
                        {t('supplier_catalogs.cheapest', { defaultValue: 'Cheapest' })}
                      </Badge>
                    )}
                  </div>
                  <div className="space-y-1.5">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-content-tertiary">
                        {t('supplier_catalogs.unit_price', { defaultValue: 'Unit price' })}
                      </p>
                      <p className="text-xl font-bold text-content-primary">
                        <MoneyDisplay amount={Number(r.unit_price)} currency={r.currency} />
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <p className="uppercase tracking-wide text-content-tertiary">
                          {t('supplier_catalogs.lead_time', { defaultValue: 'Lead time' })}
                        </p>
                        <p className="text-content-primary tabular-nums">{r.lead_time_days}d</p>
                      </div>
                      <div>
                        <p className="uppercase tracking-wide text-content-tertiary">
                          {t('supplier_catalogs.moq', { defaultValue: 'MOQ' })}
                        </p>
                        <p className="text-content-primary tabular-nums">{String(r.min_order_qty)}</p>
                      </div>
                    </div>
                    <div className="pt-1 border-t border-border-light">
                      <p className="text-xs uppercase tracking-wide text-content-tertiary">
                        {t('supplier_catalogs.rating', { defaultValue: 'Rating' })}
                      </p>
                      <StarRating rating={r.rating ?? vendor?.rating ?? null} />
                    </div>
                  </div>
                </div>
              );
              })}
            </div>
          </>
        )}
      </div>
    </WideModal>
  );
}

/* ── Create modal ──────────────────────────────────────────────────────── */

function CreateModal({
  kind,
  vendors,
  onClose,
}: {
  kind: Tab;
  vendors: Vendor[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [busy, setBusy] = useState(false);

  // Real project picker for PR/PO instead of a raw UUID textbox — far less
  // error-prone and matches every other project-scoped page.
  const projectsQ = useQuery({
    queryKey: ['sc', 'projects-lite'],
    queryFn: listProjectsLite,
    enabled: kind === 'prs' || kind === 'pos',
    staleTime: 60_000,
  });
  const projectOptions = projectsQ.data ?? [];

  const [vendorForm, setVendorForm] = useState({
    code: '',
    name: '',
    legal_name: '',
    currency: 'EUR',
    payment_terms_days: '30',
    country_code: '',
  });
  const [itemForm, setItemForm] = useState({
    sku: '',
    name: '',
    description: '',
    unit_of_measure: 'pcs',
    manufacturer: '',
  });
  const [prForm, setPrForm] = useState({
    project_id: '',
    currency: 'EUR',
    needed_by: '',
    lineDesc: '',
    lineQty: '1',
    linePrice: '0',
  });
  const [poForm, setPoForm] = useState({
    vendor_id: vendors[0]?.id || '',
    project_id: '',
    currency: 'EUR',
    expected_delivery: '',
    lineDesc: '',
    lineQty: '1',
    linePrice: '0',
  });
  const [warehouseForm, setWarehouseForm] = useState({ code: '', name: '', address: '' });

  const submit = async () => {
    setBusy(true);
    try {
      if (kind === 'vendors') {
        if (!vendorForm.code.trim() || !vendorForm.name.trim()) throw new Error('Code and name required');
        await createVendor({
          code: vendorForm.code,
          name: vendorForm.name,
          legal_name: vendorForm.legal_name || undefined,
          currency: vendorForm.currency || undefined,
          payment_terms_days: Number(vendorForm.payment_terms_days) || 30,
          country_code: vendorForm.country_code || undefined,
        });
        addToast({ type: 'success', title: t('supplier_catalogs.vendor_created', { defaultValue: 'Vendor created' }) });
        qc.invalidateQueries({ queryKey: ['sc', 'vendors'] });
      } else if (kind === 'catalog') {
        if (!itemForm.sku.trim() || !itemForm.name.trim()) throw new Error('SKU and name required');
        await createCatalogItem({
          sku: itemForm.sku,
          name: itemForm.name,
          description: itemForm.description || undefined,
          unit_of_measure: itemForm.unit_of_measure || 'pcs',
          manufacturer: itemForm.manufacturer || undefined,
        });
        addToast({ type: 'success', title: t('supplier_catalogs.item_created', { defaultValue: 'Item created' }) });
        qc.invalidateQueries({ queryKey: ['sc', 'items'] });
      } else if (kind === 'prs') {
        if (!prForm.project_id.trim()) throw new Error('Project ID required');
        if (!prForm.lineDesc.trim()) throw new Error('At least one line required');
        await createPR({
          project_id: prForm.project_id,
          currency: prForm.currency,
          needed_by: prForm.needed_by || undefined,
          lines: [
            {
              description: prForm.lineDesc,
              quantity: Number(prForm.lineQty) || 1,
              estimated_unit_price: Number(prForm.linePrice) || 0,
            },
          ],
        });
        addToast({ type: 'success', title: t('supplier_catalogs.pr_created', { defaultValue: 'Requisition created' }) });
      } else if (kind === 'pos') {
        if (!poForm.vendor_id || !poForm.project_id.trim()) throw new Error('Vendor and project required');
        if (!poForm.lineDesc.trim()) throw new Error('At least one line required');
        await createPO({
          vendor_id: poForm.vendor_id,
          project_id: poForm.project_id,
          currency: poForm.currency,
          expected_delivery: poForm.expected_delivery || undefined,
          lines: [
            {
              description: poForm.lineDesc,
              ordered_qty: Number(poForm.lineQty) || 1,
              unit_price: Number(poForm.linePrice) || 0,
            },
          ],
        });
        addToast({ type: 'success', title: t('supplier_catalogs.po_created', { defaultValue: 'PO created' }) });
      } else if (kind === 'warehouses') {
        if (!warehouseForm.code.trim() || !warehouseForm.name.trim()) throw new Error('Code and name required');
        await createWarehouse({
          code: warehouseForm.code,
          name: warehouseForm.name,
          address: warehouseForm.address || undefined,
        });
        addToast({ type: 'success', title: t('supplier_catalogs.warehouse_created', { defaultValue: 'Warehouse created' }) });
        qc.invalidateQueries({ queryKey: ['sc', 'warehouses'] });
      }
      onClose();
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  // PRs / POs have 4 header fields + 3-field line item — xl gives the
  // line-item row breathing room. Vendors/catalog/warehouses sit at lg.
  const size = kind === 'prs' || kind === 'pos' ? 'xl' : 'lg';

  return (
    <WideModal
      open
      onClose={onClose}
      title={createLabel(kind, t)}
      size={size}
      busy={busy}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          {kind !== 'match' && (
            <Button
              variant="primary"
              onClick={submit}
              loading={busy}
              icon={busy ? <Loader2 size={14} /> : <Plus size={14} />}
            >
              {t('common.create', { defaultValue: 'Create' })}
            </Button>
          )}
        </>
      }
    >
      {kind === 'vendors' && (
        <WideModalSection columns={2}>
          <WideModalField
            label={t('supplier_catalogs.code', { defaultValue: 'Code' })}
            required
          >
            <input
              value={vendorForm.code}
              onChange={(e) => setVendorForm({ ...vendorForm, code: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('supplier_catalogs.country', { defaultValue: 'Country' })}
          >
            <input
              value={vendorForm.country_code}
              onChange={(e) => setVendorForm({ ...vendorForm, country_code: e.target.value })}
              className={inputCls}
              maxLength={3}
              placeholder="DE / FR / US"
            />
          </WideModalField>
          <WideModalField
            label={t('supplier_catalogs.name', { defaultValue: 'Name' })}
            required
            span={2}
          >
            <input
              value={vendorForm.name}
              onChange={(e) => setVendorForm({ ...vendorForm, name: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('supplier_catalogs.legal_name', { defaultValue: 'Legal name' })}
            span={2}
          >
            <input
              value={vendorForm.legal_name}
              onChange={(e) => setVendorForm({ ...vendorForm, legal_name: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('common.currency', { defaultValue: 'Currency' })}
          >
            <input
              value={vendorForm.currency}
              onChange={(e) => setVendorForm({ ...vendorForm, currency: e.target.value })}
              className={inputCls}
              maxLength={3}
            />
          </WideModalField>
          <WideModalField
            label={t('supplier_catalogs.payment_terms', { defaultValue: 'Payment terms (days)' })}
          >
            <input
              type="number"
              value={vendorForm.payment_terms_days}
              onChange={(e) => setVendorForm({ ...vendorForm, payment_terms_days: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
        </WideModalSection>
      )}

      {kind === 'catalog' && (
        <WideModalSection columns={2}>
          <WideModalField
            label={t('supplier_catalogs.sku', { defaultValue: 'SKU' })}
            required
          >
            <input
              value={itemForm.sku}
              onChange={(e) => setItemForm({ ...itemForm, sku: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('supplier_catalogs.uom', { defaultValue: 'UoM' })}
          >
            <input
              value={itemForm.unit_of_measure}
              onChange={(e) => setItemForm({ ...itemForm, unit_of_measure: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('supplier_catalogs.name', { defaultValue: 'Name' })}
            required
            span={2}
          >
            <input
              value={itemForm.name}
              onChange={(e) => setItemForm({ ...itemForm, name: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('supplier_catalogs.description_field', { defaultValue: 'Description' })}
            span={2}
          >
            <textarea
              value={itemForm.description}
              onChange={(e) => setItemForm({ ...itemForm, description: e.target.value })}
              rows={2}
              className={clsx(inputCls, 'h-auto py-2')}
            />
          </WideModalField>
          <WideModalField
            label={t('supplier_catalogs.manufacturer', { defaultValue: 'Manufacturer' })}
            span={2}
          >
            <input
              value={itemForm.manufacturer}
              onChange={(e) => setItemForm({ ...itemForm, manufacturer: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
        </WideModalSection>
      )}

      {kind === 'prs' && (
        <>
          <WideModalSection
            title={t('supplier_catalogs.section_header', { defaultValue: 'Requisition' })}
            columns={3}
          >
            <WideModalField
              label={t('supplier_catalogs.project', { defaultValue: 'Project' })}
              required
              span={3}
            >
              <select
                value={prForm.project_id}
                onChange={(e) => setPrForm({ ...prForm, project_id: e.target.value })}
                className={inputCls}
              >
                <option value="">
                  — {t('common.select', { defaultValue: 'Select' })} —
                </option>
                {projectOptions.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </WideModalField>
            <WideModalField
              label={t('common.currency', { defaultValue: 'Currency' })}
            >
              <input
                value={prForm.currency}
                onChange={(e) => setPrForm({ ...prForm, currency: e.target.value })}
                className={inputCls}
                maxLength={3}
              />
            </WideModalField>
            <WideModalField
              label={t('supplier_catalogs.needed_by', { defaultValue: 'Needed by' })}
              span={2}
            >
              <input
                type="date"
                value={prForm.needed_by}
                onChange={(e) => setPrForm({ ...prForm, needed_by: e.target.value })}
                className={inputCls}
              />
            </WideModalField>
          </WideModalSection>
          <WideModalSection
            title={t('supplier_catalogs.first_line', { defaultValue: 'First line item' })}
            columns={3}
          >
            <WideModalField
              label={t('supplier_catalogs.line_description', { defaultValue: 'Description' })}
              span={3}
            >
              <input
                value={prForm.lineDesc}
                onChange={(e) => setPrForm({ ...prForm, lineDesc: e.target.value })}
                className={inputCls}
              />
            </WideModalField>
            <WideModalField label={t('supplier_catalogs.qty', { defaultValue: 'Quantity' })}>
              <input
                type="number"
                value={prForm.lineQty}
                onChange={(e) => setPrForm({ ...prForm, lineQty: e.target.value })}
                className={inputCls}
              />
            </WideModalField>
            <WideModalField
              label={t('supplier_catalogs.est_price', { defaultValue: 'Est. price' })}
              span={2}
            >
              <input
                type="number"
                value={prForm.linePrice}
                onChange={(e) => setPrForm({ ...prForm, linePrice: e.target.value })}
                className={inputCls}
              />
            </WideModalField>
          </WideModalSection>
        </>
      )}

      {kind === 'pos' && (
        <>
          <WideModalSection
            title={t('supplier_catalogs.section_header', { defaultValue: 'Order' })}
            columns={2}
          >
            <WideModalField
              label={t('supplier_catalogs.vendor', { defaultValue: 'Vendor' })}
              required
            >
              <select
                value={poForm.vendor_id}
                onChange={(e) => setPoForm({ ...poForm, vendor_id: e.target.value })}
                className={inputCls}
              >
                <option value="">—</option>
                {vendors.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.code} — {v.name}
                  </option>
                ))}
              </select>
            </WideModalField>
            <WideModalField
              label={t('supplier_catalogs.project', { defaultValue: 'Project' })}
              required
            >
              <select
                value={poForm.project_id}
                onChange={(e) => setPoForm({ ...poForm, project_id: e.target.value })}
                className={inputCls}
              >
                <option value="">
                  — {t('common.select', { defaultValue: 'Select' })} —
                </option>
                {projectOptions.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </WideModalField>
            <WideModalField
              label={t('common.currency', { defaultValue: 'Currency' })}
            >
              <input
                value={poForm.currency}
                onChange={(e) => setPoForm({ ...poForm, currency: e.target.value })}
                className={inputCls}
                maxLength={3}
              />
            </WideModalField>
            <WideModalField
              label={t('supplier_catalogs.expected_delivery', { defaultValue: 'Expected' })}
            >
              <input
                type="date"
                value={poForm.expected_delivery}
                onChange={(e) => setPoForm({ ...poForm, expected_delivery: e.target.value })}
                className={inputCls}
              />
            </WideModalField>
          </WideModalSection>
          <WideModalSection
            title={t('supplier_catalogs.first_line', { defaultValue: 'First line item' })}
            columns={3}
          >
            <WideModalField
              label={t('supplier_catalogs.line_description', { defaultValue: 'Description' })}
              span={3}
            >
              <input
                value={poForm.lineDesc}
                onChange={(e) => setPoForm({ ...poForm, lineDesc: e.target.value })}
                className={inputCls}
              />
            </WideModalField>
            <WideModalField label={t('supplier_catalogs.qty', { defaultValue: 'Quantity' })}>
              <input
                type="number"
                value={poForm.lineQty}
                onChange={(e) => setPoForm({ ...poForm, lineQty: e.target.value })}
                className={inputCls}
              />
            </WideModalField>
            <WideModalField
              label={t('supplier_catalogs.unit_price', { defaultValue: 'Unit price' })}
              span={2}
            >
              <input
                type="number"
                value={poForm.linePrice}
                onChange={(e) => setPoForm({ ...poForm, linePrice: e.target.value })}
                className={inputCls}
              />
            </WideModalField>
          </WideModalSection>
        </>
      )}

      {kind === 'warehouses' && (
        <WideModalSection columns={2}>
          <WideModalField
            label={t('supplier_catalogs.code', { defaultValue: 'Code' })}
            required
          >
            <input
              value={warehouseForm.code}
              onChange={(e) => setWarehouseForm({ ...warehouseForm, code: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('supplier_catalogs.name', { defaultValue: 'Name' })}
            required
          >
            <input
              value={warehouseForm.name}
              onChange={(e) => setWarehouseForm({ ...warehouseForm, name: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('supplier_catalogs.address', { defaultValue: 'Address' })}
            span={2}
          >
            <textarea
              value={warehouseForm.address}
              onChange={(e) => setWarehouseForm({ ...warehouseForm, address: e.target.value })}
              rows={2}
              className={clsx(inputCls, 'h-auto py-2')}
            />
          </WideModalField>
        </WideModalSection>
      )}

      {kind === 'match' && (
        <div className="text-sm text-content-secondary">
          {t('supplier_catalogs.match_create_hint', {
            defaultValue:
              'Three-way match runs automatically when a vendor invoice is posted against a PO and GR.',
          })}
        </div>
      )}
    </WideModal>
  );
}

