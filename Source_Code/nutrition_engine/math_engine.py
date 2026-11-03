"""Deterministic nutrition arithmetic for resolved USDA food records.

This module does not match ingredients or convert recipe units. The caller
must provide a food record ID, a quantity in grams, and nutrient values per
100 g for the same preparation state. Missing values are never silently
interpreted as zero.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

NUTRIENTS = (
    "calories_kcal", "protein_g", "fat_g", "carbs_g", "fiber_g",
    "sugars_g", "sodium_mg", "potassium_mg", "calcium_mg", "iron_mg",
)
CORE_NUTRIENTS = ("calories_kcal", "protein_g", "fat_g", "carbs_g")
PROVENANCE_FIELDS = (
    "description", "amount_source", "match_score", "estimated",
    "source", "notes", "reason",
)


def _valid_nonnegative_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite non-negative number") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return number


def _nutrient_values(per_100g: Mapping[str, Any], grams: float) -> tuple[dict[str, float | None], list[str]]:
    values: dict[str, float | None] = {}
    missing: list[str] = []
    for nutrient in NUTRIENTS:
        raw = per_100g.get(nutrient)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            values[nutrient] = None
            missing.append(nutrient)
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            values[nutrient] = None
            missing.append(nutrient)
            continue
        if not math.isfinite(value) or value < 0:
            values[nutrient] = None
            missing.append(nutrient)
            continue
        values[nutrient] = value * grams / 100.0
    return values, missing


def calculate_ingredient(
    fdc_id: int | str,
    amount_g: float,
    nutrients_per_100g: Mapping[str, Any],
) -> dict[str, Any]:
    """Calculate nutrient contributions for a resolved food and gram quantity."""
    grams = _valid_nonnegative_number(amount_g, "amount_g")
    values, missing = _nutrient_values(nutrients_per_100g, grams)
    return {
        "fdc_id": str(fdc_id).strip(),
        "amount_g": grams,
        "nutrients": values,
        "status": "complete" if not missing else "incomplete_nutrient_data",
        "missing_nutrients": missing,
    }


def _unknown_totals() -> dict[str, float | None]:
    return {nutrient: None for nutrient in NUTRIENTS}


def calculate_recipe(ingredients: Sequence[Mapping[str, Any]], servings: float = 1) -> dict[str, Any]:
    """Calculate recipe batch and per-serving totals from normalized ingredients.

    Supported ingredient statuses:
    - ``resolved`` (default): needs fdc_id, amount_g, and nutrients_per_100g.
    - ``estimated``: same calculation, but the ingredient is explicitly marked
      as estimated and the recipe is not represented as fully verified.
    - ``negligible_excluded``: an explicitly documented exclusion contributes
      zero by decision, not because missing data was mistaken for zero.
    - ``unresolved``: contribution is unknown. It blocks verification by
      default; set ``blocks_verification=False`` only when an upstream rule
      justifies that choice.

    Ingredient provenance fields supplied by the caller are retained.
    """
    serving_count = _valid_nonnegative_number(servings, "servings")
    if serving_count <= 0:
        raise ValueError("servings must be greater than zero")

    known_totals = {name: 0.0 for name in NUTRIENTS}
    missing_nutrients: set[str] = set()
    ingredient_results: list[dict[str, Any]] = []
    unresolved_blockers = 0
    estimated_count = 0
    excluded_count = 0
    resolved_count = 0
    known_weight_g = 0.0
    total_weight_g = 0.0
    has_unknown_weight = False

    for index, ingredient in enumerate(ingredients):
        name = str(ingredient.get("name", f"ingredient_{index + 1}"))
        status = str(ingredient.get("status", "resolved"))
        item: dict[str, Any] = {"name": name}
        for field in PROVENANCE_FIELDS:
            if field in ingredient:
                item[field] = ingredient[field]
        if "fdc_id" in ingredient:
            item["fdc_id"] = str(ingredient["fdc_id"]).strip() if ingredient["fdc_id"] is not None else None

        if status == "negligible_excluded":
            if not ingredient.get("reason"):
                raise ValueError(f"ingredient {name!r}: negligible_excluded requires a documented reason")
            item.update({"status": "negligible_excluded", "nutrients": {n: 0.0 for n in NUTRIENTS}, "missing_nutrients": []})
            excluded_count += 1
            if ingredient.get("amount_g") is None:
                has_unknown_weight = True
            else:
                grams = _valid_nonnegative_number(ingredient["amount_g"], "amount_g")
                item["amount_g"] = grams
                total_weight_g += grams
            ingredient_results.append(item)
            continue

        if status == "unresolved":
            amount = ingredient.get("amount_g")
            if amount is None or (isinstance(amount, str) and not amount.strip()):
                has_unknown_weight = True
            else:
                grams = _valid_nonnegative_number(amount, "amount_g")
                item["amount_g"] = grams
                total_weight_g += grams
            # Unknown contributions always block verified totals. A future
            # nutrient-specific exception needs an explicit, tested contract.
            unresolved_blockers += 1
            item.update({"status": "unresolved", "reason": ingredient.get("reason", "unresolved_ingredient"), "blocks_verification": True, "nutrients": _unknown_totals(), "missing_nutrients": list(NUTRIENTS)})
            ingredient_results.append(item)
            continue

        if status not in ("resolved", "estimated"):
            raise ValueError(f"ingredient {name!r}: unsupported status {status!r}")

        amount = ingredient.get("amount_g")
        try:
            grams = _valid_nonnegative_number(amount, "amount_g")
        except ValueError:
            unresolved_blockers += 1
            has_unknown_weight = True
            item.update({"status": "unresolved", "reason": ingredient.get("reason", "missing_or_invalid_amount_g"), "blocks_verification": True, "nutrients": _unknown_totals(), "missing_nutrients": list(NUTRIENTS)})
            ingredient_results.append(item)
            continue
        fdc_id = ingredient.get("fdc_id")
        profile = ingredient.get("nutrients_per_100g")
        if fdc_id is None or not isinstance(profile, Mapping):
            # An item marked resolved but lacking its required calculation inputs
            # is unresolved; do not silently discard it.
            unresolved_blockers += 1
            item.update({"amount_g": grams, "status": "unresolved", "reason": ingredient.get("reason", "missing_food_match_or_nutrient_profile"), "blocks_verification": True, "nutrients": _unknown_totals(), "missing_nutrients": list(NUTRIENTS)})
            total_weight_g += grams
            ingredient_results.append(item)
            continue

        values, missing = _nutrient_values(profile, grams)
        for nutrient, value in values.items():
            if value is None:
                missing_nutrients.add(nutrient)
            else:
                known_totals[nutrient] += value
        item.update({
            "fdc_id": str(fdc_id).strip(), "amount_g": grams,
            "nutrients": values, "missing_nutrients": missing,
            "status": "estimated" if status == "estimated" else ("complete" if not missing else "incomplete_nutrient_data"),
        })
        if status == "estimated":
            estimated_count += 1
        else:
            resolved_count += 1
        known_weight_g += grams
        total_weight_g += grams
        ingredient_results.append(item)

    # A nutrient's verified total is available only if every ingredient's
    # contribution is accounted for and that nutrient is present for all foods.
    # Explicit exclusions are allowed but are surfaced in status/coverage.
    blockers = unresolved_blockers > 0
    empty_recipe = len(ingredient_results) == 0
    totals: dict[str, float | None] = {
        nutrient: (None if blockers or empty_recipe or nutrient in missing_nutrients else known_totals[nutrient])
        for nutrient in NUTRIENTS
    }
    core_complete = all(totals[n] is not None for n in CORE_NUTRIENTS)
    complete = (not empty_recipe) and core_complete and all(value is not None for value in totals.values()) and estimated_count == 0 and excluded_count == 0
    status = "complete" if complete else ("estimated" if not empty_recipe and not blockers and core_complete and (estimated_count > 0 or excluded_count > 0) else "incomplete")
    per_serving = {n: (value / serving_count if value is not None else None) for n, value in totals.items()}
    partial_per_serving = {n: value / serving_count for n, value in known_totals.items()}
    count = len(ingredient_results)

    return {
        "servings": serving_count,
        "batch_totals": totals,
        "per_serving_totals": per_serving,
        "known_partial_totals": known_totals,
        "known_partial_per_serving_totals": partial_per_serving,
        "complete": complete,
        "core_complete": core_complete,
        "status": status,
        "coverage": {
            "ingredient_count": count,
            "resolved_ingredient_count": resolved_count,
            "unresolved_blocking_count": unresolved_blockers,
            "estimated_ingredient_count": estimated_count,
            "negligible_excluded_count": excluded_count,
            "ingredient_count_fraction": resolved_count / count if count else 0.0,
            "known_weight_g": known_weight_g,
            "total_weight_g": total_weight_g,
            "known_weight_fraction": None if has_unknown_weight else (known_weight_g / total_weight_g if total_weight_g else (1.0 if not blockers else None)),
            "missing_nutrients": sorted(missing_nutrients),
        },
        "ingredients": ingredient_results,
    }


def calculate_meal(recipe_result: Mapping[str, Any], servings_eaten: float = 1.0) -> dict[str, Any]:
    """Scale a recipe's per-serving totals by the number of servings eaten."""
    amount = _valid_nonnegative_number(servings_eaten, "servings_eaten")
    if amount <= 0:
        raise ValueError("servings_eaten must be greater than zero")
    per_serving = recipe_result.get("per_serving_totals")
    if not isinstance(per_serving, Mapping):
        raise ValueError("recipe_result must contain per_serving_totals")
    totals = {n: (float(per_serving[n]) * amount if per_serving.get(n) is not None else None) for n in NUTRIENTS}
    partial = recipe_result.get("known_partial_per_serving_totals", {})
    known_partial = {n: float(partial.get(n, 0.0)) * amount for n in NUTRIENTS}
    return {
        "servings_eaten": amount,
        "totals": totals,
        "known_partial_totals": known_partial,
        "complete": bool(recipe_result.get("complete", False)),
        "core_complete": bool(recipe_result.get("core_complete", False)),
        "status": recipe_result.get("status", "incomplete"),
    }


