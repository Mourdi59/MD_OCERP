// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { lazy } from 'react';
import { BarChart3 } from 'lucide-react';
import type { ModuleManifest } from '../_types';

const BenchmarkModule = lazy(() => import('./BenchmarkModule'));

export const manifest: ModuleManifest = {
  id: 'cost-benchmark',
  // `nav.benchmarks` rather than a key of this module's own: the locale files
  // already carry it in every language, and it names the same destination as
  // the sidebar row and the page heading.
  name: 'nav.benchmarks',
  description: 'modules.cost_benchmark.description',
  version: '1.0.0',
  icon: BarChart3,
  category: 'tools',
  defaultEnabled: true,
  depends: ['costs'],
  routes: [
    {
      path: '/benchmarks',
      title: 'nav.benchmarks',
      component: BenchmarkModule,
    },
  ],
  // navItems intentionally empty. The /benchmarks row already lives in the
  // sidebar as a static entry in the grp_cost_data group (Sidebar.tsx), gated
  // by moduleKey 'cost-benchmark' and advancedOnly. The sidebar only pulls
  // dynamic module navItems for its static group ids (grp_*, regional), never
  // for the legacy 'tools' group string a manifest would declare here, so an
  // entry would either render nowhere or duplicate the existing nav source.
  navItems: [],
  translations: {
    en: {
      'modules.cost_benchmark.description':
        'Compare cost per square metre against reference projects and percentile bands.',
    },
    de: {
      'modules.cost_benchmark.description':
        'Kosten je Quadratmeter mit Referenzprojekten und Perzentilbändern vergleichen.',
    },
    fr: {
      'modules.cost_benchmark.description': 'Comparez le coût au mètre carré avec des projets de référence et des bandes de percentile.',
    },
    es: {
      'modules.cost_benchmark.description': 'Compare el coste por metro cuadrado con proyectos de referencia y bandas de percentil.',
    },
    'es-MX': {
      'modules.cost_benchmark.description': 'Compare el costo por metro cuadrado con proyectos de referencia y bandas de percentil.',
    },
    'es-CL': {
      'modules.cost_benchmark.description': 'Compare el costo por metro cuadrado con proyectos de referencia y bandas de percentil.',
    },
    'es-CO': {
      'modules.cost_benchmark.description': 'Compare el costo por metro cuadrado con proyectos de referencia y bandas de percentil.',
    },
    pt: {
      'modules.cost_benchmark.description': 'Compare o custo por metro quadrado com projetos de referência e bandas percentuais.',
    },
    'pt-BR': {
      'modules.cost_benchmark.description': 'Compare o custo por metro quadrado com projetos de referência e faixas percentuais.',
    },
    ru: {
      'modules.cost_benchmark.description': 'Сравнивайте стоимость на квадратный метр с эталонными проектами и процентильными диапазонами.',
    },
    zh: {
      'modules.cost_benchmark.description': '将每平方米造价与参考项目及百分位区间进行对比。',
    },
    ar: {
      'modules.cost_benchmark.description': 'قارن التكلفة لكل متر مربع مع مشاريع مرجعية ونطاقات مئينية.',
    },
    hi: {
      'modules.cost_benchmark.description': 'प्रति वर्ग मीटर लागत की तुलना संदर्भ परियोजनाओं और प्रतिशतक बैंडों से करें।',
    },
    tr: {
      'modules.cost_benchmark.description': 'Metrekare başına maliyeti referans projelerle ve yüzdelik bantlarla karşılaştırın.',
    },
    it: {
      'modules.cost_benchmark.description': 'Confronta il costo al metro quadro con progetti di riferimento e fasce percentili.',
    },
    nl: {
      'modules.cost_benchmark.description': 'Vergelijk de kosten per vierkante meter met referentieprojecten en percentielbanden.',
    },
    pl: {
      'modules.cost_benchmark.description': 'Porównuj koszt za metr kwadratowy z projektami referencyjnymi i przedziałami percentylowymi.',
    },
    cs: {
      'modules.cost_benchmark.description': 'Porovnávejte náklady na metr čtvereční s referenčními projekty a percentilovými pásmy.',
    },
    ja: {
      'modules.cost_benchmark.description': '平米単価を参考プロジェクトやパーセンタイル帯と比較します。',
    },
    ko: {
      'modules.cost_benchmark.description': '제곱미터당 원가를 참조 프로젝트 및 백분위 구간과 비교합니다.',
    },
    sv: {
      'modules.cost_benchmark.description': 'Jämför kostnad per kvadratmeter med referensprojekt och percentilband.',
    },
    no: {
      'modules.cost_benchmark.description': 'Sammenlign kostnad per kvadratmeter med referanseprosjekter og persentilbånd.',
    },
    da: {
      'modules.cost_benchmark.description': 'Sammenlign omkostning pr. kvadratmeter med referenceprojekter og percentilbånd.',
    },
    fi: {
      'modules.cost_benchmark.description': 'Vertaa neliöhintaa vertailukohteisiin ja prosenttipistevälistöihin.',
    },
    bg: {
      'modules.cost_benchmark.description': 'Сравнявайте разхода на квадратен метър с еталонни проекти и процентилни диапазони.',
    },
    hr: {
      'modules.cost_benchmark.description': 'Uspoređujte trošak po kvadratnom metru s referentnim projektima i percentilnim rasponima.',
    },
    id: {
      'modules.cost_benchmark.description': 'Bandingkan biaya per meter persegi dengan proyek referensi dan pita persentil.',
    },
    ro: {
      'modules.cost_benchmark.description': 'Comparați costul pe metru pătrat cu proiecte de referință și benzi percentile.',
    },
    th: {
      'modules.cost_benchmark.description': 'เปรียบเทียบต้นทุนต่อตารางเมตรกับโครงการอ้างอิงและช่วงเปอร์เซ็นไทล์',
    },
    vi: {
      'modules.cost_benchmark.description': 'So sánh chi phí trên mỗi mét vuông với các dự án tham chiếu và các dải phân vị.',
    },
    ky: {
      'modules.cost_benchmark.description': 'Бир чарчы метрдин наркын эталондук долбоорлор жана процентилдик диапазондор менен салыштырыңыз.',
    },
    et: {
      'modules.cost_benchmark.description': 'Võrrelge ruutmeetri maksumust võrdlusprojektide ja protsentiilivahemikega.',
    },
    bn: {
      'modules.cost_benchmark.description': 'প্রতি বর্গমিটার খরচ রেফারেন্স প্রকল্প ও পার্সেন্টাইল ব্যান্ডের সাথে তুলনা করুন।',
    },
    kk: {
      'modules.cost_benchmark.description': 'Бір шаршы метрдің құнын эталондық жобалармен және процентильдік диапазондармен салыстырыңыз.',
    },
    fil: {
      'modules.cost_benchmark.description': 'Ihambing ang gastos kada metro kuwadrado sa mga reference project at percentile band.',
    },
    ur: {
      'modules.cost_benchmark.description': 'فی مربع میٹر لاگت کا موازنہ حوالہ منصوبوں اور پرسنٹائل بینڈز سے کریں۔',
    },
    fa: {
      'modules.cost_benchmark.description': 'هزینه هر متر مربع را با پروژههای مرجع و باندهای صدک مقایسه کنید.',
    },
    he: {
      'modules.cost_benchmark.description': 'השוו עלות למ"ר מול פרויקטים ייחוסיים ורצועות אחוזון.',
    },
    el: {
      'modules.cost_benchmark.description': 'Συγκρίνετε το κόστος ανά τετραγωνικό μέτρο με έργα αναφοράς και ζώνες εκατοστημορίων.',
    },
  },
};
