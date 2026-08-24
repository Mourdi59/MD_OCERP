# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The shipped statutory payment regimes, and an idempotent seeder for them.

This is where the law is written down. Every number here is a statutory default
and every entry names the sections it came from, because the one question a
quantity surveyor will ask about a computed date is which provision produced
it. Nothing here is a house rule.

Two modelling decisions run through the whole table and are worth stating once
rather than once per regime.

**The due date and the final date for payment are different dates, and only the
UK Act genuinely splits them.** The UK Act makes a sum fall due, then gives a
further period before it must be paid, and the notice deadlines hang off both.
The security-of-payment statutes have one date: the progress payment "becomes
due and payable" a set number of days after the claim. Those regimes are
therefore written with the due date on the application date and the statutory
period as the final date for payment, which is what the statute actually
imposes - a last day to pay - and which keeps the final date after the due date
in every regime shipped.

**A null deadline means the statute is silent, which is not the same as zero.**
Malaysia leaves the payment period to the contract, and the EU Late Payment
Directive and the German regimes have no notice sequence at all. The rules skip
what the regime does not set rather than treating it as an instant deadline.

Seed data lives here and not in a migration on purpose: a migration is a
schema change that runs once per deployment, and this table is content that
will be corrected as statutes are amended.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


PAYMENT_REGIMES: tuple[dict[str, Any], ...] = (
    {
        "code": "uk_hgcra",
        "jurisdiction": "United Kingdom",
        "country_code": "GB",
        "statute": "Housing Grants, Construction and Regeneration Act 1996",
        "statute_reference": (
            "sections 110, 110A, 110B and 111, as amended by the Local Democracy, Economic Development "
            "and Construction Act 2009; default periods from the Scheme for Construction Contracts"
        ),
        "due_date_basis": "period_end",
        "due_date_days": 7,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "due_date",
        "payment_notice_days": 5,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "due_date",
        "final_date_days": 17,
        "final_date_day_basis": "calendar",
        "pay_less_days": 7,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "applied_sum_becomes_notified_sum",
        "interest_basis": "reference_rate_plus_margin",
        "interest_reference_rate": "Bank of England base rate",
        "interest_margin_percent": Decimal("8.000"),
        "interest_fixed_percent": None,
        "interest_statute": "Late Payment of Commercial Debts (Interest) Act 1998",
        "notes": (
            "The periods are the Scheme's defaults and apply where the contract does not provide "
            "compliant ones; a contract may set shorter periods but may not remove the sequence. Under "
            "section 111 the notified sum must be paid in full by the final date unless a valid pay-less "
            "notice was served in time, and where the payer served no payment notice the sum the payee "
            "applied for is the notified sum. Section 110B lets the payee serve its own default payment "
            "notice when the payer missed the deadline, which postpones the final date for payment by the "
            "days between the missed deadline and that notice."
        ),
    },
    {
        "code": "ie_cca_2013",
        "jurisdiction": "Ireland",
        "country_code": "IE",
        "statute": "Construction Contracts Act 2013",
        "statute_reference": "section 4 and the Schedule",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "application_date",
        "payment_notice_days": 21,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 30,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "applied_sum_becomes_notified_sum",
        "interest_basis": "reference_rate_plus_margin",
        "interest_reference_rate": "European Central Bank main refinancing rate",
        "interest_margin_percent": Decimal("8.000"),
        "interest_fixed_percent": None,
        "interest_statute": "European Communities (Late Payment in Commercial Transactions) Regulations 2012",
        "notes": (
            "The Act does not split a due date from a final date the way the UK Act does, so the payment "
            "claim date is taken as the due date and the Act's thirty-day limit as the final date for "
            "payment. The response to a payment claim notice must state the amount proposed to be paid "
            "and the reason for any difference from the amount claimed; there is no separate pay-less "
            "notice. Unpaid amounts carry a right to suspend."
        ),
    },
    {
        "code": "au_nsw_sopa",
        "jurisdiction": "New South Wales, Australia",
        "country_code": "AU",
        "statute": "Building and Construction Industry Security of Payment Act 1999 (NSW)",
        "statute_reference": "sections 11, 13, 14 and 17",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "application_date",
        "payment_notice_days": 10,
        "payment_notice_day_basis": "business",
        "final_date_basis": "application_date",
        "final_date_days": 15,
        "final_date_day_basis": "business",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "applied_sum_becomes_notified_sum",
        "interest_basis": "prescribed_rate",
        "interest_reference_rate": "section 101 of the Civil Procedure Act 2005 (NSW)",
        "interest_margin_percent": None,
        "interest_fixed_percent": None,
        "interest_statute": "Building and Construction Industry Security of Payment Act 1999 (NSW), section 11(2)",
        "notes": (
            "The response to a payment claim is a payment schedule. Fifteen business days is the limit "
            "for a head contract and twenty for a subcontract; a contract may set a shorter period but "
            "not a longer one. Business days under this Act exclude 27 to 31 December as well as weekends "
            "and public holidays, so supply that calendar to reproduce the statutory dates exactly. Where "
            "no payment schedule is served in time the respondent becomes liable to pay the claimed "
            "amount on the due date. Interest runs at the greater of the prescribed rate and the rate the "
            "contract specifies."
        ),
    },
    {
        "code": "au_qld_bif",
        "jurisdiction": "Queensland, Australia",
        "country_code": "AU",
        "statute": "Building Industry Fairness (Security of Payment) Act 2017 (Qld)",
        "statute_reference": "sections 68, 75, 76 and 90",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "application_date",
        "payment_notice_days": 15,
        "payment_notice_day_basis": "business",
        "final_date_basis": "application_date",
        "final_date_days": 25,
        "final_date_day_basis": "business",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "applied_sum_becomes_notified_sum",
        "interest_basis": "prescribed_rate",
        "interest_reference_rate": "section 67P of the Queensland Building and Construction Commission Act 1991",
        "interest_margin_percent": None,
        "interest_fixed_percent": Decimal("10.000"),
        "interest_statute": "Queensland Building and Construction Commission Act 1991, section 67P",
        "notes": (
            "The response to a payment claim is a payment schedule. Twenty-five business days is the "
            "limit for a head contract and fifteen for a subcontract. Where no payment schedule is served "
            "in time the respondent becomes liable to pay the claimed amount on the due date. Interest "
            "runs at the greater of ten per cent a year and the prescribed rate."
        ),
    },
    {
        "code": "nz_cca_2002",
        "jurisdiction": "New Zealand",
        "country_code": "NZ",
        "statute": "Construction Contracts Act 2002",
        "statute_reference": "sections 18, 20, 21, 22 and 23",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "application_date",
        "payment_notice_days": 20,
        "payment_notice_day_basis": "business",
        "final_date_basis": "application_date",
        "final_date_days": 20,
        "final_date_day_basis": "business",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "applied_sum_becomes_notified_sum",
        "interest_basis": "contract",
        "interest_reference_rate": "",
        "interest_margin_percent": None,
        "interest_fixed_percent": None,
        "interest_statute": "",
        "notes": (
            "The response to a payment claim is a payment schedule. Both default periods run twenty "
            "working days from the payment claim, so on the default terms the payer must serve its "
            "schedule on the day payment falls due at the latest; a contract may set shorter periods. "
            "Working days under this Act exclude 24 December to 5 January as well as weekends and public "
            "holidays, so supply that calendar to reproduce the statutory dates exactly. Where no payment "
            "schedule is served the payer becomes liable for the claimed amount and it is recoverable as "
            "a debt. The Act sets no interest rate, so the contract rate applies."
        ),
    },
    {
        "code": "sg_sopa",
        "jurisdiction": "Singapore",
        "country_code": "SG",
        "statute": "Building and Construction Industry Security of Payment Act 2004",
        "statute_reference": "sections 8, 11 and 15",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "application_date",
        "payment_notice_days": 21,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 35,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "evidential_bar",
        "interest_basis": "contract",
        "interest_reference_rate": "",
        "interest_margin_percent": None,
        "interest_fixed_percent": None,
        "interest_statute": "",
        "notes": (
            "The response to a payment claim is a payment response, due twenty-one days after the claim "
            "for a construction contract and seven days for a supply contract. Payment falls due fourteen "
            "days after the payment response was required, which is where the thirty-five days comes "
            "from, unless the contract sets an earlier date. Failing to serve a payment response does not "
            "concede the claim: it bars the respondent from raising at adjudication any reason it did not "
            "put in the response."
        ),
    },
    {
        "code": "my_cipaa",
        "jurisdiction": "Malaysia",
        "country_code": "MY",
        "statute": "Construction Industry Payment and Adjudication Act 2012",
        "statute_reference": "sections 5, 6 and 36",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "application_date",
        "payment_notice_days": 10,
        "payment_notice_day_basis": "business",
        "final_date_basis": "application_date",
        "final_date_days": None,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "deemed_dispute",
        "interest_basis": "contract",
        "interest_reference_rate": "",
        "interest_margin_percent": None,
        "interest_fixed_percent": None,
        "interest_statute": "",
        "notes": (
            "The response to a payment claim is a payment response, due ten working days after the claim. "
            "The Act sets no payment period, so the final date for payment comes from the contract and "
            "has to be entered on the application; section 36 voids a clause making payment conditional "
            "on the payer itself being paid. Failing to respond within the ten working days is a deemed "
            "dispute of the whole claim rather than an admission of it, so the claimant's next step is "
            "adjudication and not a debt claim."
        ),
    },
    {
        "code": "eu_late_payment",
        "jurisdiction": "European Union",
        "country_code": "EU",
        "statute": "Directive 2011/7/EU on combating late payment in commercial transactions",
        "statute_reference": "articles 2, 3 and 4",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "application_date",
        "payment_notice_days": None,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 30,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "none",
        "interest_basis": "reference_rate_plus_margin",
        "interest_reference_rate": "European Central Bank reference rate",
        "interest_margin_percent": Decimal("8.000"),
        "interest_fixed_percent": None,
        "interest_statute": "Directive 2011/7/EU, article 2(6)",
        "notes": (
            "An interest basis rather than a notice regime: the Directive sets a payment period and the "
            "interest that runs when it is missed, and leaves notices to national law, so this regime has "
            "no payment notice and missing one has no consequence under it. Thirty days is the default "
            "period between undertakings; it may be extended to sixty by express agreement and beyond "
            "that only where the term is not grossly unfair to the creditor. Use this regime where a "
            "member state has no construction-specific payment statute, and the national regime where it "
            "has one."
        ),
    },
    # The three German regimes below carry the statutory deadlines of § 16
    # VOB/B (2016) and §§ 632a, 641, 650g BGB. The German contract-type and
    # invoice-template vocabulary (VOB_B_EINHEITSPREIS, ABSCHLAGSRECHNUNG,
    # SCHLUSSRECHNUNG, "per § 632a BGB / § 16 VOB/B") lives in
    # ``app.modules.dach_pack.config``; that module carries no deadline
    # arithmetic, so the numbers are written down here, sourced from the
    # provisions each entry names, and the wording follows dach_pack's. VOB/B
    # gives an Abschlagsrechnung and a Schlussrechnung two different clocks (21
    # and 30 days), and a regime in this table is one clock, so they are two
    # entries rather than one entry with a footnote a calculation cannot read.
    {
        "code": "de_vob_b_abschlag",
        "jurisdiction": "Germany",
        "country_code": "DE",
        "statute": "VOB/B § 16 Abs. 1 (Abschlagszahlungen)",
        "statute_reference": (
            "§ 16 Abs. 1 Nr. 3 VOB/B (2016); Nachfrist and default interest under § 16 Abs. 5 Nr. 3 "
            "VOB/B with § 288 Abs. 2 BGB"
        ),
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "due_date",
        "payment_notice_days": None,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 21,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "none",
        "interest_basis": "reference_rate_plus_margin",
        "interest_reference_rate": "Deutsche Bundesbank base rate (Basiszinssatz, § 247 BGB)",
        "interest_margin_percent": Decimal("9.000"),
        "interest_fixed_percent": None,
        "interest_statute": "§ 288 Abs. 2 BGB, applied by § 16 Abs. 5 Nr. 3 VOB/B",
        "notes": (
            "The clock for an interim payment invoice (Abschlagsrechnung) under a VOB/B contract. The claim "
            "falls due within 21 calendar days of the client receiving the verifiable statement of work "
            "(Zugang der Aufstellung), so enter that date of receipt as the application date; following the "
            "convention used for the other single-date regimes, the application date is taken as the due "
            "date and the 21-day limit as the final date for payment. VOB/B has no statutory payment or "
            "pay-less notice: an objection to the statement is informal and silence has no preclusive "
            "effect. If the client has not paid when the claim is due, § 16 Abs. 5 Nr. 3 VOB/B lets the "
            "contractor set a reasonable grace period (angemessene Nachfrist - two weeks is the customary "
            "yardstick), from whose expiry default interest under § 288 Abs. 2 BGB runs and the "
            "contractor may suspend the works until payment; at the latest, the client is in default 30 "
            "days after receipt of the invoice or statement. This module has no grace-period step, so the "
            "interest warning runs from the final date for payment and the Nachfrist has to be minded by "
            "hand."
        ),
    },
    {
        "code": "de_vob_b_schluss",
        "jurisdiction": "Germany",
        "country_code": "DE",
        "statute": "VOB/B § 16 Abs. 3 (Schlusszahlung)",
        "statute_reference": (
            "§ 16 Abs. 3 Nr. 1 VOB/B (2016); reservation of claims under § 16 Abs. 3 Nr. 2 and Nr. 5 "
            "VOB/B; Nachfrist and default interest under § 16 Abs. 5 Nr. 3 VOB/B with § 288 Abs. 2 BGB"
        ),
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "due_date",
        "payment_notice_days": None,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 30,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "none",
        "interest_basis": "reference_rate_plus_margin",
        "interest_reference_rate": "Deutsche Bundesbank base rate (Basiszinssatz, § 247 BGB)",
        "interest_margin_percent": Decimal("9.000"),
        "interest_fixed_percent": None,
        "interest_statute": "§ 288 Abs. 2 BGB, applied by § 16 Abs. 5 Nr. 3 VOB/B",
        "notes": (
            "The clock for the final invoice (Schlussrechnung) under a VOB/B contract. The final payment "
            "falls due promptly after examination and determination of the invoice, and at the latest "
            "within 30 calendar days of the client receiving it, so enter the date of receipt (Zugang der "
            "Schlussrechnung) as the application date. The period extends to at most 60 days only where "
            "that is objectively justified by the particular nature or features of the agreement and was "
            "expressly agreed (§ 16 Abs. 3 Nr. 1 sentence 2 VOB/B); record such a contract by stating "
            "the agreed final date on the application, which marks the dates as overridden. Accepting the "
            "final payment without reservation excludes further claims where the client gave written "
            "notice of the payment and of that preclusive effect; the contractor's reservation (Vorbehalt) "
            "must be declared within 28 calendar days of that notice and substantiated within a further 28 "
            "(§ 16 Abs. 3 Nr. 2 and Nr. 5 VOB/B) - a payee-side sequence this clock does not compute. "
            "Late payment carries the same Nachfrist and interest mechanics as the interim regime."
        ),
    },
    {
        "code": "de_bgb_632a",
        "jurisdiction": "Germany",
        "country_code": "DE",
        "statute": "BGB § 632a (Abschlagszahlungen)",
        "statute_reference": (
            "§ 632a Abs. 1 BGB; default without a reminder under § 286 Abs. 3 BGB; interest under "
            "§ 288 Abs. 2 BGB; final payment due on acceptance with a verifiable final invoice under "
            "§ 641 Abs. 1 and § 650g Abs. 4 BGB"
        ),
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "due_date",
        "payment_notice_days": None,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 30,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "none",
        "interest_basis": "reference_rate_plus_margin",
        "interest_reference_rate": "Deutsche Bundesbank base rate (Basiszinssatz, § 247 BGB)",
        "interest_margin_percent": Decimal("9.000"),
        "interest_fixed_percent": None,
        "interest_statute": "§ 288 Abs. 2 BGB",
        "notes": (
            "The clock for interim payments under a plain BGB construction contract, where the parties did "
            "not agree the VOB/B. § 632a Abs. 1 BGB entitles the contractor to interim payments in the "
            "amount of the value of the work performed and owed. The BGB sets no payment period - the "
            "claim is due on demand with a verifiable statement (§ 271 BGB) - so the 30 days written "
            "here are § 286 Abs. 3 BGB: the client is in default at the latest 30 days after receiving "
            "the invoice, without any reminder, and that outer limit is taken as the final date for "
            "payment. Between businesses it applies of itself; against a consumer only where the invoice "
            "said so. Interest runs at nine percentage points over the base rate for commercial debts "
            "(§ 288 Abs. 2 BGB). The final payment is a different clock: it falls due on acceptance of "
            "the works plus a verifiable final invoice (§ 641 Abs. 1, § 650g Abs. 4 BGB), which is a "
            "condition this module cannot compute from a date alone."
        ),
    },
    # The four United States regimes below are split public/private per state,
    # because that is where American prompt payment law actually divides: the
    # public duty is owed by a governmental entity under one statute and the
    # private duty is owed by an owner under another, with different periods and
    # different interest. The state pack configs
    # (``app.modules.us_tx_pack.config`` and ``app.modules.us_ca_pack.config``)
    # name these codes under ``payment_clock_regimes`` and carry the same
    # provisions as reference data; the deadline arithmetic is written down here
    # and nowhere else. None of the four has a notice sequence, so every one of
    # them takes the application date as the due date and the statutory period as
    # the final date for payment, the convention set out at the top of this file.
    {
        "code": "us_tx_public_2251",
        "jurisdiction": "Texas, United States (public)",
        "country_code": "US",
        "statute": "Texas Prompt Payment Act, Government Code Chapter 2251",
        "statute_reference": "sections 2251.021, 2251.022 and 2251.025",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "due_date",
        "payment_notice_days": None,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 30,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "none",
        "interest_basis": "reference_rate_plus_margin",
        "interest_reference_rate": "Wall Street Journal prime rate",
        "interest_margin_percent": Decimal("1.000"),
        "interest_fixed_percent": None,
        "interest_statute": "Texas Government Code § 2251.025",
        "notes": (
            "The clock for a payment owed by a governmental entity on public work. The payment becomes "
            "overdue on the 31st day after the later of the date the entity received the goods or the "
            "services were completed and the date it received the invoice, which is the 30 days written "
            "here; enter the later of those two dates as the application date. A political subdivision "
            "whose governing body meets only once a month or less often has until the 46th day instead, so "
            "state the final date for payment on the application for those bodies rather than using the "
            "computed one. The statute has no payment notice and no pay-less notice, so silence has no "
            "preclusive effect. Interest is one percent above the Wall Street Journal prime rate; the rate "
            "is fixed on 1 September for the whole fiscal year from the prime rate published on the first "
            "business day of the preceding July, is simple rather than compounded, and stops on the date "
            "the payment is sent. A prime contractor paid under this chapter must pass the appropriate "
            "share to each subcontractor by the 10th day after it receives the payment (§ 2251.022), which "
            "is a second clock this regime does not compute."
        ),
    },
    {
        "code": "us_tx_private_ch28",
        "jurisdiction": "Texas, United States (private)",
        "country_code": "US",
        "statute": "Texas Prompt Payment to Contractors and Subcontractors Act, Property Code Chapter 28",
        "statute_reference": "sections 28.002, 28.004 and 28.006",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "due_date",
        "payment_notice_days": None,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 35,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "none",
        "interest_basis": "fixed_rate",
        "interest_reference_rate": "",
        "interest_margin_percent": None,
        "interest_fixed_percent": Decimal("18.000"),
        "interest_statute": "Texas Property Code § 28.004(b)",
        "notes": (
            "The clock for private work in Texas. The owner must pay by the 35th day after it receives the "
            "contractor's written request for payment, so enter the date the owner received the request as "
            "the application date. The contractor must then pay its subcontractor by the seventh day after "
            "it receives the owner's payment (§ 28.002(b)), a downstream clock this regime does not "
            "compute. The statute states the interest monthly, at one and a half percent each month, which "
            "is the 18 percent a year written here. There is no notice sequence. An attempted waiver of the "
            "chapter is void under § 28.006, with a limited exception for certain single-family residential "
            "contracts, so a subcontract clause purporting to lengthen these periods generally does not."
        ),
    },
    {
        "code": "us_ca_public_20104",
        "jurisdiction": "California, United States (public)",
        "country_code": "US",
        "statute": "California Public Contract Code § 20104.50 (Local Agency Public Construction Act)",
        "statute_reference": "section 20104.50; legal rate under Code of Civil Procedure § 685.010(a)",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "application_date",
        "payment_notice_days": 7,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 30,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "none",
        "interest_basis": "fixed_rate",
        "interest_reference_rate": "",
        "interest_margin_percent": None,
        "interest_fixed_percent": Decimal("10.000"),
        "interest_statute": "Public Contract Code § 20104.50, applying Code of Civil Procedure § 685.010(a)",
        "notes": (
            "The clock for a progress payment owed by a Californian local agency, which includes a city, a "
            "charter city, a county, and a city and county. The agency owes interest if it fails to pay "
            "within 30 days of receiving an undisputed and properly submitted payment request. A progress "
            "payment here means everything due except the portion of the final payment the contract "
            "designates as retention, so retention release runs on its own clock under Public Contract Code "
            "§ 7107 (60 days after completion, then 7 days to pass a subcontractor's share on) and is not "
            "computed by this regime. The seven days recorded as the payment notice deadline are the "
            "agency's own: it must return an improper payment request as soon as practicable and no later "
            "than the seventh day after receipt. Missing that does not make the applied sum payable, which "
            "is why the no-notice effect is none; instead the 30 day window shrinks by however many days "
            "the agency ran over the seven, an adjustment this module does not apply, so reduce the final "
            "date by hand where a request came back late. Interest runs at the legal rate on judgments, "
            "10 percent a year for these claims."
        ),
    },
    {
        "code": "us_ca_private_8800",
        "jurisdiction": "California, United States (private)",
        "country_code": "US",
        "statute": "California prompt payment on private works, Civil Code § 8800",
        "statute_reference": "Civil Code §§ 8800 and 8812; Business and Professions Code § 7108.5",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "due_date",
        "payment_notice_days": None,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 30,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "none",
        "interest_basis": "fixed_rate",
        "interest_reference_rate": "",
        "interest_margin_percent": None,
        "interest_fixed_percent": Decimal("24.000"),
        "interest_statute": "California Civil Code § 8800",
        "notes": (
            "The clock for private work in California. The owner must pay a progress payment within 30 days "
            "after notice demanding payment is given under the contract, so enter the date that notice was "
            "given as the application date. This period is a default rather than a floor: § 8800 opens with "
            "an exception for what the owner and the direct contractor agree in writing, so a contract may "
            "lengthen it, and where it does the agreed final date should be stated on the application. Where "
            "there is a good faith dispute the owner may withhold up to 150 percent of the disputed amount "
            "and the rest still has to be paid. What § 8800 imposes is a penalty rather than interest, two "
            "percent a month on the amount wrongfully withheld in place of any interest otherwise due, "
            "written here as the 24 percent a year it comes to; the prevailing party in an action to collect "
            "it recovers costs and a reasonable attorney's fee. Downstream, a prime must pay a subcontractor "
            "within seven days of receiving a progress payment under Business and Professions Code § 7108.5 "
            "at the same two percent a month, and retention on private work is released within 45 days of "
            "completion under § 8812; neither is computed by this regime."
        ),
    },
    {
        "code": "bg_commercial_act_303a",
        "jurisdiction": "Bulgaria",
        "country_code": "BG",
        "statute": "Commercial Act (Търговски закон)",
        "statute_reference": "Article 303a",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "application_date",
        "payment_notice_days": None,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 14,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "none",
        "interest_basis": "reference_rate_plus_margin",
        "interest_reference_rate": (
            "Bulgarian National Bank base rate (основен лихвен процент), fixed on 1 January and 1 July of the current year"
        ),
        "interest_margin_percent": Decimal("10.000"),
        "interest_fixed_percent": None,
        "interest_statute": "Article 303a",
        "notes": (
            "An interest basis rather than a notice regime, the same shape as the EU Late Payment "
            "Directive this article transposes: Article 303a sets a payment term and the interest that "
            "runs when it is missed, with no payment or pay-less notice, so no_notice_effect is none. "
            "Fourteen days from receipt of the invoice or of the goods or services is the term absent "
            "agreement, written here as the final date for payment; the parties may agree a longer term "
            "up to sixty days, and beyond that only by exception in duly justified circumstances or where "
            "the nature of the goods or services requires it, so state the agreed final date on the "
            "application where a contract sets one. The statutory interest is the BNB base rate in force "
            "on 1 January or 1 July of the current year plus ten percentage points, which exceeds the "
            "Directive's own floor of eight points over the ECB reference rate: Bulgaria's transposition "
            "is stricter than the minimum, not a restatement of it, which is why this is a national row "
            "rather than a case for the eu_late_payment regime. Sourced from two independent legal "
            "practice guides rather than from the Commercial Act's own text, which this module has not "
            "independently retrieved; a reader who needs the statute's wording rather than its effect "
            "should go back to Article 303a before relying on the figures here. Whether Bulgarian public "
            "procurement carries this same period or a separate one, the way the Directive's own Article "
            "4 treats public authorities differently from transactions between undertakings, has not been "
            "checked, so this row is not confirmed for a public Bulgarian contract specifically."
        ),
    },
    {
        "code": "ng_ppa_2007",
        "jurisdiction": "Nigeria (public)",
        "country_code": "NG",
        "statute": "Public Procurement Act 2007",
        "statute_reference": "section 37",
        "due_date_basis": "application_date",
        "due_date_days": 0,
        "due_date_day_basis": "calendar",
        "payment_notice_basis": "application_date",
        "payment_notice_days": None,
        "payment_notice_day_basis": "calendar",
        "final_date_basis": "application_date",
        "final_date_days": 60,
        "final_date_day_basis": "calendar",
        "pay_less_days": None,
        "pay_less_day_basis": "calendar",
        "no_notice_effect": "none",
        "interest_basis": "contract",
        "interest_reference_rate": "",
        "interest_margin_percent": None,
        "interest_fixed_percent": None,
        "interest_statute": "",
        "notes": (
            "The clock for a payment owed by a Nigerian Ministry, Extra-Ministerial Office, government "
            "agency, parastatal or corporation on the public procurement of goods, works or services, "
            "which includes construction. Section 37(2) deems a payment delayed once it runs more than "
            "sixty days from the submission of the invoice, valuation certificate, or confirmation or "
            "authentication by the procuring entity, so enter that submission date as the application "
            "date; the sixty days is written here as the final date for payment, following the convention "
            "used for the other single-date regimes. The Act does not say whether the sixty days are "
            "calendar or working days, and this entry assumes calendar days, the reading this table gives "
            "every other statute that is silent on the point. There is no payment notice or pay-less "
            "notice in the Act, so silence carries no consequence beyond the payment becoming delayed. "
            "Section 37(3) does not fix a rate itself, it says a delayed payment attracts interest at the "
            "rate specified in the contract document, and section 37(4) obliges every contract to carry "
            "such a term, so the interest basis is contract by statutory command rather than by the Act's "
            "own silence. No private-sector statutory payment clock was found for Nigeria: this Act "
            "reaches only the procuring entities section 37(2) names, and nothing else retrieved sets a "
            "statutory period for a private Nigerian construction contract. A private clock is therefore "
            "not shipped as a second row; add one if a statute is later found rather than assuming this "
            "public clock extends to it."
        ),
    },
)

