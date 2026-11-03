
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import single_agent_planner as planner

from single_agent_planner import (
    total_for,
    choose_day,
    build_week,
    build_planning_only_week,
    catalog,
    normalize_ingredients,
    invalid_ingredient,
    recent_recipe_ids,
)


# ============================================================
# TEST DATA HELPERS
# ============================================================

def recipe(rid, slot, protein, calories):
    """Create a recipe with known deterministic macros."""
    return {
        "recipe_id": rid,
        "name": rid,
        "meal_type": slot,
        "macros": {
            "protein_g": protein,
            "calories_kcal": calories,
            "carbs_g": 20,
            "fat_g": 10,
        },
        "nutrition_verified": True,
    }


def raw_recipe(
    rid="tofu_bowl",
    slot="lunch",
    tags=None,
    ingredients=None,
):
    """Create a recipe in the format used by recipes.json."""
    if tags is None:
        tags = ["vegetarian"]

    if ingredients is None:
        ingredients = [
            {
                "name": "tofu",
                "quantity": 150,
                "unit": "g",
            }
        ]

    return {
        "recipe_id": rid,
        "name": rid,
        "meal_type": slot,
        "diet_tags": tags,
        "ingredients": ingredients,
    }


def verified_matcher(
    protein=40,
    calories=450,
    status="Included",
):
    """Fake USDA matcher: no CSV or external service required."""

    def calculate(ingredients):
        totals = {
            "protein_g": protein,
            "calories_kcal": calories,
            "carbs_g": 30,
            "fat_g": 15,
        }

        results = [
            {"status": status}
            for _ in ingredients
        ]

        return totals, results

    matcher = Mock()
    matcher.calculate_recipe_macros.side_effect = calculate
    return matcher


def diverse_week_recipes():
    """
    Three distinct recipes for each required meal slot.

    Three rotations are sufficient for the planner's
    previous-two-days nonrepeat rule.
    """
    recipes = []

    for slot in ("breakfast", "lunch", "dinner"):
        for i in range(3):
            recipes.append(
                recipe(
                    f"{slot}_{i}",
                    slot,
                    protein=50,
                    calories=500,
                )
            )

    return recipes


def planning_recipes():
    """Recipes without verified nutrition data."""
    recipes = []

    for slot in ("breakfast", "lunch", "dinner"):
        for i in range(3):
            recipes.append({
                "recipe_id": f"{slot}_{i}",
                "name": f"{slot.title()} {i}",
                "meal_type": slot,
                "macros": None,
                "nutrition_verified": False,
            })

    return recipes


def assert_no_recent_repeats(testcase, days):
    """Check the previous-two-days rule for an entire schedule."""
    for index, day in enumerate(days):
        current_ids = [
            meal["recipe_id"]
            for meal in day["meals"]
        ]

        # No duplicate recipe within the same day.
        testcase.assertEqual(
            len(current_ids),
            len(set(current_ids)),
        )

        # No recipe from either of the previous two days.
        previous_ids = {
            meal["recipe_id"]
            for previous_day in days[max(0, index - 2):index]
            for meal in previous_day["meals"]
        }

        testcase.assertTrue(
            set(current_ids).isdisjoint(previous_ids),
            msg=f"Recipe repeated on {day['day']}",
        )


# ============================================================
# 1. ORIGINAL FIVE TESTS
# ============================================================

class PlannerTests(unittest.TestCase):

    def setUp(self):
        self.recipes = [
            recipe("breakfast", "breakfast", 50, 500),
            recipe("lunch", "lunch", 50, 600),
            recipe("dinner", "dinner", 50, 600),
        ]

    def test_totals_are_summed_not_invented(self):
        totals = total_for(self.recipes)

        self.assertEqual(totals["protein_g"], 150)
        self.assertEqual(totals["calories_kcal"], 1700)

    def test_day_meets_targets(self):
        day, error = choose_day(
            self.recipes,
            140,
            2000,
        )

        self.assertIsNone(error)
        self.assertTrue(day["meets_protein"])
        self.assertTrue(day["meets_calories"])

    def test_strict_calorie_limit(self):
        day, error = choose_day(
            self.recipes,
            140,
            1700,
        )

        self.assertIsNone(error)
        self.assertFalse(day["meets_calories"])

    def test_week_has_seven_days(self):
        # Updated to provide enough recipes for no-repeat rules.
        week = build_week(
            diverse_week_recipes(),
            140,
            2000,
        )

        self.assertEqual(len(week["days"]), 7)
        self.assertTrue(week["all_days_valid"])

        assert_no_recent_repeats(
            self,
            week["days"],
        )

    def test_unreachable_protein_is_reported(self):
        day, error = choose_day(
            self.recipes,
            200,
            2000,
        )

        self.assertIsNone(error)
        self.assertFalse(day["meets_protein"])


