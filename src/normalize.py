"""Helpers for matching part numbers in bearing_cross_reference_v4.xlsx."""

import os
import re
from pathlib import Path

from openpyxl import load_workbook

# By default, look for the spreadsheet in the folder that holds the crossref/
# repo (it is kept out of git). Set CROSSREF_WORKBOOK to use another file.
DEFAULT_WORKBOOK = Path(os.environ.get(
    "CROSSREF_WORKBOOK",
    Path(__file__).resolve().parents[2] / "bearing_cross_reference_v4.xlsx"))
SHEET = "Cross Reference"

# A Cat-style number: digit, letter or digit, optional space or dash, four digits,
# then one trailing letter (for example 5D-3605T or 5F 0589E).
CAT_WITH_SUFFIX = re.compile(r"^(\d[A-Z0-9][\s-]?\d{4})([A-Z])$", re.IGNORECASE)

# Note shown on results that only matched after swapping the letter O for 0.
O_SWAP_NOTE = "matched via O/0 swap, check manually"
# Note shown when a match went through "Superseded by" but the source is unverified.
SUPERSESSION_NOTE = "supersession link unconfirmed"


# Turns a part number into match keys so different spellings compare equal.
# strict_key: uppercase, with all whitespace (spaces, tabs, CR) and dashes removed.
# loose_key:  the same, but every letter O is replaced with the digit 0
#             (people mix them up, e.g. MOX7312 vs M0X7312).
# original:   the text as given (trimmed), for display.
# An empty cell gives no keys at all (None), so empty rows never match.
def normalize_part(text):
    original = "" if text is None else str(text).strip()
    if not original:
        return None, None, original          # empty cell: no key at all
    strict_key = re.sub(r"[\s\-]", "", original.upper())
    loose_key = strict_key.replace("O", "0")
    return strict_key, loose_key, original


# Splits a part number into its base number and its suffix.
# Everything after a "/" is a suffix (2205-2RS/VT143 -> 2205-2RS + VT143).
# A single letter on the end of a Cat-style number is also a suffix
# (5D-3605T -> 5D-3605 + T). If there is no suffix, the suffix is "".
def split_base_suffix(part):
    part = "" if part is None else str(part).strip()
    if "/" in part:
        base, suffix = part.split("/", 1)
        return base.strip(), suffix.strip()
    found = CAT_WITH_SUFFIX.match(part)
    if found:
        return found.group(1), found.group(2)
    return part, ""


# Gives one key of a part number: which=0 for the strict key, which=1 for
# the loose (O->0) key. Returns None for an empty cell.
def key_of(text, which):
    return normalize_part(text)[which]


# Gives the key of a part number without its suffix (strict or loose).
# Used so that 5D-3605T can find rows listed under 5D-3605.
def base_key(part, which=0):
    base, _ = split_base_suffix(part)
    return key_of(base, which)


# Pairs of columns that hold the same size in millimetres and in inches.
MM_IN_COLUMNS = [
    ("Bore d (mm)", "Bore d (in)"),
    ("OD D (mm)", "OD D (in)"),
    ("Width (mm)", "Width (in)"),
]


# Fills in a missing millimetre value from the inch value (mm = inches x 25.4).
# This is done in Python because Excel formulas have no saved result after
# Python edits the file, so the "(mm)" cell can read as empty.
def fill_mm_from_inches(row):
    for mm_col, in_col in MM_IN_COLUMNS:
        mm, inches = row.get(mm_col), row.get(in_col)
        if mm is None and isinstance(inches, (int, float)):
            row[mm_col] = round(inches * 25.4, 3)
    return row


# Reads the "Cross Reference" sheet and returns one dictionary per row,
# using the header names as keys (e.g. row["OEM No. (Cat)"]).
# Missing millimetre values are filled in from the inch values.
def load_rows(path=DEFAULT_WORKBOOK):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET]
    rows = ws.iter_rows(values_only=True)
    headers = list(next(rows))
    data = [fill_mm_from_inches(dict(zip(headers, values))) for values in rows if any(values)]
    wb.close()
    return data


# Splits a cell that may hold several part numbers ("5D-3632; 4B-1234")
# into a list of separate numbers. Empty cells give an empty list.
def split_numbers(cell):
    if not cell:
        return []
    return [p.strip() for p in re.split(r"[;,]", str(cell)) if p.strip()]


# Goes through every row once, comparing with one kind of key
# (which=0 strict, which=1 loose). A row matches if the number is found in
# "OEM No. (Cat)", "Superseded by", "Old No.(s)" or "Bearing No.".
# If none of those match, it tries the OEM number without its suffix and
# flags that result as a suffix match.
def find_rows(rows, number, which):
    key = key_of(number, which)
    key_base = base_key(number, which)
    results = []
    for row in rows:
        oem = row.get("OEM No. (Cat)")
        columns = [
            ("OEM No.", [oem]),
            ("Superseded by", split_numbers(row.get("Superseded by"))),
            ("Old No.(s)", split_numbers(row.get("Old No.(s)"))),
            ("Bearing No.", [row.get("Bearing No.")]),
        ]

        matched_via = None
        for name, values in columns:
            if key in [key_of(v, which) for v in values]:
                matched_via = name
                break

        suffix_match = False
        row_base = base_key(oem, which)
        if matched_via is None and row_base is not None and row_base == key_base:
            matched_via = "OEM No. (base only)"
            suffix_match = True

        if matched_via:
            o_swap = which == 1
            notes = []
            if o_swap:
                notes.append(O_SWAP_NOTE)
            if matched_via == "Superseded by" and "unverified" in str(row.get("Source") or "").lower():
                notes.append(SUPERSESSION_NOTE)
            results.append({
                "oem": oem,
                "brand": row.get("Brand (cleaned)"),
                "bearing": row.get("Bearing No."),
                "match_status": row.get("Match status"),
                "superseded_by": row.get("Superseded by"),
                "bore_mm": row.get("Bore d (mm)"),
                "od_mm": row.get("OD D (mm)"),
                "width_mm": row.get("Width (mm)"),
                "matched_via": matched_via,
                "suffix_match": suffix_match,
                "o_swap": o_swap,
                "note": "; ".join(notes),
            })
    return results


# Puts results in a fixed order: exact matches first, then base-only
# (suffix) matches, then matches that needed the O/0 swap.
def sort_results(results):
    return sorted(results, key=lambda r: (r["o_swap"], r["suffix_match"]))


# Finds every row that belongs to a part number (Cat number or bearing number).
# Step 1: match on the strict key. Those are normal matches.
# Step 2: only if step 1 found nothing, match on the loose (O->0) key and
#         flag each result "matched via O/0 swap, check manually".
# Results are sorted: exact, then base-only (suffix), then O/0 swap.
# An empty input returns an empty list.
def lookup(number, rows=None):
    if key_of(number, 0) is None:
        return []
    if rows is None:
        rows = load_rows()
    results = find_rows(rows, number, which=0)
    if not results:
        results = find_rows(rows, number, which=1)
    return sort_results(results)


# Lets you run "python normalize.py 5D-3632" to try a lookup by hand.
if __name__ == "__main__":
    import sys
    for number in sys.argv[1:] or ["5D-3632"]:
        print(f"lookup({number!r}):")
        for hit in lookup(number):
            print("  ", hit)
