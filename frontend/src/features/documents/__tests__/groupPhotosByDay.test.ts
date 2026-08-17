/**
 * The timeline's day grouping, which used to live on the server.
 *
 * `GET /v1/documents/photos/timeline/` answered with date groups until the
 * pagination wave, and a list of days cannot report how many photos it left
 * out: the route capped at 500 photos and returned however many days those
 * fell into. It now answers with the photo page the gallery reads, and this
 * function does the grouping.
 *
 * The tests below pin the two things that had to survive the move: the day a
 * photo lands in, and the order days and photos come out in. The server keyed
 * on ``(taken_at or created_at).strftime('%Y-%m-%d')`` over rows already
 * sorted newest-first, and sorted the resulting day keys descending.
 */
import { describe, it, expect } from 'vitest';
import { groupPhotosByDay, type PhotoItem } from '../api';

function photo(id: string, taken_at: string | null, created_at: string): PhotoItem {
  return {
    id,
    project_id: 'proj-1',
    document_id: null,
    filename: `${id}.jpg`,
    caption: null,
    gps_lat: null,
    gps_lon: null,
    tags: [],
    taken_at,
    category: 'site',
    metadata: {},
    created_by: 'u1',
    created_at,
    updated_at: created_at,
  };
}

describe('groupPhotosByDay', () => {
  it('keys on the capture date and falls back to the upload date', () => {
    const groups = groupPhotosByDay([
      photo('a', '2026-06-03T08:00:00Z', '2026-06-05T09:00:00Z'),
      photo('b', null, '2026-06-05T09:00:00Z'),
    ]);

    expect(groups.map((g) => g.date)).toEqual(['2026-06-05', '2026-06-03']);
    expect(groups[0]?.photos.map((p) => p.id)).toEqual(['b']);
    expect(groups[1]?.photos.map((p) => p.id)).toEqual(['a']);
  });

  it('puts the newest day first and leaves the order inside a day alone', () => {
    // Arrives newest-first, the order the route returns rows in.
    const groups = groupPhotosByDay([
      photo('newest', '2026-06-05T18:00:00Z', '2026-06-05T18:00:00Z'),
      photo('older-same-day', '2026-06-05T07:00:00Z', '2026-06-05T07:00:00Z'),
      photo('previous-day', '2026-06-04T12:00:00Z', '2026-06-04T12:00:00Z'),
    ]);

    expect(groups.map((g) => g.date)).toEqual(['2026-06-05', '2026-06-04']);
    expect(groups[0]?.photos.map((p) => p.id)).toEqual(['newest', 'older-same-day']);
  });

  it('reads the day off the timestamp text, not through a Date', () => {
    // A late-evening UTC capture is the NEXT day east of Greenwich and the
    // SAME day west of it. Parsing into a Date and asking the browser for the
    // date would move this photo between days depending on where the reader
    // sits, and would disagree with the day the server used to compute. The
    // day is the first ten characters of the timestamp, full stop.
    const groups = groupPhotosByDay([photo('late', '2026-06-05T23:30:00Z', '2026-06-06T01:00:00Z')]);

    expect(groups.map((g) => g.date)).toEqual(['2026-06-05']);
  });

  it('returns nothing for an empty page rather than an empty day', () => {
    expect(groupPhotosByDay([])).toEqual([]);
  });
});
