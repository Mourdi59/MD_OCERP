import { describe, expect, it } from 'vitest';
import { importToastTone } from './importToastTone';

describe('importToastTone', () => {
  it('is a success only when something landed', () => {
    expect(importToastTone(3)).toBe('success');
    expect(importToastTone(1)).toBe('success');
  });

  it('warns when nothing landed or the count is missing', () => {
    expect(importToastTone(0)).toBe('warning');
    expect(importToastTone(undefined)).toBe('warning');
    expect(importToastTone(null)).toBe('warning');
  });
});
