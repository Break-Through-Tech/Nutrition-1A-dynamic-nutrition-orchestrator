# Deterministic nutrition math engine (initial isolated contribution)

This is the arithmetic/aggregation layer only. It does **not** match recipe ingredients to USDA records or convert household measures to grams. Those responsibilities belong in the matching/normalization layer.

## Contract

- `calculate_ingredient(fdc_id, amount_g, nutrients_per_100g)` calculates nutrients for a resolved record. Nutrients are assumed to be per 100 g and must match the ingredient's preparation state.
- `calculate_recipe(ingredients, servings=1)` returns batch totals and per-serving totals. Each resolved ingredient needs `fdc_id`, `amount_g`, and `nutrients_per_100g`.
- Ingredient `status` may be `resolved` (default), `estimated`, `negligible_excluded`, or `unresolved`. Estimated and excluded entries are explicitly surfaced and prevent a recipe from being labeled fully verified. A `negligible_excluded` entry must include a documented `reason`; it is a deliberate policy exclusion, not a missing value treated as zero.
- Unresolved entries always block verified totals in this initial version. Do not silently exempt an unresolved ingredient from verification; any future nutrient-specific exception should be backed by a documented upstream rule and tests.
- `calculate_meal(recipe_result, servings_eaten=1)` scales **per-serving** totals by the quantity actually eaten.
- `aggregate_results(results)` defaults to `per_serving_totals`, to reduce the risk of summing full recipe batches as daily intake. Pass `totals_key="batch_totals"` only when batch totals are intentional, or `totals_key="totals"` for results from `calculate_meal`.

## Missing data and interpretation

Missing, blank, NaN, infinite, or invalid nutrient values become `None`, never zero. `batch_totals` and `per_serving_totals` contain verified totals where possible; an unresolved ingredient makes those totals unknown. `known_partial_totals` and `known_partial_per_serving_totals` separately expose sums of contributions that could be calculated. These are **not verified totals**; they can be interpreted as lower bounds only when all included contributions are non-negative and no excluded/estimated assumptions distort the interpretation.

`CORE_NUTRIENTS` contains calories, protein, fat, and carbohydrates. `core_complete` says whether verified values are available for these nutrients; it does not mean the whole recipe is fully verified. `complete` is stricter and requires all listed nutrients plus no estimates or documented exclusions. This lets a missing calcium value leave a known protein total usable without claiming every nutrient is complete.

The engine preserves common provenance fields when provided: `description`, `amount_source`, `match_score`, `estimated`, `source`, `notes`, and `reason`. It normalizes `fdc_id` to a string to avoid integer/string lookup mismatches. A path-independent CSV loader is intentionally not included yet; agree on the authoritative dataset path and column schema before adding one.

## Example

```python
from nutrition_engine import calculate_recipe, calculate_meal

recipe = calculate_recipe(
    [{
        "name": "example food", "fdc_id": 123, "amount_g": 150,
        "nutrients_per_100g": {
            "calories_kcal": 120, "protein_g": 10, "fat_g": 3,
            "carbs_g": 15, "fiber_g": 2, "sugars_g": 1,
            "sodium_mg": 50, "potassium_mg": 200,
            "calcium_mg": 30, "iron_mg": 1,
        },
    }],
    servings=3,
)
meal = calculate_meal(recipe, servings_eaten=1.5)
print(meal["totals"]["protein_g"])  # 7.5 g
```

## Tests

From the repository root:

```bash
python3 -m unittest discover -s tests -v
```

This is an isolated first contribution. It is not wired into `scripts/ingredient_matching.py`, the actual recipe data, or the planner. Integration should follow agreement on the shared data contract and authoritative recipe source.
