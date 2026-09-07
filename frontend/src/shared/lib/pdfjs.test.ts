// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The contract between the PDF.js binding and the assets the build publishes.
 *
 * PDF.js only checks `wasmUrl` and `iccUrl` when a document is opened, and it
 * only fetches from them when a page carries a JBIG2 or JPEG 2000 image, so a
 * wrong URL passes every type check and every viewer test and shows up as a
 * blank scanned drawing on a user's machine. These tests pin the shape both
 * sides agree on: the directory is versioned, it lives under `/assets/`, and
 * every prefix ends in the slash PDF.js insists on.
 */
import { describe, expect, it, vi } from 'vitest';

const getDocument = vi.fn(() => ({ promise: Promise.resolve() }));

vi.mock('pdfjs-dist/legacy/build/pdf.mjs', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  version: '6.1.200',
  getDocument: (...args: unknown[]) => getDocument(...(args as [])),
}));

describe('pdfjs binding', () => {
  it('publishes the runtime assets under a versioned directory below /assets/', async () => {
    const { PDFJS_ASSET_ROOT } = await import('./pdfjs');
    expect(PDFJS_ASSET_ROOT).toBe('/assets/pdfjs/6.1.200/');
  });

  it('points the worker at the bundled legacy worker, never a CDN', async () => {
    const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
    await import('./pdfjs');
    expect(pdfjs.GlobalWorkerOptions.workerSrc).toMatch(/pdf\.worker\.min\.mjs$/);
    expect(pdfjs.GlobalWorkerOptions.workerSrc).not.toMatch(/^https?:\/\/(cdn|unpkg|cdnjs)/);
  });

  it('opens every document with the wasm and ICC directories, each ending in a slash', async () => {
    const { openPdf } = await import('./pdfjs');
    const bytes = new ArrayBuffer(8);
    openPdf(bytes);
    expect(getDocument).toHaveBeenCalledTimes(1);
    const [params] = getDocument.mock.calls[0] as unknown as [
      { data: ArrayBuffer; wasmUrl: string; iccUrl: string },
    ];
    expect(params.data).toBe(bytes);
    expect(params.wasmUrl).toBe('/assets/pdfjs/6.1.200/wasm/');
    expect(params.iccUrl).toBe('/assets/pdfjs/6.1.200/iccs/');
  });

  it('closes a document through its loading task and tolerates nothing loaded', async () => {
    const { closePdf } = await import('./pdfjs');
    const destroy = vi.fn(() => Promise.resolve());
    closePdf({ loadingTask: { destroy } } as unknown as Parameters<typeof closePdf>[0]);
    expect(destroy).toHaveBeenCalledTimes(1);
    expect(() => closePdf(null)).not.toThrow();
    expect(() => closePdf(undefined)).not.toThrow();
  });
});