def aggregate_results(results: Sequence[Mapping[str, Any]], totals_key: str = "per_serving_totals") -> dict[str, Any]:
    """Aggregate results; defaults to per-serving totals to avoid summing batches.

    Pass ``totals_key="totals"`` to aggregate meal results from calculate_meal,
    or ``totals_key="batch_totals"`` deliberately when batch totals are intended.
    Empty input is incomplete, never a verified zero-intake result.
    """
    if not results:
        return {"totals": _unknown_totals(), "known_partial_totals": {n: 0.0 for n in NUTRIENTS}, "complete": False, "core_complete": False, "status": "incomplete", "component_count": 0}

    totals: dict[str, float | None] = {}
    partial_totals = {n: 0.0 for n in NUTRIENTS}
    for nutrient in NUTRIENTS:
        values = []
        for result in results:
            component = result.get(totals_key)
            values.append(component.get(nutrient) if isinstance(component, Mapping) else None)
            if totals_key == "per_serving_totals":
                partial = result.get("known_partial_per_serving_totals", result.get("known_partial_totals"))
            else:
                partial = result.get("known_partial_totals", result.get("known_partial_per_serving_totals"))
            if isinstance(partial, Mapping) and partial.get(nutrient) is not None:
                partial_totals[nutrient] += float(partial[nutrient])
        if any(value is None for value in values):
            totals[nutrient] = None
        else:
            try:
                totals[nutrient] = math.fsum(float(value) for value in values)
            except (TypeError, ValueError):
                totals[nutrient] = None

    core_complete = all(totals[n] is not None for n in CORE_NUTRIENTS)
    complete = all(bool(result.get("complete", False)) for result in results) and all(value is not None for value in totals.values())
    status = "complete" if complete else ("estimated" if core_complete and any(result.get("status") == "estimated" for result in results) else "incomplete")
    return {"totals": totals, "known_partial_totals": partial_totals, "complete": complete, "core_complete": core_complete, "status": status, "component_count": len(results)}
