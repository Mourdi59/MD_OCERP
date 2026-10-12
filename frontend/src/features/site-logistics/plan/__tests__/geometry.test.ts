// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction

import { describe, expect, it } from 'vitest';

import {
  closeRing,
  imageToMetres,
  linePoints,
  metresPerPixel,
  metresToImage,
  moveVertex,
  panView,
  screenScale,
  zoomView,
  openRing,
  pointOf,
  removeVertex,
  screenToMetres,
  svgPoints,
  toLine,
  toPoint,
  viewBox,
  viewOf,
  type Pt,
} from '../geometry';

describe('scale', () => {
  it('two pixels and the real distance between them give metres per pixel', () => {
    expect(metresPerPixel([100, 100], [400, 500], 25)).toBe(0.05);
  });

  it('says nothing for the same pixel twice or a distance that is not positive', () => {
    expect(metresPerPixel([10, 10], [10, 10], 5)).toBeNull();
    expect(metresPerPixel([0, 0], [10, 0], 0)).toBeNull();
    expect(metresPerPixel([0, 0], [10, 0], Number.NaN)).toBeNull();
  });

  it('a pixel below the origin has a negative y, and the way back lands on the same pixel', () => {
    const calibration = { metresPerPixel: 0.05, origin: [200, 800] as Pt };
    expect(imageToMetres([400, 600], calibration)).toEqual([10, 10]);
    expect(imageToMetres([200, 900], calibration)).toEqual([0, -5]);
    expect(metresToImage([10, 10], calibration)).toEqual([400, 600]);
  });
});

describe('closing an outline', () => {
  const square: Pt[] = [
    [0, 0],
    [10, 0],
    [10, 10],
    [0, 10],
  ];

  it('repeats the first corner at the end', () => {
    expect(closeRing(square)).toEqual({
      type: 'Polygon',
      coordinates: [
        [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
          [0, 0],
        ],
      ],
    });
  });

  it('does not close twice a ring that already ends where it starts', () => {
    expect(closeRing([...square, [0, 0]])?.coordinates[0]).toHaveLength(5);
  });

  it('drops a corner clicked twice in a row', () => {
    expect(closeRing([[0, 0], [0, 0], [10, 0], [10, 10]])?.coordinates[0]).toHaveLength(4);
  });

  it('is not an outline below three different corners', () => {
    expect(closeRing([[0, 0], [10, 0]])).toBeNull();
    expect(closeRing([[0, 0], [10, 0], [10, 0], [0, 0]])).toBeNull();
  });

  it('rounds to the centimetre', () => {
    expect(closeRing([[0.004, 0], [10.126, 0], [10, 10]])?.coordinates[0]?.[1]).toEqual([10.13, 0]);
  });

  it('a stored polygon opens to its corners without the closing repeat', () => {
    expect(openRing(closeRing(square))).toEqual(square);
    expect(openRing(null)).toEqual([]);
    expect(openRing({ type: 'LineString', coordinates: [[0, 0]] })).toEqual([]);
  });
});

describe('routes and points', () => {
  it('a route needs two points', () => {
    expect(toLine([[0, 0]])).toBeNull();
    expect(toLine([[0, 0], [5, 5]])).toEqual({ type: 'LineString', coordinates: [[0, 0], [5, 5]] });
    expect(linePoints(toLine([[0, 0], [5, 5]]))).toEqual([[0, 0], [5, 5]]);
    expect(linePoints({ type: 'Polygon', coordinates: [] })).toEqual([]);
  });

  it('a point reads back as it was written', () => {
    expect(pointOf(toPoint([3.456, 7]))).toEqual([3.46, 7]);
    expect(pointOf({ type: 'Point', coordinates: ['a', 1] })).toBeNull();
  });
});

describe('editing corners', () => {
  const triangle: Pt[] = [
    [0, 0],
    [10, 0],
    [5, 8],
  ];

  it('moves one corner and leaves the others', () => {
    expect(moveVertex(triangle, 2, [6, 9])).toEqual([[0, 0], [10, 0], [6, 9]]);
  });

  it('refuses to delete below the least a shape needs', () => {
    expect(removeVertex(triangle, 1, 3)).toEqual(triangle);
    expect(removeVertex([...triangle, [0, 8]], 1, 3)).toEqual([[0, 0], [5, 8], [0, 8]]);
    expect(removeVertex(triangle, 9, 2)).toEqual(triangle);
  });
});

describe('screen', () => {
  it('an empty plan is a sheet of 100 by 60 metres', () => {
    expect(viewOf([])).toEqual({ minX: 0, minY: 0, width: 100, height: 60 });
  });

  it('the view holds every shape with a margin', () => {
    const view = viewOf([[[0, 0], [100, 50]]], 0.1);
    expect(view).toEqual({ minX: -10, minY: -10, width: 120, height: 70 });
    expect(viewBox(view)).toBe('-10 -60 120 70');
  });

  it('y is flipped on the way to the screen', () => {
    expect(svgPoints([[0, 0], [10, 5]])).toBe('0,0 10,-5');
  });

  it('a click maps to metres with one scale for both axes', () => {
    const view = { minX: 0, minY: 0, width: 100, height: 50 };
    // 200 by 200 pixels: the sheet is 200 by 100 on screen, centred, 50 pixels free above and below.
    const rect = { left: 0, top: 0, width: 200, height: 200 };
    expect(screenToMetres([0, 50], rect, view)).toEqual([0, 50]);
    expect(screenToMetres([200, 150], rect, view)).toEqual([100, 0]);
    expect(screenToMetres([100, 100], rect, view)).toEqual([50, 25]);
  });

  it('zooming keeps the point under the pointer where it is', () => {
    const view = { minX: 0, minY: 0, width: 100, height: 60 };
    expect(zoomView(view, 0.5, [50, 30])).toEqual({ minX: 25, minY: 15, width: 50, height: 30 });
    expect(zoomView(view, 0.5, [0, 0])).toEqual({ minX: 0, minY: 0, width: 50, height: 30 });
    expect(zoomView(view, 2, [100, 60])).toEqual({ minX: -100, minY: -60, width: 200, height: 120 });
  });

  it('zooming stops at a sheet one metre wide', () => {
    const view = { minX: 0, minY: 0, width: 2, height: 1 };
    expect(zoomView(view, 0.01, [0, 0]).width).toBe(1);
  });

  it('panning moves the view by metres, and a screen pixel is worth the larger of the two ratios', () => {
    const view = { minX: 0, minY: 0, width: 100, height: 50 };
    expect(panView(view, -10, 5)).toEqual({ minX: -10, minY: 5, width: 100, height: 50 });
    expect(screenScale({ width: 200, height: 200 }, view)).toBe(0.5);
    expect(screenScale({ width: 0, height: 0 }, view)).toBe(1);
  });

  it('an element without a size counts one pixel per metre', () => {
    const view = { minX: 0, minY: 0, width: 100, height: 60 };
    expect(screenToMetres([10, 20], { left: 0, top: 0, width: 0, height: 0 }, view)).toEqual([10, 40]);
  });
});
