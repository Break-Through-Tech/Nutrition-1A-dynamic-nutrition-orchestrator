"""End-to-end deterministic nutrition prototype for the repository's recipes.json.

This connects recipe data -> ingredient matching -> gram conversion -> USDA lookup
-> deterministic math engine. Uncertain matches and unsupported quantities are
surfaced rather than silently treated as zero.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .math_engine import NUTRIENTS, calculate_recipe
from .usda_loader import DEFAULT_USDA_PATH, USDAFoodDatabase

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECIPES_PATH = REPO_ROOT / "recipes.json"

# Carefully reviewed aliases for common project ingredients where the current
# generic matcher cannot safely infer the intended USDA record. Any proxy is
# explicitly marked estimated and therefore cannot produce a fully verified recipe.
MATCH_OVERRIDES: dict[str, tuple[str, str, str]] = {
    "oats": ("2708489", "resolved", "USDA oats, raw record"),
    "whole wheat bread": ("2758994", "resolved", "USDA 100% whole-wheat commercial bread record"),
    "whole wheat flour": ("790085", "resolved", "USDA whole-wheat flour record"),
    "turmeric": ("172231", "resolved", "USDA ground turmeric record"),
    "green peas": ("170419", "resolved", "USDA green peas, raw record"),
    "tomato": ("2709719", "resolved", "USDA raw tomato record"),
    "onion": ("170000", "resolved", "USDA raw onion record"),
    "red onion": ("170000", "estimated", "Raw onion used as a proxy because the selected record does not specify red onion"),
    "cucumber": ("168409", "resolved", "USDA cucumber with peel, raw record"),
    "capsicum": ("170427", "estimated", "Green sweet pepper used as a proxy for capsicum"),
    "bell peppers": ("170427", "estimated", "Green sweet pepper used as a proxy because pepper color is unspecified"),
    "carrot": ("170393", "resolved", "USDA raw carrot record"),
    "broccoli florets": ("170379", "resolved", "USDA raw broccoli record"),
    "cornstarch": ("169698", "resolved", "USDA cornstarch record"),
    "soy sauce": ("174277", "resolved", "USDA soy-and-wheat shoyu record"),
    "low-sodium soy sauce": ("172473", "resolved", "USDA low-sodium soy sauce record"),
    "garlic": ("169230", "resolved", "USDA raw garlic record"),
    "almonds": ("2707486", "estimated", "Unroasted almonds record used as a proxy; recipe does not specify preparation"),
    "edamame pods": ("2707436", "estimated", "Cooked edamame record used as a proxy; pod weight may include inedible shells"),
    "dry-roasted soya nuts": ("2707433", "estimated", "USDA soy nuts record used as a proxy for dry-roasted soya nuts"),
    "rajma": ("173744", "estimated", "Raw red kidney beans used as a proxy for rajma"),
    "mint leaves": ("173475", "estimated", "Fresh spearmint used as a proxy for unspecified mint leaves"),
    "lemon juice": ("167747", "resolved", "USDA raw lemon juice record"),
    "ghee": ("173412", "estimated", "Anhydrous butter oil used as a macro-level proxy for ghee"),
    "red chili powder": ("171319", "estimated", "Generic chili powder record used as a proxy for red chili powder"),
    "kashmiri red chili powder": ("170932", "estimated", "Red/cayenne pepper record used as a proxy for Kashmiri chili powder"),
    "degi mirch": ("170932", "estimated", "Red/cayenne pepper record used as a proxy for degi mirch"),
    "red chili flakes": ("170932", "estimated", "Red/cayenne pepper record used as a proxy for red chili flakes"),
    "cumin powder": ("170923", "estimated", "Cumin seed record used as a proxy for ground cumin"),
    "roasted cumin powder": ("170923", "estimated", "Cumin seed record used as a proxy for roasted ground cumin"),
    "cumin seeds": ("170923", "resolved", "USDA cumin seed record"),
    "sweet corn kernels": ("2710826", "resolved", "USDA fresh sweet corn kernels record"),
    "low-fat milk": ("2705387", "resolved", "USDA 1% low-fat milk record"),
    "unsweetened soy milk": ("2705405", "resolved", "USDA unsweetened soy milk record"),
    "soy flour": ("174301", "estimated", "Soy protein concentrate record used as a proxy; exact soy flour formulation not confirmed"),
    "low-fat paneer": ("2705740", "estimated", "USDA has paneer but this record does not establish a low-fat formulation"),
    "paneer": ("2705740", "resolved", "Exact USDA paneer record"),
    "moong dal": ("174256", "estimated", "Raw mature mung beans used as a proxy for moong dal; verify split/dehulled form"),
    "split moong dal": ("174256", "estimated", "Raw mature mung beans used as a proxy for split moong dal"),
    "yellow moong or toor dal": ("", "unresolved", "Ingredient name gives two alternatives, so a single food record cannot be selected safely"),
    "dry soya chunks": ("2707451", "estimated", "Textured vegetable protein, dry, used as a proxy for soya chunks"),
    "soya chunks": ("2707451", "estimated", "Textured vegetable protein, dry, used as a proxy for soya chunks"),
    "dry soya granules": ("2707451", "estimated", "Textured vegetable protein, dry, used as a proxy for soya granules"),
    "soya granules": ("2707451", "estimated", "Textured vegetable protein, dry, used as a proxy for soya granules"),
    "unflavored whey protein": ("173177", "estimated", "Whey protein isolate record used as a proxy; brand and formulation are unspecified"),
    "whey protein isolate": ("173177", "estimated", "USDA whey protein isolate record; scoop mass still needs a product-specific quantity"),
    "whey protein": ("173177", "estimated", "Whey protein isolate record used as a proxy; formulation is unspecified"),
    "oil": ("2710186", "estimated", "Generic cooking oil approximated with olive oil because the recipe does not specify the oil type"),
    "mustard oil": ("2710186", "estimated", "Olive oil used as a macro-level proxy; mustard oil is not represented by this selected record"),
    "olive oil": ("2710186", "resolved", "Exact USDA olive oil record"),
    "mustard seeds": ("170929", "estimated", "Ground mustard seed record used as a proxy for whole mustard seeds"),
    "green chili": ("170497", "resolved", "USDA green hot chili pepper, raw"),
    "ginger": ("169231", "resolved", "USDA ginger root, raw"),
    "coriander": ("169997", "resolved", "USDA coriander/cilantro leaves, raw"),
    "coriander leaves": ("169997", "resolved", "USDA coriander/cilantro leaves, raw"),
    "cilantro": ("169997", "resolved", "USDA coriander/cilantro leaves, raw"),
    "low-fat curd": ("2705423", "estimated", "Low-fat Greek yogurt record used as a proxy for curd"),
    "greek yogurt": ("2705423", "estimated", "Low-fat plain Greek yogurt used as a proxy because fat content is unspecified"),
    "fat-free greek yogurt": ("2705423", "estimated", "Low-fat Greek yogurt used as a proxy; this is not confirmed fat-free"),
    "low-fat greek yogurt": ("2705439", "resolved", "USDA low-fat Greek yogurt record"),
    "extra-firm tofu": ("172475", "estimated", "Firm tofu record used as a proxy for extra-firm tofu"),
    "firm tofu": ("172475", "resolved", "USDA firm tofu record"),
    "tofu": ("172475", "estimated", "Firm tofu record used as a proxy because firmness is unspecified"),
    "brown rice": ("2512380", "resolved", "USDA raw brown rice record"),
    "basmati rice": ("2512381", "estimated", "Raw long-grain white rice used as a proxy for basmati rice"),
    "low-fat milk": ("2705387", "resolved", "USDA 1% low-fat milk record"),
    "tomato puree": ("170546", "estimated", "Canned tomato puree with salt used as a proxy; recipe brand and added-salt status are unknown"),
    "kabuli chana": ("173756", "estimated", "Raw chickpeas used as a proxy; recipe quantity may refer to soaked/cooked weight"),
    "kala chana": ("173756", "estimated", "Common chickpea record used as a proxy for black chickpeas; variety differs"),
    "chana dal": ("173756", "estimated", "Raw chickpeas used as a proxy for split chana dal"),
    "sprouted moong": ("169957", "resolved", "USDA raw sprouted mung beans record"),
    "quinoa": ("", "unresolved", "Recipe does not specify dry versus cooked quinoa, and the selected USDA data lacks a matching raw quinoa record"),
    "quinoa-rice mix": ("", "unresolved", "Mixed quinoa and rice has no component ratio, so its nutrients cannot be calculated as one food"),
    "curry leaves": ("", "unresolved", "No suitable curry-leaf record was identified; do not substitute unrelated leafy greens"),
    "hing": ("", "unresolved", "No suitable asafoetida/hing record was identified in the cleaned USDA dataset"),
    "kadhai spice mix": ("", "unresolved", "Composite spice mix has no known ingredient proportions"),
    "biryani spice mix": ("", "unresolved", "Composite spice mix has no known ingredient proportions"),
    "chaat masala": ("", "unresolved", "Composite spice blend has no suitable record in the cleaned USDA dataset"),
    "ginger-garlic paste": ("", "unresolved", "Composite ingredient has no ginger/garlic ratio"),
    "onion-tomato base gravy": ("", "unresolved", "Composite gravy has no known onion/tomato proportions"),
    "mixed sprouts": ("", "unresolved", "Sprout mixture composition is unspecified"),
    "mint-cilantro-yogurt chutney": ("", "unresolved", "Composite chutney has no ingredient proportions"),
    "broccoli and bell peppers": ("", "unresolved", "Mixed vegetables have no component proportions"),
    "mixed bell peppers": ("", "unresolved", "Pepper colors/proportions are unspecified"),
    "mozzarella and cheddar blend": ("", "unresolved", "Cheese blend proportions are unspecified"),
    "soft paratha": ("", "unresolved", "Prepared paratha brand/size is unspecified and no suitable record was confirmed"),
    "flour tortilla": ("", "unresolved", "Tortilla type, size, and mass are unspecified"),
    "whole black urad": ("", "unresolved", "No sufficiently reliable matching record for whole black urad was identified"),
    "mixed sprouts": ("", "unresolved", "Sprout mixture composition is unspecified"),
}

# A few explicit preparation-state guards: selecting a generic raw/cooked record
# without knowing the recipe state would create false precision.
# without knowing the recipe's state would be misleading.
FORCE_UNRESOLVED = {
    "quinoa", "quinoa-rice mix", "curry leaves", "hing", "kadhai spice mix",
    "biryani spice mix", "chaat masala", "ginger-garlic paste",
    "onion-tomato base gravy", "mixed sprouts", "mint-cilantro-yogurt chutney",
    "broccoli and bell peppers", "mixed bell peppers", "mozzarella and cheddar blend",
    "soft paratha", "flour tortilla", "whole black urad", "yellow moong or toor dal",
}

# Fallback household-measure approximations. Every use is marked estimated.
# Keep these conservative and review them against the team's preferred source.
FALLBACK_GRAMS_PER_TSP = {
    "oil": 4.5, "mustard oil": 4.5, "olive oil": 4.5, "ghee": 4.7,
    "soy sauce": 5.0, "low-sodium soy sauce": 5.0, "vinegar": 5.0,
    "turmeric": 2.2, "mustard seeds": 2.0, "cumin powder": 2.0, "cumin seeds": 2.0,
    "kashmiri red chili powder": 2.0, "red chili powder": 2.0,
    "degi mirch": 2.0, "kasuri methi": 0.5, "ajwain": 2.0,
    "garam masala": 2.0, "red chili flakes": 1.8, "red chili powder": 2.0, "kashmiri red chili powder": 2.0, "roasted cumin powder": 2.0,
    "cornstarch": 3.0, "garlic": 8.0 / 3.0, "ginger": 6.0 / 3.0,
    "kala namak": 5.0, "black salt": 5.0, "sea salt": 6.0, "salt": 6.0,
}
FALLBACK_GRAMS_PER_CUP = {"broccoli florets": 91.0, "moong dal": 200.0, "split moong dal": 200.0}
FALLBACK_GRAMS_PER_ITEM = {
    "green chili": 15.0, "capsicum": 120.0, "bell peppers": 120.0,
    "red onion": 150.0, "onion": 150.0, "tomato": 123.0,
    "almonds": 1.2,
}


def _normalize_name(value: Any) -> str:
    """Normalize ingredient wording for alias and override lookups."""
    text = str(value or "").lower().strip()
    text = text.replace("-", " ").replace("_", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


MATCH_OVERRIDES_NORMALIZED = {_normalize_name(key): value for key, value in MATCH_OVERRIDES.items()}
FORCE_UNRESOLVED_NORMALIZED = {_normalize_name(value) for value in FORCE_UNRESOLVED}
FALLBACK_GRAMS_PER_TSP_NORMALIZED = {_normalize_name(key): value for key, value in FALLBACK_GRAMS_PER_TSP.items()}
FALLBACK_GRAMS_PER_CUP_NORMALIZED = {_normalize_name(key): value for key, value in FALLBACK_GRAMS_PER_CUP.items()}
FALLBACK_GRAMS_PER_ITEM_NORMALIZED = {_normalize_name(key): value for key, value in FALLBACK_GRAMS_PER_ITEM.items()}


def _get_matcher():
    """Load the project matcher only when the end-to-end prototype needs it."""
    # Import at call time so the deterministic math/loader modules remain usable
    # independently; this module is run from the repository root.
    from scripts.ingredient_matching import find_best_food, load_foods
    return load_foods(), find_best_food


def _find_food(name: str, foods: Any, find_best_food: Any, db: USDAFoodDatabase) -> tuple[dict[str, Any] | None, str, str, float | None]:
    """Resolve a recipe ingredient and return its confidence/status/reason.

    Explicit aliases take precedence; weak or missing matches stay unresolved.
    The returned status is ``resolved``, ``estimated``, or ``unresolved``.
    """
    normalized = _normalize_name(name)
    override = MATCH_OVERRIDES_NORMALIZED.get(normalized)
    if override is not None:
        fdc_id, status, reason = override
        if status == "unresolved" or not fdc_id:
            return None, "unresolved", reason, None
        record = db.get(fdc_id)
        if record is None:
            return None, "unresolved", f"Configured USDA override {fdc_id} was not found in the dataset", None
        return record, status, reason, None

    if normalized in FORCE_UNRESOLVED_NORMALIZED:
        return None, "unresolved", "Ingredient needs manual resolution before a safe USDA match can be selected", None

    match = find_best_food(name, foods)
    if match is None:
        return None, "unresolved", "No sufficiently strong USDA match was found", None
    score = float(match["score"])
    record = db.get(match["fdc_id"])
    if record is None:
        return None, "unresolved", "Matcher returned an ID absent from the authoritative USDA lookup", score
    if score < 0.60:
        return None, "unresolved", "USDA match confidence is too low to calculate reliably", score
    if score < 0.80:
        return record, "estimated", "Ingredient matched by text with medium confidence; review before treating as verified", score
    return record, "resolved", "USDA match selected by ingredient matcher", score


def _quantity_and_unit(ingredient: dict[str, Any]) -> tuple[float | None, str | None, str | None]:
    """Read a numeric recipe quantity and unit without guessing silently.

    Returns the quantity, unit, and an explanation when the input is ambiguous.
    """
    quantity = ingredient.get("quantity")
    unit = ingredient.get("unit")
    if quantity is not None and unit:
        if isinstance(quantity, bool):
            return None, None, "Recipe quantity cannot be Boolean"
        try:
            value = float(quantity)
        except (TypeError, ValueError):
            return None, None, "Recipe quantity is not numeric"
        if not math.isfinite(value) or value < 0:
            return None, None, "Recipe quantity must be finite and non-negative"
        return value, str(unit), None

    text = str(ingredient.get("quantity_text") or "").strip()
    # The only implicit count parse allowed for now is an explicitly written
    # leading count such as "1, to taste" for a chili; it remains estimated.
    match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*,?\s*to taste\s*$", text, flags=re.I)
    if match and _normalize_name(ingredient.get("name")) in {"green chili", "chili", "chilli"}:
        return float(match.group(1)), "piece", "Quantity inferred from recipe text 'to taste'; review this estimate"
    return None, None, "Recipe quantity/unit is missing or ambiguous"


def _convert_to_grams(quantity: float, unit: str, ingredient_name: str, fdc_id: str | None = None, db: USDAFoodDatabase | None = None) -> tuple[float | None, str | None, bool, str | None]:
    """Convert a recipe quantity to grams, using the safest available source.

    Args:
        quantity: Numeric quantity from the recipe.
        unit: Recipe unit, such as grams, cup, teaspoon, or piece.
        ingredient_name: Ingredient wording used to find ingredient-specific rules.
        fdc_id: Optional matched USDA ID for a food-specific portion lookup.
        db: Loaded USDA database, including optional portion/unit tables.

    Returns:
        A tuple of grams (or None), source label, whether it is estimated, and
        an explanation if conversion could not be done or used an approximation.
    """
    normalized_unit = _normalize_name(unit)
    normalized_name = _normalize_name(ingredient_name)
    if not math.isfinite(quantity) or quantity < 0:
        return None, None, False, "Ingredient quantity must be finite and non-negative"

    # Explicit mass units are deterministic.
    mass_factors = {"g": 1.0, "gram": 1.0, "grams": 1.0, "kg": 1000.0, "kilogram": 1000.0, "mg": 0.001, "milligram": 0.001}
    if normalized_unit in mass_factors:
        return quantity * mass_factors[normalized_unit], "recipe mass unit", False, None

    # Prefer an unambiguous food-specific portion conversion when the FDC ID
    # exists in the portion table. The table's IDs do not cover most current
    # nutrition records, so this is a best-effort source rather than a universal one.
    if db is not None and fdc_id is not None:
        portion_units = {
            "tsp": "teaspoon", "teaspoon": "teaspoon", "teaspoons": "teaspoon",
            "tbsp": "tablespoon", "tablespoon": "tablespoon", "tablespoons": "tablespoon",
            "cups": "cup", "cup": "cup", "slices": "slice", "slice": "slice",
            "pieces": "piece", "piece": "piece", "each": "each", "scoop": "scoop",
        }
        portion_unit = portion_units.get(normalized_unit, db.normalize_unit(unit))
        portion_grams = db.portion_grams_for(fdc_id, portion_unit)
        if portion_grams is not None:
            return quantity * portion_grams, "USDA food-specific portion table", True, "Gram amount based on an empirical USDA portion value"

    # Reuse the team's existing converter and its ingredient-specific tables.
    from scripts.ingredient_matching import convert_to_grams
    converted = convert_to_grams(quantity, unit, ingredient_name)
    if converted is not None:
        return float(converted), "existing ingredient-specific unit conversion table", True, "Household measure converted using a predefined approximation"

    if normalized_unit in {"tsp", "teaspoon", "teaspoons"} and normalized_name in FALLBACK_GRAMS_PER_TSP_NORMALIZED:
        return quantity * FALLBACK_GRAMS_PER_TSP_NORMALIZED[normalized_name], "prototype household-measure assumption", True, "Gram amount estimated from a teaspoon approximation"
    if normalized_unit in {"tbsp", "tablespoon", "tablespoons"} and normalized_name in FALLBACK_GRAMS_PER_TSP_NORMALIZED:
        return quantity * FALLBACK_GRAMS_PER_TSP_NORMALIZED[normalized_name] * 3.0, "prototype household-measure assumption", True, "Gram amount estimated as three teaspoons per tablespoon"
    if normalized_unit in {"piece", "pieces", "item", "items", "each"} and normalized_name in FALLBACK_GRAMS_PER_ITEM_NORMALIZED:
        return quantity * FALLBACK_GRAMS_PER_ITEM_NORMALIZED[normalized_name], "prototype item-weight assumption", True, "Weight per item is an approximation"
    if normalized_unit in {"slice", "slices"} and any(word in normalized_name for word in ("bread", "toast")):
        return quantity * 30.0, "prototype slice-weight assumption", True, "Bread slice assumed to weigh 30 g"
    if normalized_unit in {"ml", "milliliter", "milliliters"} and ("milk" in normalized_name):
        density = 1.03 if "soy" not in normalized_name else 1.0
        return quantity * density, "prototype liquid-density assumption", True, "Milliliters converted using an approximate milk density"
    if normalized_unit in {"cup", "cups"} and normalized_name in FALLBACK_GRAMS_PER_CUP_NORMALIZED:
        return quantity * FALLBACK_GRAMS_PER_CUP_NORMALIZED[normalized_name], "prototype household-measure assumption", True, "Gram amount estimated from a household-measure approximation"
    if normalized_unit in {"cup", "cups"} and "greek yogurt" in normalized_name:
        return quantity * 245.0, "prototype household-measure assumption", True, "Greek yogurt assumed to weigh 245 g per cup"
    if normalized_unit in {"cup", "cups"} and "mozzarella" in normalized_name:
        return quantity * 113.0, "prototype household-measure assumption", True, "Shredded cheese assumed to weigh 113 g per cup"
    if normalized_unit in {"pinch"}:
        return quantity * 0.3, "prototype pinch-weight assumption", True, "A pinch is assumed to weigh 0.3 g"
    return None, None, False, f"No safe gram conversion for unit {unit!r} and ingredient {ingredient_name!r}"


def calculate_project(recipes_path: str | Path = DEFAULT_RECIPES_PATH, usda_path: str | Path = DEFAULT_USDA_PATH) -> dict[str, Any]:
    """Run the recipe-to-USDA-to-calculator pipeline for the project data.

    Args:
        recipes_path: Path to the recipe JSON file.
        usda_path: Path to the cleaned USDA nutrient CSV.

    Returns:
        A report with dataset metadata and per-recipe ingredient details, totals,
        statuses, assumptions, and unresolved reasons.

    Raises:
        FileNotFoundError: If a required input file is missing.
        ValueError: If the recipe JSON or USDA CSV has an invalid structure.
    """
    recipes_path = Path(recipes_path).expanduser().resolve()
    with recipes_path.open("r", encoding="utf-8") as handle:
        recipes = json.load(handle)
    if not isinstance(recipes, list):
        raise ValueError("recipes.json must contain a list of recipe objects")

    db = USDAFoodDatabase(usda_path)
    foods, find_best_food = _get_matcher()
    results = []
    overall_statuses: Counter[str] = Counter()
    overall_ingredients = 0

    for recipe in recipes:
        normalized_ingredients = []
        for ingredient in recipe.get("ingredients", []):
            overall_ingredients += 1
            name = str(ingredient.get("name") or "").strip()
            quantity, unit, quantity_issue = _quantity_and_unit(ingredient)
            record, match_status, match_reason, match_score = _find_food(name, foods, find_best_food, db)
            amount_g = None
            amount_source = None
            conversion_estimated = False
            conversion_issue = None
            if quantity is not None and unit:
                amount_g, amount_source, conversion_estimated, conversion_issue = _convert_to_grams(quantity, unit, name, record["fdc_id"] if record else None, db)

            reason_parts = [part for part in (quantity_issue, conversion_issue, match_reason if match_status != "resolved" else None) if part]
            reason = "; ".join(dict.fromkeys(reason_parts)) or None

            if record is None or amount_g is None:
                status = "unresolved"
            elif match_status == "unresolved":
                status = "unresolved"
            elif match_status == "estimated" or conversion_estimated or quantity_issue:
                status = "estimated"
            else:
                status = "resolved"

            normalized = {
                "name": name,
                "status": status,
                "resolution_status": status,
                "quantity": quantity,
                "unit": unit,
                "quantity_text": ingredient.get("quantity_text"),
                "amount_g": amount_g,
                "fdc_id": record["fdc_id"] if record else None,
                "nutrients_per_100g": record["nutrients_per_100g"] if record else None,
                "description": record["description"] if record else None,
                "match_score": match_score,
                "amount_source": amount_source,
                "source": "cleanedData/clean_usda_foods.csv" if record else None,
                "notes": ingredient.get("notes"),
                "reason": reason,
            }
            normalized_ingredients.append(normalized)
            overall_statuses[status] += 1

        servings = recipe.get("servings", 1)
        result = calculate_recipe(normalized_ingredients, servings=servings)
        results.append({
            "recipe_id": recipe.get("recipe_id"),
            "name": recipe.get("name"),
            "meal_type": recipe.get("meal_type"),
            "servings": servings,
            **result,
        })

    return {
        "metadata": {
            "recipes_path": str(recipes_path),
            "usda_path": str(Path(usda_path).expanduser().resolve()),
            "usda_record_count": len(db.records),
            "usda_portion_records": sum(len(rows) for rows in db.portions.values()),
            "usda_portion_food_id_overlap": db.portion_food_id_overlap,
            "measure_unit_alias_count": len(db.unit_aliases),
            "recipe_count": len(recipes),
            "ingredient_count": overall_ingredients,
            "ingredient_status_counts": dict(overall_statuses),
            "nutrients": list(NUTRIENTS),
            "important_note": "Prototype results are not all verified: ingredient matches and household-measure conversions marked estimated need review; unresolved ingredients block verified totals.",
        },
        "recipes": results,
    }


def print_summary(report: dict[str, Any]) -> None:
    """Print recipe statuses and known partial protein contributions.

    Args:
        report: Report returned by :func:`calculate_project`.

    Returns:
        None; output is written to the terminal. Partial protein is labeled as
        partial so it is not mistaken for a verified recipe total.
    """
    meta = report["metadata"]
    print(f"USDA records loaded: {meta['usda_record_count']:,}")
    print(f"Recipes processed: {meta['recipe_count']}")
    print(f"Ingredient entries processed: {meta['ingredient_count']}")
    print("Ingredient statuses:", meta["ingredient_status_counts"])
    print("\nRecipe summary (protein shown as known partial contribution, not verified total when incomplete):")
    for recipe in report["recipes"]:
        counts = Counter(item.get("resolution_status", item["status"]) for item in recipe["ingredients"])
        partial = recipe.get("known_partial_totals", {}).get("protein_g")
        protein_text = "unknown" if partial is None else f"{partial:.1f} g partial"
        print(f"- {recipe['name']}: {recipe['status']} | {counts} | protein {protein_text}")


def write_review_csv(report: dict[str, Any], path: str | Path) -> Path:
    """Write estimated/unresolved ingredients to a human-review CSV.

    Args:
        report: Report returned by :func:`calculate_project`.
        path: Destination file; parent directories are created if needed.

    Returns:
        The resolved path of the CSV written to disk.
    """
    output_path = Path(path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "recipe_id", "recipe_name", "ingredient", "resolution_status",
        "quantity", "unit", "quantity_text", "amount_g", "amount_source",
        "fdc_id", "description", "match_score", "reason", "notes",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for recipe in report["recipes"]:
            for item in recipe["ingredients"]:
                status = item.get("resolution_status", item.get("status"))
                if status not in {"estimated", "unresolved"}:
                    continue
                writer.writerow({
                    "recipe_id": recipe.get("recipe_id"),
                    "recipe_name": recipe.get("name"),
                    "ingredient": item.get("name"),
                    "resolution_status": status,
                    "quantity": item.get("quantity"),
                    "unit": item.get("unit"),
                    "quantity_text": item.get("quantity_text"),
                    "amount_g": item.get("amount_g"),
                    "amount_source": item.get("amount_source"),
                    "fdc_id": item.get("fdc_id"),
                    "description": item.get("description"),
                    "match_score": item.get("match_score"),
                    "reason": item.get("reason"),
                    "notes": item.get("notes"),
                })
    return output_path


def main() -> None:
    """Parse command-line options and run the recipe/USDA prototype.

    The optional output paths let a developer save the full JSON report and the
    CSV review queue without changing the source data.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipes", default=str(DEFAULT_RECIPES_PATH), help="Path to recipes.json")
    parser.add_argument("--usda", default=str(DEFAULT_USDA_PATH), help="Path to clean_usda_foods.csv")
    parser.add_argument("--output", help="Optional path to write the detailed JSON report")
    parser.add_argument("--review-csv", help="Optional path to write estimated/unresolved ingredients for manual review")
    args = parser.parse_args()

    report = calculate_project(args.recipes, args.usda)
    print_summary(report)
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        print(f"\nDetailed report written to: {output_path}")
    if args.review_csv:
        review_path = write_review_csv(report, args.review_csv)
        print(f"Ingredient review CSV written to: {review_path}")


if __name__ == "__main__":
    main()
