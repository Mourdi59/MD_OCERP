// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// #436 - the client aborts, the server keeps embedding and commits, and the
// user is told the import failed. The fix has two halves: the long budget
// (guarded in vectorIndexLongBudget.test.ts) and this fallback, which watches
// the vector count after an abort so work that landed is reported as success.
//
// The hard requirement runs BOTH ways. A user whose indexing succeeded must
// not be told it failed - and a user whose indexing did not succeed must not
// be told it worked, which is why an unknown baseline refuses to claim
// success instead of guessing from a count it cannot interpret.
//
// Run: npx vitest run --pool=forks src/features/costs/__tests__/vectorIndexPollFallback.test.ts

import { describe, it, expect, vi } from 'vitest';
import { ApiError } from '@/shared/lib/api';
import {
  pollVectorIndexLanded,
  mayStillBeRunning,
  VECTOR_POLL_ATTEMPTS,
  VECTOR_READY_MIN_COUNT,
} from '../vectorIndex';

/** No real waiting: the production cadence is 7 attempts 10s apart. */
const noSleep = () => Promise.resolve();

/** Counts the vector DB reports on successive polls. */
function counter(...values: Array<number | null>): () => Promise<number | null> {
  let i = 0;
  return () => Promise.resolve(values[Math.min(i++, values.length - 1)] ?? null);
}

describe('pollVectorIndexLanded - the server finished after the client gave up', () => {
  it('reports success once the count rises above the pre-request baseline', async () => {
    const landed = await pollVectorIndexLanded({
      baseline: 0,
      readCount: counter(0, 0, 55_719),
      sleep: noSleep,
    });
    expect(landed).toBe(55_719);
  });

  it('measures against the baseline, not against zero', async () => {
    // A second region indexed on top of an install that already had vectors.
    // 55,719 was already there before the request - it proves nothing.
    const stuck = await pollVectorIndexLanded({
      baseline: 55_719,
      readCount: counter(55_719),
      sleep: noSleep,
    });
    expect(stuck).toBeNull();

    const grew = await pollVectorIndexLanded({
      baseline: 55_719,
      readCount: counter(55_719, 111_438),
      sleep: noSleep,
    });
    expect(grew).toBe(111_438);
  });

  it('refuses to claim success when the baseline could not be read', async () => {
    // The status endpoint was unreachable before the write, so a healthy-looking
    // count afterwards cannot be attributed to this run. Reporting success here
    // is the same lie as the timeout it replaces, pointing the other way.
    const landed = await pollVectorIndexLanded({
      baseline: null,
      readCount: counter(55_719),
      sleep: noSleep,
    });
    expect(landed).toBeNull();
  });

  it('holds out for the readiness threshold the BOQ editor gates AI features on', async () => {
    // vectorReady in BOQEditorPage is `vectors_count > 100`. Announcing "Vector
    // Database Ready" at 40 vectors bounces the user straight back to the setup
    // modal on their next AI action.
    const tooFew = await pollVectorIndexLanded({
      baseline: 0,
      minCount: VECTOR_READY_MIN_COUNT,
      readCount: counter(40),
      sleep: noSleep,
    });
    expect(tooFew).toBeNull();

    const enough = await pollVectorIndexLanded({
      baseline: 0,
      minCount: VECTOR_READY_MIN_COUNT,
      readCount: counter(40, 4_000),
      sleep: noSleep,
    });
    expect(enough).toBe(4_000);
  });

  it('gives up after the poll budget and does not hang', async () => {
    const readCount = vi.fn(() => Promise.resolve(0));
    const sleep = vi.fn(() => Promise.resolve());
    const landed = await pollVectorIndexLanded({ baseline: 0, readCount, sleep });
    expect(landed).toBeNull();
    expect(readCount).toHaveBeenCalledTimes(VECTOR_POLL_ATTEMPTS);
    // No trailing sleep after the last look.
    expect(sleep).toHaveBeenCalledTimes(VECTOR_POLL_ATTEMPTS - 1);
  });

  it('survives a status endpoint that is transiently unreadable', async () => {
    const landed = await pollVectorIndexLanded({
      baseline: 0,
      readCount: counter(null, null, 55_719),
      sleep: noSleep,
    });
    expect(landed).toBe(55_719);
  });

  it('stops polling when the view unmounts', async () => {
    const readCount = vi.fn(() => Promise.resolve(0));
    const landed = await pollVectorIndexLanded({
      baseline: 0,
      isMounted: () => false,
      readCount,
      sleep: noSleep,
    });
    expect(landed).toBeNull();
    expect(readCount).not.toHaveBeenCalled();
  });
});

