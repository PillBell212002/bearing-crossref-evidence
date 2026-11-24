# Bearing Cross-Reference Verification — Prototype and Lessons Learned

A small Python prototype that takes an OEM bearing part number, finds the equivalent parts that a cross-reference table lists for it, and rates **how far each match can be trusted** by comparing published dimensions. It was also my first hands-on project in evaluating an LLM against a hand-labelled answer key.

> **Status: prototype, frozen.** Built on 44 rows to design and test a verification method, not as a production tool. The limitations are listed below.

---

## The problem

Buyers often need an equivalent part from another brand: the original is obsolete, out of stock, or too expensive. Cross-reference tables say "OEM part X = aftermarket part Y", but in practice:

- tables contain errors (translation and OCR mistakes, garbled part numbers),
- part numbers are written inconsistently (`5D-3632`, `5D 3632`, `MOX7312` vs `M0X7312`),
- OEM numbers get **superseded** by new ones,
- suffix variants (`2205-2RS/VT143` vs `2205-2RS/GFP9VA944`) share a base number but are not automatically the same part,
- and OEMs often publish only one dimension, or none.

A wrong match costs more than a missed one: the wrong part on a production line is worse than a buyer asking the supplier for a drawing. So the goal was never "always give an answer". It was **never guess**: say how strong the evidence is, and say what still needs checking.

## Data

| Source | What it gave |
|---|---|
| A public cross-reference table (Scribd, Polish headers) | 44 rows: Caterpillar OEM number → bearing number and brand (Timken, FAG, Bower, Link-Belt, SKF and others) |
| Manufacturer catalogs (Timken CAD, NTN Bearing Finder, Koyo, SKF) and distributor listings | Brand-side dimensions (bore, OD, width) |
| Caterpillar parts site and resellers | OEM-side dimensions, where published |

All dimensions were collected **by hand** and recorded with their source.

**Key finding:** only **5 of the 44 rows (about 11%)** had any OEM-side dimension published. Most matches cannot be confirmed from public data alone, so the system is built around evidence levels instead of yes/no answers.

This repository contains only a small cleaned sample and my gold set, not the full source table.

## How it works

```
Part number typed in (e.g. 5D-3632, 6Y-9885, M0X7312)
        │
        ▼
normalize + lookup     clean the number (spaces, dashes, case), handle
        │              O/0 confusion, suffixes and superseded numbers,
        │              then find the brand parts the table lists for it
        ▼
compare_dims           compare ONLY dimensions of the same type
        │              (bore, roller inner diameter, OD, width), ±0.05 mm
        ▼
Evidence level + reason + what to verify
```

### Evidence levels

Rules are applied in this order; the first one that matches decides the level.

| # | Rule | Level |
|---|---|---|
| 1 | Brand dimensions not found, unverified, assumed or inferred | **Unknown** |
| 2 | A same-type pair differs by more than 0.05 mm | **Conflict** |
| 3 | 2+ same-type pairs match / exactly 1 matches | **Strong** / **Partial** |
| 4 | Brand name in the source is garbled or blank | **Unknown** |
| 5 | OEM dimensions exist, but none of the same type as the brand's | **Unknown** |
| 6 | No OEM dimensions at all | **Source only** |

The order is a design decision. Doubtful dimensions are checked **first**, so copied or assumed sizes can never produce a false "Strong". A garbled brand label is checked **after** the dimension comparison, so real matching evidence is not thrown away because of a typo in the source.

### Matching details

- **Two match keys.** A strict key (uppercase, no spaces or dashes) is tried first. Only if that fails is a loose key (letter O → digit 0) tried, and those matches are flagged "matched via O/0 swap, check manually".
- **Suffixes.** `5D-3605T` returns the exact row first, then the base `5D-3605` rows, marked as suffix matches.
- **Supersession.** Searching the new number `6Y-9885` also finds rows listed under the old `5D-3632`, with a note when the link is unconfirmed.
- **Dimension types.** A Cat "inner diameter" on an outer-ring-and-rollers part is the diameter inside the rollers, not a shaft bore. Comparing the two would be meaningless, so each value carries a type.

## Example

```
$ python3 run.py 5D-3632
  #26  BS225836  [LINKBELT]  OEM 5D-3632
    Evidence: Unknown
    Reason:   Brand sizes not usable; dimension status 'Not found'.
  #27  MOX7312  [BOWER (Federal-Mogul)?]  OEM 5D-3632
    Evidence: Strong
    Reason:   Compared: roller_ID Cat 77.56 vs brand 77.584 mm (Δ 0.024, match); OD … (Δ 0.019, match).
```

## Results

Final evidence levels on the 44 real rows:

| Level | Rows |
|---|---|
| Strong | 1 |
| Partial | 2 |
| Unknown | 14 |
| Source only | 27 |

The one Strong match (Cat 5D-3632 / 6Y-9885 → MOX7312) rests on two dimensions: roller inner diameter 77.56 vs 77.584 mm and OD 112.45 vs 112.431 mm.

## Evaluation

### Success criteria (set before testing)

1. 0 incorrect "Strong" labels on the gold set
2. 0 fabricated dimensions: every number must be traceable to the source
3. 100% of mixed-type cases return Unknown, with a note on what to verify
4. The same level in repeated runs
5. Coverage: a definite level for as many answerable rows as the data allows

### Gold set

