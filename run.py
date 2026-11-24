"""Look up a part number and show each candidate brand part with its evidence level.

Run:  python3 run.py 5D-3632
      python3 run.py 5D-3632 M0X7312      (several numbers at once)

The number can be a Cat OEM number or a brand bearing number. For each row
found, it prints the brand part, how the row was found, and the evidence level
and reason worked out by compare_dims from the dimensions. If the spreadsheet's
"Match status" says something different, that is shown too.
Reads bearing_cross_reference_v4.xlsx read-only; changes nothing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from compare import compare_dims  # noqa: E402
from normalize import load_rows, lookup  # noqa: E402


# lookup() returns a summary of each row, not the row itself, so find the
# full sheet row(s) that the summary came from (same OEM, bearing and brand).
def rows_for_hit(hit, rows):
    return [r for r in rows
            if r.get("OEM No. (Cat)") == hit["oem"]
            and r.get("Bearing No.") == hit["bearing"]
            and r.get("Brand (cleaned)") == hit["brand"]]


def show(number, rows):
    hits = lookup(number, rows)
    print(f"{number}: {len(hits)} candidate(s)")
    if not hits:
        print("  No row found under OEM No., Superseded by, Old No.(s) or Bearing No.")
        return False
    for hit in hits:
        for row in rows_for_hit(hit, rows):
            try:
                level, reason = compare_dims(row)
            except ValueError as e:
                level, reason = "Error", f"compare_dims error: {e}"
            print(f"\n  #{row.get('#')}  {hit['bearing'] or '(no bearing no.)'}  "
                  f"[{hit['brand'] or 'brand blank'}]  OEM {hit['oem']}")
            print(f"    Evidence: {level}")
            print(f"    Reason:   {reason}")
            print(f"    Found via: {hit['matched_via']}")
            if hit["note"]:
                print(f"    Note:     {hit['note']}")
            sheet = row.get("Match status")
            if sheet != level:
                print(f"    Sheet says: {sheet} (differs from computed level)")
    print()
    return True


def main(argv):
    if len(argv) < 2:
        sys.exit("Usage: python3 run.py <part number> [more part numbers]")
    rows = load_rows()
    found = [show(number, rows) for number in argv[1:]]
    return 0 if all(found) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
