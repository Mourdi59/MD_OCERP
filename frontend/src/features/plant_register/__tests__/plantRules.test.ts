// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The plant register rules as plain functions: reading a server refusal,
// what a draft is missing, what a draft sends, which step a state offers and
// where an item sits on the timeline.

import { describe, expect, it } from 'vitest';

import { ApiError } from '@/shared/lib/api';

import { plantErrorCode, plantErrorMessage, plantViolations } from '../api';
import { catalogueName, errorText, humanizeCode, type LabelContext } from '../labels';
import { longLeadOrder } from '../LongLeadTimeline';
import {
  buildTimeline,
  emptyItemDraft,
  emptyQuoteDraft,
  emptySlotDraft,
  filterCounts,
  filterItems,
  itemChanges,
  itemDraftOf,
  itemProblems,
  nextManualStep,
  nextSpareStep,
  orderDateOpen,
  paperProblems,
  quoteProblems,
  slotProblems,
  slugCode,
  toCreateInput,
  toPaperInput,
  toQuoteInput,
  toSlotInput,
  type PaperDraft,
} from '../rules';
import { TODAY, catalogue, item, refusal } from './fixtures';
import { enT } from './i18nMock';

describe('reading a refusal', () => {
  it('takes the code, the message and every violation from a coded refusal', () => {
    const err = refusal(422, 'transition_blocked', 'The state change is blocked by several rules.', [
      { code: 'route_missing', reason: 'no route', message_key: 'plant.errors.route_missing' },
      { code: 'delivery_limit_gap', reason: 'commission', message_key: 'plant.errors.delivery_limit_gap' },
    ]);
    expect(plantErrorCode(err)).toBe('transition_blocked');
    expect(plantErrorMessage(err)).toBe('The state change is blocked by several rules.');
    expect(plantViolations(err).map((v) => v.code)).toEqual(['route_missing', 'delivery_limit_gap']);
  });

  it('reads no code from a schema error, whose detail is a list', () => {
    const err = new ApiError(422, 'Unprocessable', { detail: [{ loc: ['body', 'quantity'], msg: 'send decimals as strings' }] });
    expect(plantErrorCode(err)).toBeNull();
    expect(plantViolations(err)).toEqual([]);
  });

  it('reads no code from a failure that is not an API answer', () => {
    expect(plantErrorCode(new Error('network down'))).toBeNull();
    expect(plantErrorMessage(null)).toBeNull();
  });

  it('drops a violation without a code instead of rendering an empty line', () => {
    const err = new ApiError(422, 'Refused', { detail: { code: 'transition_blocked', violations: [{ reason: 'x' }, null, { code: 'route_missing' }] } });
    expect(plantViolations(err)).toEqual([{ code: 'route_missing' }]);
  });
});

describe('labels', () => {
  const none: LabelContext = { t: enT, language: 'en', exists: () => false };
  const all: LabelContext = { t: enT, language: 'de-AT', exists: () => true };

  it('names an entry by the key the catalogue gives when the locale has it', () => {
    expect(catalogueName(all, catalogue(), 'component_classes', 'power_transformer')).toBe('Power transformer');
    // N+1 cannot be derived from its code; only the catalogue knows its key.
    expect(catalogueName(all, catalogue(), 'redundancy_schemes', 'N+1')).toBe('N+1');
  });

  it("uses a tenant catalogue's own text in the reader's language", () => {
    const cat = catalogue({ parties: [{ code: 'fit_out', labels: { en: 'Fit-out contractor', de: 'Ausbauunternehmer' } }] });
    expect(catalogueName(none, cat, 'parties', 'fit_out')).toBe('Fit-out contractor');
    expect(catalogueName({ ...none, language: 'de-AT' }, cat, 'parties', 'fit_out')).toBe('Ausbauunternehmer');
  });

  it('never shows a raw key: an unknown code is made readable', () => {
    expect(catalogueName(none, catalogue(), 'parties', 'facility_manager')).toBe('Facility manager');
    expect(catalogueName(none, null, 'redundancy_schemes', '2N+1')).toBe('2N+1');
    expect(catalogueName(none, catalogue(), 'parties', '')).toBe('');
  });

  it('falls back to the shipped key for a code the pinned catalogue does not list', () => {
    expect(catalogueName(all, catalogue(), 'lead_time_sources', 'catalogue_default')).toBe('Catalogue default');
  });

  it('gives a refusal code a sentence, the server message for a code it does not know', () => {
    const passthrough = (_key: string, opts?: Record<string, unknown>) => String(opts?.defaultValue);
    expect(errorText(passthrough, 'route_missing')).toBe('No procurement route is set.');
    expect(errorText(passthrough, 'brand_new_code', 'Said by the server')).toBe('Said by the server');
    expect(errorText(passthrough, 'brand_new_code')).toBe('Brand new code');
    expect(humanizeCode('')).toBe('');
  });
});

