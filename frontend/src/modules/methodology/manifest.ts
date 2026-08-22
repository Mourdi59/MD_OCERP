// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { lazy } from 'react';
import { Layers3 } from 'lucide-react';
import type { ModuleManifest } from '../_types';

/**
 * Estimating methodologies - the data-driven markup-cascade engine.
 *
 * Two routes: the hub (`/methodologies`, templates gallery + installed list)
 * and the editor (`/methodologies/:methodologyId`). The sidebar entry is a
 * STATIC row in the `grp_estimating` group (Sidebar.tsx), like `/boq` and
 * `/assemblies`, so `navItems` here stays empty - the Sidebar only pulls
 * dynamic module navItems for its `grp_*` group ids, never for the legacy
 * group strings a manifest declares, so a dynamic entry would render nowhere.
 *
 * The active-methodology switch lives in project Settings
 * (MethodologyActiveCard), not in the sidebar.
 */
const MethodologiesPage = lazy(() =>
  import('@/features/methodology/MethodologiesPage').then((m) => ({
    default: m.MethodologiesPage,
  })),
);

const MethodologyEditorPage = lazy(() =>
  import('@/features/methodology/MethodologyEditorPage').then((m) => ({
    default: m.MethodologyEditorPage,
  })),
);

export const manifest: ModuleManifest = {
  id: 'methodology',
  name: 'nav.methodologies',
  description: 'modules.methodology_desc',
  version: '1.0.0',
  icon: Layers3,
  category: 'estimation',
  defaultEnabled: true,
  depends: ['boq'],
  routes: [
    {
      path: '/methodologies',
      title: 'methodology.title',
      component: MethodologiesPage,
    },
    {
      path: '/methodologies/:methodologyId',
      title: 'methodology.editor_title',
      component: MethodologyEditorPage,
    },
  ],
  navItems: [],
  translations: {
    en: {
      'nav.methodologies': 'Methodologies',
      'methodology.editor_title': 'Methodology editor',
      'modules.methodology_desc':
        'Data-driven estimating: install or build a markup cascade (works vs equipment split, base sets, sequential percentage steps and VAT), with analytical dimensions and funding sources.',
    },
    de: {
      'methodology.editor_title': 'Methodik-Editor',
      'modules.methodology_desc':
        'Datenbasierte Kalkulation: Zuschlagskaskaden installieren oder selbst aufbauen (Trennung von Bauleistung und Geräten, Basismengen, aufeinanderfolgende Prozentstufen und Umsatzsteuer), mit analytischen Dimensionen und Finanzierungsquellen.',
    },
    fr: {
      'modules.methodology_desc': 'Estimation pilotée par les données : installez ou construisez une cascade de coefficients (répartition ouvrage / matériel, bases de calcul, paliers de pourcentage successifs et TVA), avec dimensions analytiques et sources de financement.',
      'methodology.editor_title': 'Éditeur de méthodologie',
    },
    es: {
      'modules.methodology_desc': 'Estimación basada en datos: instale o construya una cascada de porcentajes (separación de obra y maquinaria, bases de cálculo, escalones porcentuales sucesivos e IVA), con dimensiones analíticas y fuentes de financiación.',
      'methodology.editor_title': 'Editor de metodología',
    },
    'es-MX': {
      'modules.methodology_desc': 'Estimación basada en datos: instale o construya una cascada de porcentajes (separación de obra y maquinaria, bases de cálculo, escalones porcentuales sucesivos e IVA), con dimensiones analíticas y fuentes de financiamiento.',
      'methodology.editor_title': 'Editor de metodología',
    },
    'es-CL': {
      'modules.methodology_desc': 'Estimación basada en datos: instale o construya una cascada de porcentajes (separación de obra y maquinaria, bases de cálculo, escalones porcentuales sucesivos e IVA), con dimensiones analíticas y fuentes de financiamiento.',
      'methodology.editor_title': 'Editor de metodología',
    },
    'es-CO': {
      'modules.methodology_desc': 'Estimación basada en datos: instale o construya una cascada de porcentajes (separación de obra y maquinaria, bases de cálculo, escalones porcentuales sucesivos e IVA), con dimensiones analíticas y fuentes de financiamiento.',
      'methodology.editor_title': 'Editor de metodología',
    },
    pt: {
      'modules.methodology_desc': 'Orçamentação orientada por dados: instale ou construa uma cascata de coeficientes (separação entre obra e equipamento, bases de cálculo, escalões percentuais sucessivos e IVA), com dimensões analíticas e fontes de financiamento.',
      'methodology.editor_title': 'Editor de metodologia',
    },
    'pt-BR': {
      'modules.methodology_desc': 'Orçamentação orientada por dados: instale ou monte uma cascata de coeficientes (separação entre obra e equipamento, bases de cálculo, faixas percentuais sucessivas e impostos), com dimensões analíticas e fontes de financiamento.',
      'methodology.editor_title': 'Editor de metodologia',
    },
    ru: {
      'modules.methodology_desc': 'Сметный расчёт на основе данных: устанавливайте готовую или стройте свою каскадную схему накруток (раздельно для работ и техники, базовые суммы, последовательные процентные шаги и НДС), с аналитическими измерениями и источниками финансирования.',
      'methodology.editor_title': 'Редактор методики',
    },
    zh: {
      'modules.methodology_desc': '数据驱动的计价：安装或自建取费级联（人工与机械分离、基数、逐级百分比及增值税），支持分析维度和资金来源。',
      'methodology.editor_title': '计价方法编辑器',
    },
    ar: {
      'modules.methodology_desc': 'تقدير قائم على البيانات: ثبّت أو ابنِ سلسلة نسب متتالية (فصل أعمال الإنشاء عن المعدات، القواعد الأساسية، خطوات نسبية متتالية وضريبة القيمة المضافة)، مع أبعاد تحليلية ومصادر تمويل.',
      'methodology.editor_title': 'محرر المنهجية',
    },
    hi: {
      'modules.methodology_desc': 'डेटा-संचालित अनुमान: एक मार्कअप कैस्केड इंस्टॉल करें या बनाएं (कार्य बनाम उपकरण विभाजन, आधार सेट, क्रमिक प्रतिशत चरण और VAT), विश्लेषणात्मक आयामों और वित्तपोषण स्रोतों के साथ।',
      'methodology.editor_title': 'पद्धति संपादक',
    },
    tr: {
      'modules.methodology_desc': 'Veriye dayalı hakediş: bir zam kademesi kurun veya oluşturun (imalat ile ekipman ayrımı, baz tutarlar, ardışık yüzde basamakları ve KDV), analitik boyutlar ve finansman kaynaklarıyla birlikte.',
      'methodology.editor_title': 'Metodoloji düzenleyici',
    },
    it: {
      'modules.methodology_desc': 'Stima guidata dai dati: installa o costruisci una cascata di ricarichi (separazione opere/attrezzature, basi di calcolo, scaglioni percentuali successivi e IVA), con dimensioni analitiche e fonti di finanziamento.',
      'methodology.editor_title': 'Editor delle metodologie',
    },
    nl: {
      'modules.methodology_desc': 'Datagedreven begroten: installeer of bouw een opslagcascade (splitsing werk versus materieel, basisbedragen, opeenvolgende percentagestappen en btw), met analytische dimensies en financieringsbronnen.',
      'methodology.editor_title': 'Methodiek-editor',
    },
    pl: {
      'modules.methodology_desc': 'Kosztorysowanie oparte na danych: zainstaluj lub zbuduj kaskadę narzutów (podział na roboty i sprzęt, podstawy naliczania, kolejne stopnie procentowe i VAT), z wymiarami analitycznymi i źródłami finansowania.',
      'methodology.editor_title': 'Edytor metodyki',
    },
    cs: {
      'modules.methodology_desc': 'Kalkulace založená na datech: nainstalujte nebo si sestavte kaskádu přirážek (rozdělení práce a mechanizace, základní částky, po sobě jdoucí procentní stupně a DPH), s analytickými dimenzemi a zdroji financování.',
      'methodology.editor_title': 'Editor metodiky',
    },
    ja: {
      'modules.methodology_desc': 'データ駆動型の積算：工事費と機械費を分けた諸経費のカスケードをインストールまたは自作し（基礎額、段階的なパーセント計算、消費税）、分析軸と資金源を設定できます。',
      'methodology.editor_title': '積算方式エディタ',
    },
    ko: {
      'modules.methodology_desc': '데이터 기반 산정: 공사비와 장비비를 분리한 할증 단계를 설치하거나 직접 구성하고(기준 금액, 순차적 비율 단계, 부가가치세), 분석 차원과 재원을 함께 설정합니다.',
      'methodology.editor_title': '산정 방법론 편집기',
    },
    sv: {
      'modules.methodology_desc': 'Datadriven kalkylering: installera eller bygg en påslagskaskad (uppdelning av arbete och maskiner, baser, successiva procentsteg och moms), med analytiska dimensioner och finansieringskällor.',
      'methodology.editor_title': 'Metodikredigerare',
    },
    no: {
      'modules.methodology_desc': 'Datadrevet kalkulasjon: installer eller bygg en påslagskaskade (deling av arbeid og utstyr, grunnlag, påfølgende prosenttrinn og mva), med analytiske dimensjoner og finansieringskilder.',
      'methodology.editor_title': 'Metodikkeditor',
    },
    da: {
      'modules.methodology_desc': 'Datadrevet kalkulation: installér eller byg en tillægskaskade (opdeling af arbejde og materiel, grundbeløb, fortløbende procenttrin og moms), med analytiske dimensioner og finansieringskilder.',
      'methodology.editor_title': 'Metodeeditor',
    },
    fi: {
      'modules.methodology_desc': 'Datalähtöinen laskenta: asenna tai rakenna yleiskustannuskaskadi (työn ja kaluston erottelu, perusteet, peräkkäiset prosenttiportaat ja ALV), analyyttisin ulottuvuuksin ja rahoituslähtein.',
      'methodology.editor_title': 'Menetelmäeditori',
    },
    bg: {
      'modules.methodology_desc': 'Остойностяване на база данни: инсталирайте или изградете каскада от надбавки (разделяне на строителство и механизация, базови суми, последователни процентни стъпки и ДДС), с аналитични измерения и източници на финансиране.',
      'methodology.editor_title': 'Редактор на методика',
    },
    hr: {
      'modules.methodology_desc': 'Procjena temeljena na podacima: instalirajte ili izgradite kaskadu nakladnih stopa (razdvajanje radova i mehanizacije, osnovice, uzastopni postotni koraci i PDV), s analitičkim dimenzijama i izvorima financiranja.',
      'methodology.editor_title': 'Uređivač metodologije',
    },
    id: {
      'modules.methodology_desc': 'Estimasi berbasis data: pasang atau bangun kaskade markup (pemisahan pekerjaan dan peralatan, dasar perhitungan, tahapan persentase berurutan, dan PPN), dengan dimensi analitis dan sumber pendanaan.',
      'methodology.editor_title': 'Editor metodologi',
    },
    ro: {
      'modules.methodology_desc': 'Deviz bazat pe date: instalați sau construiți o cascadă de cote adaosuri (separarea lucrărilor de utilaje, baze de calcul, trepte procentuale succesive și TVA), cu dimensiuni analitice și surse de finanțare.',
      'methodology.editor_title': 'Editor de metodologie',
    },
    th: {
      'modules.methodology_desc': 'การประมาณราคาที่ขับเคลื่อนด้วยข้อมูล: ติดตั้งหรือสร้างลำดับขั้นค่าดำเนินการ (แยกงานก่อสร้างและเครื่องจักร ฐานคำนวณ ขั้นเปอร์เซ็นต์ตามลำดับ และภาษีมูลค่าเพิ่ม) พร้อมมิติการวิเคราะห์และแหล่งเงินทุน',
      'methodology.editor_title': 'ตัวแก้ไขวิธีการประมาณราคา',
    },
    vi: {
      'modules.methodology_desc': 'Lập dự toán dựa trên dữ liệu: cài đặt hoặc tự xây dựng chuỗi hệ số phụ phí (tách riêng phần xây lắp và máy móc, các mức cơ sở, các bậc phần trăm liên tiếp và thuế VAT), cùng các chiều phân tích và nguồn vốn.',
      'methodology.editor_title': 'Trình soạn thảo phương pháp',
    },
    ky: {
      'modules.methodology_desc': 'Дайындарга негизделген смета: үстөк баасынын каскадын орнотуңуз же өзүңүз түзүңүз (жумуш менен техниканы бөлүү, негизги суммалар, ырааттуу пайыздык баскычтар жана КНС), аналитикалык өлчөмдөр жана каржылоо булактары менен.',
      'methodology.editor_title': 'Методология редактору',
    },
    et: {
      'modules.methodology_desc': 'Andmepõhine hinnastamine: paigaldage või ehitage juurdehindluse kaskaad (tööde ja seadmete eristamine, baasid, järjestikused protsendisammud ja käibemaks), koos analüütiliste mõõtmete ja rahastusallikatega.',
      'methodology.editor_title': 'Metoodikaredaktor',
    },
    bn: {
      'modules.methodology_desc': 'ডেটা-চালিত এস্টিমেটিং: একটি মার্কআপ ক্যাসকেড ইনস্টল বা তৈরি করুন (কাজ বনাম যন্ত্রপাতি বিভাজন, বেস সেট, ধারাবাহিক শতাংশ ধাপ এবং ভ্যাট), বিশ্লেষণী মাত্রা ও অর্থায়ন উৎসসহ।',
      'methodology.editor_title': 'মেথডলজি এডিটর',
    },
    kk: {
      'modules.methodology_desc': 'Деректерге негізделген сметалау: үстеме баға каскадын орнатыңыз немесе өзіңіз құрыңыз (жұмыс пен техниканы бөлу, негізгі сомалар, кезекті пайыздық сатылар және ҚҚС), аналитикалық өлшемдермен және қаржыландыру көздерімен бірге.',
      'methodology.editor_title': 'Әдістеме редакторы',
    },
    fil: {
      'modules.methodology_desc': 'Data-driven na pagtatantya: mag-install o gumawa ng markup cascade (paghahati ng gawain at kagamitan, base na halaga, magkakasunod na hakbang ng porsyento, at VAT), may analytical dimension at pinagmumulan ng pondo.',
      'methodology.editor_title': 'Editor ng methodology',
    },
    ur: {
      'modules.methodology_desc': 'ڈیٹا پر مبنی تخمینہ: ایک مارک اپ کیسکیڈ انسٹال کریں یا خود بنائیں (کام بمقابلہ مشینری کی تقسیم، بنیادی رقوم، ترتیب وار فیصد مراحل اور VAT)، تجزیاتی جہتوں اور فنڈنگ کے ذرائع کے ساتھ۔',
      'methodology.editor_title': 'طریقہ کار ایڈیٹر',
    },
    fa: {
      'modules.methodology_desc': 'برآورد دادهمحور: یک زنجیره ضرایب بالاسری را نصب یا خودتان بسازید (تفکیک عملیات اجرایی و ماشینآلات، مبالغ پایه، پلههای درصدی پیاپی و مالیات بر ارزش افزوده)، همراه با ابعاد تحلیلی و منابع تأمین مالی.',
      'methodology.editor_title': 'ویرایشگر روششناسی',
    },
    he: {
      'modules.methodology_desc': 'אמידה מונחית נתונים: התקינו או בנו מפל תוספות (הפרדה בין עבודה לציוד, בסיסי חישוב, מדרגות אחוז עוקבות ומע"מ), עם ממדים אנליטיים ומקורות מימון.',
      'methodology.editor_title': 'עורך מתודולוגיה',
    },
    el: {
      'modules.methodology_desc': 'Εκτίμηση βάσει δεδομένων: εγκαταστήστε ή δημιουργήστε έναν καταρράκτη επιβαρύνσεων (διαχωρισμός εργασιών από μηχανήματα, βάσεις υπολογισμού, διαδοχικά ποσοστιαία κλιμάκια και ΦΠΑ), με αναλυτικές διαστάσεις και πηγές χρηματοδότησης.',
      'methodology.editor_title': 'Επεξεργαστής μεθοδολογίας',
    },
  },
};