# ============================================================
# 2. DETERMINISTIC NUTRITION MATH
# ============================================================

class NutritionMathTests(unittest.TestCase):

    def test_all_four_macros_are_summed(self):
        meals = [
            recipe("a", "breakfast", 30, 400),
            recipe("b", "lunch", 50, 600),
        ]

        totals = total_for(meals)

        self.assertEqual(totals["protein_g"], 80)
        self.assertEqual(totals["calories_kcal"], 1000)
        self.assertEqual(totals["carbs_g"], 40)
        self.assertEqual(totals["fat_g"], 20)

    def test_empty_meal_list_has_zero_totals(self):
        totals = total_for([])

        self.assertEqual(
            totals,
            {
                "calories_kcal": 0,
                "protein_g": 0,
                "carbs_g": 0,
                "fat_g": 0,
            },
        )

    def test_fractional_macros_are_summed(self):
        meals = [
            recipe("a", "breakfast", 12.5, 150.25),
            recipe("b", "lunch", 22.25, 220.5),
        ]

        totals = total_for(meals)

        self.assertAlmostEqual(
            totals["protein_g"],
            34.75,
        )

        self.assertAlmostEqual(
            totals["calories_kcal"],
            370.75,
        )

    def test_exact_protein_target_passes(self):
        meals = [
            recipe("a", "breakfast", 40, 400),
            recipe("b", "lunch", 50, 500),
            recipe("c", "dinner", 50, 500),
        ]

        day, error = choose_day(meals, 140, 2000)

        self.assertIsNone(error)
        self.assertTrue(day["meets_protein"])

    def test_one_calorie_below_limit_passes(self):
        meals = [
            recipe("a", "breakfast", 50, 600),
            recipe("b", "lunch", 50, 700),
            recipe("c", "dinner", 50, 699),
        ]

        day, error = choose_day(meals, 140, 2000)

        self.assertIsNone(error)
        self.assertEqual(
            day["totals"]["calories_kcal"],
            1999,
        )
        self.assertTrue(day["meets_calories"])

    def test_one_calorie_above_limit_fails(self):
        meals = [
            recipe("a", "breakfast", 50, 600),
            recipe("b", "lunch", 50, 700),
            recipe("c", "dinner", 50, 701),
        ]

        day, error = choose_day(meals, 140, 2000)

        self.assertIsNone(error)
        self.assertFalse(day["meets_calories"])

    def test_input_macros_are_not_mutated(self):
        meals = [
            recipe("a", "breakfast", 50, 500),
            recipe("b", "lunch", 50, 500),
        ]

        original = json.dumps(meals, sort_keys=True)

        total_for(meals)
        choose_day(meals, 100, 2000)

        self.assertEqual(
            json.dumps(meals, sort_keys=True),
            original,
        )


# ============================================================
# 3. INGREDIENT VALIDATION
# ============================================================

