// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { CalendarDays } from 'lucide-react';
import type { ModuleManifest } from '../_types';

// internal-id ddc-lineage:a17f93c4-schedule-02
export const manifest: ModuleManifest = {
  id: 'schedule',
  name: 'schedule.title',
  description: 'modules.schedule_desc',
  version: '1.0.0',
  icon: CalendarDays,
  category: 'planning',
  defaultEnabled: true,
  routes: [],
  navItems: [],
  translations: {
    en: {
      'modules.schedule_desc':
        '4D schedule linking BOQ positions to activities, with progress rolled up per period.',
    },
    de: {
      'modules.schedule_desc':
        '4D-Terminplan, der LV-Positionen mit Vorgängen verknüpft und den Fortschritt je Periode fortschreibt.',
    },
    fr: {
      'modules.schedule_desc': 'Planning 4D reliant les postes du devis aux tâches, avec l\'avancement cumulé par période.',
    },
    es: {
      'modules.schedule_desc': 'Cronograma 4D que vincula las partidas del presupuesto con las actividades, con el avance acumulado por periodo.',
    },
    'es-MX': {
      'modules.schedule_desc': 'Cronograma 4D que vincula las partidas del presupuesto con las actividades, con el avance acumulado por periodo.',
    },
    'es-CL': {
      'modules.schedule_desc': 'Cronograma 4D que vincula las partidas del presupuesto con las actividades, con el avance acumulado por periodo.',
    },
    'es-CO': {
      'modules.schedule_desc': 'Cronograma 4D que vincula los renglones del presupuesto con las actividades, con el avance acumulado por periodo.',
    },
    pt: {
      'modules.schedule_desc': 'Cronograma 4D que liga os itens da planilha orçamentária às atividades, com o progresso acumulado por período.',
    },
    'pt-BR': {
      'modules.schedule_desc': 'Cronograma 4D que liga os itens da planilha orçamentária às atividades, com o progresso acumulado por período.',
    },
    ru: {
      'modules.schedule_desc': '4D-график, связывающий позиции ВОР с работами, с накоплением прогресса по периодам.',
    },
    zh: {
      'modules.schedule_desc': '4D 进度计划，将工程量清单项与工序关联，并按周期累计进度。',
    },
    ar: {
      'modules.schedule_desc': 'جدول زمني 4D يربط بنود جدول الكميات بالأنشطة، مع تراكم التقدم لكل فترة.',
    },
    hi: {
      'modules.schedule_desc': '4D कार्यक्रम जो मात्रा विवरण की मदों को गतिविधियों से जोड़ता है, और प्रगति को हर अवधि में संचित करता है।',
    },
    tr: {
      'modules.schedule_desc': 'Keşif kalemlerini faaliyetlere bağlayan, ilerlemeyi dönem başına toplayan 4B iş programı.',
    },
    it: {
      'modules.schedule_desc': 'Cronoprogramma 4D che collega le voci del computo alle attività, con l\'avanzamento cumulato per periodo.',
    },
    nl: {
      'modules.schedule_desc': '4D-planning die ramingsposten koppelt aan activiteiten, met voortgang die per periode wordt opgeteld.',
    },
    pl: {
      'modules.schedule_desc': 'Harmonogram 4D łączący pozycje kosztorysu z zadaniami, z postępem sumowanym w każdym okresie.',
    },
    cs: {
      'modules.schedule_desc': '4D harmonogram propojující položky rozpočtu s činnostmi, s postupem sčítaným za jednotlivá období.',
    },
    ja: {
      'modules.schedule_desc': '数量明細項目を作業に紐づけ、進捗を期間ごとに積み上げる4Dスケジュール。',
    },
    ko: {
      'modules.schedule_desc': '내역서 항목을 작업과 연결하고 진척률을 기간별로 누적하는 4D 공정표.',
    },
    sv: {
      'modules.schedule_desc': '4D-tidplan som länkar poster i mängdförteckningen till aktiviteter, med framdrift som summeras per period.',
    },
    no: {
      'modules.schedule_desc': '4D fremdriftsplan som knytter poster i mengdefortegnelsen til aktiviteter, med fremdrift summert per periode.',
    },
    da: {
      'modules.schedule_desc': '4D-tidsplan, der forbinder poster i tilbudslisten med aktiviteter, med fremdrift, der summeres pr. periode.',
    },
    fi: {
      'modules.schedule_desc': '4D-aikataulu, joka yhdistää määräluettelon rivit toimintoihin ja kertyy edistymän jaksoittain.',
    },
    bg: {
      'modules.schedule_desc': '4D график, свързващ позициите от количествената сметка с дейностите, с натрупване на напредъка по периоди.',
    },
    hr: {
      'modules.schedule_desc': '4D raspored koji povezuje stavke troškovnika s aktivnostima, s napretkom zbrojenim po razdoblju.',
    },
    id: {
      'modules.schedule_desc': 'Jadwal 4D yang menghubungkan item daftar kuantitas dengan aktivitas, dengan progres yang dijumlahkan per periode.',
    },
    ro: {
      'modules.schedule_desc': 'Grafic 4D care leagă pozițiile din listă de activități, cu progresul cumulat pe fiecare perioadă.',
    },
    th: {
      'modules.schedule_desc': 'แผนงาน 4D ที่เชื่อมโยงรายการปริมาณงานกับกิจกรรม พร้อมความคืบหน้าที่สะสมตามช่วงเวลา',
    },
    vi: {
      'modules.schedule_desc': 'Tiến độ 4D liên kết các hạng mục trong bảng khối lượng với các công việc, với tiến độ được cộng dồn theo từng kỳ.',
    },
    ky: {
      'modules.schedule_desc': 'Смета позицияларын иштерге байланыштырган, ар мезгил үчүн прогрессти чогулткан 4D график.',
    },
    et: {
      'modules.schedule_desc': '4D ajakava, mis seob mahutabeli read tegevustega ja summeerib edenemise perioodide kaupa.',
    },
    bn: {
      'modules.schedule_desc': '৪ডি সময়সূচি যা বিল অফ কোয়ান্টিটিজের আইটেমগুলোকে কার্যক্রমের সাথে যুক্ত করে, প্রতি পর্যায়ে অগ্রগতি সঞ্চিত করে।',
    },
    kk: {
      'modules.schedule_desc': 'Көлемдер ведомостісінің позицияларын жұмыстармен байланыстыратын, әр кезең бойынша прогресті жинақтайтын 4D кесте.',
    },
    fil: {
      'modules.schedule_desc': '4D na iskedyul na nag-uugnay sa mga item ng BOQ sa mga aktibidad, na pinagsama-sama ang progreso bawat panahon.',
    },
    ur: {
      'modules.schedule_desc': '4D شیڈول جو مقدار کے بل کی مدوں کو سرگرمیوں سے جوڑتا ہے، اور ہر مدت میں پیش رفت کو جمع کرتا ہے۔',
    },
    fa: {
      'modules.schedule_desc': 'زمانبندی 4D که ردیفهای صورت مقادیر را به فعالیتها پیوند میدهد و پیشرفت را در هر دوره جمع میکند.',
    },
    he: {
      'modules.schedule_desc': 'לוח זמנים 4D המקשר סעיפי כתב כמויות לפעילויות, עם התקדמות שנצברת לפי תקופה.',
    },
    el: {
      'modules.schedule_desc': 'Χρονοδιάγραμμα 4D που συνδέει τα άρθρα του τιμολογίου προσφοράς με τις δραστηριότητες, με την πρόοδο να αθροίζεται ανά περίοδο.',
    },
  },
};
