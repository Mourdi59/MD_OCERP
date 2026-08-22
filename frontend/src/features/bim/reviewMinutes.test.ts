// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';

import { buildReviewMinutesHtml, type ReviewMinutesParams } from './reviewMinutes';

function params(over: Partial<ReviewMinutesParams> = {}): ReviewMinutesParams {
  return {
    title: 'Model review minutes',
    modelName: 'Tower A - Structure',
    chair: 'Dana Lang',
    heldOn: '20 August 2026, 10:00',
    agenda: [
      {
        index: 3,
        title: 'Duct clashes with beam at grid C-4',
        status: 'Resolved',
        priority: 'Critical',
        assignee: 'Dana Lang',
        due: '2026-08-25',
      },
      {
        index: 4,
        title: 'Door swing blocked by riser',
        status: 'Open',
        priority: '',
        assignee: '',
        due: null,
      },
    ],
    decisions: [
      {
        guid: 'g1',
        title: 'Duct clashes with beam at grid C-4',
        statusFrom: 'Open',
        statusTo: 'Resolved',
        note: 'MEP to reroute above the beam',
      },
    ],
    stillOpen: 1,
    ...over,
  };
}

describe('buildReviewMinutesHtml', () => {
  it('records the session facts a reader needs to trust the page', () => {
    const html = buildReviewMinutesHtml(params());
    expect(html).toContain('Model review minutes');
    expect(html).toContain('Tower A - Structure');
    expect(html).toContain('Dana Lang');
    expect(html).toContain('20 August 2026, 10:00');
    // Agenda size, decisions taken and what is still open.
    expect(html).toContain('<td>Issues reviewed</td><td>2</td>');
    expect(html).toContain('<td>Decisions taken</td><td>1</td>');
    expect(html).toContain('<td>Still open</td><td>1</td>');
  });

  it('spells a status change as from → to, and carries the note', () => {
    const html = buildReviewMinutesHtml(params());
    expect(html).toContain('Open → Resolved');
    expect(html).toContain('MEP to reroute above the beam');
  });

  it('says so plainly when nothing was decided', () => {
    const html = buildReviewMinutesHtml(params({ decisions: [], stillOpen: 2 }));
    expect(html).toContain('No status changes or notes were recorded in this session.');
    expect(html).not.toContain('→');
  });

  it('renders a note-only decision without inventing a status change', () => {
    const html = buildReviewMinutesHtml(
      params({
        decisions: [
          { guid: 'g2', title: 'Door swing blocked by riser', note: 'Architect to confirm' },
        ],
      }),
    );
    expect(html).toContain('Architect to confirm');
    expect(html).not.toContain('→');
  });

  it('escapes issue text so a title can never inject markup', () => {
    const html = buildReviewMinutesHtml(
      params({
        decisions: [
          {
            guid: 'g3',
            title: '<script>alert(1)</script>',
            note: 'a & b "quoted"',
            statusFrom: 'Open',
            statusTo: 'Closed',
          },
        ],
      }),
    );
    expect(html).not.toContain('<script>alert(1)</script>');
    expect(html).toContain('&lt;script&gt;');
    expect(html).toContain('a &amp; b &quot;quoted&quot;');
  });

  it('honours localised labels and the empty-cell dash', () => {
    const html = buildReviewMinutesHtml(
      params({
        labels: {
          model: 'Modell',
          chair: 'Leitung',
          decisions: 'Entscheidungen',
          none: '—',
        },
      }),
    );
    expect(html).toContain('Modell');
    expect(html).toContain('Leitung');
    expect(html).toContain('<h2>Entscheidungen</h2>');
    // The undated, unassigned agenda row falls back to the supplied dash.
    expect(html).toContain('<td>—</td>');
  });

  it('survives a review with no model on screen', () => {
    const html = buildReviewMinutesHtml(params({ modelName: null }));
    expect(html).toContain('20 August 2026, 10:00');
    expect(html).toContain('<td>Model</td><td>-</td>');
  });
});
