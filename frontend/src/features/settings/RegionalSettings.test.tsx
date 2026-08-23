// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// Component tests for <RegionalSettings>.
//
// The panel had no test that rendered it. `numberFormatChoices.test.ts` reads
// this component as a string, which is the right instrument for "the picker
// builds its buttons from one list" and blind to everything else: it cannot
// see which button is lit, and it cannot see what goes on the wire.
//
// Both of those have shipped broken. The currency was PATCHed under `currency`
// while the backend declares `currency_code`, so the field was accepted, thrown
// away, and the chosen currency vanished on the next reload with no error
// anywhere. And the number-format row was measured on the stand with `de-DE`
// stored and every button reading `aria-pressed="false"`, because the account
// column has been written in two vocabularies and the raw string was cast to
// the union instead of translated into it.
//
// So the assertions below are about the two things a screenshot cannot show:
// the payload, and which control is lit. A row that lights nothing is a control
// that cannot describe the product it configures, and a row that lights the
// wrong thing is worse, so both are stated separately.
//
// The i18n mock in src/test/setup.ts returns the key itself when a call passes
// no defaultValue; every string this panel renders passes one, so the labels
// below are the English defaults written in the component.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Only the two calls this panel makes are replaced. The rest of the module
// stays real because <Card> comes from the shared barrel, which drags in every
// component beside it, and several of those read API_BASE at module-eval time.
vi.mock('@/shared/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/shared/lib/api')>('@/shared/lib/api');
  return { ...actual, apiGet: vi.fn(), apiPatch: vi.fn() };
});

import { RegionalSettings } from './RegionalSettings';
import * as api from '@/shared/lib/api';
import { usePreferencesStore, resolveNumberLocale } from '@/stores/usePreferencesStore';
import { formatCurrency } from '@/shared/lib/money';

const apiGetMock = vi.mocked(api.apiGet);
const apiPatchMock = vi.mocked(api.apiPatch);

/** The same sample the buttons are labelled with. Seven digits, because at four
 *  `en-IN` and `en-US` are identical and the labels stop telling anything
 *  apart. */
const SAMPLE = 1234567.89;

const example = (locale: string) => new Intl.NumberFormat(locale).format(SAMPLE);

/**
 * Whitespace, flattened, on both sides of the comparison.
 *
 * German writes the euro after the amount and separates it with a non-breaking
 * space, and `toHaveTextContent` collapses whitespace in the DOM only, leaving
 * the expected string carrying a U+00A0 the DOM side no longer has. The
 * mismatch is invisible in the failure output, since both strings print
 * identically, and it says "the preview did not follow the click" about a
 * preview that followed it perfectly. English hid it: `€1,234,567.89` has no
 * space in it at all.
 */
const flatten = (text: string | null) => (text ?? '').replace(/\s+/g, ' ');

/**
 * What the line under the buttons should read, in a given locale and currency.
 *
 * Built through `formatCurrency`, the module every money surface formats
 * through, because this line's correctness condition is agreement and not
 * well-formedness: its entire job is to show the reader what the product
 * prints. A formatter restated here would be free to drift alongside the one
 * in the component, which is exactly what had happened - see the yen case
 * below.
 */
const previewFor = (locale: string, currency = 'EUR') =>
  flatten(`Amounts across the app now read ${formatCurrency(SAMPLE, currency, locale)}`);

/**
 * What the preview printed before it asked the resolver: a ceiling of two
 * decimals on whatever currency arrived, with no floor under it.
 *
 * Kept so the yen case can require its absence. A test that only says "the
 * preview equals the resolver" passes without ever showing that the resolver
 * and the formatter it replaced disagree on the fixture, and a fixture they
 * agree on proves nothing at all.
 */
const asTheOldPreviewPrinted = (locale: string, currency: string) =>
  flatten(
    new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    }).format(SAMPLE),
  );

/** The store's own defaults, restated so each test starts from a known place.
 *  Zustand is not mocked here on purpose: the panel writes to it and the
 *  writes are half of what these tests check. */
const STORE_DEFAULTS = {
  currency: 'EUR',
  defaultCurrency: 'EUR',
  measurementSystem: 'metric' as const,
  dateFormat: 'auto' as const,
  numberLocale: 'auto' as const,
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RegionalSettings />
    </QueryClientProvider>,
  );
}

/** The block holding one label, its control and any hint under it.
 *  Four ToggleGroups render on this panel and every one of their buttons
 *  carries `aria-pressed`, so an unscoped pressed-button query spans all of
 *  them and says nothing about the row under test. */
function row(label: string): HTMLElement {
  const element = screen.getByText(label).parentElement;
  if (!element) throw new Error(`the "${label}" label has no container`);
  return element;
}

