// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The three nothings a BCF thumbnail can be in have to stay three.
 *
 * Collapsing them is not a styling detail: a viewpoint that never carried a PNG
 * is the ordinary case (the schema makes the snapshot optional and the demo
 * seeder writes no key), so drawing it with a failure affordance turns a
 * register of healthy issues into a grid of broken pictures, and labelling a
 * lost snapshot "never taken" tells the reader something untrue about the data.
 */

import { describe, expect, it } from 'vitest';

import { snapshotPlaceholder } from './snapshotState';

describe('snapshotPlaceholder', () => {
  it('draws nothing when the viewpoint carries an image', () => {
    expect(snapshotPlaceholder({ has_snapshot: true }, false)).toBeNull();
  });

  it('separates a lost snapshot from one that was never taken', () => {
    expect(snapshotPlaceholder({ has_snapshot: true }, true)).toBe('failed');
    expect(snapshotPlaceholder({ has_snapshot: false }, false)).toBe('no_snapshot');
  });

  it('calls an issue with no viewpoint neither missing nor broken', () => {
    expect(snapshotPlaceholder(null, false)).toBe('no_viewpoint');
    expect(snapshotPlaceholder(undefined, false)).toBe('no_viewpoint');
  });

  it('gives every state a name of its own', () => {
    const states = [
      snapshotPlaceholder({ has_snapshot: true }, true),
      snapshotPlaceholder({ has_snapshot: false }, false),
      snapshotPlaceholder(null, false),
    ];
    expect(new Set(states).size).toBe(states.length);
  });
});
