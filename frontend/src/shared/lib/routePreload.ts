// Hover-intent chunk preloader: when the user hovers a sidebar nav item,
// we fire the dynamic import() for that route's page component so the
// chunk is already in the browser cache by the time they click.
//
// Keys must match navCatalog `to:` values exactly. The import() call is
// idempotent — the bundler caches the module after the first resolve.

const preloaders: Record<string, () => void> = {
  // ── Estimation & BOQ ──
  '/boq': () => void import('@/features/boq/BOQEditorPage'),
  '/takeoff': () => void import('@/features/takeoff/TakeoffPage'),
  '/dwg-takeoff': () => void import('@/features/dwg-takeoff/DwgTakeoffPage'),
  '/catalog': () => void import('@/features/catalog/CatalogPage'),
  '/norm-expansion': () => void import('@/features/norm-expansion/NormExpansionPage'),
  '/labor-rates': () => void import('@/features/labor-rates/LaborRatesPage'),
  '/waste-factors': () => void import('@/features/waste-factors/WasteFactorsPage'),
  '/price-index': () => void import('@/features/price-index/PriceIndexPage'),
  '/resource-summary': () => void import('@/features/resource-summary/ResourceSummaryPage'),
  '/cost-match': () => void import('@/features/cost-match'),
  '/supplier-catalogs': () => void import('@/features/supplier-catalogs'),

  // ── Schedule & Planning ──
  '/schedule': () => void import('@/features/schedule/SchedulePage'),
  '/schedule-advanced': () => void import('@/features/schedule-advanced'),
  '/deadlines': () => void import('@/features/deadlines/DeadlinesPage'),
  '/resources': () => void import('@/features/resources'),

  // ── BIM & CAD ──
  '/bim': () => void import('@/features/bim/BIMPage'),
  '/data-explorer': () => void import('@/features/cad-explorer/CadDataExplorerPage'),
  '/pointcloud': () => void import('@/features/pointcloud/PointCloudPage'),
  '/model-review': () => void import('@/features/bim/ModelReviewPage'),
  '/clash': () => void import('@/features/clash/ClashDetectionPage'),
  '/bcf': () => void import('@/features/bcf/BcfPage'),
  '/coordination': () => void import('@/features/coordination/CoordinationHubPage'),
  '/match-elements': () => void import('@/features/match-elements/MatchElementsPage'),
  '/geo': () => void import('@/features/geo-hub'),

  // ── Documents & Files ──
  '/files': () => void import('@/features/file-manager/FileManagerPage'),
  '/cde': () => void import('@/features/cde/CDEPage'),
  '/transmittals': () => void import('@/features/transmittals/TransmittalsPage'),
  '/markups': () => void import('@/features/markups/MarkupsPage'),
  '/plan-room': () => void import('@/features/plan-room/PlanRoomPage'),

  // ── Commercial & Finance ──
  '/finance': () => void import('@/features/finance/FinancePage'),
  '/contracts': () => void import('@/features/contracts'),
  '/tendering': () => void import('@/features/tendering/TenderingPage'),
  '/bid-management': () => void import('@/features/bid-management'),
  '/procurement': () => void import('@/features/procurement/ProcurementPage'),
  '/postcalc': () => void import('@/features/postcalc/PostCalcPage'),
  '/variations': () => void import('@/features/variations'),
  '/changeorders': () => void import('@/features/changeorders/ChangeOrdersPage'),
  '/payment-clock': () => void import('@/features/payment-clock'),
  '/tax-withholding': () => void import('@/features/tax-withholding'),
  '/tax-rates': () => void import('@/features/tax-rates'),
  '/full-evm': () => void import('@/features/full-evm'),
  '/fx': () => void import('@/features/fx'),
  '/change-intelligence': () => void import('@/features/change-intelligence'),
  '/claims-evidence': () => void import('@/features/claims-evidence'),
  '/value': () => void import('@/features/value'),
  '/reconciliation': () => void import('@/features/reconciliation'),

  // ── Field & Site ──
  '/field-reports': () => void import('@/features/fieldreports/FieldReportsPage'),
  '/field-time': () => void import('@/features/field-time'),
  '/daily-diary': () => void import('@/features/daily-diary'),
  '/safety': () => void import('@/features/safety/SafetyPage'),
  '/hse-advanced': () => void import('@/features/hse-advanced'),
  '/site-supervision': () => void import('@/features/site-supervision/SiteSupervisionPage'),
  '/site-prep': () => void import('@/features/site-prep/SitePrepPage'),
  '/site-inventory': () => void import('@/features/site-inventory/SiteInventoryPage'),
  '/temporary-works': () => void import('@/features/temporary-works/TemporaryWorksPage'),
  '/inspections': () => void import('@/features/inspections/InspectionsPage'),
  '/construction-control': () => void import('@/features/construction_control'),
  '/punchlist': () => void import('@/features/punchlist/PunchListPage'),
  '/ncr': () => void import('@/features/ncr/NCRPage'),
  '/moc': () => void import('@/features/moc/MoCPage'),
  '/defects-liability': () => void import('@/features/defects-liability'),
  '/commissioning': () => void import('@/features/commissioning/CommissioningPage'),
  '/closeout': () => void import('@/features/closeout/CloseoutPage'),

  // ── Communication & Collaboration ──
  '/correspondence': () => void import('@/features/correspondence/CorrespondencePage'),
  '/rfi': () => void import('@/features/rfi/RFIPage'),
  '/submittals': () => void import('@/features/submittals/SubmittalsPage'),
  '/meetings': () => void import('@/features/meetings/MeetingsPage'),
  '/inbox': () => void import('@/features/inbox'),
  '/contacts': () => void import('@/features/contacts/ContactsPage'),
  '/tasks': () => void import('@/features/tasks/TasksPage'),
  '/signing': () => void import('@/features/signing/SigningPage'),

  // ── Analytics & Reports ──
  '/analytics': () => void import('@/features/analytics/AnalyticsPage'),
  '/reports': () => void import('@/features/reports/ReportsPage'),
  '/reporting': () => void import('@/features/reporting/ReportingPage'),
  '/risks': () => void import('@/features/risk/RiskRegisterPage'),
  '/progress': () => void import('@/features/progress/ProgressPage'),
  '/project-controls': () => void import('@/features/project-controls'),
  '/bi-dashboards': () => void import('@/features/bi-dashboards'),

  // ── Portfolio & Management ──
  '/portfolio': () => void import('@/features/portfolio'),
  '/subcontractors': () => void import('@/features/subcontractors'),
  '/equipment': () => void import('@/features/equipment'),
  '/payroll': () => void import('@/features/payroll/PayrollPage'),
  '/crm': () => void import('@/features/crm'),
  '/carbon': () => void import('@/features/carbon'),
  '/accommodation': () => void import('@/features/accommodation'),
  '/property-dev': () => void import('@/features/property-dev'),
  '/interface-management': () => void import('@/features/interface-management'),
  '/service': () => void import('@/features/service'),
  '/connectors': () => void import('@/features/connectors'),
  '/inbound': () => void import('@/features/inbound'),
  '/inbound-email': () => void import('@/features/inbound-email'),
  '/source-data': () => void import('@/features/source-data/SourceDataPage'),
  '/project-route': () => void import('@/features/project-route/ProjectRoutePage'),
  '/authority-submissions': () => void import('@/features/authority-submission/AuthoritySubmissionPage'),
  '/review-authority': () => void import('@/features/review-authority/ReviewAuthorityPage'),
  '/qms': () => void import('@/features/qms'),

  // ── AI & Tools ──
  '/advisor': () => void import('@/features/ai/AdvisorPage'),
  '/chat': () => void import('@/features/erp-chat/full-page/ChatFullPage'),
  '/module-builder': () => void import('@/features/module-builder/ModuleBuilderPage'),
  '/pipelines': () => void import('@/features/pipelines/PipelinesPage'),

  // ── Admin ──
  '/settings': () => void import('@/features/settings/SettingsPage'),
  '/governance': () => void import('@/features/governance'),
};

// Debounce: only preload if the pointer stays on the item for 80ms.
// This avoids firing imports when the user scrolls past many items.
const timers = new Map<string, ReturnType<typeof setTimeout>>();

export function preloadRouteOnHover(path: string): void {
  // Strip query params — navCatalog items like '/boq?tab=templates'
  // should match the '/boq' preloader.
  const qIdx = path.indexOf('?');
  const base = qIdx === -1 ? path : path.slice(0, qIdx);
  const loader = preloaders[base];
  if (!loader) return;
  if (timers.has(base)) return; // already scheduled
  timers.set(
    base,
    setTimeout(() => {
      timers.delete(base);
      loader();
    }, 80),
  );
}

export function cancelRoutePreload(path: string): void {
  const qIdx = path.indexOf('?');
  const base = qIdx === -1 ? path : path.slice(0, qIdx);
  const t = timers.get(base);
  if (t != null) {
    clearTimeout(t);
    timers.delete(base);
  }
}
