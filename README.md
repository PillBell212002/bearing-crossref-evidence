# bearing-crossref-evidence

Cross-reference of Caterpillar OEM bearing numbers to brand bearing numbers,
with an evidence level (Strong / Partial / Unknown / Source only / Conflict)
calculated from same-type dimensions (±0.05 mm).

```
src/normalize.py   part-number cleaning and lookup()
src/compare.py     compare_dims(): evidence level from dimensions
tests/             unittest tests
data/gold_set.csv        rows hand-classified for an independent check (8 rows)
data/cleaned_sample.csv  5 sample rows of the cleaned "Cross Reference" sheet
```

The full spreadsheet (`bearing_cross_reference_v4.xlsx`) is **not** in this repo.
The code looks for it in the folder above the repo, or in `$CROSSREF_WORKBOOK`.
The tests need it.

```bash
python3 -m pip install openpyxl
python3 -m unittest discover -s tests -v
python3 src/compare.py          # writes comparison_report.csv (git-ignored)
python3 src/normalize.py 6Y-9885 M0X7312
```
