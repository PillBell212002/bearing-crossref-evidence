"""Tests for normalize.py. Run all tests with:  python3 -m unittest discover -s tests -v"""

import sys
from pathlib import Path

# Make src/ importable when running:  python3 -m unittest discover -s tests -v
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import unittest

from openpyxl import load_workbook

from normalize import (DEFAULT_WORKBOOK, fill_mm_from_inches, lookup, load_rows,
                       normalize_part, sort_results, split_base_suffix)

# Read the spreadsheet once and share it between the lookup tests.
ROWS = load_rows()


class NormalizeTests(unittest.TestCase):

    # "5D 3632", "5D-3632" and "5d3632" should all give the same key.
    def test_cat_spellings_give_same_key(self):
        keys = {normalize_part(t)[0] for t in ["5D 3632", "5D-3632", "5d3632"]}
        self.assertEqual(keys, {"5D3632"})

    # MOX7312 (letter O) and M0X7312 (digit 0) have different strict keys
    # but the same loose key. The original text is kept for display.
    def test_letter_o_and_digit_zero_loose_key(self):
        strict_o, loose_o, original = normalize_part("MOX7312")
        strict_0, loose_0, _ = normalize_part("M0X7312")
        self.assertNotEqual(strict_o, strict_0)
        self.assertEqual(loose_o, loose_0)
        self.assertEqual(original, "MOX7312")

    # Empty cells give no key, and tabs / CR characters are removed.
    def test_empty_and_hidden_characters(self):
        self.assertEqual(normalize_part(None), (None, None, ""))
        self.assertEqual(normalize_part("   "), (None, None, ""))
        self.assertEqual(normalize_part("5D\t3632\r")[0], "5D3632")
        self.assertEqual(lookup("", ROWS), [])

    # lookup("M0X7312") finds the MOX7312 row only via the O/0 swap (flagged);
    # lookup("MOX7312") matches on the strict key, so no flag.
    def test_lookup_o_zero_swap_flag(self):
        swapped = lookup("M0X7312", ROWS)
        self.assertEqual([h["bearing"] for h in swapped], ["MOX7312"])
        self.assertTrue(swapped[0]["o_swap"])
        self.assertEqual(swapped[0]["note"], "matched via O/0 swap, check manually")

        normal = lookup("MOX7312", ROWS)
        self.assertEqual([h["bearing"] for h in normal], ["MOX7312"])
        self.assertFalse(normal[0]["o_swap"])
        self.assertEqual(normal[0]["note"], "")

    # A trailing letter on a Cat number is a suffix.
    def test_cat_trailing_letter_suffix(self):
        self.assertEqual(split_base_suffix("5D-3605T"), ("5D-3605", "T"))

    # Anything after "/" is a suffix.
    def test_slash_suffix(self):
        self.assertEqual(split_base_suffix("2205-2RS/VT143"), ("2205-2RS", "VT143"))

    # lookup("5D-3632") returns its rows and the 6Y-9885 supersession.
    def test_lookup_returns_superseded_number(self):
        hits = lookup("5D-3632", ROWS)
        self.assertTrue(hits)
        self.assertTrue(all(h["superseded_by"] == "6Y-9885" for h in hits))
        self.assertEqual({h["bearing"] for h in hits}, {"BS225836", "MOX7312"})

    # Extra check: the new number 6Y-9885 also finds the old 5D-3632 rows.
    def test_lookup_by_new_number_finds_old_rows(self):
        hits = lookup("6Y-9885", ROWS)
        self.assertEqual({h["oem"] for h in hits}, {"5D-3632"})
        self.assertTrue(all(h["matched_via"] == "Superseded by" for h in hits))

    # Fix 1a: an empty mm cell is filled from inches (x 25.4); a filled mm
    # cell is left alone.
    def test_fill_mm_from_inches(self):
        row = {"Bore d (mm)": None, "Bore d (in)": 2.5,
               "OD D (mm)": 42, "OD D (in)": 9.99,
               "Width (mm)": None, "Width (in)": None}
        fill_mm_from_inches(row)
        self.assertEqual(row["Bore d (mm)"], 63.5)
        self.assertEqual(row["OD D (mm)"], 42)
        self.assertIsNone(row["Width (mm)"])

    # Fix 1b: on the real sheet, the inch-only Timken 3982 row (5D-3605)
    # now has mm values: bore 63.5 mm, width 1.183 in = 30.048 mm.
    def test_real_rows_have_mm_values(self):
        hit = [h for h in lookup("5D-3605", ROWS) if h["oem"] == "5D-3605"][0]
        self.assertEqual(hit["bore_mm"], 63.5)
        self.assertAlmostEqual(hit["width_mm"], 30.048, places=3)

    # Fix 1c: the v4 sheet itself no longer holds formulas in the
    # Cross Reference sheet, so every value is stored.
    def test_sheet_has_no_formulas(self):
        ws = load_workbook(DEFAULT_WORKBOOK)["Cross Reference"]
        formulas = [c.coordinate for row in ws.iter_rows() for c in row
                    if isinstance(c.value, str) and c.value.startswith("=")]
        self.assertEqual(formulas, [])

    # Fix 2: MOX7312 brand-side sizes come from the NTN M0X7312A listing;
    # the Cat sizes 77.56 / 112.45 stay only in the Cat dim columns.
    def test_mox7312_brand_vs_cat_values(self):
        row = [r for r in ROWS if r["Bearing No."] == "MOX7312"][0]
        self.assertEqual(row["Bore d (mm)"], 77.584)
        self.assertEqual(row["OD D (mm)"], 112.431)
        self.assertEqual(row["Dimension source"], "NTN M0X7312A listing (variant unconfirmed)")
        self.assertEqual(row["Cat dim value (mm)"], "77.56; 112.45")
        brand_cells = [row[c] for c in ("Bore d (mm)", "OD D (mm)", "Width (mm)")]
        self.assertNotIn(77.56, brand_cells)
        self.assertNotIn(112.45, brand_cells)

    # Fix 3a: on the real sheet, lookup("5D-3605T") lists the exact
    # 5D-3605T row before the base-only 5D-3605 row.
    def test_sort_exact_before_suffix(self):
        hits = lookup("5D-3605T", ROWS)
        self.assertEqual([h["oem"] for h in hits], ["5D-3605T", "5D-3605"])

    # Fix 3b: sort order is exact, then suffix, then O/0 swap
    # (made-up results, given in the wrong order on purpose).
    def test_sort_order_all_three_kinds(self):
        unsorted = [
            {"name": "swap", "o_swap": True, "suffix_match": False},
            {"name": "suffix", "o_swap": False, "suffix_match": True},
            {"name": "exact", "o_swap": False, "suffix_match": False},
        ]
        self.assertEqual([r["name"] for r in sort_results(unsorted)],
                         ["exact", "suffix", "swap"])

    # Fix 4: a match through "Superseded by" with an "unverified" Source
    # gets the note; a direct OEM match on the same rows does not.
    def test_supersession_note(self):
        via_new = lookup("6Y-9885", ROWS)
        self.assertTrue(via_new)
        self.assertTrue(all(h["note"] == "supersession link unconfirmed" for h in via_new))
        via_old = lookup("5D-3632", ROWS)
        self.assertTrue(all(h["note"] == "" for h in via_old))

    # lookup("5D-3605T") finds the 5D-3605 rows, flagged as suffix matches.
    # Its own exact 5D-3605T row is also returned, and is NOT flagged.
    def test_lookup_suffix_finds_base_rows(self):
        hits = lookup("5D-3605T", ROWS)
        base_hits = [h for h in hits if h["oem"] == "5D-3605"]
        self.assertTrue(base_hits)
        self.assertTrue(all(h["suffix_match"] for h in base_hits))
        exact = [h for h in hits if h["oem"] == "5D-3605T"]
        self.assertEqual(len(exact), 1)
        self.assertFalse(exact[0]["suffix_match"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