describe('item draft', () => {
  it('a new item needs a code, a title and a kind of plant', () => {
    expect(itemProblems(emptyItemDraft(), true)).toEqual(['code_required', 'title_required', 'class_required']);
    expect(itemProblems({ ...emptyItemDraft(), code: 'PL 001', title: 'x', component_class_code: 'lift' }, true)).toEqual([
      'code_invalid',
    ]);
  });

  it('an edit does not ask for the code again', () => {
    expect(itemProblems({ ...emptyItemDraft(), title: 'x', component_class_code: 'lift' }, false)).toEqual([]);
  });

  it('asks for the reason behind a vendor binding and behind each override', () => {
    const draft = {
      ...emptyItemDraft(),
      code: 'PL-9',
      title: 'x',
      component_class_code: 'lift',
      vendor_policy: 'bound' as const,
      critical: 'no' as const,
      long_lead: 'yes' as const,
    };
    expect(itemProblems(draft, true)).toEqual([
      'vendor_reason_required',
      'critical_reason_required',
      'long_lead_reason_required',
    ]);
  });

  it('refuses a quantity of zero or text', () => {
    const base = { ...emptyItemDraft(), code: 'PL-9', title: 'x', component_class_code: 'lift' };
    expect(itemProblems({ ...base, quantity: '0' }, true)).toEqual(['quantity_invalid']);
    expect(itemProblems({ ...base, quantity: 'two' }, true)).toEqual(['quantity_invalid']);
  });

  it('a create sends the quantity as a string and nothing the reader left empty', () => {
    const body = toCreateInput({ ...emptyItemDraft(), code: ' PL-9 ', title: ' Lift ', component_class_code: 'lift', quantity: '3' });
    expect(body).toEqual({ code: 'PL-9', title: 'Lift', component_class_code: 'lift', quantity: '3', vendor_policy: 'neutral' });
    expect(typeof body.quantity).toBe('string');
  });

  it('a create drops requirement rows without a name', () => {
    const body = toCreateInput({
      ...emptyItemDraft(),
      code: 'PL-9',
      title: 'Lift',
      component_class_code: 'lift',
      performance: [
        { key: ' rated_load ', value: '1600', unit: 'kg' },
        { key: '', value: '8', unit: 'stops' },
      ],
    });
    expect(body.performance).toEqual([{ key: 'rated_load', value: '1600', unit: 'kg' }]);
  });

  it('an untouched edit sends nothing, so a frozen specification is not touched', () => {
    const original = item();
    expect(itemChanges(original, itemDraftOf(original))).toEqual({});
  });

  it('an edit sends only what changed, never the code, and clears a date with null', () => {
    const original = item();
    const changes = itemChanges(original, { ...itemDraftOf(original), code: 'OTHER', title: 'Renamed', need_date_fixed: '' });
    expect(changes).toEqual({ title: 'Renamed', need_date_fixed: null });
  });

  it('an override turned back to the default is sent as null with its reason cleared', () => {
    const original = item({ critical_override: false, critical_reason: 'Spare unit on site' });
    expect(itemChanges(original, { ...itemDraftOf(original), critical: 'default' })).toEqual({
      critical_override: null,
      critical_reason: '',
    });
  });
});

describe('states', () => {
  it('offers the one step a reader takes by hand', () => {
    expect(nextManualStep('identified')).toBe('specified');
    expect(nextManualStep('specified')).toBe('enquired');
    expect(nextManualStep('enquired')).toBe('route_set');
    expect(nextManualStep('ordered')).toBe('manufactured');
  });

  it('offers no hand step where the state is read from the order or commissioning', () => {
    for (const s of ['route_set', 'manufactured', 'delivered', 'installed', 'commissioned', 'handed_over', 'cancelled'] as const) {
      expect(nextManualStep(s)).toBeNull();
    }
  });

  it('walks a spare from required to handed over and stops there', () => {
    expect(nextSpareStep('required')).toBe('specified');
    expect(nextSpareStep('specified')).toBe('delivered');
    expect(nextSpareStep('delivered')).toBe('handed_over');
    expect(nextSpareStep('handed_over')).toBeNull();
    expect(nextSpareStep('waived')).toBeNull();
  });

  it('stops warning about the order date once the item is ordered', () => {
    expect(orderDateOpen({ status: 'route_set' })).toBe(true);
    expect(orderDateOpen({ status: 'ordered' })).toBe(false);
  });
});

