import { describe, it, expect } from 'vitest';
import { resolveRouteAfterProjectSwitch } from './Header';

const OLD = '11111111-1111-4111-8111-111111111111';
const NEW = '22222222-2222-4222-8222-222222222222';
const REC = '33333333-3333-4333-8333-333333333333';

describe('resolveRouteAfterProjectSwitch', () => {
  it('swaps the project of a project-scoped module page', () => {
    expect(resolveRouteAfterProjectSwitch(`/projects/${OLD}/boq`, NEW)).toBe(`/projects/${NEW}/boq`);
    expect(resolveRouteAfterProjectSwitch(`/projects/${OLD}`, NEW)).toBe(`/projects/${NEW}`);
  });

  it('keeps a static sub-page of the module', () => {
    expect(resolveRouteAfterProjectSwitch(`/projects/${OLD}/clash/profiles`, NEW)).toBe(
      `/projects/${NEW}/clash/profiles`,
    );
  });

  it('drops a record of the old project from a project-scoped route', () => {
    expect(resolveRouteAfterProjectSwitch(`/projects/${OLD}/bim/${REC}`, NEW)).toBe(`/projects/${NEW}/bim`);
    expect(resolveRouteAfterProjectSwitch(`/projects/${OLD}/contracts/claims/${REC}`, NEW)).toBe(
      `/projects/${NEW}/contracts`,
    );
  });

  it('sends a module detail route back to its list', () => {
    expect(resolveRouteAfterProjectSwitch(`/bim/${REC}`, NEW)).toBe('/bim');
    expect(resolveRouteAfterProjectSwitch(`/accommodation/${REC}`, NEW)).toBe('/accommodation');
    expect(resolveRouteAfterProjectSwitch(`/schedule/${REC}/cpm`, NEW)).toBe('/schedule');
  });

  it('leaves a page without a record alone', () => {
    expect(resolveRouteAfterProjectSwitch('/boq', NEW)).toBeNull();
    expect(resolveRouteAfterProjectSwitch('/bim', NEW)).toBeNull();
  });
});
