"""Public interface for deterministic nutrition calculations."""

from .usda_loader import USDAFoodDatabase

from .math_engine import (
    CORE_NUTRIENTS,
    NUTRIENTS,
    aggregate_results,
    calculate_ingredient,
    calculate_meal,
    calculate_recipe,
)

__all__ = [
    "CORE_NUTRIENTS",
    "USDAFoodDatabase",
    "NUTRIENTS",
    "aggregate_results",
    "calculate_ingredient",
    "calculate_meal",
    "calculate_recipe",
]
