"""Tests for the calculator arithmetic and its handling of incomplete recipe inputs."""

import unittest

from nutrition_engine.math_engine import CORE_NUTRIENTS, NUTRIENTS, aggregate_results, calculate_ingredient, calculate_meal, calculate_recipe

# This is intentionally synthetic: tests can check exact answers by hand without
# depending on a changing external dataset. Real-data checks live in other files.
PROFILE = {
    "calories_kcal": 200, "protein_g": 20, "fat_g": 5, "carbs_g": 10,
    "fiber_g": 2, "sugars_g": 1, "sodium_mg": 100,
    "potassium_mg": 250, "calcium_mg": 50, "iron_mg": 2,
}


class IngredientCalculationTests(unittest.TestCase):
    """Checks one-food calculations before recipes or aggregation are involved."""
    def test_100_grams_returns_reference_values(self):
        """A 100 g input should reproduce the supplied per-100-g reference values."""
        result = calculate_ingredient(123, 100, PROFILE)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nutrients"]["protein_g"], 20)
        self.assertEqual(result["nutrients"]["calories_kcal"], 200)

    def test_200_grams_doubles_values_and_normalizes_id(self):
        """Doubling the grams should double nutrients, and USDA IDs should have one consistent type."""
        result = calculate_ingredient("123", 200, PROFILE)
        self.assertEqual(result["fdc_id"], "123")
        self.assertEqual(result["nutrients"]["protein_g"], 40)
        self.assertEqual(result["nutrients"]["sodium_mg"], 200)

    def test_missing_nan_and_empty_string_nutrients_are_unknown(self):
        """Missing or malformed nutrient values must stay unknown rather than becoming zero."""
        profile = dict(PROFILE, protein_g=None, calcium_mg=float("nan"), iron_mg="")
        result = calculate_ingredient(123, 100, profile)
        for nutrient in ("protein_g", "calcium_mg", "iron_mg"):
            self.assertIsNone(result["nutrients"][nutrient])
            self.assertIn(nutrient, result["missing_nutrients"])

    def test_invalid_weight_rejected_including_boolean(self):
        """Bad weights should fail early instead of creating plausible-looking nutrition numbers."""
        for amount in (-1, float("nan"), float("inf"), None, True):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                calculate_ingredient(123, amount, PROFILE)


