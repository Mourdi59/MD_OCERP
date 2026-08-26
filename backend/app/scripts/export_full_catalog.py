# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Export FULL resource catalog from ONE CWICR region.

Columns match oe_catalog_resource DB schema exactly, so the file
can be imported directly via API.

Extra properties go into the 'specifications' JSON column.

Usage (from any directory):
    python -m app.scripts.export_full_catalog

The source parquet lives in a DDC toolkit checkout beside this repository;
point ``CWICR_TOOLKIT_ROOT`` at it if yours is somewhere else. The export lands
in ``<data dir>/catalog``, which is ``<repo>/data/catalog`` for a checkout.
"""

import json
import math
import os
from pathlib import Path

import pandas as pd

from app.core.storage import resolve_data_dir


def _f(val) -> float | None:
    """Safe float."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        return round(float(val), 4)
    except (ValueError, TypeError):
        return None


def _s(val) -> str:
    """Safe string."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    return str(val).strip()


# ── Category keywords ────────────────────────────────────────────────────

MAT_CATS = {
    "Concrete & Cement": ["concrete", "cement", "mortar"],
    "Steel & Metal": ["steel", "metal", "iron", "forging", "structure", "channel", "beam", "angle"],
    "Welding Consumables": ["weld", "electrode"],
    "Wood & Timber": ["wood", "timber", "lumber", "plywood", "board", "sleeper", "prop"],
    "Pipes & Fittings": ["pipe", "tube", "valve", "fitting", "flange"],
    "Paint & Coatings": ["paint", "primer", "varnish", "putty", "enamel", "lacquer"],
    "Insulation": ["insulation", "thermal", "mineral wool"],
    "Aggregates & Earth": ["sand", "gravel", "crushed", "rock", "soil", "clay"],
    "Fasteners": ["bolt", "nut", "screw", "washer", "nail", "anchor", "rivet"],
    "Waterproofing": ["waterproof", "bitumen", "membrane", "mastic", "roofing"],
    "Electrical": ["cable", "wire", "insulating tape"],
    "Glass & Glazing": ["glass", "window", "glazing"],
    "Chemicals & Gases": ["oxygen", "acetylene", "propane", "acid", "alcohol", "solvent", "kerosene"],
    "Water & Utilities": ["water", "tap water"],
    "Rubber & Seals": ["rubber", "gasket", "seal", "paronite"],
}
EQU_CATS = {
    "Cranes": ["crane", "lifting"],
    "Trucks & Vehicles": ["truck", "flatbed", "semi-trailer", "tractor"],
    "Welding Equipment": ["weld", "arc weld", "inverter"],
    "Excavators": ["excavator"],
    "Bulldozers": ["bulldozer"],
    "Hoists & Winches": ["winch", "hoist"],
    "Compressors": ["compressor"],
    "Pumps": ["pump"],
}


def _categorize(name: str, typ: str) -> str:
    nl = name.lower()
    cats = MAT_CATS if typ in ("material", "abstract_material") else EQU_CATS if typ == "equipment" else {}
    for cat, kws in cats.items():
        if any(kw in nl for kw in kws):
            return cat
    return {
        "labor": "Labor",
        "operator": "Machine Operators",
        "electricity": "Electricity",
    }.get(typ, "General")


def _real_type(row) -> str:
    rt = _s(row.get("row_type", ""))
    is_mach = bool(row.get("is_machine", False))
    is_mat = bool(row.get("is_material", False))
    is_abs = bool(row.get("is_abstract", False))
    unit = _s(row.get("resource_unit", "")).lower()
    if rt == "Machinist":
        return "operator"
    if rt == "Electricity":
        return "electricity"
    if is_abs:
        return "abstract_material"
    if is_mach:
        return "equipment"
    if is_mat:
        if unit in ("hrs", "h", "person-hour", "person-hours"):
            return "labor"
        return "material"
    return "other"


#: Environment variable naming the DDC toolkit checkout that holds the source
#: parquet. Deliberately NOT ``CWICR_PARQUET_ROOT``: that variable is already
#: taken by :mod:`app.modules.costs.parquet_lookup` for a different layout
#: (``<root>/<XX>___DDC_CWICR/``), and reusing the name would point one of them
#: at the other's tree.
_TOOLKIT_ROOT_ENV = "CWICR_TOOLKIT_ROOT"


def _toolkit_root() -> Path:
    """Return the DDC toolkit checkout that holds the source parquet.

    The toolkit is not part of this repository and is not shipped with the
    package, so the default is where a developer checkout puts it: beside the
    repository, which is what the previous ``os.getcwd() / ".." / ".."`` reached
    when the script was run the one way its docstring describes. Anchoring on
    ``__file__`` reaches the same place from any working directory.

    An installed wheel has no toolkit tree at all and will fail loudly on the
    read. That is the correct outcome - this is a developer tool, not a product
    surface.
    """
    declared = os.environ.get(_TOOLKIT_ROOT_ENV, "").strip()
    if declared:
        return Path(declared).expanduser().resolve()
    # app/scripts/export_full_catalog.py -> parents[3] is the repo root, so
    # parents[4] is the directory the repository itself sits in.
    return Path(__file__).resolve().parents[4] / "DDC_Toolkit"


def _source_parquet_path() -> Path:
    """Return the CWICR parquet this export reads."""
    return _toolkit_root() / "pricing" / "data" / "parquet" / "ENG_TORONTO_workitems_costs_resources_DDC_CWICR.parquet"


def _catalog_output_dir() -> Path:
    """Return the directory the exported catalog is written to.

    ``resolve_data_dir()`` is ``<repo>/data`` for a source checkout, so this is
    the same directory the working-directory-relative version reached when it
    was run from ``backend/`` - and now it is that directory from anywhere,
    including a data dir an operator moved with ``OE_DATA_DIR``.
    """
    return resolve_data_dir() / "catalog"


def main() -> None:
    parquet_path = _source_parquet_path()
    print(f"Reading: {parquet_path.name}")
    df = pd.read_parquet(parquet_path)
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Filter to real resources
    res = df[
        (df["row_type"] != "Scope of work") & (df["resource_name"].notna()) & (df["resource_name"].str.strip() != "")
    ].copy()
    res["real_type"] = res.apply(_real_type, axis=1)

    grouped = res.groupby(["resource_code", "real_type"], sort=False)
    print(f"Unique resources: {len(grouped):,}")

    rows = []
    for (code, rtype), group in grouped:
        first = group.iloc[0]
        rates = group["resource_price_per_unit_eur_current"].dropna()
        rates = rates[rates > 0]
        costs = group["resource_cost_eur"].dropna()
        costs = costs[costs > 0]
        qtys = group["resource_quantity"].dropna()
        qtys = qtys[qtys > 0]

        name = _s(first.get("resource_name", ""))
        unit = _s(first.get("resource_unit", ""))
        category = _categorize(name, rtype)

        avg_rate = round(float(rates.mean()), 2) if len(rates) > 0 else 0
        min_rate = round(float(rates.min()), 2) if len(rates) > 0 else 0
        max_rate = round(float(rates.max()), 2) if len(rates) > 0 else 0

        # Build specifications dict (all extra properties)
        specs: dict = {}
        specs["unit_rate_median"] = round(float(rates.median()), 2) if len(rates) > 0 else 0
        specs["price_variants_count"] = int(rates.nunique()) if len(rates) > 0 else 0
        specs["avg_cost_per_use"] = round(float(costs.mean()), 2) if len(costs) > 0 else 0
        specs["avg_quantity_per_use"] = round(float(qtys.mean()), 4) if len(qtys) > 0 else 0
        specs["used_in_rate_codes"] = int(group["rate_code"].nunique())
        specs["row_type"] = _s(first.get("row_type", ""))
        specs["is_material"] = bool(first.get("is_material", False))
        specs["is_machine"] = bool(first.get("is_machine", False))
        specs["is_abstract"] = bool(first.get("is_abstract", False))

        # Hierarchy
        specs["parent_category"] = _s(first.get("category_type", ""))
        specs["parent_collection"] = _s(first.get("collection_name", ""))
        specs["parent_department"] = _s(first.get("department_name", ""))[:100]
        specs["parent_section"] = _s(first.get("section_name", ""))[:100]

        # Machine-specific
        mc = _s(first.get("machine_class2_name", ""))
        if mc:
            specs["machine_class"] = mc
        eg = _s(first.get("personnel_machinist_grade", ""))
        if eg:
            specs["machinist_grade"] = eg
        ekwh = _f(first.get("electricity_consumption_kwh_per_machine_hour"))
        if ekwh:
            specs["electricity_kwh_per_hour"] = ekwh
        ecu = _f(first.get("electricity_cost_per_unit"))
        if ecu:
            specs["electricity_cost_per_unit"] = ecu

        # Abstract
        if rtype == "abstract_material":
            acn = _s(first.get("price_abstract_resource_common_start", ""))
            if acn:
                specs["abstract_common_name"] = acn[:150]
            avc = _f(first.get("price_abstract_resource_position_count"))
            if avc:
                specs["abstract_variant_count"] = int(avc)
            apmin = _f(first.get("price_abstract_resource_est_price_min"))
            if apmin is not None:
                specs["abstract_price_min"] = apmin
            apmax = _f(first.get("price_abstract_resource_est_price_max"))
            if apmax is not None:
                specs["abstract_price_max"] = apmax
            apmean = _f(first.get("price_abstract_resource_est_price_mean"))
            if apmean is not None:
                specs["abstract_price_mean"] = apmean
            atg = _s(first.get("abstract_resource_tech_group", ""))
            if atg:
                specs["abstract_tech_group"] = atg
            avp = _s(first.get("price_abstract_resource_variable_parts", ""))
            if avp:
                specs["abstract_variable_parts"] = avp[:300]

        # Mass
        mn = _s(first.get("mass_name", ""))
        if mn:
            specs["mass_name"] = mn
            specs["mass_value"] = _f(first.get("mass_value"))
            specs["mass_unit"] = _s(first.get("mass_unit", ""))

        # ── Row matching DB schema exactly ──
        rows.append(
            {
                # DB columns
                "resource_code": code,
                "name": name,
                "resource_type": rtype,
                "category": category,
                "unit": unit,
                "base_price": str(avg_rate),
                "min_price": str(min_rate),
                "max_price": str(max_rate),
                "currency": "EUR",
                "usage_count": len(group),
                "source": "cwicr_extraction",
                "region": "ENG_TORONTO",
                "specifications": json.dumps(specs, ensure_ascii=False),
                "is_active": True,
            }
        )

    out_df = pd.DataFrame(rows)
    out_df = out_df.sort_values("usage_count", ascending=False)

    # ── Export ──
    out_dir = _catalog_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV (for import)
    csv_path = out_dir / "ENG_TORONTO_catalog.csv"
    out_df.to_csv(csv_path, index=False, encoding="utf-8")

    # Excel (for review, with specs unpacked)
    xlsx_path = out_dir / "ENG_TORONTO_Full_Resource_Catalog.xlsx"

    # Unpack specs for Excel readability
    specs_expanded = out_df.copy()
    spec_cols = set()
    for _, row in specs_expanded.iterrows():
        try:
            sp = json.loads(row["specifications"])
            spec_cols.update(sp.keys())
        except Exception:
            pass

    for col in sorted(spec_cols):
        specs_expanded[f"spec_{col}"] = specs_expanded["specifications"].apply(
            lambda s: json.loads(s).get(col, "") if s else ""
        )

    materials = specs_expanded[specs_expanded["resource_type"] == "material"]
    equipment = specs_expanded[specs_expanded["resource_type"] == "equipment"]
    abstract = specs_expanded[specs_expanded["resource_type"] == "abstract_material"]
    labor = specs_expanded[specs_expanded["resource_type"] == "labor"]
    operators = specs_expanded[specs_expanded["resource_type"] == "operator"]
    electricity = specs_expanded[specs_expanded["resource_type"] == "electricity"]

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        specs_expanded.to_excel(writer, sheet_name=f"All ({len(specs_expanded)})", index=False)
        materials.to_excel(writer, sheet_name=f"Materials ({len(materials)})", index=False)
        equipment.to_excel(writer, sheet_name=f"Equipment ({len(equipment)})", index=False)
        abstract.to_excel(writer, sheet_name=f"Abstract ({len(abstract)})", index=False)
        labor.to_excel(writer, sheet_name=f"Labor ({len(labor)})", index=False)
        operators.to_excel(writer, sheet_name=f"Operators ({len(operators)})", index=False)
        electricity.to_excel(writer, sheet_name=f"Electricity ({len(electricity)})", index=False)

    csv_kb = csv_path.stat().st_size // 1024
    xlsx_mb = xlsx_path.stat().st_size / (1024 * 1024)

    print(f"\n{'=' * 60}")
    print("  EXPORTED (DB-compatible format)")
    print(f"{'=' * 60}")
    print(f"  Into:  {out_dir}")
    print(f"  CSV:   {csv_path.name} ({csv_kb} KB) - for import")
    print(f"  Excel: {xlsx_path.name} ({xlsx_mb:.1f} MB) - for review")
    print(f"  Total: {len(out_df):,} resources")
    print()
    print("  DB columns (14): resource_code, name, resource_type, category,")
    print("    unit, base_price, min_price, max_price, currency,")
    print("    usage_count, source, region, specifications, is_active")
    print()
    print(f"  Extra specs in JSON: {len(spec_cols)} fields")
    print("  By type:")
    for t, cnt in out_df["resource_type"].value_counts().items():
        print(f"    {t}: {cnt}")


if __name__ == "__main__":
    main()
