# Deterministic nutrition math engine and data prototype

This module now connects the initial deterministic calculator to the repository's cleaned USDA nutrient CSV and `recipes.json`. It is a **working prototype**, not yet a fully verified nutrition planner: estimates and unresolved ingredients are reported rather than silently treated as exact.

## Run it

From the repository root:

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 -m nutrition_engine.prototype --output /tmp/nutrition-prototype-report.json --review-csv /tmp/nutrition-ingredient-review.csv
```

The command prints a summary for all recipes and can write a detailed JSON report plus a review CSV of estimated/unresolved ingredients. The JSON report contains recipe-level totals, per-serving totals, known partial contributions, ingredient match IDs/descriptions, quantity conversion sources, confidence/assumption notes, and unresolved reasons; the CSV is a convenient human-review queue.

## Data flow

1. Read `recipes.json`.
2. Match each ingredient to a USDA `fdc_id` using the existing matcher plus explicit, reviewable project-specific overrides.
3. Convert supported ingredient quantities to grams. Prefer an unambiguous food-specific row from `cleanedData/food_portion_clean.csv` when the food ID and unit are available; otherwise use the existing ingredient-specific converter or a clearly flagged prototype assumption.
4. Load nutrient values per 100 g from `cleanedData/clean_usda_foods.csv` by normalized string `fdc_id`.
5. Call `calculate_recipe` to calculate batch/per-serving totals and completeness/coverage statuses.

The `measure_unit_clean.csv` aliases are loaded for unit normalization. The portion table contains 4,394 rows but only 82 food IDs overlap with the current 13,615-record nutrient CSV, so it cannot provide conversions for most current foods; missing conversions are not fabricated.

## Important correctness rules

- Empty/missing nutrient values become `None`; measured zeros remain `0.0`.
- A recipe ingredient is not silently dropped when its quantity or match is unresolved.
- A match or household-measure conversion based on a proxy/assumption is marked `estimated` and prevents the recipe from being labeled fully verified.
- Composite ingredients such as spice mixes and mixed vegetables remain unresolved when their proportions are unknown.
- `known_partial_totals` are **not verified totals**. They include calculated contributions from available resolved/estimated ingredients and must be interpreted alongside the ingredient statuses.
- Batch totals and per-serving totals remain separate; `calculate_meal` scales per-serving totals by servings eaten; `aggregate_results` defaults to per-serving values.

## Known limitations / next integration tasks

- `MATCH_OVERRIDES` in `prototype.py` are explicit prototype assumptions. Review them with the team and replace estimates with exact, preparation-state-matched records where possible.
- Many recipe quantities are missing or described as “to taste”; the engine flags these instead of inventing amounts.
- Some recipe ingredients are composites (e.g. quinoa/rice mix, ginger-garlic paste, spice blends) with no proportions. Those need normalized component-level recipe data.
- Several USDA portion IDs do not align with the IDs in the cleaned nutrient file. Investigate dataset-version/source alignment before relying on portions more broadly.
- The current prototype calculates each recipe. A real day/week result still requires the planner's selected meals and serving counts to be passed into `calculate_meal` / `aggregate_results`.

## Standalone math API

- `calculate_ingredient(fdc_id, amount_g, nutrients_per_100g)` calculates a resolved food contribution.
- `calculate_recipe(ingredients, servings=1)` returns batch and per-serving totals, partial totals, completeness, and coverage.
- `calculate_meal(recipe_result, servings_eaten=1)` calculates an eaten portion from per-serving totals.
- `aggregate_results(results, totals_key="per_serving_totals")` aggregates meals/recipes without accidentally summing full batches.

Run the unit and integration tests with `python3 -m unittest discover -s tests -v`.
For a tour of the test files and what each group covers, see [`tests/README.md`](../tests/README.md).