REGIME_CODES: tuple[str, ...] = tuple(regime["code"] for regime in PAYMENT_REGIMES)


def regime_by_code(code: str) -> dict[str, Any] | None:
    """The shipped catalogue entry for ``code``, or ``None`` when unknown."""
    for regime in PAYMENT_REGIMES:
        if regime["code"] == code:
            return dict(regime)
    return None


async def seed_payment_regimes(session: AsyncSession, *, refresh: bool = False) -> dict[str, int]:
    """Insert the shipped regimes that are not in the table yet.

    Idempotent, so it is safe on every startup and safe to call from a read
    path: a regime already present is left alone unless ``refresh`` is set, in
    which case its statutory fields are rewritten from the catalogue. Refresh is
    off by default because an operator may have corrected a period to match a
    contract's own compliant terms, and a silent overwrite on next boot would
    change every date computed afterwards.

    Args:
        session: Active async session. The caller owns the transaction.
        refresh: Rewrite regimes that already exist from the shipped catalogue.

    Returns:
        Counts under ``created``, ``updated`` and ``unchanged``.
    """
    from sqlalchemy import select

    from app.modules.payment_clock.models import PaymentRegime

    existing_rows = (await session.execute(select(PaymentRegime))).scalars().all()
    existing = {row.code: row for row in existing_rows}

    created = updated = unchanged = 0
    for entry in PAYMENT_REGIMES:
        row = existing.get(entry["code"])
        if row is None:
            session.add(PaymentRegime(**entry))
            created += 1
            continue
        if not refresh:
            unchanged += 1
            continue
        for key, value in entry.items():
            setattr(row, key, value)
        updated += 1

    await session.flush()
    logger.info(
        "Payment regimes seeded: %d created, %d updated, %d unchanged",
        created,
        updated,
        unchanged,
    )
    return {"created": created, "updated": updated, "unchanged": unchanged}


__all__ = [
    "PAYMENT_REGIMES",
    "REGIME_CODES",
    "regime_by_code",
    "seed_payment_regimes",
]
