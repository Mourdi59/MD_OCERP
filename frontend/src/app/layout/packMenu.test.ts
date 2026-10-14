// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// What a framework pack does to the menu list, and what it leaves to the user.
import { describe, it, expect } from 'vitest';
import {
  applyPackMenu,
  isMenuMarker,
  packMarker,
  routesOfModules,
  visibleHiddenRoutes,
} from './packMenu';

const ROUTES = {
  '/site-logistics': 'oe_site_logistics',
  '/finance': 'oe_finance',
  '/quantities': ['oe_takeoff', 'oe_boq'],
  '/rfi': 'oe_rfi',
};
const SLUG = 'eleven-areas-framework';
const MODULES = ['oe_site_logistics', 'oe_boq', 'oe_unlisted'];

describe('routesOfModules', () => {
  it('maps modules to their sidebar rows, including a row served by several modules', () => {
    expect(routesOfModules(MODULES, ROUTES)).toEqual(['/site-logistics', '/quantities']);
  });

  it('knows no rows for a module the sidebar does not list', () => {
    expect(routesOfModules(['oe_unlisted'], ROUTES)).toEqual([]);
  });
});

describe('applyPackMenu', () => {
  const run = (hidden: string[], activeSlug: string | null = SLUG) =>
    applyPackMenu({ hidden, activeSlug, packModules: MODULES, routeModules: ROUTES });

  it('hides the pack rows and records the marker, keeping what the user had hidden', () => {
    expect(run(['/rfi'])).toEqual(['/rfi', packMarker(SLUG), '/site-logistics', '/quantities']);
  });

  it('does not repeat a row that is already hidden', () => {
    expect(run(['/site-logistics'])).toEqual(['/site-logistics', packMarker(SLUG), '/quantities']);
  });

  it('leaves the list alone once the marker is there, so a row shown again stays shown', () => {
    expect(run([packMarker(SLUG)])).toBeNull();
    expect(run([packMarker(SLUG), '/quantities'])).toBeNull();
  });

  it('does nothing when no pack is active or the pack does not hide rows', () => {
    expect(run([], null)).toBeNull();
    expect(run([], 'some-country-pack')).toBeNull();
  });
});

describe('markers', () => {
  it('tells the markers from the rows and leaves them out of the hidden count', () => {
    expect(isMenuMarker(packMarker(SLUG))).toBe(true);
    expect(isMenuMarker('/finance')).toBe(false);
    expect(visibleHiddenRoutes(['/finance', packMarker(SLUG), '/rfi'])).toEqual(['/finance', '/rfi']);
  });
});
