// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { lazy } from 'react';
import { Workflow } from 'lucide-react';
import type { ModuleManifest } from '../_types';

/**
 * Pipeline Builder — visual node-graph automation editor (BETA, Phase 1).
 *
 * Cloned from the EAC block-editor stack (`@xyflow/react` v12) — no new
 * dependency. Route `/pipelines`, advanced-only, registered via the central
 * registry (no `App.tsx` / `Sidebar.tsx` edit — routes resolve through
 * `useModuleRouteElements`, the sidebar nav item through `getModuleNavItems`).
 *
 * NOTE: the shared `ModuleNavItem` contract only carries
 * `labelKey/to/icon/group/advancedOnly`, and the Sidebar derives the module
 * id from `labelKey.split('.')[1]` — so the labelKey is `nav.pipelines` to
 * resolve `isModuleEnabled('pipelines')`. The requested `badge:'BETA'` and
 * `data-tour="pipelines"` are not part of that contract; the BETA label is
 * surfaced in the page itself and `data-tour="pipelines"` is set on the page
 * root for onboarding instead.
 */
export const manifest: ModuleManifest = {
  id: 'pipelines',
  name: 'nav.pipelines',
  description: 'modules.pipelines.description',
  version: '0.1.0',
  icon: Workflow,
  category: 'tools',
  // Enabled by default so the statically-listed "Pipeline Builder" sidebar
  // entry (Automation & AI group, advanced-only) resolves to a mounted
  // route. `useModuleRouteElements` only mounts a module's routes when
  // `isModuleEnabled(id)` is true; with this false the nav link 404'd (the
  // sidebar item is NOT gated by module-enabled, so the link showed while
  // the route was absent). Every other statically-listed feature module
  // (schedule, validation, tendering, cost-benchmark, …) is defaultEnabled
  // too. BETA is still communicated via the in-page BetaBanner.
  defaultEnabled: true,
  depends: ['validation'],
  routes: [
    {
      path: '/pipelines',
      title: 'nav.pipelines',
      component: lazy(() => import('@/features/pipelines/PipelinesPage')),
    },
  ],
  navItems: [
    {
      labelKey: 'nav.pipelines',
      to: '/pipelines',
      icon: Workflow,
      group: 'ai',
      advancedOnly: true,
    },
  ],
  translations: {
    en: {
      'nav.pipelines': 'Pipeline Builder',
      'modules.pipelines.description':
        'Visually compose construction automations: triggers, data sources, transforms, validation gates and outputs as a node graph.',
    },
    es: {
      'modules.pipelines.description': 'Componga visualmente automatizaciones de obra: disparadores, fuentes de datos, transformaciones, controles de validación y salidas, como un grafo de nodos.',
      'nav.pipelines': 'Constructor de pipelines',
    },
    de: {
      'nav.pipelines': 'Pipeline-Builder',
      'modules.pipelines.description':
        'Bauabläufe visuell automatisieren: Auslöser, Datenquellen, Transformationen, Prüfregeln und Ausgaben als Knotengraph.',
    },
    'es-MX': {
      'modules.pipelines.description': 'Componga visualmente automatizaciones de obra: disparadores, fuentes de datos, transformaciones, controles de validación y salidas, como un grafo de nodos.',
    },
    'es-CL': {
      'modules.pipelines.description': 'Componga visualmente automatizaciones de obra: disparadores, fuentes de datos, transformaciones, controles de validación y salidas, como un grafo de nodos.',
    },
    'es-CO': {
      'modules.pipelines.description': 'Componga visualmente automatizaciones de obra: disparadores, fuentes de datos, transformaciones, controles de validación y salidas, como un grafo de nodos.',
    },
    pt: {
      'modules.pipelines.description': 'Componha visualmente automações de obra: gatilhos, fontes de dados, transformações, portas de validação e saídas, como um grafo de nós.',
    },
    'pt-BR': {
      'modules.pipelines.description': 'Componha visualmente automações de obra: gatilhos, fontes de dados, transformações, portas de validação e saídas, como um grafo de nós.',
    },
    zh: {
      'modules.pipelines.description': '以节点图的方式可视化编排施工自动化：触发器、数据源、转换、校验关卡和输出。',
    },
    ar: {
      'modules.pipelines.description': 'قم بتركيب أتمتة أعمال البناء بصريًا: المشغّلات، مصادر البيانات، التحويلات، بوابات التحقق، والمخرجات، على هيئة رسم بياني للعقد.',
    },
    hi: {
      'modules.pipelines.description': 'निर्माण स्वचालन को दृश्य रूप से रचें: ट्रिगर, डेटा स्रोत, ट्रांसफ़ॉर्म, सत्यापन गेट और आउटपुट, एक नोड ग्राफ़ के रूप में।',
    },
    tr: {
      'modules.pipelines.description': 'İnşaat otomasyonlarını görsel olarak kurun: tetikleyiciler, veri kaynakları, dönüşümler, doğrulama kapıları ve çıktılar, bir düğüm grafiği olarak.',
    },
    it: {
      'modules.pipelines.description': 'Componi visivamente le automazioni di cantiere: trigger, fonti dati, trasformazioni, controlli di validazione e output, come un grafo a nodi.',
    },
    nl: {
      'modules.pipelines.description': 'Stel bouwautomatiseringen visueel samen: triggers, gegevensbronnen, transformaties, validatiepoorten en uitvoer, als een knooppuntgrafiek.',
    },
    pl: {
      'modules.pipelines.description': 'Wizualnie komponuj automatyzacje budowlane: wyzwalacze, źródła danych, transformacje, bramki walidacji i wyjścia, jako graf węzłów.',
    },
    cs: {
      'modules.pipelines.description': 'Vizuálně sestavujte automatizace na stavbě: spouštěče, zdroje dat, transformace, kontrolní brány a výstupy jako graf uzlů.',
    },
    ja: {
      'modules.pipelines.description': 'トリガー、データソース、変換、検証ゲート、出力をノードグラフとして視覚的に組み立て、施工の自動化を構成します。',
    },
    ko: {
      'modules.pipelines.description': '트리거, 데이터 소스, 변환, 검증 게이트, 출력을 노드 그래프로 시각적으로 구성해 시공 자동화를 만듭니다.',
    },
    sv: {
      'modules.pipelines.description': 'Bygg visuellt byggautomationer: utlösare, datakällor, transformationer, valideringsgrindar och utdata, som en nodgraf.',
    },
    no: {
      'modules.pipelines.description': 'Sett visuelt sammen byggautomatiseringer: utløsere, datakilder, transformasjoner, valideringsporter og utdata, som en nodegraf.',
    },
    da: {
      'modules.pipelines.description': 'Sammensæt visuelt byggeautomatiseringer: udløsere, datakilder, transformationer, valideringsporte og output, som en knudegraf.',
    },
    fi: {
      'modules.pipelines.description': 'Kokoa rakennusautomaatioita visuaalisesti: liipaisimet, datalähteet, muunnokset, validointiportit ja tulosteet solmugraafina.',
    },
    bg: {
      'modules.pipelines.description': 'Съставяйте визуално строителни автоматизации: тригери, източници на данни, трансформации, портали за валидация и изходи, като граф от възли.',
    },
    hr: {
      'modules.pipelines.description': 'Vizualno sastavljajte automatizacije na gradilištu: okidače, izvore podataka, transformacije, validacijske vratnice i izlaze, kao graf čvorova.',
    },
    id: {
      'modules.pipelines.description': 'Susun otomatisasi konstruksi secara visual: pemicu, sumber data, transformasi, gerbang validasi, dan output, sebagai graf node.',
    },
    ro: {
      'modules.pipelines.description': 'Compuneți vizual automatizări de șantier: declanșatoare, surse de date, transformări, porți de validare și ieșiri, sub forma unui graf de noduri.',
    },
    th: {
      'modules.pipelines.description': 'ประกอบระบบอัตโนมัติของงานก่อสร้างด้วยภาพ: ตัวกระตุ้น แหล่งข้อมูล การแปลงข้อมูล ประตูตรวจสอบความถูกต้อง และผลลัพธ์ ในรูปแบบกราฟโหนด',
    },
    vi: {
      'modules.pipelines.description': 'Xây dựng trực quan các tự động hóa thi công: bộ kích hoạt, nguồn dữ liệu, phép biến đổi, cổng kiểm tra hợp lệ và đầu ra, dưới dạng đồ thị nút.',
    },
    ky: {
      'modules.pipelines.description': 'Курулуш автоматташтырууларын визуалдык түрдө түзүңүз: триггерлер, дайын булактары, түрлөндүрүүлөр, текшерүү дарбазалары жана чыгыштар, түйүн графы катары.',
    },
    et: {
      'modules.pipelines.description': 'Koostage visuaalselt ehitusautomatiseeringuid: käivitajad, andmeallikad, teisendused, valideerimisväravad ja väljundid, sõlmegraafina.',
    },
    bn: {
      'modules.pipelines.description': 'নির্মাণ স্বয়ংক্রিয়করণ দৃশ্যতভাবে তৈরি করুন: ট্রিগার, ডেটা উৎস, ট্রান্সফর্ম, ভ্যালিডেশন গেট এবং আউটপুট, একটি নোড গ্রাফ হিসেবে।',
    },
    kk: {
      'modules.pipelines.description': 'Құрылыс автоматтандыруларын көрнекі түрде құрастырыңыз: триггерлер, дерек көздері, түрлендірулер, тексеру қақпалары және шығыстар, түйін графигі ретінде.',
    },
    fil: {
      'modules.pipelines.description': 'Bumuo nang biswal ng mga automation sa construction: trigger, pinagmumulan ng data, transform, validation gate, at output, bilang isang node graph.',
    },
    ur: {
      'modules.pipelines.description': 'تعمیراتی آٹومیشنز کو بصری طور پر ترتیب دیں: ٹرگرز، ڈیٹا ذرائع، ٹرانسفارمز، ویلیڈیشن گیٹس اور آؤٹ پٹس، ایک نوڈ گراف کے طور پر۔',
    },
    fa: {
      'modules.pipelines.description': 'اتوماسیونهای ساختوساز را بهصورت بصری بسازید: محرکها، منابع داده، تبدیلها، دروازههای اعتبارسنجی و خروجیها، به شکل یک گراف گرهای.',
    },
    he: {
      'modules.pipelines.description': 'הרכיבו ויזואלית אוטומציות לאתר: טריגרים, מקורות נתונים, טרנספורמציות, שערי אימות ופלטים, כגרף צמתים.',
    },
    el: {
      'modules.pipelines.description': 'Συνθέστε οπτικά αυτοματισμούς εργοταξίου: ενεργοποιητές, πηγές δεδομένων, μετασχηματισμούς, πύλες επικύρωσης και εξόδους, ως γράφημα κόμβων.',
    },
    fr: {
      'modules.pipelines.description': 'Composez visuellement des automatisations de chantier : déclencheurs, sources de données, transformations, contrôles de validation et sorties, sous forme de graphe de nœuds.',
      'nav.pipelines': 'Générateur de pipelines',
    },
    ru: {
      'modules.pipelines.description': 'Визуально собирайте автоматизации для стройки: триггеры, источники данных, преобразования, шлюзы проверки и результаты в виде графа узлов.',
      'nav.pipelines': 'Конструктор конвейеров',
    },
  },
};