describe('lead time quote draft', () => {
  const filled = { ...emptyQuoteDraft(), source: 'supplier_quote', enquiry_date: '2026-10-01', lead_weeks_min: '40' };

  it('an empty draft is missing the source, the enquiry date and the weeks', () => {
    expect(quoteProblems(emptyQuoteDraft(), TODAY)).toEqual(['source_required', 'enquiry_date_required', 'lead_weeks_required']);
  });

  it('refuses an enquiry date in the future and a response before the enquiry', () => {
    expect(quoteProblems({ ...filled, enquiry_date: '2026-10-13' }, TODAY)).toEqual(['enquiry_date_in_future']);
    expect(quoteProblems({ ...filled, response_date: '2026-09-30' }, TODAY)).toEqual(['response_before_enquiry']);
  });

  it('accepts today as the enquiry date', () => {
    expect(quoteProblems({ ...filled, enquiry_date: TODAY }, TODAY)).toEqual([]);
  });

  it('refuses a shortest lead time above the longest, and weeks that are not whole', () => {
    expect(quoteProblems({ ...filled, lead_weeks_max: '30' }, TODAY)).toEqual(['lead_weeks_range']);
    expect(quoteProblems({ ...filled, lead_weeks_min: '4.5' }, TODAY)).toEqual(['lead_weeks_required']);
  });

  it('a single figure is sent as a range of one, weeks as numbers, empty dates as null', () => {
    expect(toQuoteInput(filled)).toMatchObject({
      lead_weeks_min: 40,
      lead_weeks_max: 40,
      enquiry_date: '2026-10-01',
      response_date: null,
      valid_until: null,
      set_basis: true,
    });
    expect(toQuoteInput({ ...filled, lead_weeks_max: '52' }).lead_weeks_max).toBe(52);
  });
});

describe('production slot draft', () => {
  it('sends only what was filled in, and the fee as the string that was typed', () => {
    const body = toSlotInput({ ...emptySlotDraft(), vendor_name: ' Manufacturer A ', reservation_fee: '12500.50', currency: 'eur' });
    expect(body).toEqual({
      vendor_name: 'Manufacturer A',
      reservation_fee: '12500.50',
      currency: 'EUR',
      fee_credited_to_order: false,
    });
  });

  it('refuses a window that ends before it starts, a negative fee and a currency that is no code', () => {
    expect(slotProblems({ ...emptySlotDraft(), slot_from: '2027-03-01', slot_to: '2027-02-01' })).toEqual(['slot_range']);
    expect(slotProblems({ ...emptySlotDraft(), reservation_fee: '-5' })).toEqual(['fee_invalid']);
    expect(slotProblems({ ...emptySlotDraft(), currency: 'euro' })).toEqual(['currency_invalid']);
    expect(slotProblems(emptySlotDraft())).toEqual([]);
  });
});

