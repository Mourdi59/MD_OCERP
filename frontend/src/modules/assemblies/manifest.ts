// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { Layers } from 'lucide-react';
import type { ModuleManifest } from '../_types';

// module registry lineage: ddc-lineage:a17f93c4-assemblies-01
export const manifest: ModuleManifest = {
  id: 'assemblies',
  name: 'nav.assemblies',
  description: 'modules.assemblies_desc',
  version: '1.0.0',
  icon: Layers,
  category: 'estimation',
  defaultEnabled: true,
  routes: [],
  navItems: [],
  translations: {
    en: {
      'modules.assemblies_desc':
        'Compose reusable assemblies from labour, material and equipment, and price a BOQ position from one line.',
    },
    de: {
      'modules.assemblies_desc':
        'Wiederverwendbare Positionen aus Lohn, Material und Geräten zusammenstellen und LV-Positionen daraus kalkulieren.',
    },
    fr: {
      'modules.assemblies_desc': 'Composez des assemblages réutilisables à partir de main-d\'œuvre, de matériaux et de matériel, et calculez le prix d\'un poste du devis depuis une seule ligne.',
    },
    es: {
      'modules.assemblies_desc': 'Componga partidas alzadas reutilizables a partir de mano de obra, material y maquinaria, y calcule el precio de una partida del presupuesto desde una sola línea.',
    },
    'es-MX': {
      'modules.assemblies_desc': 'Componga partidas reutilizables a partir de mano de obra, material y maquinaria, y calcule el precio de una partida del presupuesto desde una sola línea.',
    },
    'es-CL': {
      'modules.assemblies_desc': 'Componga partidas reutilizables a partir de mano de obra, material y maquinaria, y calcule el precio de una partida del presupuesto desde una sola línea.',
    },
    'es-CO': {
      'modules.assemblies_desc': 'Componga partidas reutilizables a partir de mano de obra, material y maquinaria, y calcule el precio de un renglón del presupuesto desde una sola línea.',
    },
    pt: {
      'modules.assemblies_desc': 'Componha composições reutilizáveis a partir de mão de obra, material e equipamento, e calcule o preço de um item da planilha orçamentária a partir de uma única linha.',
    },
    'pt-BR': {
      'modules.assemblies_desc': 'Componha composições reutilizáveis a partir de mão de obra, material e equipamento, e calcule o preço de um item da planilha orçamentária a partir de uma única linha.',
    },
    ru: {
      'modules.assemblies_desc': 'Собирайте многократно используемые сборные расценки из труда, материалов и техники и рассчитывайте позицию ВОР одной строкой.',
    },
    zh: {
      'modules.assemblies_desc': '由人工、材料和机械组合可复用的组合单价，并在一行内为工程量清单项定价。',
    },
    ar: {
      'modules.assemblies_desc': 'قم بتجميع بنود مركبة قابلة لإعادة الاستخدام من العمالة والمواد والمعدات، وسعّر بند جدول الكميات من سطر واحد.',
    },
    hi: {
      'modules.assemblies_desc': 'श्रम, सामग्री और उपकरण से पुन: प्रयोज्य संयुक्त दरें बनाएं, और एक ही पंक्ति से मात्रा विवरण की मद का मूल्य निर्धारित करें।',
    },
    tr: {
      'modules.assemblies_desc': 'İşçilik, malzeme ve ekipmandan yeniden kullanılabilir imalat analizleri oluşturun ve tek bir satırdan bir keşif kalemini fiyatlandırın.',
    },
    it: {
      'modules.assemblies_desc': 'Componi analisi prezzi riutilizzabili da manodopera, materiali e attrezzature, e determina il prezzo di una voce del computo da un\'unica riga.',
    },
    nl: {
      'modules.assemblies_desc': 'Stel herbruikbare samenstellingen samen uit arbeid, materiaal en materieel, en bepaal de prijs van een raming-post vanuit één regel.',
    },
    pl: {
      'modules.assemblies_desc': 'Twórz wielokrotnego użytku nakłady złożone z robocizny, materiałów i sprzętu i wyceniaj pozycję kosztorysu z jednego wiersza.',
    },
    cs: {
      'modules.assemblies_desc': 'Sestavujte znovu použitelné sestavy z práce, materiálu a mechanizace a oceňte položku rozpočtu z jediného řádku.',
    },
    ja: {
      'modules.assemblies_desc': '労務・材料・機械から再利用可能な複合単価を組み立て、数量明細項目を1行から価格設定します。',
    },
    ko: {
      'modules.assemblies_desc': '노무, 자재, 장비로 재사용 가능한 일위대가를 구성하고 한 줄에서 내역서 항목의 가격을 산정합니다.',
    },
    sv: {
      'modules.assemblies_desc': 'Sätt ihop återanvändbara sammansatta kalkylrader från arbete, material och maskiner, och prissätt en post i mängdförteckningen från en enda rad.',
    },
    no: {
      'modules.assemblies_desc': 'Sett sammen gjenbrukbare sammensatte poster fra arbeid, materiale og utstyr, og prissett en post i mengdefortegnelsen fra én linje.',
    },
    da: {
      'modules.assemblies_desc': 'Sammensæt genbrugelige sammensatte poster af arbejdskraft, materiale og materiel, og prissæt en post i tilbudslisten fra én linje.',
    },
    fi: {
      'modules.assemblies_desc': 'Kokoa uudelleenkäytettäviä panosrakenteita työstä, materiaalista ja kalustosta, ja hinnoittele määräluettelon rivi yhdellä rivillä.',
    },
    bg: {
      'modules.assemblies_desc': 'Съставяйте многократно използваеми анализни цени от труд, материали и механизация и остойностявайте позиция от количествената сметка от един ред.',
    },
    hr: {
      'modules.assemblies_desc': 'Sastavljajte sklopove za višekratnu upotrebu od rada, materijala i mehanizacije te odredite cijenu stavke troškovnika iz jednog retka.',
    },
    id: {
      'modules.assemblies_desc': 'Susun rakitan yang dapat digunakan kembali dari tenaga kerja, material, dan peralatan, lalu tetapkan harga satu item daftar kuantitas dari satu baris.',
    },
    ro: {
      'modules.assemblies_desc': 'Compuneți ansambluri reutilizabile din manoperă, materiale și utilaje și stabiliți prețul unei poziții din listă dintr-o singură linie.',
    },
    th: {
      'modules.assemblies_desc': 'ประกอบชุดราคาต่อหน่วยที่นำกลับมาใช้ใหม่ได้จากค่าแรง วัสดุ และเครื่องจักร และกำหนดราคารายการปริมาณงานจากบรรทัดเดียว',
    },
    vi: {
      'modules.assemblies_desc': 'Xây dựng các tổ hợp có thể tái sử dụng từ nhân công, vật liệu và máy móc, và định giá một hạng mục trong bảng khối lượng chỉ từ một dòng.',
    },
    ky: {
      'modules.assemblies_desc': 'Эмгек, материал жана техникадан кайра колдонула турган чогулмаларды түзүңүз жана смета позициясын бир сап аркылуу баалаңыз.',
    },
    et: {
      'modules.assemblies_desc': 'Koostage taaskasutatavaid koostisi tööjõust, materjalist ja seadmetest ning hinnastage mahutabeli rida ühelt realt.',
    },
    bn: {
      'modules.assemblies_desc': 'শ্রম, উপকরণ ও যন্ত্রপাতি থেকে পুনর্ব্যবহারযোগ্য অ্যাসেম্বলি তৈরি করুন এবং এক লাইন থেকেই বিল অফ কোয়ান্টিটিজের একটি আইটেমের দাম নির্ধারণ করুন।',
    },
    kk: {
      'modules.assemblies_desc': 'Еңбек, материал және техникадан қайта пайдалануға болатын жинақтарды құрастырыңыз және көлемдер ведомостісінің позициясын бір жолдан бағалаңыз.',
    },
    fil: {
      'modules.assemblies_desc': 'Bumuo ng magagamit-muling assembly mula sa lakas-paggawa, materyales, at kagamitan, at magtakda ng presyo ng isang item sa BOQ mula sa iisang linya.',
    },
    ur: {
      'modules.assemblies_desc': 'مزدوری، مواد اور مشینری سے دوبارہ قابل استعمال اسمبلیز تیار کریں، اور ایک ہی لائن سے مقدار کے بل کی مد کی قیمت طے کریں۔',
    },
    fa: {
      'modules.assemblies_desc': 'مجموعههای قابل استفاده مجدد را از نیروی کار، مواد و ماشینآلات بسازید و قیمت یک ردیف صورت مقادیر را از یک خط تعیین کنید.',
    },
    he: {
      'modules.assemblies_desc': 'הרכיבו מכלולים לשימוש חוזר מעבודה, חומרים וציוד, ותמחרו סעיף בכתב הכמויות משורה אחת.',
    },
    el: {
      'modules.assemblies_desc': 'Συνθέστε επαναχρησιμοποιήσιμα σύνθετα άρθρα από εργατικά, υλικά και μηχανήματα, και τιμολογήστε ένα άρθρο του τιμολογίου προσφοράς από μία μόνο γραμμή.',
    },
  },
};
