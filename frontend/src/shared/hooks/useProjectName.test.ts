// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useProjectContextStore } from '@/stores/useProjectContextStore';

import { useProjectName } from './useProjectName';

describe('useProjectName', () => {
  beforeEach(() => useProjectContextStore.getState().setActiveProject('p1', 'Harbour Tower'));

  it('gives the name when the page is open on the active project', () => {
    expect(renderHook(() => useProjectName('p1')).result.current).toBe('Harbour Tower');
  });

  it('gives nothing for another project, so the page keeps its generic label', () => {
    expect(renderHook(() => useProjectName('p2')).result.current).toBeNull();
    expect(renderHook(() => useProjectName(undefined)).result.current).toBeNull();
  });
});
