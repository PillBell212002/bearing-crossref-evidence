"""Tests for compare.py. Run all tests with:  python3 -m unittest discover -s tests -v"""

import sys
from pathlib import Path

# Make src/ importable when running:  python3 -m unittest discover -s tests -v
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import unittest

from compare import compare_dims
from normalize import load_rows, lookup

# Read the spreadsheet once; ROW[n] is the row whose "#" column is n.
ROWS = load_rows()
ROW = {r["#"]: r for r in ROWS}


class CompareDimsTests(unittest.TestCase):

    # Row 27 (5D-3632 / MOX7312): Cat roller_ID 77.56 and OD 112.45 against
    # brand roller_ID 77.584 and OD 112.431 -> two same-type matches -> Strong.
    def test_row_27_strong(self):
        level, reason = compare_dims(ROW[27])
        self.assertEqual(level, "Strong")
        self.assertIn("roller_ID Cat 77.56 vs brand 77.584", reason)
        self.assertIn("OD Cat 112.45 vs brand 112.431", reason)

    # Row 33 (5D-6059 / M1213EAHX): Cat roller_ID 80.523 vs brand BORE 65.
    # Different types must NOT be compared, so this is not a Conflict;
    # Cat sizes exist but none pair with the brand side -> Unknown.
    def test_row_33_different_types_not_compared(self):
        level, reason = compare_dims(ROW[33])
        self.assertNotEqual(level, "Conflict")
        self.assertEqual(level, "Unknown")
        self.assertIn("Different dimension types: Cat gives roller_ID, "
                      "brand gives bore, OD, width.", reason)

    # A row with Cat roller_ID only and brand bore only -> Unknown, with a
    # note saying which size to look up on each side.
    def test_cat_roller_id_only_brand_bore_only_is_unknown(self):
        row = dict(ROW[33], **{"OD D (mm)": None, "OD D (in)": None,
                               "Width (mm)": None, "Width (in)": None})
        level, reason = compare_dims(row)
        self.assertEqual(level, "Unknown")
        self.assertEqual(reason,
                         "Different dimension types: Cat gives roller_ID, brand gives bore. "
                         "Verify: find the brand's roller_ID (or Cat's bore).")

    # Synthetic: row 27's two matching pairs (roller_ID, OD), a clear brand, and a
    # Dimension source that says "Assumed". Rule 1 (assumed/inferred sizes) is
    # checked before Strong, so the result is Unknown, not Strong.
    def test_assumed_source_beats_two_matching_pairs(self):
        row = dict(ROW[27], **{"Brand (as printed)": "NTN",
                               "Dimension source": "Assumed = NTN M0X7312A"})
        level, reason = compare_dims(row)
        self.assertEqual(level, "Unknown")
        self.assertIn("assumed/inferred", reason)

    # Synthetic: row 27's two matching pairs with brand "DROZD" (unclear).
    # The brand check (rule 4) comes after Strong/Partial (rule 3) -> Strong.
    def test_unclear_brand_with_two_matching_pairs_is_strong(self):
        row = dict(ROW[27], **{"Brand (as printed)": "DROZD"})
        level, reason = compare_dims(row)
        self.assertEqual(level, "Strong")
        self.assertNotIn("unclear", reason)

    # Synthetic: blank brand and Cat OD 114.43 vs brand OD 112.431 (differs by
    # more than 0.05 mm). Conflict (rule 2) comes before the brand check -> Conflict.
    def test_blank_brand_with_conflicting_pair_is_conflict(self):
        row = dict(ROW[27], **{"Brand (as printed)": None,
                               "Cat dim value (mm)": "77.56; 114.43",
                               "Cat dim type": "roller_ID; OD"})
        level, reason = compare_dims(row)
        self.assertEqual(level, "Conflict")
        self.assertIn("OD Cat 114.43 vs brand 112.431", reason)

    # Row 35 (5D-6297 / 93825): Cat bore 209.55 vs brand bore 209.55 -> Partial.
    def test_row_35_partial(self):
        level, reason = compare_dims(ROW[35])
        self.assertEqual(level, "Partial")
        self.assertIn("bore Cat 209.55 vs brand 209.55", reason)

    # Row 35 changed by 0.1 mm on the brand side -> Conflict.
    def test_row_35_changed_gives_conflict(self):
        row = dict(ROW[35], **{"Bore d (mm)": 209.65})
        self.assertEqual(compare_dims(row)[0], "Conflict")

    # Row 35 with the mm cell empty: the inch cell (8.25 in) is used instead.
    def test_row_35_uses_inches_when_mm_empty(self):
        row = dict(ROW[35], **{"Bore d (mm)": None})
        self.assertEqual(row["Bore d (in)"], 8.25)
        self.assertEqual(compare_dims(row)[0], "Partial")

    # The calculated level agrees with the sheet's Match status on all 44 rows.
    def test_all_rows_agree_with_sheet(self):
        self.assertEqual(len(ROWS), 44)
        disagree = [r["#"] for r in ROWS if compare_dims(r)[0] != r["Match status"]]
        self.assertEqual(disagree, [])

    # lookup now shows "Brand (cleaned)" instead of "Brand (as printed)".
    def test_lookup_uses_cleaned_brand(self):
        hit = lookup("MOX7312", ROWS)[0]
        self.assertEqual(hit["brand"], "BOWER (Federal-Mogul)?")


if __name__ == "__main__":
    unittest.main(verbosity=2)