class RecipeCalculationTests(unittest.TestCase):
    """Checks how ingredient results combine into batches, servings, and completeness statuses."""
    def test_recipe_batch_and_per_serving(self):
        """Batch totals should sum ingredients and per-serving totals should divide by the recipe yield."""
        ingredients = [
            {"name": "food A", "fdc_id": 1, "amount_g": 100, "nutrients_per_100g": PROFILE},
            {"name": "food B", "fdc_id": 2, "amount_g": 50, "nutrients_per_100g": PROFILE},
        ]
        result = calculate_recipe(ingredients, servings=3)
        self.assertTrue(result["complete"])
        self.assertEqual(result["batch_totals"]["protein_g"], 30)
        self.assertEqual(result["per_serving_totals"]["protein_g"], 10)
        self.assertEqual(result["coverage"]["ingredient_count_fraction"], 1.0)

    def test_unresolved_ingredient_blocks_verified_totals_but_keeps_partial_lower_bound(self):
        """An unresolved item should block verified totals while keeping known contributions visible."""
        ingredients = [
            {"name": "food A", "fdc_id": 1, "amount_g": 100, "nutrients_per_100g": PROFILE},
            {"name": "unknown", "status": "unresolved", "amount_g": 20, "reason": "no USDA match"},
        ]
        result = calculate_recipe(ingredients)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["batch_totals"]["protein_g"])
        self.assertEqual(result["known_partial_totals"]["protein_g"], 20)
        self.assertEqual(result["coverage"]["resolved_ingredient_count"], 1)
        self.assertAlmostEqual(result["coverage"]["known_weight_fraction"], 100 / 120)

    def test_missing_optional_nutrient_does_not_invalidate_core_totals(self):
        """An unknown optional nutrient should not erase valid core nutrient results."""
        profile = dict(PROFILE, calcium_mg=None)
        result = calculate_recipe([{"fdc_id": 1, "amount_g": 100, "nutrients_per_100g": profile}])
        self.assertFalse(result["complete"])
        self.assertTrue(result["core_complete"])
        self.assertIsNone(result["batch_totals"]["calcium_mg"])
        self.assertEqual(result["batch_totals"]["protein_g"], 20)

    def test_estimated_ingredient_is_flagged_and_not_fully_verified(self):
        """Estimated inputs can be calculated but must remain visibly unverified."""
        result = calculate_recipe([{"name": "estimated food", "status": "estimated", "fdc_id": 1, "amount_g": 100, "nutrients_per_100g": PROFILE, "reason": "quantity estimated"}])
        self.assertFalse(result["complete"])
        self.assertEqual(result["status"], "estimated")
        self.assertEqual(result["batch_totals"]["protein_g"], 20)

    def test_negligible_exclusion_requires_reason_and_is_flagged(self):
        """A deliberately excluded ingredient needs a reason so zero contribution is an explicit decision."""
        with self.assertRaises(ValueError):
            calculate_recipe([{"name": "salt", "status": "negligible_excluded"}])
        result = calculate_recipe([{"name": "tiny spice", "status": "negligible_excluded", "reason": "documented negligible quantity"}])
        self.assertFalse(result["complete"])
        self.assertEqual(result["status"], "estimated")
        self.assertEqual(result["coverage"]["negligible_excluded_count"], 1)

    def test_missing_amount_is_unresolved_not_a_crash(self):
        """A missing amount should become an unresolved ingredient rather than crash the whole recipe."""
        result = calculate_recipe([{"name": "chili", "fdc_id": 1, "nutrients_per_100g": PROFILE}])
        self.assertFalse(result["complete"])
        self.assertEqual(result["ingredients"][0]["status"], "unresolved")
        self.assertIsNone(result["batch_totals"]["protein_g"])

    def test_empty_recipe_is_not_complete_zero_nutrition(self):
        """No ingredients is not evidence that a recipe has zero nutrients."""
        result = calculate_recipe([])
        self.assertFalse(result["complete"])
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["batch_totals"]["protein_g"])

    def test_invalid_servings_rejected(self):
        """A recipe needs a positive numeric serving count to calculate per-serving totals."""
        for servings in (0, -1, True):
            with self.subTest(servings=servings), self.assertRaises(ValueError):
                calculate_recipe([], servings=servings)

    def test_provenance_is_preserved(self):
        """The result should retain source and matching details needed to review its inputs."""
        result = calculate_recipe([{"name": "paneer", "fdc_id": 1, "amount_g": 100, "nutrients_per_100g": PROFILE, "amount_source": "USDA portion", "match_score": 0.93, "description": "cottage cheese"}])
        item = result["ingredients"][0]
        self.assertEqual(item["amount_source"], "USDA portion")
        self.assertEqual(item["match_score"], 0.93)
        self.assertEqual(item["description"], "cottage cheese")

    def test_calculate_meal_scales_per_serving_not_batch(self):
        """The amount eaten should scale per-serving values, not the whole batch."""
        recipe = calculate_recipe([{"fdc_id": 1, "amount_g": 100, "nutrients_per_100g": PROFILE}], servings=4)
        meal = calculate_meal(recipe, servings_eaten=1.5)
        self.assertEqual(meal["totals"]["protein_g"], 7.5)


class AggregationTests(unittest.TestCase):
    """Checks combining multiple recipe/meal results without hiding missing data."""
    def test_empty_aggregate_is_incomplete(self):
        """An empty list should not look like a verified zero-nutrition meal or day."""
        result = aggregate_results([])
        self.assertFalse(result["complete"])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["component_count"], 0)
        self.assertIsNone(result["totals"]["protein_g"])

    def test_aggregate_defaults_to_per_serving_totals(self):
        """Default aggregation should add servings, not entire recipe batches of different sizes."""
        a = calculate_recipe([{"fdc_id": 1, "amount_g": 100, "nutrients_per_100g": PROFILE}], servings=2)
        b = calculate_recipe([{"fdc_id": 2, "amount_g": 100, "nutrients_per_100g": PROFILE}], servings=4)
        result = aggregate_results([a, b])
        self.assertEqual(result["totals"]["protein_g"], 15)

    def test_aggregate_does_not_hide_incomplete_totals(self):
        """One incomplete component must keep affected totals unknown after aggregation."""
        complete = {"complete": True, "per_serving_totals": {n: 1 for n in NUTRIENTS}}
        incomplete = {"complete": False, "per_serving_totals": {n: (None if n == "protein_g" else 2) for n in NUTRIENTS}}
        result = aggregate_results([complete, incomplete])
        self.assertFalse(result["complete"])
        self.assertIsNone(result["totals"]["protein_g"])
        self.assertEqual(result["totals"]["calories_kcal"], 3)

    def test_core_nutrient_constant(self):
        """The core nutrient list should stay explicit and stable for completeness checks."""
        self.assertEqual(CORE_NUTRIENTS, ("calories_kcal", "protein_g", "fat_g", "carbs_g"))


if __name__ == "__main__":
    unittest.main()
