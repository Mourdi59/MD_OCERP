// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { usePreferencesStore } from './usePreferencesStore';
import { apiGet } from '@/shared/lib/api';

vi.mock('@/shared/lib/api', () => ({ apiGet: vi.fn() }));
const mockApiGet = vi.mocked(apiGet);

describe('usePreferencesStore', () => {
  beforeEach(() => {
    localStorage.clear();
    mockApiGet.mockReset();
    usePreferencesStore.getState().resetPreferences();
  });

  it('should have correct default values', () => {
    const state = usePreferencesStore.getState();
    expect(state.currency).toBe('EUR');
    expect(state.measurementSystem).toBe('metric');
    // 'auto' = follow the UI language. See the date-format block below.
    expect(state.dateFormat).toBe('auto');
    // 'auto' = follow the UI language, same as dateFormat above. It used to be
    // a hardcoded 'de-DE', which is what put the money surfaces on German
    // separators inside an English UI while every other number followed the
    // language. See `numbersAgreeAcrossSurfaces.test.tsx`.
    expect(state.numberLocale).toBe('auto');
    expect(state.vatRate).toBe(19);
  });

  it('should update currency via setPreference', () => {
    usePreferencesStore.getState().setPreference('currency', 'GBP');
    expect(usePreferencesStore.getState().currency).toBe('GBP');
  });

  it('should update measurement system via setPreference', () => {
    usePreferencesStore.getState().setPreference('measurementSystem', 'imperial');
    expect(usePreferencesStore.getState().measurementSystem).toBe('imperial');
  });

  it('should update date format via setPreference', () => {
    usePreferencesStore.getState().setPreference('dateFormat', 'MM/DD/YYYY');
    expect(usePreferencesStore.getState().dateFormat).toBe('MM/DD/YYYY');
  });

  it('should update number locale via setPreference', () => {
    usePreferencesStore.getState().setPreference('numberLocale', 'en-US');
    expect(usePreferencesStore.getState().numberLocale).toBe('en-US');
  });

  it('should update VAT rate via setPreference', () => {
    usePreferencesStore.getState().setPreference('vatRate', 20);
    expect(usePreferencesStore.getState().vatRate).toBe(20);
  });

  it('should update multiple preferences at once', () => {
    usePreferencesStore.getState().setPreferences({ currency: 'USD', vatRate: 0 });
    const state = usePreferencesStore.getState();
    expect(state.currency).toBe('USD');
    expect(state.vatRate).toBe(0);
  });

  it('should reset to defaults', () => {
    usePreferencesStore.getState().setPreference('currency', 'CHF');
    usePreferencesStore.getState().resetPreferences();
    expect(usePreferencesStore.getState().currency).toBe('EUR');
  });

  it('should format currency correctly', () => {
    const { formatCurrency } = usePreferencesStore.getState();
    const result = formatCurrency(1234.56);
    expect(result).toContain('1');
    expect(result).toContain('234');
  });

  it('should format numbers correctly', () => {
    const { formatNumber } = usePreferencesStore.getState();
    const result = formatNumber(1234.567, 2);
    expect(result).toContain('1');
    expect(result).toContain('234');
  });

  it('should persist to localStorage', () => {
    usePreferencesStore.getState().setPreference('currency', 'JPY');
    const stored = JSON.parse(localStorage.getItem('oe_preferences') || '{}');
    expect(stored.currency).toBe('JPY');
  });

  describe('hydrateFromServer (issue #335)', () => {
    it('applies the account regional prefs and writes them through to localStorage', async () => {
      mockApiGet.mockResolvedValueOnce({
        measurement_system: 'imperial',
        date_format: 'MM/DD/YYYY',
        number_format: '1,234.56',
        currency_code: 'USD',
      });
      await usePreferencesStore.getState().hydrateFromServer();
      const s = usePreferencesStore.getState();
      expect(s.measurementSystem).toBe('imperial');
      expect(s.dateFormat).toBe('MM/DD/YYYY');
      expect(s.numberLocale).toBe('en-US'); // '1,234.56' pattern -> en-US
      expect(s.currency).toBe('USD');
      expect(s.defaultCurrency).toBe('USD');
      expect(mockApiGet).toHaveBeenCalledWith('/v1/users/me/preferences/');
      const stored = JSON.parse(localStorage.getItem('oe_preferences') || '{}');
      expect(stored.measurementSystem).toBe('imperial');
    });

    it('skips a server value that is not a known option, keeping the default', async () => {
      mockApiGet.mockResolvedValueOnce({
        measurement_system: 'martian', // not in the union
        currency_code: '', // "not chosen" on the account
      });
      await usePreferencesStore.getState().hydrateFromServer();
      const s = usePreferencesStore.getState();
      expect(s.measurementSystem).toBe('metric');
      expect(s.currency).toBe('EUR');
    });

    it('swallows a server error and leaves the offline cache untouched', async () => {
      usePreferencesStore.getState().setPreference('measurementSystem', 'imperial');
      mockApiGet.mockRejectedValueOnce(new Error('offline'));
      await expect(usePreferencesStore.getState().hydrateFromServer()).resolves.toBeUndefined();
      expect(usePreferencesStore.getState().measurementSystem).toBe('imperial');
    });
  });

  // The date format is the one preference whose stored value cannot be trusted
  // at face value. `users.date_format` is NOT NULL and defaulted to
  // 'DD.MM.YYYY' long before any surface read the preference, so every account
  // carries that value whether or not a human ever chose it. Hydration - not
  // the store default - is therefore where a naive wiring would flip existing
  // users to numeric day-first dates on their next sign-in.
  describe('date format hydration', () => {
    it('reads the legacy account default as "never chose" and stays automatic', async () => {
      mockApiGet.mockResolvedValueOnce({ date_format: 'DD.MM.YYYY' });
      await usePreferencesStore.getState().hydrateFromServer();
      expect(usePreferencesStore.getState().dateFormat).toBe('auto');
    });

    it('adopts an order the account default could never have produced', async () => {
      mockApiGet.mockResolvedValueOnce({ date_format: 'YYYY-MM-DD' });
      await usePreferencesStore.getState().hydrateFromServer();
      expect(usePreferencesStore.getState().dateFormat).toBe('YYYY-MM-DD');
    });

    it('adopts an explicit automatic from the account', async () => {
      usePreferencesStore.getState().setPreference('dateFormat', 'MM/DD/YYYY');
      mockApiGet.mockResolvedValueOnce({ date_format: 'auto' });
      await usePreferencesStore.getState().hydrateFromServer();
      expect(usePreferencesStore.getState().dateFormat).toBe('auto');
    });

    it('keeps day-first when this browser chose it, rather than reading it as the default', async () => {
      usePreferencesStore.getState().setPreference('dateFormat', 'DD.MM.YYYY');
      mockApiGet.mockResolvedValueOnce({ date_format: 'DD.MM.YYYY' });
      await usePreferencesStore.getState().hydrateFromServer();
      expect(usePreferencesStore.getState().dateFormat).toBe('DD.MM.YYYY');
    });

    it('leaves an order outside the vocabulary alone, landing on automatic', async () => {
      // The regional packs also ship DD/MM/YYYY and YYYY/MM/DD, which this
      // toggle has no button for.
      mockApiGet.mockResolvedValueOnce({ date_format: 'DD/MM/YYYY' });
      await usePreferencesStore.getState().hydrateFromServer();
      expect(usePreferencesStore.getState().dateFormat).toBe('auto');
    });
  });
});
