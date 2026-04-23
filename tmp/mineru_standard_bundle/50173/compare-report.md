# GB50173-2014 Parse Comparison

## 50173 Raw Summary

- canonical pages: 86
- canonical tables: 107
- sections: 105
- full markdown chars: 176899
- anchored sections: 8
- section/page coverage: 0.0762

## 50173 Cleaned Summary

- sections: 100
- dropped sections: 5
- backfilled sections: 86
- anchored sections: 94
- section/page coverage: 0.94

## Baseline Notes

- GB50147-2010: modern MinerU raw output already had 102 non-empty pages, 7 tables, 64,283 markdown chars, and 131 headings.
- GB50148-2010: downstream AI pipeline could persist 140 clauses, but still had 78 warnings and 63 bad or missing page starts.
- GB50150-2016: canonical bundle summary already reached 170 pages, 60 tables, 1,102 sections, and 129,979 markdown chars.

## Practical Reading

- 50173 raw OCR is strong on content volume and table recall: 176,899 chars and 107 tables from 86 pages.
- The raw section bundle is not directly usable because page anchors were initially sparse (7.62% coverage).
- A deterministic loose heading-to-page backfill lifts coverage to 0.94, which is enough for local review and likely enough to feed current parse-asset consumers more safely.
- This supports the skill direction: canonicalize MinerU output first, then apply deterministic cleanup before any downstream clause extraction or formal ingestion.
- It does not prove final clause-extraction quality by itself; GB50148 remains the counterexample showing downstream AST/LLM stages can still degrade quality even when OCR completed.
