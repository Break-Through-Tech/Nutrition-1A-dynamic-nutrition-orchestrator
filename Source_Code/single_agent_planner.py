
import argparse
import importlib.util
import json
import math
import os
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MACROS = ("calories_kcal", "protein_g", "carbs_g", "fat_g")
SLOTS = ("breakfast", "lunch", "dinner", "snack")
DAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday"
)


def load_recipes():
    with (ROOT / "recipes.json").open(encoding="utf-8") as file:
        recipes = json.load(file)

    if not isinstance(recipes, list):
        raise ValueError("recipes.json must contain a list")

    return recipes


def load_matcher():
    """Load the existing USDA matcher without modifying it."""
    script = ROOT / "scripts" / "ingredient_matching.py"

    if not script.exists():
        raise FileNotFoundError(f"Matcher not found: {script}")

    original_directory = Path.cwd()

    try:
        os.chdir(script.parent)

        spec = importlib.util.spec_from_file_location(
            "ingredient_matching", script
        )
        matcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(matcher)

        return matcher

    finally:
        os.chdir(original_directory)


def normalize_ingredients(recipe):
    raw = recipe.get("ingredients", [])

    if isinstance(raw, dict):
        ingredients = []

        for name, details in raw.items():
            if isinstance(details, dict):
                ingredient = dict(details)
                ingredient["name"] = str(name)
            else:
                ingredient = {
                    "name": str(name),
                    "quantity": None,
                    "unit": None,
                    "quantity_text": str(details),
                }

            ingredients.append(ingredient)

        return ingredients

    if isinstance(raw, list):
        return [
            dict(item)
            if isinstance(item, dict)
            else {
                "name": str(item),
                "quantity": None,
                "unit": None,
            }
            for item in raw
        ]

    return None


def invalid_ingredient(ingredient):
    """
    Reject missing or invalid quantities before
    treating nutrition calculations as verified.
    """
    quantity = ingredient.get("quantity")
    name = ingredient.get("name")
    unit = ingredient.get("unit")

    if not str(name or "").strip():
        return True

    if isinstance(quantity, bool):
        return True

    if not isinstance(quantity, (int, float)):
        return True

    if not math.isfinite(quantity) or quantity <= 0:
        return True

    if not str(unit or "").strip():
        return True

    return False


def recent_recipe_ids(days):
    """
    Return recipes used during the previous two days.

    This enforces a two-day scheduling window,
    rather than exact meal timestamps.
    """
    return {
        meal["recipe_id"]
        for day in days[-2:]
        for meal in day["meals"]
    }


def catalog(
    matcher,
    recipes,
    diet="vegetarian",
    planning_only=False,
):
    """
    Filter recipes and optionally verify USDA nutrition.

    Planning-only mode does not claim verified macros.
    """
    valid = []
    rejected = []

    for recipe in recipes:
        tags = recipe.get("diet_tags", [])

        if isinstance(tags, str):
            tags = [tags]

        tags = [str(tag).lower() for tag in tags]

        if diet and diet.lower() not in tags:
            continue

        ingredients = normalize_ingredients(recipe)

        if not ingredients:
            rejected.append({
                "recipe_id": recipe.get("recipe_id"),
                "reason": "Missing ingredient data",
            })
            continue

        item = {
            "recipe_id": recipe.get("recipe_id"),
            "name": recipe.get("name", "Unnamed recipe"),
            "meal_type": str(
                recipe.get("meal_type", "")
            ).lower(),
            "ingredients": ingredients,
            "macros": None,
            "nutrition_verified": False,
        }

        if planning_only:
            valid.append(item)
            continue

        # Reject incomplete quantities before USDA verification.
        invalid_inputs = [
            ingredient
            for ingredient in ingredients
            if invalid_ingredient(ingredient)
        ]

        if invalid_inputs:
            rejected.append({
                "recipe_id": item["recipe_id"],
                "reason": "Invalid ingredient quantities",
                "invalid_ingredients": invalid_inputs,
            })
            continue

        # Existing matcher expects ingredient dictionaries,
        # not the entire recipe dictionary.
        totals, results = matcher.calculate_recipe_macros(
            ingredients
        )

        failures = [
            result
            for result in results
            if result.get("status") != "Included"
        ]

        missing_macros = [
            key for key in MACROS
            if key not in totals
        ]

        invalid_totals = any(
            isinstance(totals.get(key), bool)
            or not isinstance(totals.get(key), (int, float))
            or not math.isfinite(totals[key])
            or totals[key] < 0
            for key in MACROS
            if key in totals
        )

        if (
            failures
            or missing_macros
            or invalid_totals
            or len(results) != len(ingredients)
        ):
            rejected.append({
                "recipe_id": item["recipe_id"],
                "reason": "Incomplete nutrition verification",
                "failed_ingredients": failures,
                "missing_macros": missing_macros,
                "invalid_totals": invalid_totals,
            })
            continue

        item["macros"] = {
            key: float(totals[key])
            for key in MACROS
        }

        item["nutrition_verified"] = True
        valid.append(item)

    return valid, rejected