class IngredientValidationTests(unittest.TestCase):

    def test_valid_ingredient(self):
        ingredient = {
            "name": "tofu",
            "quantity": 100,
            "unit": "g",
        }

        self.assertFalse(invalid_ingredient(ingredient))

    def test_missing_quantity_is_invalid(self):
        ingredient = {
            "name": "tofu",
            "unit": "g",
        }

        self.assertTrue(invalid_ingredient(ingredient))

    def test_zero_quantity_is_invalid(self):
        ingredient = {
            "name": "tofu",
            "quantity": 0,
            "unit": "g",
        }

        self.assertTrue(invalid_ingredient(ingredient))

    def test_negative_quantity_is_invalid(self):
        ingredient = {
            "name": "tofu",
            "quantity": -100,
            "unit": "g",
        }

        self.assertTrue(invalid_ingredient(ingredient))

    def test_missing_unit_is_invalid(self):
        ingredient = {
            "name": "tofu",
            "quantity": 100,
        }

        self.assertTrue(invalid_ingredient(ingredient))

    def test_empty_name_is_invalid(self):
        ingredient = {
            "name": "",
            "quantity": 100,
            "unit": "g",
        }

        self.assertTrue(invalid_ingredient(ingredient))

    def test_boolean_quantity_is_invalid(self):
        ingredient = {
            "name": "tofu",
            "quantity": True,
            "unit": "g",
        }

        self.assertTrue(invalid_ingredient(ingredient))

    def test_nan_quantity_is_invalid(self):
        ingredient = {
            "name": "tofu",
            "quantity": math.nan,
            "unit": "g",
        }

        self.assertTrue(invalid_ingredient(ingredient))

    def test_infinite_quantity_is_invalid(self):
        ingredient = {
            "name": "tofu",
            "quantity": math.inf,
            "unit": "g",
        }

        self.assertTrue(invalid_ingredient(ingredient))

    def test_normalize_list_ingredients(self):
        data = raw_recipe()

        ingredients = normalize_ingredients(data)

        self.assertEqual(len(ingredients), 1)
        self.assertEqual(ingredients[0]["name"], "tofu")

    def test_normalize_dictionary_ingredients(self):
        data = {
            "ingredients": {
                "tofu": {
                    "quantity": 100,
                    "unit": "g",
                }
            }
        }

        ingredients = normalize_ingredients(data)

        self.assertEqual(ingredients[0]["name"], "tofu")
        self.assertEqual(ingredients[0]["quantity"], 100)

    def test_normalize_string_ingredient(self):
        data = {
            "ingredients": ["tofu"]
        }

        ingredients = normalize_ingredients(data)

        self.assertEqual(ingredients[0]["name"], "tofu")
        self.assertIsNone(ingredients[0]["quantity"])

    def test_unsupported_ingredient_structure(self):
        data = {
            "ingredients": 12345
        }

        self.assertIsNone(
            normalize_ingredients(data)
        )


# ============================================================
# 4. USDA MATCHER INTEGRATION
# ============================================================

