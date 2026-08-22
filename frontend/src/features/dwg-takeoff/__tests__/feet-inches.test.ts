// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Architectural feet-and-inches notation on the DWG takeoff canvas.
 *
 * The DWG screen formats measurement labels through two paths that never meet,
 * and the notation has to reach both or the same drawing contradicts itself:
 *
 *   - `formatMeasurement` (lib/measurement.ts) takes the metric-canonical value
 *     the DWG layer stores and converts at the display boundary. This is the
 *     preset-scale path.
 *   - `formatCalibrated` (components/AnnotationOverlay.tsx) starts from raw
 *     pixels and the estimator's own two-click calibration unit, and used to
 *     bypass the measurement system entirely.
 *
 * The regression these tests exist for is the pair reading differently side by
 * side: a calibrated annotation saying "41.01 ft" next to a preset-scale one
 * saying 12'-6 3/4" on the same sheet.
 *
 * The empty-string contract matters as much as the notation. `formatFeetInches`
 * returns '' for degenerate input because its original caller also rendered ''
 * there; both DWG paths render a number instead, so both must fall through to
 * their decimal tiers rather than pass the empty string to the canvas and leave
 * an annotation with no dimension text at all.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import { formatMeasurement } from '../lib/measurement';
import { formatCalibrated } from '../components/AnnotationOverlay';
import { usePreferencesStore } from '@/stores/usePreferencesStore';

const setSystem = (system: 'metric' | 'imperial') =>
  usePreferencesStore.getState().setPreference('measurementSystem', system);

beforeEach(() => setSystem('metric'));
afterEach(() => setSystem('metric'));

describe('preset-scale path: formatMeasurement', () => {
  it('writes a linear imperial length in feet and inches', () => {
    setSystem('imperial');
    // 3.8227 m is 12 ft 6.5 in, which lands on a clean 1/2 after rounding to
    // sixteenths, so the fraction must be reduced rather than shown as 8/16.
    expect(formatMeasurement(3.8227, 'm')).toBe("12'-6 1/2\"");
  });

  it('leaves the metric path byte-identical', () => {
    expect(formatMeasurement(3.8227, 'm')).toBe('3.82 m');
    expect(formatMeasurement(1500, 'm')).toBe('1.50 km');
  });

  it('keeps area and volume decimal in imperial', () => {
    setSystem('imperial');
    // Nobody dimensions a slab as square feet and three quarters, so composite
    // units keep the decimal reading with the imperial label.
    expect(formatMeasurement(10, 'm²')).toMatch(/ft²$/);
    expect(formatMeasurement(10, 'm³')).toMatch(/ft³$/);
  });

  it('does not read an already-imperial value as metres', () => {
    setSystem('imperial');
    // AnnotationOverlay passes `ann.measurement_unit ?? fallbackUnit`, so this
    // function is reachable with whatever the wire sent. A value already in ft
    // must not be converted a second time as if it were metres.
    //
    // Pin the whole string rather than asserting the absence of an apostrophe.
    // Absence passes for two different reasons - the guard correctly declined,
    // or the value was silently rescaled on the way to a decimal reading - and
    // only the number distinguishes them. 12.5 ft must still be 12.5 ft.
    expect(formatMeasurement(12.5, 'ft')).toBe('12.50 ft');
  });

  it('falls through to the decimal tier rather than blanking a zero label', () => {
    setSystem('imperial');
    // Feet-and-inches has nothing to say below 1/16", and an empty string here
    // would erase the annotation's text on the canvas. Pin what the fall-through
    // actually prints: "not empty" would also be satisfied by a stray label with
    // no number in it, which is the failure this test exists to catch.
    expect(formatMeasurement(0, 'm')).toBe('0.00 ft');
    expect(formatMeasurement(1e-6, 'm')).toMatch(/^[\d.]+ ft$/);
  });

  it('never coins an SI-prefixed imperial unit', () => {
    setSystem('imperial');
    // Found by pinning the fall-through above: the linear tiers glue k/m onto
    // whatever label survived conversion, so an imperial reader was shown
    // "millifeet" and "kilofeet". Neither is a unit. Both ends, because the two
    // tiers are separate branches and fixing one leaves the other.
    expect(formatMeasurement(1e-6, 'm')).not.toContain('mft');
    expect(formatMeasurement(1000, 'm')).not.toContain('kft');
    // A unit with no imperial mapping is not converted, so it keeps the
    // prefixing it has always had - this fix must not reach past imperial.
    expect(formatMeasurement(1500, 'pcs')).toContain('kpcs');
  });

  it('carries a whole-foot length without an impossible sixteenth', () => {
    setSystem('imperial');
    // The integer-sixteenths carry is the reason this is not done in floating
    // point: 1.2192 m is exactly 4 ft, and a float path prints 3'-11 16/16".
    expect(formatMeasurement(1.2192, 'm')).toBe("4'-0\"");
  });
});

describe('calibrated path: formatCalibrated', () => {
  it('writes feet and inches when the estimator calibrated in feet', () => {
    // Declared imperial: the unit chosen in the calibration dialog is a
    // statement about this drawing and decides on its own, with no dependence
    // on the global preference.
    expect(formatCalibrated(100, false, { unitsPerPixel: 0.125, unit: 'ft' }))
      .toBe("12'-6\"");
  });

  it('honours a feet calibration even when the app preference is metric', () => {
    setSystem('metric');
    expect(formatCalibrated(100, false, { unitsPerPixel: 0.125, unit: 'ft' }))
      .toBe("12'-6\"");
  });

  it('writes feet and inches for a metric calibration read in imperial', () => {
    setSystem('imperial');
    // 100 px at 0.038227 m/px is the same 12 ft 6 1/2 in as the preset case.
    expect(formatCalibrated(100, false, { unitsPerPixel: 0.038227, unit: 'm' }))
      .toBe("12'-6 1/2\"");
  });

  it('leaves a metric calibration alone for a metric reader', () => {
    setSystem('metric');
    expect(formatCalibrated(100, false, { unitsPerPixel: 0.038227, unit: 'm' }))
      .toBe('3.82 m');
  });

  it('agrees with the preset path on the same physical length', () => {
    // The whole point: one drawing, two formatting paths, one reading.
    setSystem('imperial');
    const preset = formatMeasurement(3.8227, 'm');
    const calibrated = formatCalibrated(100, false, { unitsPerPixel: 0.038227, unit: 'm' });
    expect(calibrated).toBe(preset);
  });

  it('keeps calibrated areas decimal', () => {
    setSystem('imperial');
    expect(formatCalibrated(100, true, { unitsPerPixel: 0.5, unit: 'ft' }))
      .toBe('25.00 ft²');
  });

  it('falls through to the decimal tier on a degenerate value', () => {
    setSystem('imperial');
    expect(formatCalibrated(0, false, { unitsPerPixel: 0.5, unit: 'ft' })).not.toBe('');
  });

  it('converts an inch calibration through metres, not by relabelling', () => {
    // 150 in is 12'-6". Reading the number as feet would print 150'-0".
    expect(formatCalibrated(150, false, { unitsPerPixel: 1, unit: 'in' }))
      .toBe("12'-6\"");
  });
});