I labelled 8 real rows by hand, with the code's answer hidden, and added 3 **synthetic** rows (marked S1–S3) to test cases the real data never produced: Conflict, and a three-dimension match. The real rows are in `data/gold_set.csv`; the synthetic rows are defined in `src/compare_llm.py`.

### Code tests

`unittest` tests cover normalization, lookup, supersession, suffixes, O/0 swaps, the inch-to-mm fallback, mixed dimension types, and deliberately changed values that must produce Conflict. A regression test fails when any of the 44 results changes.

### LLM test

I gave an LLM (Claude, in a fresh chat each run) the same rules and only the evidence columns (no labels), asked for JSON with the level, the pairs compared and a reason, and ran it several times.

| Measure | Result |
|---|---|
| Accuracy on the gold rows (first test, 12 rows × 3 runs) | 36 / 36 |
| Consistency (same label in every run) | 46 / 47 rows in the first test; 47 / 47 after clarifying the rule order |
| Invented values | 0 |
| Mixed-type row (roller ID vs bore) | Unknown in every run |
| Final run vs the code, after aligning the rules | Same counts on all 44 rows |

For clear rules like these, plain code is cheaper and more reliable than an LLM. The LLM's real value is in the step code can't do: reading messy product pages. That is the next project.

## What went wrong, and what it taught me

| What happened | Lesson |
|---|---|
| The mm columns were Excel formulas, which had no saved values after Python edited the file, so every inch-based row looked dimensionless | Compute derived values in code, not in spreadsheet formulas |
| For one row, the brand-side columns held the OEM's own values, so the comparison always matched | A check that compares a value with itself always passes; the two sides must come from different sources |
| The code "agreed" with the sheet on all 44 rows, but the sheet had been labelled with the same rules | Agreement with earlier labels proves consistency, not accuracy; only an independent hand-labelled gold set found the errors |
| The gold set exposed a row where an OEM value was never entered, and a case no rule covered (OEM dimensions exist but no same-type pair) | Missing data and missing rules look the same in the output; check both |
| I labelled two rows differently on two different days | Human labels drift too; write labelling guidelines and hide the model's answer while labelling |
| Adding "first matching rule wins" to the prompt fixed one row and silently changed nine others from Unknown to Source only | A **prompt regression**: after any prompt change, compare every row against a trusted reference, not just the labelled ones |
| The prompt and the code defined "unclear brand" with different column names | A rule defined in two places drifts apart; define it once and reuse it |
| A table pasted into a chat lost its empty cells, and some synthetic values had no dimension type | Check the test input as carefully as the output |
| An LLM gave the right label while ignoring a third dimension | Check the reasoning (`pairs_compared`), not only the label |

**What I learned (in my own words):**
Through this project I understood the basic concepts of LLMs, how they work, and how to use AI (in this case Claude) to work on an issue that people in purchasing face all the time.

I learned that many OEMs do not share part dimensions with customers, and that taking dimensions from third-party websites is not very reliable. Prompting an AI never works well on the first attempt: making the prompt as descriptive as possible is key. An LLM will give different answers from run to run, and consistency only came once the rules in the prompt were exact and unambiguous.

Scalability was the other issue I met. This prototype has only 44 hand-picked rows, and growing the dataset is hard. Unless collecting the dimensions is automated, the tool becomes a burden rather than a help, because a buyer could do the same analysis manually. That is why I see this as a good prototype for learning, and why automating the dimension extraction is the next project.

## Limitations

- **44 rows.** As a lookup tool this adds little; its value is as a test bed for the method.
- **Lookup only finds what the table lists.** It does not discover new equivalents.
- **Dimensions were entered by hand.** Nothing is fetched automatically yet.
- **The LLM test covers the decision step only.** It received numbers that were already extracted.
- **Small gold set** (8 real rows + 3 synthetic); the precision figures prove little at this size.
- **Unverified sources.** The cross-reference table is a third-party document, and the 5D-3632 → 6Y-9885 supersession is from my own research and not confirmed by Caterpillar.

## Next steps

1. **Automatic dimension extraction (project 2).** An LLM reads a product page or screenshot and returns each dimension with its type, value in mm and the exact source quote, evaluated against a hand-labelled set of pages. The extracted values then feed `compare_dims`.
2. **Reverse search (later).** Given a part's dimensions, find catalog parts that fit.

## Repository layout

```
src/
  normalize.py      part-number cleaning, base/suffix split, lookup
  compare.py        compare_dims and the evidence rules
  compare_llm.py    compares LLM labels with compare_dims, row by row
run.py              command-line demo: python3 run.py <part number>
tests/              unittest unit and regression tests
data/
  gold_set.csv          my hand-labelled real rows
  cleaned_sample.csv    5 rows of the cleaned cross-reference sheet
```

The full spreadsheet (`bearing_cross_reference_v4.xlsx`) is not in this repository.
The code looks for it in the folder above the repository, or in `$CROSSREF_WORKBOOK`;
`run.py`, `src/compare.py`, `src/compare_llm.py` and the tests need it.

```bash
python3 -m pip install openpyxl
python3 -m unittest discover -s tests -v
python3 run.py 5D-3632
```

## Tools

Python (openpyxl, regular expressions), unittest, Claude (LLM evaluation, and Claude Code as a coding assistant), Databricks Genie (cross-checking the level counts), Excel.
