# California Construction Pack

State depth for California, layered on top of the US Construction Pack rather
than repeating it. The national pack already carries the classification
structures, the owner-contractor agreement family, the progress payment
application and imperial units. This pack carries the things that change when a
job is in California and that an estimator working from national defaults gets
wrong.

## What this pack carries

### Sales tax, and the line between a material and a fixture

The statewide base is 7.25 percent, made of 6.00 state, 1.00 local jurisdiction
and 0.25 local transportation fund. It fell to that on 1 January 2017 when the
temporary quarter-percent expired. Almost no California address pays only the
base: voter-approved district taxes stack on top, they can stack with each
other, and the rate tables are republished quarterly. The rate is a property of
the jobsite address and the quarter it is billed in, so this pack hard-codes no
district rate.

The rule that costs money is not the rate. A construction contractor is the
**consumer** of the materials it furnishes and installs and owes tax on its own
purchase price of them, charging the customer nothing. The same contractor on
the same job is the **retailer** of the fixtures it furnishes and installs and
owes tax on the retail selling price, which under a lump sum contract is the
contractor's cost price of the fixture. One invoice, two treatments, and the
split follows what the item is rather than how the contract is worded.
Construction labor is outside the tax base either way.

### Prevailing wage

California runs its own regime under the Labor Code, and it is not the federal
one. The state labour department makes the determinations. A federally funded
California job can carry both regimes and the higher rate governs, so treating
a federal determination as satisfying California is a mistake this pack exists
to prevent.

The duty bites at 1,000 dollars, which is far lower than most people assume. An
awarding body that runs an approved labour compliance programme may elect not
to require prevailing wage at 25,000 dollars or less for construction, or
15,000 or less for alteration, demolition, repair or maintenance, but that
election does not exist without the approved programme. Contractors and
subcontractors on public works must also register with the state labour
department, which is a separate thing from the contractor licence.

### Retention

- **Public work.** Capped at 5 percent since contracts entered into on or after
  1 January 2012. It may go higher only where the governing body, or the
  department director for a state entity, made a finding before the bid that
  the project is substantially complex, and the bid documents set out the basis
  and the actual retention amount. No finding in the bid documents means no
  basis for retention above 5 percent.
- **Private work.** Also capped at 5 percent now, of each individual payment
  and of the total contract price in aggregate, for construction agreements
  entered into on or after 1 January 2026. The cap runs the whole chain, owner
  to contractor to subcontractor to lower tier. It does not reach a purely
  residential building of four storeys or fewer, nor a downstream contract
  where bond requirements were noticed before bidding and the subcontractor
  then failed to furnish bonds from an admitted surety.
- **Release.** Public retention comes out within 60 days of completion and the
  prime passes a subcontractor's share on within 7 days, at 2 percent a month
  for failing to. Private retention comes out within 45 days of completion.

### Payment and lien clocks

- Public progress payments: a local agency owes interest at the legal rate if
  it does not pay within 30 days of an undisputed and properly submitted
  request. It must return an improper request within 7 days, and every day over
  that comes off its own 30.
- Private progress payments: the owner pays within 30 days of the contractual
  notice demanding payment, but this one is a default rather than a floor, since
  the owner and direct contractor may agree otherwise in writing. Wrongful
  withholding runs at 2 percent a month in place of interest.
- Down the chain: 7 days from receipt, at 2 percent a month, on private and
  public work alike, with disputed withholding capped at 150 percent of the
  amount in dispute.
- Mechanics lien: preliminary notice reaches back only 20 days, so late notice
  shortens the claim rather than killing it. The claim of lien goes on record
  within 90 days of completion, but a recorded notice of completion cuts that
  to 60 days for the direct contractor and 30 for everyone else. Suit follows
  within 90 days of recording, and none of these can be tolled.

## Contractor licensing

California licenses contractors at state level and a licence is required to
bid. Public works work needs the separate registration mentioned above as well.

## Where the numbers live

Every figure above is served by the `oe_us_ca_pack` backend module at
`/api/v1/us-ca-pack/rules/`, and every rule there carries the statute it comes
from. Nothing in this pack states a rule without a citation. The statutory
payment periods are also seeded into the payment clock as the regimes
`us_ca_public_20104` and `us_ca_private_8800`, so the clock computes real dates
rather than describing them.

## Install

This pack ships inside OpenConstructionERP. Activate it from Modules then
Packs: click Rescan, find "California Construction Pack", then Activate pack.

To run a workspace that boots straight into it:

```bash
OE_PACK=us-california openconstructionerp serve
```

## What this pack is not

It bundles no cost data, no wage determinations and no district tax table. The
district rate depends on the jobsite address and the billing quarter, and the
wage determination depends on the craft and the county, so both are imported
rather than shipped.

The figures are current as at the pack version and every one names its statute
so it can be checked. They are a working reference, not legal advice, and a
project of any size should confirm the position with its own counsel.
