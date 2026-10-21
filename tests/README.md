# Test guide

This folder tests the nutrition calculator in layers. The goal is to catch math and data-quality problems early, before anyone trusts a generated meal plan.

## Run the full suite

Run this from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The verbose output prints each test name and whether it passed. A final `OK` means the assertions passed; it does not mean every recipe has accurate, fully verified nutrition.

## What's covered

- **`test_math_engine.py` — calculation rules.** Uses a small, deliberately fixed example nutrient profile so expected answers are known by hand. It checks scaling by grams, batch and per-serving totals, missing values, estimates, exclusions, unresolved ingredients, provenance, and aggregation.
- **`test_usda_loader.py` — real CSV loading.** Opens `cleanedData/clean_usda_foods.csv` and checks a known record, ID normalization, missing versus real-zero nutrients, unit aliases, portion-table loading, and unknown IDs.
- **`test_matching_safety.py` — risky name matches.** Checks that generic terms such as oil and milk don't select arbitrary variants, and that specific ingredients aren't confused with composite dishes.
- **`test_prototype_integration.py` — whole-project smoke tests.** Runs the current `recipes.json` through the USDA loader, matcher, quantity conversion, and calculator, then checks that unresolved data is visible in the results.

## How to read a failure

- A failure in `test_math_engine.py` usually points to calculation or completeness rules.
- A failure in `test_usda_loader.py` usually points to CSV columns, ID formatting, or missing-value handling.
- A failure in `test_matching_safety.py` usually means the matcher chose a questionable food record.
- A failure in `test_prototype_integration.py` may indicate that the current project data or one of the pipeline steps changed.

## What the tests do not prove yet

The fixed profile in `test_math_engine.py` is intentionally synthetic. The loader tests do use the actual USDA CSV, and the integration tests run the actual project recipes, but the latter are smoke tests—not a manual nutrition audit of every ingredient. We still need to review ingredient-to-USDA matches, raw/cooked states, composite ingredients, quantity estimates, and serving yields before calling recipe totals accurate.
