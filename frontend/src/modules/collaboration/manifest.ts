// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { lazy } from 'react';
import { Users } from 'lucide-react';
import type { ModuleManifest } from '../_types';

// internal-id ddc-lineage:a17f93c4-collab-01
export const manifest: ModuleManifest = {
  id: 'collaboration',
  name: 'collab.title',
  description: 'modules.collaboration.description',
  version: '1.0.0',
  icon: Users,
  category: 'tools',
  defaultEnabled: true,
  depends: ['boq'],
  routes: [
    {
      path: '/collaboration',
      title: 'nav.collaboration',
      component: lazy(() => import('./CollaborationModule')),
    },
  ],
  navItems: [],
  translations: {
    en: {
      'modules.collaboration.description':
        'Collaborate on estimates with your team in real-time using Yjs CRDT',
      'collab.peers_connected': '{{count}} peer(s) connected',
      'collab.share_link': 'Share collaboration link',
      'collab.conflict_detected': 'Conflict detected',
      'collab.keep_mine': 'Keep mine',
      'collab.accept_theirs': 'Accept theirs',
      'collab.resolve_manually': 'Resolve manually',
      'collab.no_conflicts': 'No conflicts',
    },
    de: {
      'modules.collaboration.description':
        'Kalkulationen gemeinsam im Team in Echtzeit bearbeiten, auf Basis von Yjs CRDT',
      'collab.peers_connected': '{{count}} Teilnehmer verbunden',
      'collab.share_link': 'Kollaborations-Link teilen',
      'collab.conflict_detected': 'Konflikt erkannt',
      'collab.keep_mine': 'Meine behalten',
      'collab.accept_theirs': 'Ihre übernehmen',
      'collab.resolve_manually': 'Manuell lösen',
      'collab.no_conflicts': 'Keine Konflikte',
    },
    es: {
      'modules.collaboration.description': 'Colabore en las estimaciones con su equipo en tiempo real mediante Yjs CRDT',
    },
    'es-MX': {
      'modules.collaboration.description': 'Colabore en las estimaciones con su equipo en tiempo real mediante Yjs CRDT',
    },
    'es-CL': {
      'modules.collaboration.description': 'Colabore en las estimaciones con su equipo en tiempo real mediante Yjs CRDT',
    },
    'es-CO': {
      'modules.collaboration.description': 'Colabore en las estimaciones con su equipo en tiempo real mediante Yjs CRDT',
    },
    pt: {
      'modules.collaboration.description': 'Colabore em orçamentos com a sua equipa em tempo real através de Yjs CRDT',
    },
    'pt-BR': {
      'modules.collaboration.description': 'Colabore em orçamentos com sua equipe em tempo real usando Yjs CRDT',
    },
    zh: {
      'modules.collaboration.description': '通过 Yjs CRDT 与团队实时协作编制估算',
    },
    ar: {
      'modules.collaboration.description': 'تعاونوا في إعداد التقديرات مع فريقكم في الوقت الفعلي باستخدام Yjs CRDT',
    },
    hi: {
      'modules.collaboration.description': 'Yjs CRDT का उपयोग करके अपनी टीम के साथ वास्तविक समय में अनुमानों पर सहयोग करें',
    },
    tr: {
      'modules.collaboration.description': 'Yjs CRDT kullanarak ekibinizle gerçek zamanlı olarak keşifler üzerinde iş birliği yapın',
    },
    it: {
      'modules.collaboration.description': 'Collabora alle stime con il tuo team in tempo reale grazie a Yjs CRDT',
    },
    nl: {
      'modules.collaboration.description': 'Werk in real-time met uw team samen aan ramingen via Yjs CRDT',
    },
    pl: {
      'modules.collaboration.description': 'Współpracuj nad kosztorysami z zespołem w czasie rzeczywistym dzięki Yjs CRDT',
    },
    cs: {
      'modules.collaboration.description': 'Spolupracujte na rozpočtech se svým týmem v reálném čase pomocí Yjs CRDT',
    },
    ja: {
      'modules.collaboration.description': 'Yjs CRDTを使ってチームとリアルタイムに積算を共同編集します',
    },
    ko: {
      'modules.collaboration.description': 'Yjs CRDT를 사용해 팀과 실시간으로 견적을 공동 작업합니다',
    },
    sv: {
      'modules.collaboration.description': 'Samarbeta om kalkyler med ditt team i realtid med Yjs CRDT',
    },
    no: {
      'modules.collaboration.description': 'Samarbeid om kalkyler med teamet ditt i sanntid ved hjelp av Yjs CRDT',
    },
    da: {
      'modules.collaboration.description': 'Samarbejd om kalkulationer med dit team i realtid ved hjælp af Yjs CRDT',
    },
    fi: {
      'modules.collaboration.description': 'Tee kustannusarviota tiiminne kanssa reaaliajassa Yjs CRDT:n avulla',
    },
    bg: {
      'modules.collaboration.description': 'Работете съвместно по сметни разчети с екипа си в реално време чрез Yjs CRDT',
    },
    hr: {
      'modules.collaboration.description': 'Surađujte na troškovnicima s timom u stvarnom vremenu pomoću Yjs CRDT-a',
    },
    id: {
      'modules.collaboration.description': 'Berkolaborasi dalam estimasi bersama tim secara real-time menggunakan Yjs CRDT',
    },
    ro: {
      'modules.collaboration.description': 'Colaborați la devize cu echipa dvs. în timp real folosind Yjs CRDT',
    },
    th: {
      'modules.collaboration.description': 'ทำงานร่วมกับทีมของคุณแบบเรียลไทม์ในการประมาณราคาโดยใช้ Yjs CRDT',
    },
    vi: {
      'modules.collaboration.description': 'Cộng tác lập dự toán với nhóm của bạn theo thời gian thực bằng Yjs CRDT',
    },
    ky: {
      'modules.collaboration.description': 'Командаңыз менен чыныгы убакытта Yjs CRDT аркылуу сметалар боюнча биргелешип иштеңиз',
    },
    et: {
      'modules.collaboration.description': 'Tehke hinnangute kallal koostööd oma meeskonnaga reaalajas, kasutades Yjs CRDT-d',
    },
    bn: {
      'modules.collaboration.description': 'Yjs CRDT ব্যবহার করে আপনার টিমের সাথে রিয়েল-টাইমে এস্টিমেটে সহযোগিতা করুন',
    },
    kk: {
      'modules.collaboration.description': 'Командаңызбен Yjs CRDT арқылы нақты уақытта сметалар бойынша бірлесіп жұмыс істеңіз',
    },
    fil: {
      'modules.collaboration.description': 'Makipagtulungan sa mga estimate kasama ang iyong team nang real-time gamit ang Yjs CRDT',
    },
    ur: {
      'modules.collaboration.description': 'Yjs CRDT کا استعمال کرتے ہوئے اپنی ٹیم کے ساتھ ریئل ٹائم میں تخمینوں پر تعاون کریں',
    },
    fa: {
      'modules.collaboration.description': 'با تیم خود بهصورت بلادرنگ روی برآوردها همکاری کنید، با استفاده از Yjs CRDT',
    },
    he: {
      'modules.collaboration.description': 'שתפו פעולה על אומדנים עם הצוות שלכם בזמן אמת באמצעות Yjs CRDT',
    },
    el: {
      'modules.collaboration.description': 'Συνεργαστείτε σε προμετρήσεις με την ομάδα σας σε πραγματικό χρόνο μέσω Yjs CRDT',
    },
    fr: {
      'modules.collaboration.description': 'Collaborez sur les estimations avec votre équipe en temps réel grâce à Yjs CRDT',
      'collab.peers_connected': '{{count}} participant(s) connecté(s)',
      'collab.share_link': 'Partager le lien de collaboration',
      'collab.conflict_detected': 'Conflit détecté',
      'collab.keep_mine': 'Garder le mien',
      'collab.accept_theirs': 'Accepter le leur',
      'collab.resolve_manually': 'Résoudre manuellement',
      'collab.no_conflicts': 'Aucun conflit',
    },
    ru: {
      'modules.collaboration.description': 'Совместная работа над сметами с командой в реальном времени на основе Yjs CRDT',
      'collab.peers_connected': '{{count}} участник(ов) подключено',
      'collab.share_link': 'Поделиться ссылкой',
      'collab.conflict_detected': 'Обнаружен конфликт',
      'collab.keep_mine': 'Оставить мои',
      'collab.accept_theirs': 'Принять их',
      'collab.resolve_manually': 'Решить вручную',
      'collab.no_conflicts': 'Конфликтов нет',
    },
  },
};
