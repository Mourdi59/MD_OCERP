// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { lazy } from 'react';
import { Leaf } from 'lucide-react';
import type { ModuleManifest } from '../_types';

const SustainabilityPage = lazy(() =>
  import('@/features/sustainability/SustainabilityPage').then((m) => ({
    default: m.SustainabilityPage,
  })),
);

// build ref: ddc-lineage:a17f93c4-sustain-01
export const manifest: ModuleManifest = {
  id: 'sustainability',
  // `nav.sustainability` rather than a key of this module's own: the locale
  // files already carry it in every language, and it is the same word the
  // sidebar row uses for the same destination.
  name: 'nav.sustainability',
  description: 'modules.sustainability.description',
  version: '1.0.0',
  icon: Leaf,
  category: 'tools',
  defaultEnabled: true,
  depends: ['boq'],
  routes: [
    {
      path: '/sustainability',
      title: 'nav.sustainability',
      component: SustainabilityPage,
    },
  ],
  navItems: [
    {
      labelKey: 'nav.sustainability',
      to: '/sustainability',
      icon: Leaf,
      group: 'tools',
      advancedOnly: true,
    },
  ],
  translations: {
    en: {
      'modules.sustainability.description':
        'Carbon and EPD data on BOQ positions, with a life-cycle view of the estimate.',
      'sustainability.epd_data': 'EPD Data',
      'sustainability.carbon_budget': 'Carbon Budget',
      'sustainability.lifecycle_phase': 'Life Cycle Phase',
    },
    de: {
      'modules.sustainability.description':
        'CO₂- und EPD-Daten an den LV-Positionen, mit Lebenszyklussicht auf die Kalkulation.',
      'sustainability.epd_data': 'EPD-Daten',
      'sustainability.carbon_budget': 'CO₂-Budget',
      'sustainability.lifecycle_phase': 'Lebenszyklusphase',
    },
    es: {
      'modules.sustainability.description': 'Datos de carbono y EPD en las partidas del presupuesto, con una vista del ciclo de vida de la estimación.',
    },
    'es-MX': {
      'modules.sustainability.description': 'Datos de carbono y EPD en las partidas del presupuesto, con una vista del ciclo de vida de la estimación.',
    },
    'es-CL': {
      'modules.sustainability.description': 'Datos de carbono y EPD en las partidas del presupuesto, con una vista del ciclo de vida de la estimación.',
    },
    'es-CO': {
      'modules.sustainability.description': 'Datos de carbono y EPD en los renglones del presupuesto, con una vista del ciclo de vida de la estimación.',
    },
    pt: {
      'modules.sustainability.description': 'Dados de carbono e EPD nos itens da planilha orçamentária, com uma vista do ciclo de vida do orçamento.',
    },
    'pt-BR': {
      'modules.sustainability.description': 'Dados de carbono e EPD nos itens da planilha orçamentária, com uma visão do ciclo de vida do orçamento.',
    },
    zh: {
      'modules.sustainability.description': '工程量清单项上的碳排放和 EPD 数据，提供估算的全生命周期视图。',
    },
    ar: {
      'modules.sustainability.description': 'بيانات الكربون وEPD على بنود جدول الكميات، مع عرض لدورة حياة التقدير.',
    },
    hi: {
      'modules.sustainability.description': 'मात्रा विवरण की मदों पर कार्बन और EPD डेटा, अनुमान के जीवन-चक्र दृश्य के साथ।',
    },
    tr: {
      'modules.sustainability.description': 'Keşif kalemleri üzerinde karbon ve EPD verileri, tahminin yaşam döngüsü görünümüyle birlikte.',
    },
    it: {
      'modules.sustainability.description': 'Dati di carbonio ed EPD sulle voci del computo, con una vista del ciclo di vita della stima.',
    },
    nl: {
      'modules.sustainability.description': 'Koolstof- en EPD-gegevens op ramingsposten, met een levenscyclusweergave van de raming.',
    },
    pl: {
      'modules.sustainability.description': 'Dane o śladzie węglowym i EPD na pozycjach kosztorysu, wraz z widokiem cyklu życia kosztorysu.',
    },
    cs: {
      'modules.sustainability.description': 'Data o uhlíkové stopě a EPD u položek rozpočtu, s pohledem na životní cyklus kalkulace.',
    },
    ja: {
      'modules.sustainability.description': '数量明細項目の炭素排出量とEPDデータ、積算のライフサイクル表示。',
    },
    ko: {
      'modules.sustainability.description': '내역서 항목에 대한 탄소 및 EPD 데이터와 견적의 생애주기 관점.',
    },
    sv: {
      'modules.sustainability.description': 'Koldioxid- och EPD-data på poster i mängdförteckningen, med en livscykelvy av kalkylen.',
    },
    no: {
      'modules.sustainability.description': 'Karbon- og EPD-data på poster i mengdefortegnelsen, med en livssyklusvisning av kalkylen.',
    },
    da: {
      'modules.sustainability.description': 'CO2- og EPD-data på poster i tilbudslisten, med et livscyklusoverblik over kalkulationen.',
    },
    fi: {
      'modules.sustainability.description': 'Hiili- ja EPD-tiedot määräluettelon riveillä sekä arvion elinkaarinäkymä.',
    },
    bg: {
      'modules.sustainability.description': 'Данни за въглероден отпечатък и EPD върху позициите от количествената сметка, с изглед на жизнения цикъл на сметния разчет.',
    },
    hr: {
      'modules.sustainability.description': 'Podaci o ugljiku i EPD na stavkama troškovnika, s prikazom životnog ciklusa procjene.',
    },
    id: {
      'modules.sustainability.description': 'Data karbon dan EPD pada item daftar kuantitas, dengan tampilan siklus hidup estimasi.',
    },
    ro: {
      'modules.sustainability.description': 'Date privind carbonul și EPD la nivelul pozițiilor din listă, cu o imagine asupra ciclului de viață al devizului.',
    },
    th: {
      'modules.sustainability.description': 'ข้อมูลคาร์บอนและ EPD บนรายการปริมาณงาน พร้อมมุมมองวงจรชีวิตของการประมาณราคา',
    },
    vi: {
      'modules.sustainability.description': 'Dữ liệu carbon và EPD trên các hạng mục bảng khối lượng, cùng góc nhìn vòng đời của dự toán.',
    },
    ky: {
      'modules.sustainability.description': 'Смета позицияларындагы көмүртек жана EPD дайындары, сметанын жашоо циклинин көрүнүшү менен.',
    },
    et: {
      'modules.sustainability.description': 'Süsiniku- ja EPD-andmed mahutabeli ridadel koos hinnangu elutsükli vaatega.',
    },
    bn: {
      'modules.sustainability.description': 'বিল অফ কোয়ান্টিটিজের আইটেমে কার্বন ও EPD ডেটা, এস্টিমেটের লাইফ-সাইকেল দৃশ্যসহ।',
    },
    kk: {
      'modules.sustainability.description': 'Көлемдер ведомостісінің позицияларындағы көміртек және EPD деректері, сметаның өмірлік циклін көрсетумен бірге.',
    },
    fil: {
      'modules.sustainability.description': 'Datos ng carbon at EPD sa mga item ng BOQ, may tanaw sa buhay-siklo ng estimate.',
    },
    ur: {
      'modules.sustainability.description': 'مقدار کے بل کی مدوں پر کاربن اور EPD ڈیٹا، تخمینے کے لائف سائیکل منظر کے ساتھ۔',
    },
    fa: {
      'modules.sustainability.description': 'دادههای کربن و EPD روی ردیفهای صورت مقادیر، همراه با نمای چرخه عمر برآورد.',
    },
    he: {
      'modules.sustainability.description': 'נתוני פחמן ו-EPD על סעיפי כתב הכמויות, עם תצוגת מחזור חיים של האומדן.',
    },
    el: {
      'modules.sustainability.description': 'Δεδομένα άνθρακα και EPD στα άρθρα του τιμολογίου προσφοράς, με προβολή του κύκλου ζωής της εκτίμησης.',
    },
    fr: {
      'modules.sustainability.description': 'Données carbone et EPD sur les postes du devis, avec une vue du cycle de vie de l\'estimation.',
      'sustainability.epd_data': 'Données EPD',
      'sustainability.carbon_budget': 'Budget carbone',
      'sustainability.lifecycle_phase': 'Phase du cycle de vie',
    },
    ru: {
      'modules.sustainability.description': 'Данные об углеродном следе и EPD на позициях ВОР, с обзором жизненного цикла сметы.',
      'sustainability.epd_data': 'Данные EPD',
      'sustainability.carbon_budget': 'Углеродный бюджет',
      'sustainability.lifecycle_phase': 'Фаза жизненного цикла',
    },
  },
};