def total_for(meals):
    """Sum verified macros without inventing values."""
    return {
        key: round(
            sum(meal["macros"][key] for meal in meals),
            4,
        )
        for key in MACROS
    }


def choose_day(
    candidates,
    protein_target,
    calorie_limit,
    offset=0,
    forbidden_ids=None,
):
    """
    Choose meals while excluding recipes used
    during the previous two days.
    """
    forbidden_ids = set(forbidden_ids or [])

    by_slot = {
        slot: [
            recipe
            for recipe in candidates
            if recipe["meal_type"] == slot
            and recipe["recipe_id"] not in forbidden_ids
        ]
        for slot in SLOTS
    }

    core_slots = [
        slot for slot in SLOTS[:3]
        if by_slot[slot]
    ]

    if not core_slots:
        return None, (
            "No available breakfast, lunch, or dinner recipes"
        )

    options = [
        by_slot[slot]
        for slot in core_slots
    ]

    if by_slot["snack"]:
        options.append([None] + by_slot["snack"])

    best = None

    for index, combination in enumerate(product(*options)):
        if index >= 100000:
            break

        meals = [
            meal for meal in combination
            if meal is not None
        ]

        recipe_ids = [
            meal["recipe_id"]
            for meal in meals
        ]

        # Do not use the same recipe twice in one day.
        if len(recipe_ids) != len(set(recipe_ids)):
            continue

        totals = total_for(meals)

        protein_gap = max(
            0,
            protein_target - totals["protein_g"],
        )

        calorie_over = max(
            0,
            totals["calories_kcal"] - calorie_limit + 0.0001,
        )

        score = (
            protein_gap > 0 or calorie_over > 0,
            protein_gap * 10 + calorie_over,
            (index - offset) % 100000,
        )

        if best is None or score < best[0]:
            best = (score, meals, totals)

    if best is None:
        return None, "No valid meal combinations available"

    _, meals, totals = best

    return {
        "meals": [
            {
                "meal_type": meal["meal_type"],
                "recipe_id": meal["recipe_id"],
                "name": meal["name"],
                "macros": meal["macros"],
            }
            for meal in meals
        ],
        "totals": totals,
        "meets_protein": (
            totals["protein_g"] >= protein_target
        ),
        "meets_calories": (
            totals["calories_kcal"] < calorie_limit
        ),
    }, None


def build_week(candidates, protein_target, calorie_limit):
    """Build a verified seven-day plan."""
    days = []

    for index, day_name in enumerate(DAYS):
        forbidden = recent_recipe_ids(days)

        day, error = choose_day(
            candidates,
            protein_target,
            calorie_limit,
            offset=index,
            forbidden_ids=forbidden,
        )

        if error:
            return {
                "error": (
                    f"{day_name}: {error}. "
                    "Cannot complete the week without "
                    "violating the two-day repeat rule."
                ),
                "days": days,
                "weekly_totals": None,
                "all_days_valid": False,
                "nutrition_verified": False,
                "repeat_rule_satisfied": False,
            }

        days.append({
            "day": day_name,
            **day,
        })

    weekly_totals = {
        key: round(
            sum(day["totals"][key] for day in days),
            4,
        )
        for key in MACROS
    }

    return {
        "days": days,
        "weekly_totals": weekly_totals,
        "all_days_valid": all(
            day["meets_protein"] and day["meets_calories"]
            for day in days
        ),
        "nutrition_verified": True,
        "repeat_rule_satisfied": True,
    }


