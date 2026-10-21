"""Regression tests for ingredient-matcher cases where a loose text match could be misleading."""

import unittest

from scripts.ingredient_matching import find_best_food, load_foods


class IngredientMatcherSafetyTests(unittest.TestCase):
    """Checks a few known risky matching cases against the current cleaned food list."""
    @classmethod
    def setUpClass(cls):
        """Load the food list once because all matcher tests use the same dataset."""
        cls.foods = load_foods()

    def test_ambiguous_generic_oil_and_milk_do_not_pick_random_variants(self):
        """Generic oil and milk should remain ambiguous when the type is not specified."""
        self.assertIsNone(find_best_food("oil", self.foods))
        self.assertIsNone(find_best_food("milk", self.foods))

    def test_brown_rice_does_not_match_a_composite_food(self):
        """The matcher should select a plain brown-rice record, not a prepared mixed dish."""
        match = find_best_food("brown rice", self.foods)
        self.assertIsNotNone(match)
        self.assertEqual(match["fdc_id"], "2512380")
        self.assertIn("Rice, Brown", match["description"])

    def test_salt_matches_salt_not_a_food_that_mentions_salt(self):
        """A short ingredient name should match the ingredient itself rather than any description containing the word."""
        match = find_best_food("salt", self.foods)
        self.assertIsNotNone(match)
        self.assertEqual(match["fdc_id"], "173468")
        self.assertEqual(match["description"], "Salt, Table")


if __name__ == "__main__":
    unittest.main()
