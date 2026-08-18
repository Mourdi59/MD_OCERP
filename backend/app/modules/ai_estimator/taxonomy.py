# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Trade-bucket taxonomy seed for the AI Estimate Builder grouping pass.

Stage 2 buckets every quantity group into a coarse trade so the review grid
can show a per-category summary and the AI group-refinement pass has a stable
label vocabulary to map onto. The buckets are derived from the CostEstimate
TOP-30/40 keyword analysis cross-checked with the CWICR
``classification.collection`` / ``department`` axes - the same ~15 trade
families a construction estimate is organised by, from earthworks through
finishing and MEP.

This is a deterministic keyword classifier, NOT machine learning: it tags a
group from its description / IFC class / classifier hint so that even with no
AI key the groups still carry a trade. The AI pass (when a key is present) may
rename or merge groups, but the trade vocabulary stays fixed so the UI never
sees a label it cannot render.
"""

from __future__ import annotations

import unicodedata

# Ordered list of (trade_key, keyword tuple). Order matters: the first bucket
# whose keywords match wins, so the more-specific families (MEP, finishes)
# precede the broad structural ones. Keywords are lower-cased substrings
# matched against the accent-folded group text (see ``fold_accents``), so a
# keyword may be written with its marks and still match a spelling that lost
# them. They intentionally mix English and a handful of high-frequency German
# / Russian stems so a multilingual CWICR description still classifies without
# a translation hop.
TRADE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "demolition",
        ("demolition", "demolish", "strip out", "abriss", "rückbau", "снос", "демонтаж"),
    ),
    (
        "earthworks",
        ("earthwork", "excavat", "backfill", "grading", "trench", "soil", "erdarbeit", "aushub", "земляны", "грунт"),
    ),
    (
        "foundations",
        ("foundation", "footing", "pile", "raft", "pier", "fundament", "gründung", "фундамент", "свая"),
    ),
    (
        "structure",
        (
            "concrete",
            "reinforc",
            "rebar",
            "beam",
            "column",
            "slab",
            "structural steel",
            "stahlbeton",
            "bewehrung",
            "stütze",
            "бетон",
            "арматур",
            "колонн",
            "балк",
        ),
    ),
    (
        "masonry",
        ("masonry", "brick", "block", "blockwork", "mauerwerk", "ziegel", "кладк", "кирпич"),
    ),
    (
        "envelope",
        (
            "facade",
            "cladding",
            "curtain wall",
            "roof",
            "roofing",
            "waterproof",
            "insulation",
            "fassade",
            "dach",
            "dämmung",
            "фасад",
            "кровл",
            "гидроизол",
            "утеплен",
        ),
    ),
    (
        "openings",
        ("window", "door", "glazing", "fenster", "tür", "окн", "двер", "остеклен"),
    ),
    (
        "finishes",
        (
            "plaster",
            "render",
            "screed",
            "paint",
            "floor",
            "ceiling",
            "tiling",
            "tile",
            "putz",
            "estrich",
            "bodenbelag",
            "штукатур",
            "стяжк",
            "покраск",
            "плитк",
            "потол",
            "пол",
        ),
    ),
    (
        "mep_mechanical",
        ("hvac", "duct", "ventilation", "heating", "boiler", "chiller", "lüftung", "heizung", "вентиляц", "отоплен"),
    ),
    (
        "mep_plumbing",
        ("plumbing", "pipe", "drainage", "sanitary", "water supply", "sanitär", "rohr", "водопровод", "канализац"),
    ),
    (
        "mep_electrical",
        ("electric", "wiring", "cable", "lighting", "switchgear", "elektro", "kabel", "электр", "кабел", "освещен"),
    ),
    (
        "sitework",
        ("landscap", "paving", "fencing", "external works", "kerb", "außenanlage", "благоустройств", "озеленен"),
    ),
)

# Stable display order for the per-category summary block. A group that
# matches no keyword lands in ``other`` so the bucket is always present.
TRADE_ORDER: tuple[str, ...] = tuple(key for key, _ in TRADE_KEYWORDS) + ("other",)

# Human-readable default labels (English source; the UI translates via
# ``t('ai_estimator.trade.<key>', {defaultValue})``).
TRADE_LABELS: dict[str, str] = {
    "demolition": "Demolition",
    "earthworks": "Earthworks",
    "foundations": "Foundations",
    "structure": "Structure",
    "masonry": "Masonry",
    "envelope": "Envelope",
    "openings": "Openings",
    "finishes": "Finishes",
    "mep_mechanical": "Mechanical (HVAC)",
    "mep_plumbing": "Plumbing",
    "mep_electrical": "Electrical",
    "sitework": "Sitework",
    "other": "Other",
}


# Letters that do not decompose under NFKD but have a settled Latin fold, so
# the Swiss "Aussenanlagen" and the German "Außenanlagen" reach one form.
_FOLD_MAP = {
    "ß": "ss",
    "ẞ": "ss",
    "ø": "o",
    "Ø": "o",
    "đ": "d",
    "Đ": "d",
    "ł": "l",
    "Ł": "l",
    "æ": "ae",
    "Æ": "ae",
    "œ": "oe",
    "Œ": "oe",
}


def fold_accents(text: str) -> str:
    """Drop diacritics so a spelling that lost its marks still matches.

    ``"Façade"`` becomes ``"Facade"`` and ``"Dämmung"`` becomes ``"Dammung"``.
    Both the keyword and the text being classified go through this, because
    folding one side alone would only move which spelling gets missed. The
    Cyrillic ``й`` and ``ё`` decompose too and come out as ``и`` and ``е``;
    that is harmless here precisely because both sides are folded alike.
    """
    if not text:
        return ""
    out: list[str] = []
    for ch in text:
        if ch in _FOLD_MAP:
            out.append(_FOLD_MAP[ch])
            continue
        decomposed = unicodedata.normalize("NFKD", ch)
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        out.append(stripped or ch)
    return "".join(out)


# Keywords whose mark carries the meaning, matched against the raw text
# instead. Folded, ``tür`` is ``tur``, and that trigraph sits inside
# structure, substructure, architectural, furniture, moisture, temperature,
# natural and Absturzsicherung: on the demo corpus folding it moved 347
# strings into openings. A keyword only belongs here if folding it really
# would swallow an ordinary word, which is checked from the other side in
# ``test_ai_estimator_taxonomy.py`` so the list cannot outlive its reason.
ACCENT_IS_LOAD_BEARING: frozenset[str] = frozenset({"tür"})

# (trade, keywords matched folded, keywords matched literally), built once.
_MATCH_TABLE: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = tuple(
    (
        trade_key,
        tuple(fold_accents(kw) for kw in keywords if kw not in ACCENT_IS_LOAD_BEARING),
        tuple(kw for kw in keywords if kw in ACCENT_IS_LOAD_BEARING),
    )
    for trade_key, keywords in TRADE_KEYWORDS
)


def classify_trade(*text_parts: str | None) -> str:
    """Return the trade bucket for a group from its descriptive text.

    Joins every supplied part (description, IFC class, classifier hint,
    category) into one lower-cased haystack and returns the first matching
    trade key, or ``"other"`` when nothing matches. Deterministic and
    side-effect-free so it works identically on the no-AI deterministic path.

    A missing accent does not change the answer: an export that wrote
    ``Rueckbau``, ``Servicos`` or ``Demolition`` where the source had
    ``Rückbau``, ``Serviços`` or ``Démolition`` lands in the same bucket as
    the accented spelling.
    """
    haystack = " ".join(p for p in text_parts if p).lower()
    if not haystack.strip():
        return "other"
    folded = fold_accents(haystack)
    for trade_key, folded_keywords, literal_keywords in _MATCH_TABLE:
        if any(kw in folded for kw in folded_keywords) or any(kw in haystack for kw in literal_keywords):
            return trade_key
    return "other"