class USDAMatcherTests(unittest.TestCase):

    def test_successful_match_is_verified(self):
        matcher = verified_matcher()

        valid, rejected = catalog(
            matcher,
            [raw_recipe()],
        )

        self.assertEqual(len(valid), 1)
        self.assertEqual(len(rejected), 0)
        self.assertTrue(valid[0]["nutrition_verified"])

    def test_matcher_receives_ingredient_list(self):
        matcher = verified_matcher()

        catalog(
            matcher,
            [raw_recipe()],
        )

        args, kwargs = (
            matcher.calculate_recipe_macros.call_args
        )

        self.assertIsInstance(args[0], list)
        self.assertIsInstance(args[0][0], dict)
        self.assertEqual(args[0][0]["name"], "tofu")

    def test_skipped_ingredient_rejects_recipe(self):
        matcher = verified_matcher(
            status="Skipped: unsupported unit or unknown conversion"
        )

        valid, rejected = catalog(
            matcher,
            [raw_recipe()],
        )

        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)

    def test_low_confidence_match_rejects_recipe(self):
        matcher = verified_matcher(
            status="Skipped: match confidence is too low for calculation"
        )

        valid, rejected = catalog(
            matcher,
            [raw_recipe()],
        )

        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)

    def test_no_suitable_match_rejects_recipe(self):
        matcher = verified_matcher(
            status="Skipped: no suitable match found"
        )

        valid, rejected = catalog(
            matcher,
            [raw_recipe()],
        )

        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)

    def test_missing_macro_rejects_recipe(self):
        matcher = verified_matcher()

        matcher.calculate_recipe_macros.return_value = (
            {
                "calories_kcal": 450,
                "protein_g": 40,
                "carbs_g": 30,
            },
            [{"status": "Included"}],
        )

        matcher.calculate_recipe_macros.side_effect = None

        valid, rejected = catalog(
            matcher,
            [raw_recipe()],
        )

        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)

    def test_negative_macro_rejects_recipe(self):
        matcher = verified_matcher(
            protein=-10,
        )

        valid, rejected = catalog(
            matcher,
            [raw_recipe()],
        )

        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)

    def test_nan_macro_rejects_recipe(self):
        matcher = verified_matcher(
            calories=math.nan,
        )

        valid, rejected = catalog(
            matcher,
            [raw_recipe()],
        )

        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)

    def test_infinite_macro_rejects_recipe(self):
        matcher = verified_matcher(
            protein=math.inf,
        )

        valid, rejected = catalog(
            matcher,
            [raw_recipe()],
        )

        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)

    def test_missing_quantity_cannot_be_verified(self):
        matcher = verified_matcher()

        data = raw_recipe(
            ingredients=[
                {
                    "name": "tofu",
                    "quantity": None,
                    "unit": "g",
                }
            ]
        )

        valid, rejected = catalog(
            matcher,
            [data],
        )

        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)

    def test_incomplete_matcher_results_reject_recipe(self):
        matcher = Mock()

        matcher.calculate_recipe_macros.return_value = (
            {
                "calories_kcal": 450,
                "protein_g": 40,
                "carbs_g": 30,
                "fat_g": 15,
            },
            [],
        )

        valid, rejected = catalog(
            matcher,
            [raw_recipe()],
        )

        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)

    def test_multiple_ingredients_all_must_match(self):
        matcher = Mock()

        matcher.calculate_recipe_macros.return_value = (
            {
                "calories_kcal": 450,
                "protein_g": 40,
                "carbs_g": 30,
                "fat_g": 15,
            },
            [
                {"status": "Included"},
                {"status": "Skipped: no suitable match found"},
            ],
        )

        data = raw_recipe(
            ingredients=[
                {"name": "tofu", "quantity": 100, "unit": "g"},
                {"name": "rice", "quantity": 100, "unit": "g"},
            ]
        )

        valid, rejected = catalog(
            matcher,
            [data],
        )

        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)


# ============================================================
# 5. DIETARY RESTRICTIONS
# ============================================================

class DietaryRestrictionTests(unittest.TestCase):

    def test_vegetarian_recipe_is_allowed(self):
        valid, rejected = catalog(
            None,
            [raw_recipe(tags=["vegetarian"])],
            planning_only=True,
        )

        self.assertEqual(len(valid), 1)

    def test_meat_recipe_is_excluded(self):
        valid, rejected = catalog(
            None,
            [raw_recipe(tags=["meat"])],
            planning_only=True,
        )

        self.assertEqual(len(valid), 0)

    def test_vegetarian_tag_is_case_insensitive(self):
        valid, rejected = catalog(
            None,
            [raw_recipe(tags=["Vegetarian"])],
            planning_only=True,
        )

        self.assertEqual(len(valid), 1)

    def test_string_diet_tag_is_supported(self):
        valid, rejected = catalog(
            None,
            [raw_recipe(tags="vegetarian")],
            planning_only=True,
        )

        self.assertEqual(len(valid), 1)

    def test_requested_diet_is_respected(self):
        recipes = [
            raw_recipe("vegetarian_1", tags=["vegetarian"]),
            raw_recipe("vegan_1", tags=["vegan"]),
        ]

        valid, rejected = catalog(
            None,
            recipes,
            diet="vegan",
            planning_only=True,
        )

        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["recipe_id"], "vegan_1")

    def test_missing_diet_tag_is_excluded(self):
        valid, rejected = catalog(
            None,
            [raw_recipe(tags=[])],
            planning_only=True,
        )

        self.assertEqual(len(valid), 0)


# ============================================================
# 6. SEVEN-DAY PLANNING AND REPEAT RULES
# ============================================================

