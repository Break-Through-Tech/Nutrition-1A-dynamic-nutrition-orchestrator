"""End-to-end checks using the repository recipes and actual cleaned USDA dataset."""

import unittest

from nutrition_engine.prototype import calculate_project
from nutrition_engine.usda_loader import DEFAULT_USDA_PATH


class PrototypeIntegrationTests(unittest.TestCase):
    """Checks that the loader, matcher, conversions, and math engine run together on project data."""
    def test_runs_all_real_project_recipes_against_usda_data(self):
        """The full pipeline should process every current recipe and expose unresolved/estimated inputs."""
        report = calculate_project(usda_path=DEFAULT_USDA_PATH)
        self.assertEqual(report["metadata"]["usda_record_count"], 13615)
        self.assertEqual(report["metadata"]["recipe_count"], 26)
        self.assertEqual(report["metadata"]["ingredient_count"], 175)
        self.assertEqual(len(report["recipes"]), 26)
        self.assertGreater(report["metadata"]["ingredient_status_counts"].get("resolved", 0), 0)
        self.assertGreater(report["metadata"]["ingredient_status_counts"].get("estimated", 0), 0)
        self.assertGreater(report["metadata"]["ingredient_status_counts"].get("unresolved", 0), 0)
        # This dataset contains unresolved quantities and proxies, so do not
        # let the prototype label every recipe as verified.
        self.assertTrue(all(recipe["status"] != "complete" for recipe in report["recipes"]))

    def test_unresolved_ingredient_is_exposed_in_recipe_output(self):
        """A known recipe with unresolved ingredients should report the reason and keep partial protein visible."""
        report = calculate_project(usda_path=DEFAULT_USDA_PATH)
        recipe = next(item for item in report["recipes"] if item["recipe_id"] == "protein-oats-upma")
        unresolved = [item for item in recipe["ingredients"] if item["status"] == "unresolved"]
        self.assertTrue(unresolved)
        self.assertTrue(all(item.get("reason") for item in unresolved))
        self.assertIsNone(recipe["batch_totals"]["protein_g"])
        self.assertIsNotNone(recipe["known_partial_totals"]["protein_g"])


if __name__ == "__main__":
    unittest.main()
