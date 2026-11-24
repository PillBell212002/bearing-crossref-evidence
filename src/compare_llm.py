"""Compare an LLM's evidence levels with compare_dims, row by row.

Run:  python3 src/compare_llm.py llm_results.csv

The CSV needs a "row" column (the "#" number, or a synthetic id such as S1)
and a "level" column (Strong / Partial / Source only / Unknown / Conflict).
Other columns are ignored. Header names are case-insensitive.

It compares the 44 rows of bearing_cross_reference_v4.xlsx (read-only) plus the
synthetic rows in SYNTHETIC below, prints how many agree, and lists every row
that differs, with both levels and compare_dims' reason.
"""

import csv
import sys

from compare import LEVELS, compare_dims
from normalize import load_rows

# Synthetic rows: row 27 (5D-3632 / MOX7312) with only the Cat-side columns changed.
# S1: OD 114.43 instead of 112.45 -> should be Conflict.
# S2, S3: three Cat values but only two Cat types -> compare_dims raises an
#         error for these (shown as level "Error").
SYNTHETIC = {
    "S1": {"Cat dim value (mm)": "77.56; 114.43", "Cat dim type": "roller_ID; OD"},
    "S2": {"Cat dim value (mm)": "77.56; 114.43;33.78", "Cat dim type": "roller_ID; OD"},
    "S3": {"Cat dim value (mm)": "77.56; 110.43;33.78", "Cat dim type": "roller_ID; OD"},
}
SYNTHETIC_BASE = "27"


# Turns a row id into a comparable string: 27, "27", "27.0" -> "27"; "s1" -> "S1".
def row_key(value):
    text = str(value).strip()
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text.upper()


# Spells a level the way LEVELS does ("source only" -> "Source only").
# Anything not in LEVELS is returned as written, so it shows up as a difference.
def clean_level(value):
    text = " ".join(str(value or "").split())
    for level in LEVELS:
        if text.lower() == level.lower():
            return level
    return text


# Reads the LLM CSV into {row key: level}. Stops if a row id appears twice.
def read_llm_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        names = {(n or "").strip().lower(): n for n in reader.fieldnames or []}
        row_col = names.get("row") or names.get("#")
        level_col = names.get("level")
        if not row_col or not level_col:
            sys.exit(f"{path}: needs 'row' and 'level' columns, found {reader.fieldnames}")
        results = {}
        for line in reader:
            if not str(line[row_col] or "").strip():
                continue
            key = row_key(line[row_col])
            if key in results:
                sys.exit(f"{path}: row {key} appears more than once")
            results[key] = clean_level(line[level_col])
    return results


# Builds {row key: row} for the 44 sheet rows plus the synthetic rows.
def all_rows(rows=None):
    if rows is None:
        rows = load_rows()
    by_key = {row_key(r["#"]): r for r in rows}
    for key, changes in SYNTHETIC.items():
        by_key[key] = dict(by_key[SYNTHETIC_BASE], **changes)
    return by_key


# Runs compare_dims, turning an error (e.g. bad Cat value/type count) into
# level "Error" so one bad row doesn't stop the run.
def computed_level(row):
    try:
        return compare_dims(row)
    except ValueError as e:
        return "Error", f"compare_dims error: {e}"


# Compares the two sets of levels. Returns (matches, differences), where each
# difference is (row key, LLM level, compare_dims level, reason).
# A row missing on one side counts as a difference ("(missing)").
def compare(llm, rows):
    matches, diffs = 0, []
    for key in sorted(set(llm) | set(rows), key=sort_key):
        llm_level = llm.get(key, "(missing)")
        if key in rows:
            level, reason = computed_level(rows[key])
        else:
            level, reason = "(missing)", "Row not in the sheet or SYNTHETIC."
        if llm_level == level:
            matches += 1
        else:
            diffs.append((key, llm_level, level, reason))
    return matches, diffs


# Sheet rows in number order first, then synthetic/other ids alphabetically.
def sort_key(key):
    return (0, int(key), "") if key.isdigit() else (1, 0, key)


def main(argv):
    if len(argv) != 2:
        sys.exit("Usage: python3 src/compare_llm.py llm_results.csv")
    llm = read_llm_csv(argv[1])
    rows = all_rows()
    matches, diffs = compare(llm, rows)
    total = matches + len(diffs)
    print(f"{matches} of {total} rows match "
          f"({len(rows) - len(SYNTHETIC)} sheet rows + {len(SYNTHETIC)} synthetic; "
          f"{len(llm)} rows in {argv[1]}).")
    if diffs:
        print(f"\nRows that differ: {len(diffs)}")
        for key, llm_level, level, reason in diffs:
            print(f"  #{key}: LLM {llm_level} -> compare_dims {level} | {reason}")


if __name__ == "__main__":
    main(sys.argv)
