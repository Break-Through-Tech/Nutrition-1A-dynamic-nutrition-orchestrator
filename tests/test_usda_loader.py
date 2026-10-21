"""Tests for loading and looking up the real cleaned USDA data files."""

import csv
import tempfile
import unittest
from pathlib import Path

from nutrition_engine.math_engine import NUTRIENTS
from nutrition_engine.usda_loader import DEFAULT_USDA_PATH, USDAFoodDatabase


class USDALoaderTests(unittest.TestCase):
    """Checks the CSV loader separately from recipe matching and nutrient arithmetic."""
    def test_loads_real_project_dataset_and_normalizes_ids(self):
        """A known USDA row should load with the expected ID, description, and protein value."""
        db = USDAFoodDatabase(DEFAULT_USDA_PATH)
        self.assertEqual(len(db.records), 13615)
        record = db.get(2708489)
        self.assertIsNotNone(record)
        self.assertEqual(record["fdc_id"], "2708489")
        self.assertEqual(record["description"], "Oats, Raw")
        self.assertAlmostEqual(record["nutrients_per_100g"]["protein_g"], 13.15, places=2)

    def test_missing_nutrient_is_unknown_but_true_zero_stays_zero(self):
        """A blank nutrient cell must differ from a real numeric zero."""
        columns = ["fdc_id", "description", *NUTRIENTS]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "foods.csv"
            row = {name: "" for name in columns}
            row.update({"fdc_id": "123", "description": "Test Food", "calories_kcal": "0", "protein_g": ""})
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerow(row)
            db = USDAFoodDatabase(path)
            profile = db.nutrients_for("123")
            self.assertEqual(profile["calories_kcal"], 0.0)
            self.assertIsNone(profile["protein_g"])

    def test_measure_unit_aliases_and_portion_table_are_loaded(self):
        """The optional unit and portion tables should be read and made available for conversions."""
        db = USDAFoodDatabase(DEFAULT_USDA_PATH)
        self.assertEqual(db.normalize_unit("teaspoons"), "teaspoon")
        self.assertGreater(len(db.unit_aliases), 0)
        self.assertGreater(db.portion_food_id_overlap, 0)

    def test_unknown_id_returns_none(self):
        """An ID absent from the dataset should return no record instead of a random match."""
        db = USDAFoodDatabase(DEFAULT_USDA_PATH)
        self.assertIsNone(db.get("not-a-real-id"))


if __name__ == "__main__":
    unittest.main()
