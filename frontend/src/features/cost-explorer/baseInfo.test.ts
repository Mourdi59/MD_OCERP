// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { describe, expect, it } from 'vitest';
import { baseCurrencies, describeBases, readableRegion } from './baseInfo';
import type { BaseCatalog, BaseFamily, BaseVariant } from '@/features/costs/baseCatalog';

function variant(over: Partial<BaseVariant> & { region: string }): BaseVariant {
  return {
    variant_id: over.region,
    base_region: over.region,
    market_catalog: '',
    active: false,
    market: '',
    city: '',
    language: '',
    lang_code: '',
    currency: '',
    flag: '',
    positions: 0,
    bundled: false,
    coefficient: false,
    loaded: false,
    loaded_positions: 0,
    ...over,
  };
}

function family(name: string, norm: string, variants: BaseVariant[]): BaseFamily {
  return {
    key: name.toLowerCase(),
    name,
    norm_system: norm,
    origin: '',
    origin_flag: '',
    description: '',
    market_count: variants.length,
    repriceable_markets: 0,
    positions: 0,
    loaded_count: 0,
    variants,
  };
}

const catalog: BaseCatalog = {
  repo: 'x/y',
  total_bases: 3,
  total_families: 2,
  loaded_regions: [],
  families: [
    family('Global CWICR', 'GESN / FER / TER', [
      variant({ region: 'DE_BERLIN', market: 'Germany / DACH', city: 'Berlin', currency: 'EUR', flag: 'de' }),
    ]),
    family('China Dinge', 'Dinge', [
      variant({ region: 'ZH_CHINA', market: 'China', city: 'National', currency: 'CNY', flag: 'cn' }),
      // A market card: it reprices the China base into London, so its own
      // `region` is a market id that never lands in oe_costs_item.region.
      variant({
        region: 'GB_LONDON',
        variant_id: 'ZH_CHINA:GB_LONDON_en',
        base_region: 'ZH_CHINA',
        market_catalog: 'GB_LONDON_en',
        market: 'China base, London prices',
        currency: 'GBP',
        flag: 'gb',
      }),
    ]),
  ],
};

describe('readableRegion', () => {
  it('renders a CC_CITY id as a place', () => {
    expect(readableRegion('DE_BERLIN')).toBe('DE / Berlin');
    expect(readableRegion('RU_STPETERSBURG')).toBe('RU / Stpetersburg');
  });

  it('echoes back an id it cannot split', () => {
    expect(readableRegion('CUSTOM')).toBe('CUSTOM');
    expect(readableRegion('')).toBe('');
  });
});

describe('describeBases', () => {
  it('decorates a loaded base from the registry', () => {
    const [b] = describeBases(['DE_BERLIN'], catalog, { DE_BERLIN: 55719 });
    expect(b).toMatchObject({
      region: 'DE_BERLIN',
      market: 'Germany / DACH',
      city: 'Berlin',
      currency: 'EUR',
      flag: 'de',
      positions: 55719,
      normSystem: 'GESN / FER / TER',
      known: true,
    });
  });

  it('prefers the card whose own id is the id a load lands under', () => {
    // Both cards of the China family carry base_region ZH_CHINA; only the home
    // card names a base id that can appear as a loaded region. Picking the
    // market card here would print GBP over a CNY catalogue.
    const [b] = describeBases(['ZH_CHINA'], catalog, {});
    expect(b?.currency).toBe('CNY');
    expect(b?.market).toBe('China');
  });

  it('keeps a base the registry does not carry, and invents nothing for it', () => {
    const [b] = describeBases(['DE_HAMBURG'], catalog, { DE_HAMBURG: 1200 });
    expect(b).toMatchObject({
      region: 'DE_HAMBURG',
      market: 'DE / Hamburg',
      currency: '',
      positions: 1200,
      known: false,
    });
  });

  it('reports an unmeasured size as null rather than as zero', () => {
    const [b] = describeBases(['DE_HAMBURG'], catalog, {});
    expect(b?.positions).toBeNull();
  });

  it('renders every base before the catalog arrives', () => {
    const out = describeBases(['DE_BERLIN', 'ZH_CHINA'], undefined, {});
    expect(out.map((b) => b.market)).toEqual(['DE / Berlin', 'ZH / China']);
    expect(out.every((b) => !b.known)).toBe(true);
  });

  it('keeps the order of the base id list', () => {
    const out = describeBases(['ZH_CHINA', 'DE_BERLIN'], catalog, {});
    expect(out.map((b) => b.region)).toEqual(['ZH_CHINA', 'DE_BERLIN']);
  });
});

describe('baseCurrencies', () => {
  it('lists distinct currencies once, in first-seen order', () => {
    const bases = describeBases(['ZH_CHINA', 'DE_BERLIN', 'DE_HAMBURG'], catalog, {});
    expect(baseCurrencies(bases)).toEqual(['CNY', 'EUR']);
  });
});