class WeeklyPlanningTests(unittest.TestCase):

    def test_days_are_in_correct_order(self):
        week = build_week(
            diverse_week_recipes(),
            140,
            2000,
        )

        self.assertEqual(
            [day["day"] for day in week["days"]],
            list(planner.DAYS),
        )

    def test_all_seven_days_meet_targets(self):
        week = build_week(
            diverse_week_recipes(),
            140,
            2000,
        )

        self.assertTrue(week["all_days_valid"])

        for day in week["days"]:
            self.assertTrue(day["meets_protein"])
            self.assertTrue(day["meets_calories"])

    def test_weekly_totals_equal_daily_sums(self):
        week = build_week(
            diverse_week_recipes(),
            140,
            2000,
        )

        for macro in planner.MACROS:
            expected = sum(
                day["totals"][macro]
                for day in week["days"]
            )

            self.assertAlmostEqual(
                week["weekly_totals"][macro],
                expected,
            )

    def test_no_recipe_repeated_within_two_days(self):
        week = build_week(
            diverse_week_recipes(),
            140,
            2000,
        )

        assert_no_recent_repeats(
            self,
            week["days"],
        )

    def test_not_enough_recipes_reports_error(self):
        recipes = [
            recipe("breakfast", "breakfast", 50, 500),
            recipe("lunch", "lunch", 50, 500),
            recipe("dinner", "dinner", 50, 500),
        ]

        week = build_week(
            recipes,
            140,
            2000,
        )

        self.assertLess(len(week["days"]), 7)
        self.assertFalse(week["all_days_valid"])
        self.assertIn("error", week)

    def test_empty_catalog_reports_error(self):
        week = build_week([], 140, 2000)

        self.assertEqual(len(week["days"]), 0)
        self.assertFalse(week["all_days_valid"])
        self.assertIn("error", week)

    def test_forbidden_recipe_is_not_selected(self):
        recipes = [
            recipe("lunch_a", "lunch", 50, 500),
            recipe("lunch_b", "lunch", 50, 500),
        ]

        day, error = choose_day(
            recipes,
            40,
            2000,
            forbidden_ids={"lunch_a"},
        )

        self.assertIsNone(error)

        selected_ids = {
            meal["recipe_id"]
            for meal in day["meals"]
        }

        self.assertNotIn("lunch_a", selected_ids)

    def test_no_available_recipes_returns_error(self):
        recipes = [
            recipe("lunch_a", "lunch", 50, 500),
        ]

        day, error = choose_day(
            recipes,
            40,
            2000,
            forbidden_ids={"lunch_a"},
        )

        self.assertIsNone(day)
        self.assertIsNotNone(error)

    def test_recent_recipe_ids_uses_only_two_days(self):
        days = [
            {
                "meals": [{"recipe_id": "old"}]
            },
            {
                "meals": [{"recipe_id": "recent_a"}]
            },
            {
                "meals": [{"recipe_id": "recent_b"}]
            },
        ]

        recent = recent_recipe_ids(days)

        self.assertNotIn("old", recent)
        self.assertIn("recent_a", recent)
        self.assertIn("recent_b", recent)

    def test_repeated_recipe_id_same_day_is_rejected(self):
        recipes = [
            recipe("same_id", "breakfast", 50, 500),
            recipe("same_id", "lunch", 50, 500),
        ]

        day, error = choose_day(
            recipes,
            100,
            2000,
        )

        self.assertIsNone(day)
        self.assertIsNotNone(error)

    def test_unreachable_weekly_protein_is_reported(self):
        recipes = diverse_week_recipes()

        week = build_week(
            recipes,
            protein_target=300,
            calorie_limit=2000,
        )

        self.assertEqual(len(week["days"]), 7)
        self.assertFalse(week["all_days_valid"])

        self.assertTrue(
            any(
                not day["meets_protein"]
                for day in week["days"]
            )
        )


# ============================================================
# 7. PLANNING-ONLY MODE
# ============================================================

