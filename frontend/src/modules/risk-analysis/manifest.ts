// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { Dices } from 'lucide-react';
import type { ModuleManifest } from '../_types';

export const manifest: ModuleManifest = {
  id: 'risk-analysis',
  name: 'risk.title',
  description: 'modules.risk_analysis.description',
  version: '1.0.0',
  icon: Dices,
  category: 'tools',
  defaultEnabled: false,
  depends: ['boq'],
  // IA merge (#71): the standalone Risk Analysis page is retired so there is
  // a single Monte Carlo home. Cost-risk simulation from the BOQ lives in the
  // 5D Cost Model and register-driven simulation lives in the Risk Register
  // Monte Carlo tab, so this module no longer registers its own route or
  // sidebar entry. The static `/risk-analysis` redirect in App.tsx sends any
  // old deep link to `/risks?tab=montecarlo`. The page component is kept on
  // disk (RiskAnalysisModule.tsx) for reference and a possible later home.
  // (internal cache lineage: ddc-lineage:a17f93c4-risk-01)
  routes: [],
  navItems: [],
  translations: {
    en: {
      'nav.risk_analysis': 'Risk Analysis',
      'risk.title': 'Risk Analysis (Monte Carlo)',
      'modules.risk_analysis.description':
        'Probabilistic cost estimation with Monte Carlo simulation, sensitivity analysis, and contingency recommendations',
      'risk.subtitle': 'Probabilistic cost estimation with Monte Carlo simulation',
      'risk.run': 'Run Monte Carlo Simulation',
      'risk.running': 'Running simulation...',
      'risk.contingency': 'Contingency (P80 − P50)',
      'risk.recommended_budget': 'Recommended Budget (P80)',
      'risk.top_drivers': 'Top 10 Risk Drivers',
      'risk.distribution': 'Cost Distribution (Histogram)',
    },
    de: {
      'nav.risk_analysis': 'Risikoanalyse',
      'risk.title': 'Risikoanalyse (Monte Carlo)',
      'modules.risk_analysis.description':
        'Probabilistische Kostenermittlung mit Monte-Carlo-Simulation, Sensitivitätsanalyse und Empfehlungen zur Risikovorsorge',
      'risk.subtitle': 'Probabilistische Kostenermittlung mit Monte-Carlo-Simulation',
      'risk.run': 'Monte-Carlo-Simulation starten',
      'risk.running': 'Simulation läuft...',
      'risk.contingency': 'Risikovorsorge (P80 − P50)',
      'risk.recommended_budget': 'Empfohlenes Budget (P80)',
      'risk.top_drivers': 'Top 10 Risikotreiber',
      'risk.distribution': 'Kostenverteilung (Histogramm)',
    },
    es: {
      'modules.risk_analysis.description': 'Estimación probabilística de costes con simulación Monte Carlo, análisis de sensibilidad y recomendaciones de contingencia',
    },
    'es-MX': {
      'modules.risk_analysis.description': 'Estimación probabilística de costos con simulación Monte Carlo, análisis de sensibilidad y recomendaciones de contingencia',
    },
    'es-CL': {
      'modules.risk_analysis.description': 'Estimación probabilística de costos con simulación Monte Carlo, análisis de sensibilidad y recomendaciones de contingencia',
    },
    'es-CO': {
      'modules.risk_analysis.description': 'Estimación probabilística de costos con simulación Monte Carlo, análisis de sensibilidad y recomendaciones de contingencia',
    },
    pt: {
      'modules.risk_analysis.description': 'Estimativa probabilística de custos com simulação Monte Carlo, análise de sensibilidade e recomendações de contingência',
    },
    'pt-BR': {
      'modules.risk_analysis.description': 'Estimativa probabilística de custos com simulação Monte Carlo, análise de sensibilidade e recomendações de contingência',
    },
    zh: {
      'modules.risk_analysis.description': '采用蒙特卡洛模拟的概率造价估算、敏感性分析和风险预备金建议',
    },
    ar: {
      'modules.risk_analysis.description': 'تقدير تكلفة احتمالي بمحاكاة مونت كارلو وتحليل الحساسية وتوصيات الاحتياطي',
    },
    hi: {
      'modules.risk_analysis.description': 'मोंटे कार्लो सिमुलेशन, संवेदनशीलता विश्लेषण और आकस्मिकता अनुशंसाओं के साथ संभाव्य लागत अनुमान',
    },
    tr: {
      'modules.risk_analysis.description': 'Monte Carlo simülasyonu, duyarlılık analizi ve beklenmedik gider önerileriyle olasılıksal maliyet tahmini',
    },
    it: {
      'modules.risk_analysis.description': 'Stima probabilistica dei costi con simulazione Monte Carlo, analisi di sensitività e raccomandazioni sull\'accantonamento per imprevisti',
    },
    nl: {
      'modules.risk_analysis.description': 'Probabilistische kostenraming met Monte Carlo-simulatie, gevoeligheidsanalyse en aanbevelingen voor onvoorzien',
    },
    pl: {
      'modules.risk_analysis.description': 'Probabilistyczne szacowanie kosztów za pomocą symulacji Monte Carlo, analizy wrażliwości i rekomendacji dotyczących rezerwy',
    },
    cs: {
      'modules.risk_analysis.description': 'Pravděpodobnostní odhad nákladů pomocí simulace Monte Carlo, analýzy citlivosti a doporučení k rezervě',
    },
    ja: {
      'modules.risk_analysis.description': 'モンテカルロシミュレーションによる確率的コスト予測、感度分析、予備費の提案',
    },
    ko: {
      'modules.risk_analysis.description': '몬테카를로 시뮬레이션을 이용한 확률적 원가 추정, 민감도 분석, 예비비 권장 사항',
    },
    sv: {
      'modules.risk_analysis.description': 'Probabilistisk kostnadsberäkning med Monte Carlo-simulering, känslighetsanalys och rekommendationer för oförutsett',
    },
    no: {
      'modules.risk_analysis.description': 'Probabilistisk kostnadsestimering med Monte Carlo-simulering, sensitivitetsanalyse og anbefalinger for uforutsette utgifter',
    },
    da: {
      'modules.risk_analysis.description': 'Probabilistisk omkostningsestimering med Monte Carlo-simulering, følsomhedsanalyse og anbefalinger til uforudsete udgifter',
    },
    fi: {
      'modules.risk_analysis.description': 'Todennäköisyyspohjainen kustannusarvio Monte Carlo -simuloinnilla, herkkyysanalyysillä ja varausesityksillä',
    },
    bg: {
      'modules.risk_analysis.description': 'Вероятностна оценка на разходите чрез симулация Монте Карло, анализ на чувствителността и препоръки за резерв',
    },
    hr: {
      'modules.risk_analysis.description': 'Probabilistička procjena troškova simulacijom Monte Carlo, analizom osjetljivosti i preporukama za pričuvu',
    },
    id: {
      'modules.risk_analysis.description': 'Estimasi biaya probabilistik dengan simulasi Monte Carlo, analisis sensitivitas, dan rekomendasi biaya tak terduga',
    },
    ro: {
      'modules.risk_analysis.description': 'Estimare probabilistică a costurilor prin simulare Monte Carlo, analiză de sensibilitate și recomandări privind rezerva de risc',
    },
    th: {
      'modules.risk_analysis.description': 'การประมาณต้นทุนเชิงความน่าจะเป็นด้วยการจำลอง Monte Carlo การวิเคราะห์ความอ่อนไหว และคำแนะนำเงินสำรองเผื่อเหลือเผื่อขาด',
    },
    vi: {
      'modules.risk_analysis.description': 'Ước tính chi phí xác suất bằng mô phỏng Monte Carlo, phân tích độ nhạy và khuyến nghị dự phòng',
    },
    ky: {
      'modules.risk_analysis.description': 'Монте-Карло симуляциясы, сезгичтик анализи жана резерв боюнча сунуштар менен ыктымалдуулук наркын баалоо',
    },
    et: {
      'modules.risk_analysis.description': 'Tõenäosuslik kuluhinnang Monte Carlo simulatsiooniga, tundlikkusanalüüsiga ja reservi soovitustega',
    },
    bn: {
      'modules.risk_analysis.description': 'মন্টে কার্লো সিমুলেশন, সেনসিটিভিটি অ্যানালাইসিস ও কন্টিনজেন্সি সুপারিশসহ প্রায়িকতাভিত্তিক কস্ট এস্টিমেট',
    },
    kk: {
      'modules.risk_analysis.description': 'Монте-Карло симуляциясымен, сезімталдық талдауымен және резерв бойынша ұсыныстармен ықтималдық шығынды бағалау',
    },
    fil: {
      'modules.risk_analysis.description': 'Probabilistikong pagtatantya ng gastos gamit ang Monte Carlo simulation, sensitivity analysis, at mga rekomendasyon sa contingency',
    },
    ur: {
      'modules.risk_analysis.description': 'Monte Carlo سیمولیشن، حساسیت کے تجزیے اور ہنگامی سفارشات کے ساتھ امکانی لاگت کا تخمینہ',
    },
    fa: {
      'modules.risk_analysis.description': 'برآورد احتمالاتی هزینه با شبیهسازی مونتکارلو، تحلیل حساسیت و توصیههای ذخیره احتیاطی',
    },
    he: {
      'modules.risk_analysis.description': 'אמידת עלות הסתברותית עם סימולציית מונטה קרלו, ניתוח רגישות והמלצות לרזרבה',
    },
    el: {
      'modules.risk_analysis.description': 'Πιθανοτική εκτίμηση κόστους με προσομοίωση Monte Carlo, ανάλυση ευαισθησίας και συστάσεις για απρόβλεπτα',
    },
    fr: {
      'modules.risk_analysis.description': 'Estimation probabiliste des coûts par simulation Monte Carlo, analyse de sensibilité et recommandations de provision pour aléas',
      'nav.risk_analysis': 'Analyse des risques',
      'risk.title': 'Analyse des risques (Monte Carlo)',
      'risk.subtitle': 'Estimation probabiliste des coûts par simulation Monte Carlo',
      'risk.run': 'Lancer la simulation Monte Carlo',
      'risk.running': 'Simulation en cours...',
      'risk.contingency': 'Provision (P80 − P50)',
      'risk.recommended_budget': 'Budget recommandé (P80)',
    },
    ru: {
      'modules.risk_analysis.description': 'Вероятностная оценка стоимости методом Монте-Карло, анализ чувствительности и рекомендации по резерву',
      'nav.risk_analysis': 'Анализ рисков',
      'risk.title': 'Анализ рисков (Монте-Карло)',
      'risk.subtitle': 'Вероятностная оценка стоимости методом Монте-Карло',
      'risk.run': 'Запустить симуляцию Монте-Карло',
      'risk.running': 'Симуляция выполняется...',
      'risk.contingency': 'Резерв (P80 − P50)',
      'risk.recommended_budget': 'Рекомендуемый бюджет (P80)',
      'risk.top_drivers': 'Топ-10 факторов риска',
      'risk.distribution': 'Распределение стоимости (гистограмма)',
    },
  },
};
