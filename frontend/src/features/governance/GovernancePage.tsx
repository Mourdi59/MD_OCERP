// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// GovernancePage — one home for the three platform-governance surfaces
// that used to live as standalone admin pages:
//
//   • Permissions      ← PermissionsMatrixPage  (was /admin/permissions)
//   • Approval Routes   ← ApprovalRoutesPage      (was /approval-routes)
//   • Validation Rules  ← ValidationRulesSettingsPage (was /admin/validation-rules)
//
// The three pages are mounted verbatim as tab panels — no logic is
// duplicated here. The active tab is driven by a `?tab=` query param
// (permissions | approvals | validation, default permissions) so each
// tab is deep-linkable and the browser back/forward buttons move
// between tabs. The old standalone routes redirect here preserving the
// right tab (see App.tsx).
//
// The tab strip intentionally reuses the exact look of the /modules
// page tab bar (ModulesPage): a `bg-surface-secondary` pill rail with
// equal-width `flex-1` buttons that lift to `bg-surface-elevated` when
// active. Keyboard navigation follows the WAI-ARIA "tabs" pattern via
// the shared `useTabKeyboardNav` hook — same wiring ModulesPage uses.

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import clsx from 'clsx';
import { ScrollText, ShieldCheck, Workflow, type LucideIcon } from 'lucide-react';
import { Breadcrumb } from '@/shared/ui';
import { useTabKeyboardNav } from '@/shared/hooks/useTabKeyboardNav';
import { PermissionsMatrixPage } from '@/features/admin/PermissionsMatrixPage';
import { ApprovalRoutesPage } from '@/features/approval-routes';
import { ValidationRulesSettingsPage } from '@/features/property-dev';

/* ── Tab definitions ───────────────────────────────────────────────────── */

const GOVERNANCE_TAB_IDS = ['permissions', 'approvals', 'validation'] as const;
type TabKey = (typeof GOVERNANCE_TAB_IDS)[number];

const DEFAULT_TAB: TabKey = 'permissions';

const TABS: { key: TabKey; labelKey: string; defaultLabel: string; icon: LucideIcon }[] = [
  {
    key: 'permissions',
    labelKey: 'governance.tab_permissions',
    defaultLabel: 'Permissions',
    icon: ShieldCheck,
  },
  {
    key: 'approvals',
    labelKey: 'governance.tab_approvals',
    defaultLabel: 'Approval Routes',
    icon: Workflow,
  },
  {
    key: 'validation',
    labelKey: 'governance.tab_validation',
    defaultLabel: 'Validation Rules',
    icon: ScrollText,
  },
];

function isTabKey(value: string | null): value is TabKey {
  return value !== null && (GOVERNANCE_TAB_IDS as readonly string[]).includes(value);
}

/* ── Page ──────────────────────────────────────────────────────────────── */

export function GovernancePage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  // The query param is the single source of truth for the active tab,
  // so the URL is deep-linkable and browser back/forward swap tabs.
  // An unknown / missing value falls back to Permissions.
  const rawTab = searchParams.get('tab');
  const activeTab: TabKey = isTabKey(rawTab) ? rawTab : DEFAULT_TAB;

  const setActiveTab = useMemo(
    () => (next: TabKey) => {
      const params = new URLSearchParams(searchParams);
      params.set('tab', next);
      // Push (not replace) so each tab switch is its own history entry —
      // Back returns to the previously viewed tab.
      setSearchParams(params);
    },
    [searchParams, setSearchParams],
  );

  const onTabKeyDown = useTabKeyboardNav<TabKey>({
    ids: GOVERNANCE_TAB_IDS,
    activeId: activeTab,
    onChange: setActiveTab,
    orientation: 'horizontal',
  });

  return (
    <div className="w-full animate-fade-in">
      <Breadcrumb
        items={[
          {
            label: t('sidebar.admin_grid.governance', { defaultValue: 'Governance' }),
          },
        ]}
        className="mb-4"
      />

      {/* Header */}
      <div className="mb-6 animate-card-in">
        <h1 className="text-2xl font-bold text-content-primary">
          {t('governance.title', { defaultValue: 'Governance' })}
        </h1>
        <p className="mt-1 text-sm text-content-secondary">
          {t('governance.subtitle', {
            defaultValue:
              'Roles & permissions, approval routes, and validation rules — in one place.',
          })}
        </p>
      </div>

      {/* Tab bar — identical look to the /modules page tab strip. */}
      <div
        className="mb-6 flex gap-1 rounded-lg bg-surface-secondary p-1 animate-card-in"
        role="tablist"
        aria-label={t('governance.tabs', { defaultValue: 'Governance sections' })}
        onKeyDown={onTabKeyDown}
        style={{ animationDelay: '30ms' }}
      >
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              role="tab"
              id={`governance-tab-${tab.key}`}
              aria-selected={isActive}
              aria-controls={`governance-panel-${tab.key}`}
              tabIndex={isActive ? 0 : -1}
              className={clsx(
                'flex-1 inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all duration-fast',
                isActive
                  ? 'bg-surface-elevated text-content-primary shadow-xs'
                  : 'text-content-secondary hover:text-content-primary',
              )}
            >
              <Icon size={16} />
              {t(tab.labelKey, { defaultValue: tab.defaultLabel })}
            </button>
          );
        })}
      </div>

      {/* Tab content — each existing page mounted verbatim as a panel. */}
      <div
        role="tabpanel"
        id={`governance-panel-${activeTab}`}
        aria-labelledby={`governance-tab-${activeTab}`}
      >
        {activeTab === 'permissions' && <PermissionsMatrixPage />}
        {activeTab === 'approvals' && <ApprovalRoutesPage />}
        {activeTab === 'validation' && <ValidationRulesSettingsPage />}
      </div>
    </div>
  );
}