class PlanningOnlyTests(unittest.TestCase):

    def test_planning_only_generates_seven_days(self):
        week = build_planning_only_week(
            planning_recipes()
        )

        self.assertEqual(len(week["days"]), 7)

    def test_planning_only_never_claims_verified_macros(self):
        week = build_planning_only_week(
            planning_recipes()
        )

        self.assertFalse(week["nutrition_verified"])
        self.assertFalse(week["all_days_valid"])
        self.assertIsNone(week["weekly_totals"])

        for day in week["days"]:
            self.assertIsNone(day["totals"])
            self.assertIsNone(day["meets_protein"])
            self.assertIsNone(day["meets_calories"])

    def test_planning_only_respects_repeat_rule(self):
        week = build_planning_only_week(
            planning_recipes()
        )

        self.assertEqual(len(week["days"]), 7)

        assert_no_recent_repeats(
            self,
            week["days"],
        )

    def test_planning_only_does_not_call_matcher(self):
        matcher = Mock()

        valid, rejected = catalog(
            matcher,
            [raw_recipe()],
            planning_only=True,
        )

        self.assertEqual(len(valid), 1)

        matcher.calculate_recipe_macros.assert_not_called()

    def test_planning_only_accepts_unknown_quantity(self):
        data = raw_recipe(
            ingredients=[
                {
                    "name": "tofu",
                    "quantity": None,
                    "unit": None,
                }
            ]
        )

        valid, rejected = catalog(
            None,
            [data],
            planning_only=True,
        )

        self.assertEqual(len(valid), 1)
        self.assertFalse(valid[0]["nutrition_verified"])

    def test_planning_only_empty_catalog(self):
        week = build_planning_only_week([])

        self.assertEqual(len(week["days"]), 0)
        self.assertFalse(week["all_days_valid"])
        self.assertIn("error", week)

    def test_planning_only_insufficient_variety(self):
        recipes = [
            {
                "recipe_id": "only_lunch",
                "name": "Only Lunch",
                "meal_type": "lunch",
                "macros": None,
            }
        ]

        week = build_planning_only_week(recipes)

        self.assertLess(len(week["days"]), 7)
        self.assertFalse(week["all_days_valid"])
        self.assertIn("error", week)


# ============================================================
# 8. RECIPE FILE LOADING
# ============================================================

class RecipeLoadingTests(unittest.TestCase):

    def test_load_valid_recipe_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)

            data = [
                raw_recipe("test_1"),
                raw_recipe("test_2"),
            ]

            (path / "recipes.json").write_text(
                json.dumps(data),
                encoding="utf-8",
            )

            with patch.object(planner, "ROOT", path):
                loaded = planner.load_recipes()

            self.assertEqual(len(loaded), 2)

    def test_non_list_recipe_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)

            (path / "recipes.json").write_text(
                json.dumps({"recipes": []}),
                encoding="utf-8",
            )

            with patch.object(planner, "ROOT", path):
                with self.assertRaises(ValueError):
                    planner.load_recipes()

    def test_missing_recipe_file_raises_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                planner,
                "ROOT",
                Path(directory),
            ):
                with self.assertRaises(FileNotFoundError):
                    planner.load_recipes()


# ============================================================
# 9. DETERMINISM / REPRODUCIBILITY
# ============================================================

class ReproducibilityTests(unittest.TestCase):

    def test_same_input_produces_same_week(self):
        recipes = diverse_week_recipes()

        first = build_week(recipes, 140, 2000)
        second = build_week(recipes, 140, 2000)

        self.assertEqual(first, second)

    def test_same_input_produces_same_day(self):
        recipes = diverse_week_recipes()

        first, error1 = choose_day(
            recipes,
            140,
            2000,
        )

        second, error2 = choose_day(
            recipes,
            140,
            2000,
        )

        self.assertEqual(error1, error2)
        self.assertEqual(first, second)


# ============================================================
# 10. OPTIONAL LLM INTEGRATION
# ============================================================

@unittest.skipUnless(
    hasattr(planner, "optional_llm_tool_selection"),
    "LLM integration has not been implemented yet",
)
class LLMIntegrationTests(unittest.TestCase):
    """
    Reserved for future agent integration.

    No real API calls are made.
    These tests can be expanded when the LLM tool-calling
    interface is finalized.
    """

    def test_llm_function_exists(self):
        self.assertTrue(
            callable(planner.optional_llm_tool_selection)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