/** The currency control is a searchable dropdown, so a choice takes two
 *  clicks: open, then pick. Before it is opened the row holds exactly one
 *  button, which is the trigger. */
function openCurrencyPicker() {
  fireEvent.click(within(row('Currency')).getByRole('button'));
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  usePreferencesStore.setState(STORE_DEFAULTS);
  apiGetMock.mockResolvedValue({});
  apiPatchMock.mockResolvedValue({});
});

describe('the currency the panel saves', () => {
  it('goes on the wire under the key the backend actually declares', async () => {
    renderPanel();
    await screen.findByText('€ EUR - Euro');

    openCurrencyPicker();
    fireEvent.click(screen.getByRole('button', { name: '$ USD - US Dollar' }));

    await waitFor(() => expect(apiPatchMock).toHaveBeenCalledTimes(1));
    const [path, payload] = apiPatchMock.mock.calls[0] ?? [];
    expect(path).toBe('/v1/users/me/preferences/');
    expect(payload).toEqual({ currency_code: 'USD' });
    // Stated separately from the equality above, because this is the bug: the
    // old payload carried `currency`, which UserPreferencesUpdate does not
    // declare and FastAPI drops without complaining.
    expect(payload).not.toHaveProperty('currency');
  });

  it('reaches both store keys, so the next screen agrees with this one', async () => {
    renderPanel();
    await screen.findByText('€ EUR - Euro');

    openCurrencyPicker();
    fireEvent.click(screen.getByRole('button', { name: '$ USD - US Dollar' }));

    await waitFor(() => {
      const state = usePreferencesStore.getState();
      expect(state.currency).toBe('USD');
      expect(state.defaultCurrency).toBe('USD');
    });
  });

  it('shows what the server persisted rather than a hardcoded euro', async () => {
    apiGetMock.mockResolvedValue({ currency_code: 'BRL' });
    renderPanel();
    // The whole point of reading `currency_code`: an account that saved
    // Brazilian reais gets them back, instead of the panel falling to EUR and
    // quietly reporting a currency nobody chose.
    expect(await screen.findByText('R$ BRL - Brazilian Real')).toBeInTheDocument();
  });
});

describe('the custom currency code', () => {
  it('does not put the sentinel on the wire', async () => {
    renderPanel();
    await screen.findByText('€ EUR - Euro');

    openCurrencyPicker();
    fireEvent.click(screen.getByRole('button', { name: 'Custom...' }));

    expect(screen.getByLabelText('Custom currency code')).toBeInTheDocument();
    // `__custom__` is a marker for this dropdown, not a currency. Sending it
    // would leave every amount in the product formatted against a code `Intl`
    // throws on.
    expect(apiPatchMock).not.toHaveBeenCalled();
  });

  it('saves once when the field is left, not once per keystroke', async () => {
    renderPanel();
    await screen.findByText('€ EUR - Euro');

    openCurrencyPicker();
    fireEvent.click(screen.getByRole('button', { name: 'Custom...' }));

    const input = screen.getByLabelText('Custom currency code');
    fireEvent.change(input, { target: { value: 'x' } });
    fireEvent.change(input, { target: { value: 'xo' } });
    fireEvent.change(input, { target: { value: 'xof' } });
    // Three keystrokes towards one code. A request per keystroke would also
    // mean a success toast per keystroke, and two of the three codes it saved
    // are not what anybody meant.
    expect(apiPatchMock).not.toHaveBeenCalled();

    fireEvent.blur(input);
    await waitFor(() => expect(apiPatchMock).toHaveBeenCalledTimes(1));
    expect(apiPatchMock.mock.calls[0]?.[1]).toEqual({ currency_code: 'XOF' });
  });
});

