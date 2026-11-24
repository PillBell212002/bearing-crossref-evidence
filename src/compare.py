"""Calculate the evidence level for each row from its dimensions,
instead of reading the "Match status" column.

Run:  python3 src/compare.py
It reads bearing_cross_reference_v4.xlsx (read-only), writes
comparison_report.csv in the repo root (git-ignored), and prints a sheet-vs-computed table.
"""

import csv
from collections import Counter
from pathlib import Path

from normalize import load_rows

TOLERANCE_MM = 0.05
UNCLEAR_BRANDS = {"DROZD", "BOWANIE", "BÓR", ""}
LEVELS = ["Strong", "Partial", "Source only", "Unknown", "Conflict"]
REPORT = Path(__file__).resolve().parents[1] / "comparison_report.csv"


# Turns a cell into a list of pieces split on ";" ("77.56; 112.45" -> two items).
# A single number gives a one-item list; an empty cell gives an empty list.
def split_cell(value):
    if value is None or str(value).strip() == "":
        return []
    return [p.strip() for p in str(value).split(";")]


# Reads one size in millimetres. If the mm cell is empty but the inch cell
# has a number, it uses inches x 25.4. Returns None if neither has a number.
def mm_value(row, mm_col, in_col):
    mm = row.get(mm_col)
    if isinstance(mm, (int, float)):
        return float(mm)
    inches = row.get(in_col)
    if isinstance(inches, (int, float)):
        return round(inches * 25.4, 3)
    return None


# Collects the Cat-side sizes as a dictionary {type: mm},
# e.g. {"roller_ID": 77.56, "OD": 112.45}.
def cat_dims(row):
    values = split_cell(row.get("Cat dim value (mm)"))
    types = split_cell(row.get("Cat dim type"))
    if len(values) != len(types):
        raise ValueError(f"Cat dim value/type count differs: {values} vs {types}")
    return {t: float(v) for t, v in zip(types, values)}


# Collects the brand-side sizes as a dictionary {type: mm}.
# The "Bore d (mm)" column takes its type from "Brand dim type" (default "bore");
# OD and width are always "OD" and "width". Empty sizes are left out.
def brand_dims(row):
    bore_type = (row.get("Brand dim type") or "bore").strip()
    found = {
        bore_type: mm_value(row, "Bore d (mm)", "Bore d (in)"),
        "OD": mm_value(row, "OD D (mm)", "OD D (in)"),
        "width": mm_value(row, "Width (mm)", "Width (in)"),
    }
    return {t: v for t, v in found.items() if v is not None}


# Says why the brand-side SIZES can't be trusted, or "" if they can:
# Dimension status "Not found"/"Unverified", or Dimension source says
# assumed/inferred. Checked before any comparison (rule 1).
def dimension_reason(row):
    status = row.get("Dimension status")
    if status in ("Not found", "Unverified"):
        return f"dimension status '{status}'"
    source = str(row.get("Dimension source") or "")
    if "assumed" in source.lower() or "inferred" in source.lower():
        return "brand sizes assumed/inferred"
    return ""


# Says why the brand NAME is unclear, or "" if it is clear: "Brand (as printed)",
# trimmed, is exactly one of UNCLEAR_BRANDS (case-sensitive; blank counts).
# Checked only after Conflict/Strong/Partial (rule 4).
def brand_reason(row):
    brand = str(row.get("Brand (as printed)") or "").strip()
    if brand in UNCLEAR_BRANDS:
        return "brand blank" if brand == "" else f"brand '{brand}' unclear"
    return ""


