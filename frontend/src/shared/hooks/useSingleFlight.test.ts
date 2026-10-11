import { describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useSingleFlight } from './useSingleFlight';

function deferred() {
  let resolve!: () => void;
  let reject!: (e: Error) => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useSingleFlight', () => {
  it('drops a second call while the first is still pending', async () => {
    const { result } = renderHook(() => useSingleFlight());
    const d = deferred();
    const task = vi.fn(() => d.promise);
    result.current(task);
    result.current(task);
    expect(task).toHaveBeenCalledTimes(1);
    await act(async () => {
      d.resolve();
      await d.promise;
    });
    result.current(task);
    expect(task).toHaveBeenCalledTimes(2);
  });

  it('releases the lock after a failure so the user can retry', async () => {
    const { result } = renderHook(() => useSingleFlight());
    const d = deferred();
    const failing = vi.fn(() => d.promise);
    result.current(failing);
    await act(async () => {
      d.reject(new Error('boom'));
      await d.promise.catch(() => undefined);
    });
    const retry = vi.fn(() => Promise.resolve());
    result.current(retry);
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('releases the lock when the task throws synchronously', () => {
    const { result } = renderHook(() => useSingleFlight());
    result.current(() => {
      throw new Error('sync');
    });
    const next = vi.fn(() => Promise.resolve());
    result.current(next);
    expect(next).toHaveBeenCalledTimes(1);
  });
});