describe('the number format row', () => {
  it('lights exactly one button, and it is the one the resolver names', async () => {
    renderPanel();
    const buttons = await waitFor(() => {
      const pressed = within(row('Number Format')).getAllByRole('button', { pressed: true });
      expect(pressed).toHaveLength(1);
      return pressed;
    });
    expect(buttons[0]).toHaveTextContent(example(resolveNumberLocale('auto')));
  });

  it('refuses the seeded German pattern on a browser that never chose', async () => {
    // `users.number_format` is NOT NULL and was seeded with the German display
    // pattern for every account created anywhere in the world, so the stored
    // string cannot tell "chose German" from "never chose". A panel that
    // adopted it would light the German button for the entire world.
    expect(resolveNumberLocale('auto')).not.toBe('de-DE');

    apiGetMock.mockResolvedValue({ number_format: '1.234,56' });
    renderPanel();

    const pressed = await waitFor(() => {
      const found = within(row('Number Format')).getAllByRole('button', { pressed: true });
      expect(found).toHaveLength(1);
      return found;
    });
    expect(pressed[0]).not.toHaveTextContent(example('de-DE'));
    expect(pressed[0]).toHaveTextContent(example(resolveNumberLocale('auto')));
  });

  it('keeps the German pattern once this browser has chosen German', async () => {
    // Same stored string, different answer, and the difference is the local
    // choice rather than the value. A browser sitting on an explicit `de-DE`
    // has demonstrably chosen, so the account value is read as agreement.
    usePreferencesStore.setState({ numberLocale: 'de-DE' });
    apiGetMock.mockResolvedValue({ number_format: '1.234,56' });
    renderPanel();

    await waitFor(() => {
      const pressed = within(row('Number Format')).getAllByRole('button', { pressed: true });
      expect(pressed).toHaveLength(1);
      expect(pressed[0]).toHaveTextContent(example('de-DE'));
    });
  });

  it('moves the amount under it when a button is clicked', async () => {
    renderPanel();
    const numberRow = await waitFor(() => row('Number Format'));
    expect(flatten(numberRow.textContent)).toContain(previewFor(resolveNumberLocale('auto')));

    fireEvent.click(within(numberRow).getByRole('button', { name: example('de-DE') }));

    // The preview subscribes to the preference rather than sampling it once.
    // A snapshot reader leaves this line showing the previous format after the
    // click, which is exactly the case where somebody is choosing blind.
    await waitFor(() =>
      expect(flatten(row('Number Format').textContent)).toContain(previewFor('de-DE')),
    );
    expect(apiPatchMock).toHaveBeenCalledWith('/v1/users/me/preferences/', {
      number_format: 'de-DE',
    });
  });

  // The preview is the only figure on this screen that is not a button label,
  // so it is the only one that can be wrong rather than merely unchosen. It
  // built its own formatter and capped every currency at two decimals, which
  // is a claim about currencies rather than a rounding preference: an account
  // holding yen was promised "¥1,234,567.89" while every register in the
  // product rounds that amount to "¥1,234,568". Somebody was being asked to
  // choose a number format against a sample nothing else would produce.
  //
  // Yen because ISO and CLDR agree it has no minor unit, so this case does not
  // rest on the open question about the currencies where they disagree - and a
  // euro fixture would render identically through both formatters and prove
  // nothing.
  it('prints the saved currency the way the money surfaces print it', async () => {
    apiGetMock.mockResolvedValue({ currency_code: 'JPY' });
    renderPanel();

    const locale = resolveNumberLocale('auto');
    await waitFor(() =>
      expect(flatten(row('Number Format').textContent)).toContain(previewFor(locale, 'JPY')),
    );
    expect(asTheOldPreviewPrinted(locale, 'JPY')).not.toBe(
      flatten(formatCurrency(SAMPLE, 'JPY', locale)),
    );
    expect(flatten(row('Number Format').textContent)).not.toContain(
      asTheOldPreviewPrinted(locale, 'JPY'),
    );
  });
});

describe('the date format row', () => {
  it('describes what dates render with, not what the account column holds', async () => {
    // The column is free-form and NOT NULL, and the regional packs ship orders
    // this toggle has no button for. Reading it raw lights nothing while the
    // product is quite definitely rendering dates in some order.
    apiGetMock.mockResolvedValue({ date_format: 'DD/MM/YYYY' });
    renderPanel();

    await waitFor(() => {
      const pressed = within(row('Date Format')).getAllByRole('button', { pressed: true });
      expect(pressed).toHaveLength(1);
      expect(pressed[0]).toHaveTextContent('Automatic');
    });
  });

  it('lights the order the store carries', async () => {
    usePreferencesStore.setState({ dateFormat: 'YYYY-MM-DD' });
    renderPanel();

    await waitFor(() => {
      const pressed = within(row('Date Format')).getAllByRole('button', { pressed: true });
      expect(pressed).toHaveLength(1);
      expect(pressed[0]).toHaveTextContent('2026-04-07');
    });
  });
});

describe('the rows that were never in doubt', () => {
  it('still lights one measurement system and one paper size', async () => {
    apiGetMock.mockResolvedValue({ measurement_system: 'imperial', paper_size: 'Letter' });
    renderPanel();

    await waitFor(() => {
      const units = within(row('Measurement System')).getAllByRole('button', { pressed: true });
      expect(units).toHaveLength(1);
      expect(units[0]).toHaveTextContent('Imperial (ft, lb)');
    });
    const paper = within(row('Paper Size')).getAllByRole('button', { pressed: true });
    expect(paper).toHaveLength(1);
    expect(paper[0]).toHaveTextContent('Letter (8.5 x 11 in)');
  });
});