describe('decision paper draft', () => {
  const draft: PaperDraft = {
    question: 'Which manufacturer?',
    criteria: [
      { rowId: 'c1', code: '', title: 'Local service', weight: '2' },
      { rowId: 'c2', code: 'cost', title: 'Cost', weight: '3' },
      { rowId: 'c3', code: '', title: '', weight: '1' },
    ],
    options: [
      { rowId: 'o1', code: 'a', title: 'Manufacturer A', lead_weeks: '40', cost: '410000', currency: 'eur', scores: { c1: '4', c2: '2', c3: '9' } },
      { rowId: 'o2', code: 'b', title: 'Manufacturer B', lead_weeks: '', cost: '', currency: '', scores: {}, keep: { quote_id: 'q7' } },
    ],
    recommendation: 'o2',
    rationale: ' Cheaper. ',
  };

  it('keys every score by its criterion code and sends numbers as strings', () => {
    const body = toPaperInput(draft);
    expect(body.criteria).toEqual([
      { code: 'local_service', title: 'Local service', weight: '2' },
      { code: 'cost', title: 'Cost', weight: '3' },
    ]);
    expect(body.options[0]).toEqual({
      code: 'a',
      title: 'Manufacturer A',
      lead_weeks: 40,
      cost: '410000',
      currency: 'EUR',
      scores: { local_service: '4', cost: '2' },
    });
  });

  it('names the recommended option by its code and keeps the links it does not edit', () => {
    const body = toPaperInput(draft);
    expect(body.recommendation).toBe('b');
    expect(body.options[1]).toMatchObject({ quote_id: 'q7', cost: null, lead_weeks: null, currency: null });
    expect(body.rationale).toBe('Cheaper.');
  });

  it('refuses a missing question, an option without a title, two options with one code and a score in words', () => {
    expect(paperProblems({ ...draft, question: ' ' })).toEqual(['question_required']);
    const twins = { ...draft, options: draft.options.map((o) => ({ ...o, code: 'a', title: o.rowId === 'o2' ? '' : o.title })) };
    expect(paperProblems(twins)).toEqual(['option_incomplete', 'option_codes_unique']);
    const worded = { ...draft, options: [{ ...draft.options[0]!, scores: { c1: 'good' } }, draft.options[1]!] };
    expect(paperProblems(worded)).toEqual(['score_invalid']);
    expect(paperProblems(draft)).toEqual([]);
  });

  it('makes a code from a title and falls back when the title has no letters', () => {
    expect(slugCode('  Lead time (weeks) ', 'criterion_1')).toBe('lead_time_weeks');
    expect(slugCode('???', 'criterion_1')).toBe('criterion_1');
  });
});

describe('register filters', () => {
  const items = [
    item({ id: 'a', long_lead: true, critical: true, order_status: 'overdue' }),
    item({ id: 'b', long_lead: true, critical: false, order_status: 'ok' }),
    item({ id: 'c', long_lead: false, critical: false, order_status: 'due_soon' }),
  ];

  it('counts and filters by long-lead, critical and overdue', () => {
    expect(filterCounts(items)).toEqual({ all: 3, long_lead: 2, critical: 1, overdue: 1 });
    expect(filterItems(items, 'long_lead').map((i) => i.id)).toEqual(['a', 'b']);
    expect(filterItems(items, 'overdue').map((i) => i.id)).toEqual(['a']);
    expect(filterItems(items, 'all')).toHaveLength(3);
  });
});

describe('long-lead timeline', () => {
  it('lists the tightest item first, items without a float last, and leaves out cancelled and short ones', () => {
    const order = longLeadOrder([
      item({ id: 'slack', float_days: 90 }),
      item({ id: 'undated', float_days: null }),
      item({ id: 'late', float_days: -59 }),
      item({ id: 'gone', float_days: -200, status: 'cancelled' }),
      item({ id: 'short', float_days: -300, long_lead: false }),
    ]);
    expect(order.map((i) => i.id)).toEqual(['late', 'slack', 'undated']);
  });

  it('places today, the order date and the need date on one axis', () => {
    const tl = buildTimeline(
      [item({ latest_order_date: '2026-10-02', need_date: '2027-01-20' }), item({ id: 'undated', latest_order_date: null, need_date: null })],
      '2026-10-12',
    );
    expect(tl.start).toBe('2026-10-02');
    expect(tl.end).toBe('2027-01-20');
    expect(tl.rows[0]).toMatchObject({ orderAt: 0, needAt: 100 });
    // 10 of 110 days in.
    expect(tl.todayAt).toBeCloseTo(9.1, 1);
    expect(tl.rows[1]).toMatchObject({ orderAt: null, needAt: null });
  });

  it('starts the axis at today when every order date is still ahead', () => {
    const tl = buildTimeline([item({ latest_order_date: '2026-11-01', need_date: '2027-01-20' })], '2026-10-12');
    expect(tl.start).toBe('2026-10-12');
    expect(tl.todayAt).toBe(0);
    expect(tl.rows[0]!.orderAt).toBeGreaterThan(0);
  });

  it('does not divide by zero when there is nothing but today', () => {
    const tl = buildTimeline([], '2026-10-12');
    expect(tl.todayAt).toBe(0);
    expect(tl.rows).toEqual([]);
  });
});
