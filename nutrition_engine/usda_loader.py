"""Path-independent, conservative loader for the cleaned USDA nutrient CSV."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from .math_engine import NUTRIENTS

DATA_DIR = Path(__file__).resolve().parents[1] / "cleanedData"
DEFAULT_USDA_PATH = DATA_DIR / "clean_usda_foods.csv"
DEFAULT_PORTION_PATH = DATA_DIR / "food_portion_clean.csv"
DEFAULT_UNIT_PATH = DATA_DIR / "measure_unit_clean.csv"
REQUIRED_COLUMNS = {"fdc_id", "description", *NUTRIENTS}


def _parse_nutrient(raw: Any) -> float | None:
    """Return a finite non-negative nutrient value; preserve unknowns as None."""
    if raw is None or not str(raw).strip():
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


class USDAFoodDatabase:
    """Lookup cleaned USDA food records by normalized string ``fdc_id``."""

    def __init__(self, path: str | Path = DEFAULT_USDA_PATH, portion_path: str | Path = DEFAULT_PORTION_PATH, unit_path: str | Path = DEFAULT_UNIT_PATH):
        """Load nutrient records and optional portion/unit lookup tables.

        Args:
            path: Cleaned USDA nutrient CSV.
            portion_path: Optional CSV of food-specific household portions.
            unit_path: Optional CSV of unit-name aliases.

        Raises:
            FileNotFoundError: If the required nutrient CSV is missing.
            ValueError: If a required column is missing or IDs are duplicated.
        """
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"USDA nutrient CSV not found: {self.path}")

        self.records: dict[str, dict[str, Any]] = {}
        with self.path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = REQUIRED_COLUMNS - columns
            if missing:
                raise ValueError(f"USDA CSV missing required columns: {sorted(missing)}")

            for row in reader:
                raw_id = row.get("fdc_id")
                if raw_id is None or not raw_id.strip():
                    continue
                fdc_id = raw_id.strip()
                if fdc_id in self.records:
                    raise ValueError(f"Duplicate fdc_id in USDA CSV: {fdc_id}")
                self.records[fdc_id] = {
                    "fdc_id": fdc_id,
                    "description": (row.get("description") or "").strip(),
                    "data_type": (row.get("data_type") or "").strip(),
                    "nutrients_per_100g": {
                        nutrient: _parse_nutrient(row.get(nutrient))
                        for nutrient in NUTRIENTS
                    },
                }

        self.portions: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.portion_path = Path(portion_path).expanduser().resolve()
        if self.portion_path.is_file():
            with self.portion_path.open("r", newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                required = {"fdc_id", "unit_name", "modifier", "g_per_unit", "n_obs"}
                missing = required - set(reader.fieldnames or [])
                if missing:
                    raise ValueError(f"USDA portion CSV missing required columns: {sorted(missing)}")
                for row in reader:
                    fdc_id = str(row.get("fdc_id") or "").strip()
                    unit_name = _normalize_unit(row.get("unit_name"))
                    grams = _parse_nutrient(row.get("g_per_unit"))
                    if not fdc_id or not unit_name or grams is None:
                        continue
                    self.portions.setdefault((fdc_id, unit_name), []).append({
                        "grams": grams,
                        "modifier": str(row.get("modifier") or "").strip(),
                        "n_obs": int(row.get("n_obs") or 0),
                    })

        self.unit_aliases: dict[str, str] = {}
        self.unit_path = Path(unit_path).expanduser().resolve()
        if self.unit_path.is_file():
            with self.unit_path.open("r", newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                if {"raw_name", "unit_name"} <= set(reader.fieldnames or []):
                    for row in reader:
                        raw_name = _normalize_unit(row.get("raw_name"))
                        unit_name = _normalize_unit(row.get("unit_name"))
                        if raw_name and unit_name:
                            self.unit_aliases[raw_name] = unit_name

    def get(self, fdc_id: int | str) -> dict[str, Any] | None:
        """Return a food record, accepting either integer or string IDs.

        Args:
            fdc_id: USDA FoodData Central identifier.

        Returns:
            The loaded record, or None if the ID is absent from this dataset.
        """
        if fdc_id is None:
            return None
        return self.records.get(str(fdc_id).strip())

    def nutrients_for(self, fdc_id: int | str) -> dict[str, float | None] | None:
        """Return a copy of the nutrient profile, or None for an unknown ID."""
        record = self.get(fdc_id)
        return None if record is None else dict(record["nutrients_per_100g"])

    def normalize_unit(self, unit: str) -> str:
        """Normalize a unit through the project's cleaned measurement table.

        Args:
            unit: Unit spelling found in recipe or portion data.

        Returns:
            A normalized label, using the alias table when one is available.
        """
        normalized = _normalize_unit(unit)
        if normalized in self.unit_aliases:
            return self.unit_aliases[normalized]
        if normalized.endswith("s") and normalized[:-1] in self.unit_aliases:
            return self.unit_aliases[normalized[:-1]]
        return normalized

    def portion_grams_for(self, fdc_id: int | str, unit: str) -> float | None:
        """Return an unambiguous food-specific portion conversion when present.

        Args:
            fdc_id: USDA ID for the exact food.
            unit: Household unit to look up, such as cup or tablespoon.

        Returns:
            Grams for one unit, or None when no safe single conversion is available.

        The portion table can contain different weights for modifiers such as
        peeled/unpeeled. We only use a blank-modifier row, or a sole candidate;
        ambiguous alternatives are deliberately not averaged together.
        """
        key = (str(fdc_id).strip(), self.normalize_unit(unit))
        candidates = self.portions.get(key, [])
        if not candidates:
            return None
        blank_modifier = [item for item in candidates if not item["modifier"]]
        if len(blank_modifier) == 1:
            return blank_modifier[0]["grams"]
        if len(candidates) == 1:
            return candidates[0]["grams"]
        return None

    @property
    def portion_food_id_overlap(self) -> int:
        """Count distinct portion-table food IDs also present in the nutrient file."""
        return len({fdc_id for fdc_id, _ in self.portions if fdc_id in self.records})


def _normalize_unit(value: Any) -> str:
    """Make unit labels comparable without changing their meaning."""
    text = str(value or "").lower().strip()
    text = text.replace("_", " ").replace("-", " ")
    return " ".join(text.split())