describe('mayStillBeRunning - only poll when the server plausibly kept working', () => {
  it('recognises our own client timeout', () => {
    // The exact shape api.ts throws when its abort controller fires.
    const timeout = new Error('The request took too long and was cancelled.') as Error & {
      isTimeout?: boolean;
    };
    timeout.isTimeout = true;
    expect(mayStillBeRunning(timeout)).toBe(true);
  });

  it('recognises a bare AbortError and a gateway timeout', () => {
    const aborted = new Error('aborted');
    aborted.name = 'AbortError';
    expect(mayStillBeRunning(aborted)).toBe(true);
    expect(mayStillBeRunning(new ApiError(504, 'Gateway Timeout', undefined))).toBe(true);
    expect(mayStillBeRunning(new ApiError(502, 'Bad Gateway', undefined))).toBe(true);
  });

  it('does not poll on an answer the server actually gave', () => {
    // 503 is the vector backend reporting itself unavailable - a real answer.
    // Polling for a minute would only delay an honest failure.
    expect(
      mayStillBeRunning(new ApiError(503, 'Service Unavailable', { indexed: 0, message: 'no embedder' })),
    ).toBe(false);
    expect(mayStillBeRunning(new ApiError(403, 'Forbidden', undefined))).toBe(false);
    expect(mayStillBeRunning(new Error('Failed to fetch'))).toBe(false);
    expect(mayStillBeRunning(null)).toBe(false);
  });
});

describe('a partially committed index is not a ready index', () => {
  it('refuses to announce success on a count that rose but has not arrived', async () => {
    // The backend commits in batches, so the count leaves the baseline long
    // before the catalogue is embedded. `baseline + 1` is enough to prove the
    // server kept working; it is NOT enough to tell the user the index is
    // ready. Without the threshold this poll announces a finished index on the
    // first batch, and the next AI action bounces the user straight back into
    // the setup modal they had just dismissed.
    const partial = await pollVectorIndexLanded({
      baseline: 0,
      minCount: VECTOR_READY_MIN_COUNT,
      readCount: counter(12, 40, 88, 100),
      sleep: noSleep,
    });
    expect(partial).toBeNull();

    // 100 exactly is still not ready - `vectorReady` in the BOQ editor reads
    // `vectors_count > 100`, so the comparison here has to be strict too.
    const onTheLine = await pollVectorIndexLanded({
      baseline: 0,
      minCount: VECTOR_READY_MIN_COUNT,
      readCount: counter(100),
      sleep: noSleep,
    });
    expect(onTheLine).toBeNull();

    // The control, so the two assertions above are not just proving that this
    // poll never succeeds: the same series, run to a batch past the threshold.
    const arrived = await pollVectorIndexLanded({
      baseline: 0,
      minCount: VECTOR_READY_MIN_COUNT,
      readCount: counter(12, 40, 88, 101),
      sleep: noSleep,
    });
    expect(arrived).toBe(101);
  });

  it('counts from the baseline and the threshold at once, not either alone', async () => {
    // An install that already holds a full index and is having a second region
    // added. Every count here clears the threshold; none of them clears the
    // baseline, and the run added nothing. Passing minCount must not turn the
    // baseline comparison into an OR.
    const nothingLanded = await pollVectorIndexLanded({
      baseline: 55_719,
      minCount: VECTOR_READY_MIN_COUNT,
      readCount: counter(55_719),
      sleep: noSleep,
    });
    expect(nothingLanded).toBeNull();
  });
});
