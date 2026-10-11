import { useCallback, useRef } from 'react';

/**
 * Lets a submit handler run only once at a time.
 *
 * A disabled or loading button is not enough on its own: the mutation's
 * `isPending` only reaches the DOM after the next render, so a fast double
 * click (or Enter pressed twice) fires two submits and creates two records.
 * The ref flips synchronously, so the second call is dropped before it can
 * reach the server. The lock is released when the task settles, success or
 * failure, so a failed create can be retried.
 *
 * Rejections are swallowed here on purpose: callers pass `mutateAsync`, whose
 * mutation already reports the failure through its own `onError`.
 */
export function useSingleFlight(): (task: () => Promise<unknown>) => void {
  const inFlight = useRef(false);
  return useCallback((task: () => Promise<unknown>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    let pending: Promise<unknown>;
    try {
      pending = task();
    } catch {
      inFlight.current = false;
      return;
    }
    pending.then(
      () => {
        inFlight.current = false;
      },
      () => {
        inFlight.current = false;
      },
    );
  }, []);
}