def build_planning_only_week(candidates):
    """
    Schedule recipes without calculating nutrition.

    Enforce no repeats within the previous two days.
    """
    by_slot = {
        slot: [
            recipe
            for recipe in candidates
            if recipe["meal_type"] == slot
        ]
        for slot in SLOTS
    }

    if not any(by_slot.values()):
        return {
            "error": "No recipes for supported meal slots",
            "days": [],
            "all_days_valid": False,
            "nutrition_verified": False,
        }

    days = []

    for index, day_name in enumerate(DAYS):
        forbidden = recent_recipe_ids(days)
        meals = []

        for slot in SLOTS:
            options = [
                recipe
                for recipe in by_slot[slot]
                if recipe["recipe_id"] not in forbidden
            ]

            if not options:
                if by_slot[slot] and slot != "snack":
                    return {
                        "error": (
                            f"Cannot schedule {day_name} {slot} "
                            "without repeating a recipe "
                            "within two days"
                        ),
                        "days": days,
                        "weekly_totals": None,
                        "all_days_valid": False,
                        "nutrition_verified": False,
                        "repeat_rule_satisfied": False,
                    }

                continue

            recipe = options[index % len(options)]

            forbidden.add(recipe["recipe_id"])

            meals.append({
                "meal_type": slot,
                "recipe_id": recipe["recipe_id"],
                "name": recipe["name"],
                "macros": None,
                "nutrition_verified": False,
            })

        days.append({
            "day": day_name,
            "meals": meals,
            "totals": None,
            "meets_protein": None,
            "meets_calories": None,
            "nutrition_verified": False,
        })

    return {
        "days": days,
        "weekly_totals": None,
        "all_days_valid": False,
        "nutrition_verified": False,
        "repeat_rule_satisfied": True,
        "note": (
            "Planning-only schedule. "
            "Nutrition totals and target compliance "
            "have not been verified."
        ),
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--protein",
        type=float,
        default=140,
    )

    parser.add_argument(
        "--calories",
        type=float,
        default=2000,
    )

    parser.add_argument(
        "--diet",
        default="vegetarian",
    )

    parser.add_argument(
        "--planning-only",
        action="store_true",
    )

    parser.add_argument(
        "--output",
        default="meal_plan_output.json",
    )

    args = parser.parse_args()

    if (
        not math.isfinite(args.protein)
        or not math.isfinite(args.calories)
        or args.protein < 0
        or args.calories <= 0
    ):
        parser.error(
            "Protein must be nonnegative and "
            "calorie limit must be positive"
        )

    matcher = (
        None
        if args.planning_only
        else load_matcher()
    )

    recipes = load_recipes()

    valid, rejected = catalog(
        matcher,
        recipes,
        diet=args.diet,
        planning_only=args.planning_only,
    )

    if args.planning_only:
        plan = build_planning_only_week(valid)
    else:
        plan = build_week(
            valid,
            args.protein,
            args.calories,
        )

    result = {
        "requirements": {
            "protein_g_per_day": args.protein,
            "calories_strictly_below_per_day": args.calories,
            "diet": args.diet,
        },
        "eligible_recipes": len(valid),
        "excluded_recipes": rejected,
        "planning_mode": (
            "planning_only"
            if args.planning_only
            else "deterministic_baseline"
        ),
        **plan,
    }

    output_path = ROOT / args.output

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(result, file, indent=2)

    print(
        f"Eligible recipes: {len(valid)}; "
        f"excluded: {len(rejected)}"
    )

    print(f"Output: {output_path}")

    print(
        "Seven-day targets met:",
        result.get("all_days_valid", False),
    )

    if result.get("error"):
        print("BLOCKED:", result["error"])

    elif args.planning_only:
        print(
            "PLANNING ONLY: nutrition totals and "
            "target compliance are unverified"
        )

    elif not valid:
        print(
            "BLOCKED: no complete recipes; "
            "inspect excluded_recipes in output JSON"
        )


if __name__ == "__main__":
    main()
