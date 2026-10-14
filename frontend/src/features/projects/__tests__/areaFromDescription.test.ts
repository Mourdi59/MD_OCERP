// A German project description writes 16.000 m2 with a point as the thousands
// separator. Read as a decimal it became 16, and the hub printed a cost per m2
// a thousand times too high. The gross floor area must also win over the plot.

import { describe, it, expect } from 'vitest';
import { areaFromDescription } from '../ProjectDetailPage';

describe('areaFromDescription', () => {
  it('reads a German thousands point as a thousands separator', () => {
    expect(areaFromDescription('Wohnfläche ca. 11.000 m2')).toBe(11000);
  });

  it('prefers the gross floor area over an earlier plot area', () => {
    const text = 'Grundstück ca. 14.000 m2, BGF ca. 16.000 m2 oberirdisch, ca. 11.000 m2 Wohnfläche.';
    expect(areaFromDescription(text)).toBe(16000);
  });

  it('reads an English thousands comma and a plain number', () => {
    expect(areaFromDescription('GFA approx. 6,800 m2 on a 1.1 ha site')).toBe(6800);
    expect(areaFromDescription('A 450 m² annex')).toBe(450);
  });

  it('reads a decimal fraction as a fraction', () => {
    expect(areaFromDescription('Pavilion of 12,5 m2')).toBe(12.5);
  });

  it('returns null when no area is stated', () => {
    expect(areaFromDescription('No figures here')).toBeNull();
    expect(areaFromDescription(null)).toBeNull();
  });
});