# Works out the evidence level for one row from its sizes, and returns
# (level, reason). Only sizes of the same type are compared (bore with bore,
# roller_ID with roller_ID, OD with OD, width with width), within ±0.05 mm.
# Order (first rule that fits wins):
#   1. Dimension status Not found/Unverified, or source assumed/inferred -> Unknown
#   2. Conflict   3. Strong / Partial
#   4. Brand (as printed) in UNCLEAR_BRANDS -> Unknown
#   5. Cat sizes exist but no same-type pair -> Unknown (with a note on which size to look up)
#   6. No Cat sizes -> Source only
def compare_dims(row):
    why = dimension_reason(row)
    if why:
        return "Unknown", f"Brand sizes not usable; {why}."

    cat = cat_dims(row)
    brand = brand_dims(row)

    pairs, conflict = [], False
    for dim_type, cat_mm in cat.items():
        if dim_type in brand:
            diff = abs(cat_mm - brand[dim_type])
            ok = diff <= TOLERANCE_MM
            conflict = conflict or not ok
            pairs.append(f"{dim_type} Cat {cat_mm:g} vs brand {brand[dim_type]:g} mm "
                         f"(Δ {diff:.3f}, {'match' if ok else 'DIFFERS'})")
    unpaired = [f"Cat {t} {v:g} mm has no brand {t}" for t, v in cat.items() if t not in brand]
    compared = "; ".join(pairs + unpaired)

    if conflict:
        return "Conflict", f"Compared: {compared}."
    if len(pairs) >= 2:
        return "Strong", f"Compared: {compared}."
    if len(pairs) == 1:
        return "Partial", f"Compared: {compared}."

    why = brand_reason(row)
    if why:
        extra = f" ({compared})" if compared else ""
        return "Unknown", f"No same-type pair; {why}{extra}."
    if cat:
        cat_types = ", ".join(cat)
        brand_types = ", ".join(brand) or "none"
        or_cat = f" (or Cat's {brand_types})" if brand else ""
        return "Unknown", (f"Different dimension types: Cat gives {cat_types}, "
                           f"brand gives {brand_types}. "
                           f"Verify: find the brand's {cat_types}{or_cat}.")
    if not cat:
        return "Source only", "No Cat-side dimensions; nothing compared."
    return "Source only", f"No same-type pair to compare: {compared}."


# Runs compare_dims on every row, writes comparison_report.csv and
# returns the report lines (one dictionary per row).
def build_report(rows=None, path=REPORT):
    if rows is None:
        rows = load_rows()
    report = []
    for row in rows:
        level, reason = compare_dims(row)
        sheet = row.get("Match status")
        report.append({
            "row #": row.get("#"),
            "OEM no.": row.get("OEM No. (Cat)"),
            "bearing no.": row.get("Bearing No."),
            "sheet Match status": sheet,
            "computed level": level,
            "reason": reason,
            "agree (Y/N)": "Y" if level == sheet else "N",
        })
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(report[0]))
        writer.writeheader()
        writer.writerows(report)
    return report


# Prints a table counting sheet level (rows) against computed level (columns).
def print_crosstab(report):
    counts = Counter((r["sheet Match status"], r["computed level"]) for r in report)
    width = max(len(x) for x in LEVELS) + 2
    print("sheet \\ computed".ljust(width) + "".join(l.rjust(width) for l in LEVELS) + "Total".rjust(8))
    for sheet in LEVELS:
        cells = [counts[(sheet, comp)] for comp in LEVELS]
        print(sheet.ljust(width) + "".join(str(c).rjust(width) for c in cells) + str(sum(cells)).rjust(8))
    totals = [sum(counts[(s, c)] for s in LEVELS) for c in LEVELS]
    print("Total".ljust(width) + "".join(str(t).rjust(width) for t in totals) + str(sum(totals)).rjust(8))


if __name__ == "__main__":
    lines = build_report()
    print(f"Wrote {REPORT} ({len(lines)} rows)\n")
    print_crosstab(lines)
    disagree = [r for r in lines if r["agree (Y/N)"] == "N"]
    print(f"\nRows that disagree: {len(disagree)}")
    for r in disagree:
        print(f"  #{r['row #']} {r['OEM no.']} {r['bearing no.']}: "
              f"sheet {r['sheet Match status']} -> computed {r['computed level']} | {r['reason']}")
