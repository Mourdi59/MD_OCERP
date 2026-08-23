// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// The embedder card's install sentence used to come from the backend as
// English prose and was rendered verbatim, so on the one path where it
// appeared the card left the reader's language for every locale but English.
// It now comes from a reason code the UI translates.
//
// A reason code is only safe to ship if the frontend degrades in the right
// direction at each of the ways it can fail to recognise one, and the case
// that decides it is the old backend: a frontend that ignores an unrecognised
// shape and renders nothing is worse than one showing English. So these pin
// all four rungs of the chain, including the two where nothing is recognised,
// and the invariant that matters more than any of them - the sentence is
// never empty.

import { describe, it, expect } from 'vitest';
import type { TFunction } from 'i18next';

import { installSentence } from '../EmbedderStatusCard';
import type { EmbedderStatus } from '../api';

/** Stand-in for i18next that reports which key was asked for, so a test can
 *  tell a translated sentence from prose that merely reads like one. */
const t = ((key: string, fallback?: string) => `[${key}]${fallback ?? ''}`) as unknown as TFunction;

function status(over: Partial<EmbedderStatus> = {}): EmbedderStatus {
  return {
    installed: false,
    model_loaded: false,
    model_name: 'BAAI/bge-m3',
    model_id_runtime: 'gpahal/bge-m3-onnx-int8',
    license: 'MIT',
    open_source: true,
    homepage: 'https://huggingface.co/BAAI/bge-m3',
    languages_supported: 100,
    size_mb_int8: 700,
    size_mb_fp32: 2300,
    int8_mode: true,
    pip_command: 'pip install --upgrade openconstructionerp[semantic]',
    missing_packages: ['FlagEmbedding'],
    extra_name: 'semantic',
    ...over,
  };
}

const PROSE = 'This is the desktop build. It ships a fixed set of packages and has no pip.';

describe('installSentence', () => {
  it('translates the frozen-bundle reason instead of quoting the backend', () => {
    const out = installSentence(
      status({ pip_command: '', install_hint: PROSE, install_hint_code: 'frozen_no_extra' }),
      t,
    );
    expect(out).toContain('match_elements.embedder_required_frozen');
    // The whole point: the prose is present in the payload and NOT used.
    expect(out).not.toContain(PROSE);
  });

  it('uses the general sentence for the pip reason', () => {
    const out = installSentence(status({ install_hint_code: 'pip', install_hint: PROSE }), t);
    expect(out).toContain('match_elements.embedder_required_body');
    expect(out).not.toContain(PROSE);
  });

  it('falls back to the backend prose for a reason code it has never heard of', () => {
    // A backend newer than this build. Rendering nothing here would be the
    // one outcome worse than English.
    const out = installSentence(
      status({ pip_command: '', install_hint: PROSE, install_hint_code: 'some_future_reason' }),
      t,
    );
    expect(out).toBe(PROSE);
  });

  it('falls back to the backend prose when there is no reason code at all', () => {
    // The backend as it stands today: prose, no code.
    const out = installSentence(status({ pip_command: '', install_hint: PROSE }), t);
    expect(out).toBe(PROSE);
  });

  it('shows the general translated sentence on a backend that sends neither field', () => {
    // A backend older than `install_hint` itself, which is what HEAD serves.
    const out = installSentence(status(), t);
    expect(out).toContain('match_elements.embedder_required_body');
  });

  it('never returns an empty sentence, whatever the payload says', () => {
    const payloads: Partial<EmbedderStatus>[] = [
      {},
      { install_hint: '' },
      { install_hint: '   ' },
      { pip_command: '', install_hint: '' },
      { pip_command: '', install_hint: '', install_hint_code: '' },
      { install_hint_code: 'pip' },
      { install_hint_code: 'frozen_no_extra' },
      { install_hint_code: 'unknown', install_hint: '' },
      { install_hint_code: 'unknown', install_hint: '  ' },
    ];
    for (const over of payloads) {
      expect(installSentence(status(over), t).trim().length).toBeGreaterThan(0);
    }
  });
});
