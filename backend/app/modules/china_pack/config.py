# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Regional configuration for China.

The platform already carried China almost everywhere - a zh locale, two seeded
Chinese demo projects, GB 50500 markup templates, a Chinese partner pack - and
nowhere did anything declare what measurement system a Chinese project uses.
``app.core.regional_packs`` resolves that from the packs' own ``countries``
lists, so a project in a country no pack claims resolves to ``None``, and
``BOQUnitSystemConsistencyRule`` returns an empty result on ``None``. The rule
was therefore silent on every Chinese bill: not passing, not failing, absent.
This pack is what makes it speak.

On the standard edition. GB/T 50500-2024 superseded GB 50500-2013 from
2025-09-01, together with the GB/T 50854-2024 to GB/T 50862-2024 measurement
family. We hold neither text, so this pack names the edition whose content we
can actually verify rather than the newest one, exactly as the two Chinese demo
projects do. Note the prefix when reading the pair: the 2013 edition is GB, a
mandatory code, and the 2024 edition is GB/T, a recommended standard.
"""

from decimal import Decimal
from typing import Any

PACK_CONFIG: dict[str, Any] = {
    # ── Identity ─────────────────────────────────────────────────────────────
    "region_code": "CN",
    "countries": ["CN"],
    "default_currency": "CNY",
    "supported_currencies": ["CNY"],
    "default_locale": "zh",
    "measurement_system": "metric",
    "paper_size": "A4",
    "date_format": "YYYY-MM-DD",
    "number_format": "1,234.56",
    # ── Standards ────────────────────────────────────────────────────────────
    "standards": [
        {
            "code": "GB_50500",
            "name": "GB 50500-2013 - 建设工程工程量清单计价规范",
            "description": (
                "Code for bill of quantities valuation of construction works. Prescribes the "
                "bill format, the nine-digit item coding and the comprehensive unit rate that "
                "carries labour, materials, plant, overheads and profit in one figure."
            ),
        },
        {
            "code": "GB_50854_FAMILY",
            "name": "GB 50854 to GB 50862 - 工程量计算规范 (measurement rules)",
            "description": (
                "The measurement family that sits under GB 50500, one code per work type: "
                "GB 50854 building and decoration works, GB 50856 general installation works, "
                "GB 50857 municipal works, and the remainder of the 50854-50862 range."
            ),
        },
        {
            "code": "GB_50300",
            "name": "GB 50300-2013 - 建筑工程施工质量验收统一标准",
            "description": "Unified standard for acceptance of construction quality of building works.",
        },
        {
            "code": "GB_50011",
            "name": "GB 50011-2010 - 建筑抗震设计规范",
            "description": "Code for seismic design of buildings; sets the fortification intensity a design works to.",
        },
        {
            "code": "GB_T_50378",
            "name": "GB/T 50378 - 绿色建筑评价标准",
            "description": "Assessment standard for green building, rated one to three stars.",
        },
    ],
    # ── Cost data references ─────────────────────────────────────────────────
    "cost_database_references": [
        {
            "code": "NATIONAL_QUOTA",
            "name": "全国统一建筑工程基础定额 - National unified basic quota",
            "description": (
                "The national consumption quota for labour, material and plant per unit of work. "
                "Provinces issue their own priced quota on top of it, so a rate is only "
                "meaningful together with the province and the year it belongs to."
            ),
        },
        {
            "code": "PROVINCIAL_QUOTA",
            "name": "省级消耗量定额 - Provincial consumption quota",
            "description": (
                "Each province and directly administered municipality publishes its own priced "
                "quota, for example for Shanghai, Guangdong or Beijing. This is the level a "
                "comprehensive unit rate is normally built from."
            ),
        },
        {
            "code": "COST_INFORMATION",
            "name": "工程造价信息 - Construction cost information bulletins",
            "description": (
                "Material and plant prices published periodically by provincial and municipal "
                "cost management stations; the usual source for adjusting a quota rate to a "
                "current price level."
            ),
        },
    ],
    # ── Contract types ───────────────────────────────────────────────────────
    "contract_types": [
        {
            "code": "GF_2017_0201",
            "name": "GF-2017-0201 - 建设工程施工合同(示范文本)",
            "description": "Model construction contract issued for building and civil works.",
        },
        {
            "code": "GF_2020_0216",
            "name": "GF-2020-0216 - 建设项目工程总承包合同(示范文本)",
            "description": "Model design-build / EPC contract for whole-project general contracting.",
        },
        {
            "code": "UNIT_PRICE",
            "name": "单价合同 - Unit price contract",
            "description": "Payment on measured quantities at the tendered comprehensive unit rates.",
        },
        {
            "code": "LUMP_SUM",
            "name": "总价合同 - Lump sum contract",
            "description": "Fixed price for the whole defined scope.",
        },
        {
            "code": "FIDIC_CN",
            "name": "FIDIC Conditions (adapted for China)",
            "description": "Used on internationally funded and cross-border projects.",
        },
    ],
    # ── Tax rules (增值税 / VAT) ──────────────────────────────────────────────
    "tax_rules": [
        {
            "code": "CN_VAT_13",
            "name": "增值税 - 13% (goods)",
            "type": "vat",
            "rate_pct": "13",
            "description": "Standard rate on goods, which is what construction materials are bought at.",
        },
        {
            "code": "CN_VAT_9",
            "name": "增值税 - 9% (construction services)",
            "type": "vat",
            "rate_pct": "9",
            "description": "Rate for construction and installation services under the general method.",
            "note": "This is the rate a works contract normally carries.",
        },
        {
            "code": "CN_VAT_6",
            "name": "增值税 - 6% (modern services)",
            "type": "vat",
            "rate_pct": "6",
            "description": "Design, supervision, cost consultancy and other modern services.",
        },
        {
            "code": "CN_VAT_3_SIMPLIFIED",
            "name": "增值税 - 3% 简易计税 (simplified method)",
            "type": "vat",
            "rate_pct": "3",
            "description": (
                "Simplified assessment available to qualifying projects, for example "
                "contractor-supplied-labour-only works and certain older projects."
            ),
        },
    ],
    # ── Payment milestones (typical) ─────────────────────────────────────────
    "payment_templates": [
        {
            "code": "PROGRESS_PAYMENT",
            "name": "工程进度款 - Progress payment",
            "description": "Interim payment on measured progress, the usual monthly cycle on a works contract.",
            "fields": [
                "period",
                "measured_value",
                "advance_recovery",
                "retention_pct",
                "retention_amount",
                "previous_payments",
                "net_amount_due",
                "vat",
                "total_payable",
            ],
        },
        {
            "code": "SETTLEMENT",
            "name": "竣工结算 - Final settlement",
            "description": "Final measurement and settlement of the contract sum on completion.",
        },
    ],
    # ── Chinese number grouping ──────────────────────────────────────────────
    "number_system": {
        "name": "Chinese numbering system",
        "description": "Groups by four digits: 万 is 10,000 and 亿 is 100,000,000.",
        "examples": [
            {"value": 10000, "formatted": "10,000", "word": "1 万"},
            {"value": 100000000, "formatted": "100,000,000", "word": "1 亿"},
        ],
    },
    # ── Units (metric defaults, written the way a bill writes them) ──────────
    #
    # These are the words, not the Latin short codes, because that is what a
    # GB 50500 bill contains and what an estimator types. A pack that
    # prescribes a unit the validation vocabulary cannot read is how the rule
    # went blind on the Russian market, so the pairing is pinned by
    # ``test_the_china_pack_declares_its_default_units_in_chinese``.
    "default_units": {
        "length": "米",
        "area": "平方米",
        "volume": "立方米",
        "weight": "千克",
        "temperature": "°C",
    },
    # ── VAT rates ────────────────────────────────────────────────────────────
    #
    # "standard" is the 9% construction-services rate rather than the 13% goods
    # rate: this is the figure a works contract is priced with, and it is the
    # one a bill total needs.
    "vat_rates": {
        "CN": {
            "standard": Decimal("0.09"),
            "reduced": Decimal("0.06"),
            "zero": Decimal("0.00"),
        },
    },
}
